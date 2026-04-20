from __future__ import annotations

import csv
import io
import ipaddress
import logging
import re
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests

from .config import Settings
from .normalize import map_party_name, normalize_text, similarity

CAMPAIGN_BOOKLET_RESOURCE_NAME = "campaign_booklet"
KRPOLTEXT_MANIFEST_PATHS = ("index.json", "metadata.json")
logger = logging.getLogger(__name__)


def load_krpoltext_manifest_payload(
    session: requests.Session,
    settings: Settings,
) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str | None]:
    errors: list[str] = []
    for path in KRPOLTEXT_MANIFEST_PATHS:
        manifest_url = f"{settings.krpoltext_base_url.rstrip('/')}/{path}"
        try:
            response = session.get(
                manifest_url,
                headers={"User-Agent": settings.user_agent},
                timeout=settings.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if isinstance(payload, (dict, list)):
            return payload, path
        errors.append(f"{path}: unexpected JSON payload type {type(payload).__name__}")
    if errors:
        logger.warning("krpoltext manifest fetch failed: %s", "; ".join(errors))
    return None, None


def allowed_krpoltext_hosts(settings: Settings) -> set[str]:
    hosts: set[str] = set()
    for value in (settings.krpoltext_base_url, settings.krpoltext_campaign_booklet_url):
        if not value:
            continue
        hostname = urlparse(str(value)).hostname
        if hostname:
            hosts.add(hostname.lower())
    return hosts


def resolve_trusted_krpoltext_url(settings: Settings, raw_url: str | None) -> str | None:
    return _resolve_trusted_url(
        settings,
        raw_url,
        allowed_hosts=allowed_krpoltext_hosts(settings),
    )


def resolve_trusted_campaign_booklet_url(settings: Settings, raw_url: str | None) -> str | None:
    return _resolve_trusted_url(
        settings,
        raw_url,
        allowed_hosts=allowed_campaign_booklet_hosts(settings),
    )


def allowed_campaign_booklet_hosts(settings: Settings) -> set[str]:
    return allowed_krpoltext_hosts(settings) | {"osf.io", "files.osf.io", "storage.googleapis.com"}


def _resolve_trusted_url(
    settings: Settings,
    raw_url: str | None,
    *,
    allowed_hosts: set[str],
) -> str | None:
    if raw_url in (None, ""):
        return None
    cleaned = str(raw_url).strip()
    if not cleaned or cleaned.startswith("//"):
        return None
    parsed = urlparse(cleaned)
    normalized = cleaned if parsed.scheme else urljoin(f"{settings.krpoltext_base_url.rstrip('/')}/", cleaned.lstrip("/"))
    parsed = urlparse(normalized)
    if parsed.scheme.lower() != "https":
        return None
    hostname = (parsed.hostname or "").lower()
    if not hostname or _is_disallowed_network_host(hostname):
        return None
    return normalized if hostname in allowed_hosts else None


def _is_disallowed_network_host(hostname: str) -> bool:
    lowered = hostname.strip().lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )

OFFICE_ALIASES: dict[str, set[str]] = {
    "president": {"president", "대통령", "대통령선거"},
    "national_assembly": {
        "national_assembly",
        "국회의원",
        "국회의원선거",
        "지역구국회의원",
        "비례대표국회의원",
    },
    "regional_head": {
        "regional_head",
        "광역단체장",
        "광역단체장선거",
        "광역시장",
        "도지사",
        "특별시장",
        "특별자치시장",
    },
    "basic_head": {
        "basic_head",
        "기초단체장",
        "기초단체장선거",
        "구청장",
        "군수",
        "시장",
    },
    "regional_council": {
        "regional_council",
        "광역의원",
        "광역의원선거",
        "시도의원",
        "시의원",
        "도의원",
    },
    "basic_council": {
        "basic_council",
        "기초의원",
        "기초의원선거",
        "구의원",
        "군의원",
        "시의원",
    },
    "superintendent": {
        "superintendent",
        "교육감",
        "교육감선거",
        "교육의원",
    },
}


def canonical_office_name(value: str | None) -> str | None:
    normalized = normalize_text(value)
    if not normalized:
        return None
    for canonical, aliases in OFFICE_ALIASES.items():
        alias_tokens = {normalize_text(alias) for alias in aliases}
        if normalized == canonical:
            return canonical
        if normalized in alias_tokens:
            return canonical
        if any(token and token in normalized for token in alias_tokens if len(token) >= 2):
            return canonical
    if "대통령" in normalized:
        return "president"
    if "국회의원" in normalized or "국회" in normalized:
        return "national_assembly"
    if "교육감" in normalized or "교육의원" in normalized:
        return "superintendent"
    if "광역의원" in normalized or "도의원" in normalized:
        return "regional_council"
    if "기초의원" in normalized or "구의원" in normalized or "군의원" in normalized:
        return "basic_council"
    if (
        "광역단체장" in normalized
        or "광역시장" in normalized
        or "도지사" in normalized
        or "특별시장" in normalized
        or "특별자치시장" in normalized
    ):
        return "regional_head"
    if "기초단체장" in normalized or "구청장" in normalized or "군수" in normalized or "시장" in normalized:
        return "basic_head"
    return None


def office_similarity(query: str | None, row_office: str | None, row_office_id: str | None = None) -> float:
    if not query:
        return 0.0
    query_canonical = canonical_office_name(query)
    row_canonical = canonical_office_name(row_office) or canonical_office_name(row_office_id)
    if query_canonical and row_canonical and query_canonical == row_canonical:
        return 1.0
    return similarity(query, row_office or row_office_id)


def build_region_district_label(region: str | None, district: str | None) -> str | None:
    parts = [part.strip() for part in (region, district) if part and part.strip()]
    if not parts:
        return None
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0]
    return " ".join(parts)


class CampaignBookletCorpus:
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        manifest_loader: Callable[[], dict[str, Any] | None] | None = None,
        row_loader: Callable[[], Iterable[dict[str, Any]]] | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.manifest_loader = manifest_loader
        self.row_loader = row_loader
        self._manifest_cache: dict[str, Any] | None = None
        self._resource_cache: dict[str, Any] | None = None

    def dataset_version(self) -> str | None:
        manifest = self._load_manifest()
        if isinstance(manifest.get("generated_at"), str) and manifest["generated_at"]:
            return str(manifest["generated_at"])
        package = manifest.get("package")
        if isinstance(package, dict):
            version = package.get("version")
            if version:
                return str(version)
        api_version = manifest.get("api_version")
        return str(api_version) if api_version else None

    def campaign_booklet_download_url(self) -> str | None:
        target = self._campaign_booklet_download_target()
        return target[1] if target else None

    def time_coverage(self) -> str | None:
        resource = self._campaign_booklet_resource()
        value = resource.get('time_coverage') or resource.get('coverage')
        text = str(value or '').strip()
        return text or None

    def supported_year_range(self) -> tuple[int | None, int | None]:
        return self._parse_year_range(self.time_coverage())

    def _campaign_booklet_download_target(self) -> tuple[str, str] | None:
        resource = self._campaign_booklet_resource()
        download_urls = self._trusted_download_urls(resource)
        parquet_url = download_urls.get("parquet")
        if parquet_url and self._parquet_supported():
            return "parquet", parquet_url
        csv_url = download_urls.get("csv")
        if csv_url:
            return "csv", csv_url
        if parquet_url:
            logger.warning(
                "Campaign booklet parquet URL is available, but pyarrow is not installed; CSV fallback was unavailable."
            )
        path = resource.get("path")
        if path:
            path_url = resolve_trusted_campaign_booklet_url(self.settings, str(path))
            if path_url:
                path_format = self._infer_resource_format(resource, path_url)
                if path_format == "parquet" and not self._parquet_supported():
                    logger.warning(
                        "Campaign booklet parquet path requires pyarrow; no CSV fallback was available."
                    )
                    return None
                return path_format, path_url
        fallback_url = resolve_trusted_campaign_booklet_url(
            self.settings,
            self.settings.krpoltext_campaign_booklet_url,
        )
        if self.settings.krpoltext_campaign_booklet_url and not fallback_url:
            logger.warning(
                "Configured campaign booklet fallback URL rejected because host is not trusted: %s",
                self.settings.krpoltext_campaign_booklet_url,
            )
        if fallback_url:
            fallback_format = self._infer_resource_format({}, fallback_url)
            if fallback_format == "parquet" and not self._parquet_supported():
                logger.warning(
                    "Configured campaign booklet parquet fallback requires pyarrow; no CSV fallback was available."
                )
                return None
            return fallback_format, fallback_url
        return None

    def search_rows(
        self,
        *,
        candidate_name: str | None = None,
        election_year: int | None = None,
        office_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        code: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not any([candidate_name, election_year, office_name, district_name, party_name, code]):
            return []

        matches: list[tuple[float, dict[str, Any]]] = []
        for row in self.iter_rows():
            score = self._score_row(
                row,
                candidate_name=candidate_name,
                election_year=election_year,
                office_name=office_name,
                district_name=district_name,
                party_name=party_name,
                code=code,
            )
            if score < 0.45:
                continue
            matches.append((score, row))
        matches.sort(key=lambda item: item[0], reverse=True)
        return [dict(row, _match_score=score) for score, row in matches[:limit]]

    def iter_rows(self) -> Iterable[dict[str, Any]]:
        if self.row_loader:
            for row in self.row_loader():
                if isinstance(row, dict):
                    yield row
            return

        download_target = self._campaign_booklet_download_target()
        if not download_target:
            logger.warning(
                "Campaign booklet dataset URL is unavailable or outside trusted krpoltext hosts."
            )
            return
        download_format, download_url = download_target

        try:
            response = self.session.get(
                download_url,
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.request_timeout_seconds * 3,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Campaign booklet dataset fetch failed: %s", exc)
            return
        final_url = resolve_trusted_campaign_booklet_url(self.settings, getattr(response, "url", download_url))
        if not final_url:
            logger.warning("Campaign booklet dataset redirect resolved outside trusted hosts.")
            return
        if download_format == "parquet":
            yield from self._iter_parquet_rows(response.content)
            return
        stream = io.StringIO(response.content.decode("utf-8-sig", errors="replace"))
        reader = csv.DictReader(stream)
        for row in reader:
            if isinstance(row, dict):
                yield {key: value for key, value in row.items()}

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest_cache is not None:
            return self._manifest_cache
        if self.manifest_loader:
            payload = self.manifest_loader() or {}
            self._manifest_cache = payload if isinstance(payload, dict) else {}
            return self._manifest_cache
        payload, _ = load_krpoltext_manifest_payload(self.session, self.settings)
        self._manifest_cache = payload if isinstance(payload, dict) else {}
        return self._manifest_cache

    def _campaign_booklet_resource(self) -> dict[str, Any]:
        if self._resource_cache is not None:
            return self._resource_cache
        manifest = self._load_manifest()
        resources = manifest.get("resources")
        candidates: list[dict[str, Any]] = []
        if isinstance(resources, list):
            for resource in resources:
                if isinstance(resource, dict) and resource.get("name") == CAMPAIGN_BOOKLET_RESOURCE_NAME:
                    candidates.append(resource)
        if candidates:
            self._resource_cache = min(candidates, key=self._campaign_booklet_resource_sort_key)
            return self._resource_cache
        metadata_resource = manifest.get(CAMPAIGN_BOOKLET_RESOURCE_NAME)
        if isinstance(metadata_resource, dict):
            metadata_candidates = self._metadata_campaign_booklet_candidates(metadata_resource)
            if metadata_candidates:
                self._resource_cache = min(metadata_candidates, key=self._campaign_booklet_resource_sort_key)
                return self._resource_cache
            self._resource_cache = {
                "name": CAMPAIGN_BOOKLET_RESOURCE_NAME,
                **metadata_resource,
            }
            return self._resource_cache
        self._resource_cache = {}
        return self._resource_cache

    def _metadata_campaign_booklet_candidates(self, resource: dict[str, Any]) -> list[dict[str, Any]]:
        variants = resource.get("variants")
        if not isinstance(variants, dict):
            return []
        shared_fields = {
            str(key): value
            for key, value in resource.items()
            if key != "variants" and value not in (None, "")
        }
        candidates: list[dict[str, Any]] = []
        for variant_name, variant_payload in variants.items():
            if not isinstance(variant_payload, dict):
                continue
            candidates.append(
                {
                    "name": CAMPAIGN_BOOKLET_RESOURCE_NAME,
                    **shared_fields,
                    **variant_payload,
                    "variant": str(variant_name).strip().lower() or shared_fields.get("variant"),
                }
            )
        return candidates

    def _trusted_download_urls(self, resource: dict[str, Any]) -> dict[str, str]:
        urls: dict[str, str] = {}
        raw_urls = resource.get("download_urls")
        if isinstance(raw_urls, dict):
            for format_name, raw_url in raw_urls.items():
                trusted_url = resolve_trusted_campaign_booklet_url(self.settings, str(raw_url) if raw_url else None)
                if not trusted_url:
                    continue
                urls[str(format_name).strip().lower()] = trusted_url
        raw_download_url = resource.get("download_url")
        download_url = resolve_trusted_campaign_booklet_url(
            self.settings,
            str(raw_download_url) if raw_download_url else None,
        )
        if raw_download_url and not download_url:
            logger.warning(
                "Campaign booklet manifest download URL rejected because host is not trusted: %s",
                raw_download_url,
            )
        if download_url:
            urls.setdefault(self._infer_resource_format(resource, download_url), download_url)
        return urls

    def _campaign_booklet_resource_sort_key(self, resource: dict[str, Any]) -> tuple[int, int]:
        variant = self._campaign_booklet_resource_variant(resource)
        format_name = self._infer_resource_format(resource)
        if variant == "enriched" and format_name == "parquet" and self._parquet_supported():
            return 0, 0
        if variant == "enriched" and format_name == "csv":
            return 1, 0
        if format_name == "parquet" and self._parquet_supported():
            return 2, 0
        if format_name == "csv":
            return 3, 0
        if variant == "enriched" and format_name == "parquet":
            return 4, 0
        if format_name == "parquet":
            return 5, 0
        return 6, 0

    @staticmethod
    def _campaign_booklet_resource_variant(resource: dict[str, Any]) -> str | None:
        variant = str(resource.get("variant") or "").strip().lower()
        if variant:
            return variant
        for candidate in (resource.get("file"), resource.get("schema_url")):
            text = str(candidate or "").strip().lower()
            if "enriched" in text:
                return "enriched"
        return None

    def _iter_parquet_rows(self, content: bytes) -> Iterable[dict[str, Any]]:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            logger.warning("Campaign booklet parquet support requires pyarrow.")
            return

        parquet = pq.ParquetFile(io.BytesIO(content))
        for batch in parquet.iter_batches():
            for row in batch.to_pylist():
                if isinstance(row, dict):
                    yield {str(key): value for key, value in row.items()}

    @staticmethod
    def _infer_resource_format(resource: dict[str, Any], download_url: str | None = None) -> str:
        candidates = [
            resource.get("format"),
            resource.get("default_format"),
            resource.get("file"),
            download_url,
        ]
        for candidate in candidates:
            text = str(candidate or "").strip().lower()
            if not text:
                continue
            if text == "parquet" or text.endswith(".parquet"):
                return "parquet"
            if text == "csv" or text.endswith(".csv"):
                return "csv"
        return "csv"

    @staticmethod
    def _parquet_supported() -> bool:
        try:
            import pyarrow.parquet  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _parse_year_range(value: Any) -> tuple[int | None, int | None]:
        years = [int(match) for match in re.findall(r'\d{4}', str(value or ''))]
        if not years:
            return None, None
        if len(years) == 1:
            return years[0], years[0]
        return years[0], years[1]

    def _score_row(
        self,
        row: dict[str, Any],
        *,
        candidate_name: str | None,
        election_year: int | None,
        office_name: str | None,
        district_name: str | None,
        party_name: str | None,
        code: str | None,
    ) -> float:
        score = 0.0

        row_code = str(row.get("code") or "").strip()
        if code:
            requested = str(code).strip()
            if requested.lower() == row_code.lower():
                score += 0.75
            elif requested.replace("-", "").replace("_", "").lower() == row_code.replace("_", "").lower():
                score += 0.7
            else:
                return 0.0

        if candidate_name:
            candidate_score = similarity(row.get("name"), candidate_name)
            if candidate_score < 0.55 and not code:
                return 0.0
            score += candidate_score * 0.55

        if election_year:
            row_year = self._extract_year(row.get("date"))
            if row_year == election_year:
                score += 0.2
            elif row_year is not None:
                if not code:
                    return 0.0
                score -= 0.25

        if office_name:
            query_score = office_similarity(office_name, row.get("office"), row.get("office_id"))
            if query_score < 0.45 and not code:
                return 0.0
            score += query_score * 0.15

        if district_name:
            district_label = build_region_district_label(row.get("region"), row.get("district"))
            district_score = max(similarity(district_label, district_name), similarity(row.get("district"), district_name))
            if district_score < 0.45 and not code:
                return 0.0
            score += district_score * 0.1

        if party_name:
            party_score = similarity(map_party_name(row.get("party")), party_name)
            if party_score < 0.45 and not code:
                return 0.0
            score += party_score * 0.05

        return round(min(max(score, 0.0), 1.0), 3)

    @staticmethod
    def _extract_year(value: Any) -> int | None:
        if not value:
            return None
        text = str(value)
        digits = "".join(char for char in text if char.isdigit())
        if len(digits) < 4:
            return None
        return int(digits[:4])
