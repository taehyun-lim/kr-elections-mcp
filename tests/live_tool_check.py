from __future__ import annotations

import json
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import pytest

from app.cache import SimpleFileCache
from app.config import Settings
from app.diagnostics import DiagnosticsService
from app.krpoltext_api import KrPolTextClient
from app.models import (
    AssembleCandidatePacketInput,
    CandidateLookupInput,
    DiagnoseInput,
    DistrictResultsInput,
    ElectionOverviewInput,
    KrPolTextInput,
    ListDistrictsInput,
    ListElectionsInput,
    ListPartiesInput,
    PartyVoteShareHistoryInput,
    SearchCandidatesInput,
)
from app.nec_api import NecApiClient
from app.results_api import ResultsApiClient
from app.tool_handlers import ToolHandlers

pytestmark = pytest.mark.skip("requires live API")


REPORT_PATH = Path('.cache/live_tool_report.json')
DEFAULT_LEGISLATIVE_QUERY = {
    'candidate_name': '곽상언',
    'sg_id': '20240410',
    'sg_typecode': '2',
    'sd_name': '서울특별시',
    'district_name': '서울특별시 종로구',
}
FALLBACK_CANDIDATE_QUERIES = [
    DEFAULT_LEGISLATIVE_QUERY,
    {
        'candidate_name': '최재형',
        'sg_id': '20240410',
        'sg_typecode': '2',
        'sd_name': '서울특별시',
        'district_name': '서울특별시 종로구',
    },
    {
        'candidate_name': '윤석열',
        'sg_id': '20220309',
        'sg_typecode': '1',
        'sd_name': '서울특별시',
    },
    {
        'candidate_name': '이재명',
        'sg_id': '20220309',
        'sg_typecode': '1',
        'sd_name': '경기도',
    },
]
FALLBACK_KRPOLTEXT_QUERIES = [
    {'candidate_name': '윤석열', 'election_year': 2022, 'office_name': '대통령'},
    {'candidate_name': '이재명', 'election_year': 2022, 'office_name': '대통령'},
    {'candidate_name': '곽상언', 'election_year': 2024, 'district_name': '서울특별시 종로구'},
]


def build_handlers() -> ToolHandlers:
    settings = Settings.from_env()
    cache = SimpleFileCache(settings.cache_dir, settings.cache_ttl_seconds)
    nec_client = NecApiClient(settings=settings, cache=cache)
    results_client = ResultsApiClient(settings=settings, nec_client=nec_client)
    krpoltext_client = KrPolTextClient(settings=settings)
    diagnostics_service = DiagnosticsService(nec_client=nec_client, results_client=results_client)
    return ToolHandlers(
        nec_client=nec_client,
        results_client=results_client,
        krpoltext_client=krpoltext_client,
        diagnostics_service=diagnostics_service,
    )


def json_safe(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        try:
            return value.model_dump(mode='json')
        except TypeError:
            return value.model_dump()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def scrub_text(value: str) -> str:
    value = re.sub(r'serviceKey=[^&\s]+', 'serviceKey=[REDACTED]', value)
    value = re.sub(r'NEC_API_KEY_[A-Z_]+=([^\s]+)', 'NEC_API_KEY_[REDACTED]', value)
    return value


def payload_excerpt(payload: Any) -> Any:
    if isinstance(payload, dict):
        excerpt: dict[str, Any] = {}
        for key, value in payload.items():
            if key == 'items' and isinstance(value, list):
                excerpt[key] = value[:3]
            elif key == 'checks' and isinstance(value, list):
                excerpt[key] = value[:5]
            else:
                excerpt[key] = payload_excerpt(value)
        return excerpt
    if isinstance(payload, list):
        return [payload_excerpt(item) for item in payload[:3]]
    return payload


def count_items(payload: dict[str, Any], *keys: str) -> int | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, list):
        return len(current)
    return None


def summarize_check_statuses(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        status = str(check.get('status') or 'UNKNOWN')
        counts[status] = counts.get(status, 0) + 1
    return counts


def expect_nonempty_items(payload: dict[str, Any]) -> tuple[str, str]:
    count = count_items(payload, 'items')
    if count and count > 0:
        return 'ok', f'{count} items returned.'
    return 'fail', 'The tool responded but returned no items.'


def expect_profile(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get('profile'):
        return 'ok', 'Candidate profile resolved successfully.'
    resolution = payload.get('resolution') or {}
    return 'fail', f"Candidate profile was not resolved ({resolution.get('status')})."


def expect_policies(payload: dict[str, Any]) -> tuple[str, str]:
    resolution = payload.get('resolution') or {}
    if resolution.get('status') != 'resolved':
        return 'fail', f"Candidate policies lookup did not resolve a candidate ({resolution.get('status')})."
    availability = payload.get('availability')
    items = payload.get('items') or []
    return 'ok', f'Policy lookup completed with availability={availability} and {len(items)} items.'


def expect_summary(payload: dict[str, Any]) -> tuple[str, str]:
    summary = payload.get('summary') or {}
    if not summary:
        return 'fail', 'No district summary object was returned.'
    electorate = summary.get('electorate_count')
    turnout = summary.get('turnout_count')
    if electorate is None and turnout is None:
        return 'partial', 'District summary returned, but turnout totals were missing.'
    return 'ok', 'District summary returned with turnout metrics.'


def expect_history(payload: dict[str, Any]) -> tuple[str, str]:
    count = count_items(payload, 'items') or 0
    if count > 0:
        return 'ok', f'{count} party vote-share history points returned.'
    return 'partial', 'Party vote-share history call succeeded but returned no points.'


def expect_overview(payload: dict[str, Any]) -> tuple[str, str]:
    overview = payload.get('overview') or {}
    if not overview:
        return 'fail', 'No election overview object was returned.'
    if overview.get('district_count'):
        return 'ok', f"Election overview returned {overview.get('district_count')} districts."
    return 'partial', 'Election overview returned, but district_count was empty.'


def expect_packet(payload: dict[str, Any]) -> tuple[str, str]:
    resolution = payload.get('resolution') or {}
    if resolution.get('status') != 'resolved':
        return 'fail', f"Candidate packet did not resolve a candidate ({resolution.get('status')})."
    krpoltext = payload.get('krpoltext') or []
    return 'ok', f'Candidate packet resolved with {len(krpoltext)} krpoltext records.'


def expect_diagnostics(payload: dict[str, Any]) -> tuple[str, str]:
    checks = payload.get('checks') or []
    if not checks:
        return 'fail', 'Diagnostics report returned no checks.'
    status_counts = summarize_check_statuses(checks)
    bad_statuses = {'error', 'unauthorized', 'not_applied'}
    if any(status in bad_statuses for status in status_counts):
        return 'fail', f'Diagnostics reported problems: {status_counts}.'
    if 'empty' in status_counts:
        return 'partial', f'Diagnostics completed with empty endpoints: {status_counts}.'
    return 'ok', f'Diagnostics checks passed: {status_counts}.'




def expect_text(payload: dict[str, Any]) -> tuple[str, str]:
    count = count_items(payload, 'items') or 0
    if count > 0:
        return 'ok', f'{count} krpoltext records returned.'
    return 'fail', 'krpoltext lookup returned no records.'


def run_tool(
    name: str,
    tool_input: dict[str, Any],
    fn: Callable[[], Any],
    expectation: Callable[[dict[str, Any]], tuple[str, str]],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        result = fn()
        payload = json_safe(result)
        verdict, note = expectation(payload)
        return {
            'tool': name,
            'input': tool_input,
            'verdict': verdict,
            'note': note,
            'elapsed_seconds': round(time.perf_counter() - started_at, 3),
            'payload_excerpt': payload_excerpt(payload),
            'payload': payload,
        }
    except Exception as exc:
        return {
            'tool': name,
            'input': tool_input,
            'verdict': 'error',
            'note': scrub_text(str(exc)),
            'error_type': type(exc).__name__,
            'elapsed_seconds': round(time.perf_counter() - started_at, 3),
        }


def extract_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = ''.join(character for character in str(value) if character.isdigit())
    if len(digits) >= 4:
        return int(digits[:4])
    return None


def discover_candidate_context(handlers: ToolHandlers) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None
    for query in FALLBACK_CANDIDATE_QUERIES:
        payload = SearchCandidatesInput(limit=5, **query)
        output = handlers.search_candidates(payload)
        summary = {
            'query': query,
            'count': len(output.items),
            'warnings': output.warnings,
        }
        if output.items:
            candidate = output.items[0]
            candidate_payload = json_safe(candidate)
            summary['first_candidate'] = candidate_payload
            if chosen is None:
                chosen = {
                    'query': query,
                    'candidate': candidate_payload,
                    'candidate_ref': candidate_payload.get('candidate_ref') or {},
                }
        attempts.append(summary)
        if chosen is not None:
            break
    return {'attempts': attempts, 'selected': chosen}




def discover_krpoltext_context(
    handlers: ToolHandlers,
    candidate_context: dict[str, Any] | None,
) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    if candidate_context:
        candidate = candidate_context['candidate']
        candidate_ref = candidate_context['candidate_ref']
        queries.append(
            {
                'candidate_name': candidate_ref.get('candidate_name'),
                'election_year': extract_year(candidate.get('election_date')),
                'office_name': candidate.get('sg_name'),
                'district_name': candidate_ref.get('district_label'),
            }
        )
    queries.extend(FALLBACK_KRPOLTEXT_QUERIES)

    attempts: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None
    for query in queries:
        clean_query = {
            key: value
            for key, value in query.items()
            if value not in (None, '') and key in {'candidate_name', 'code', 'election_year', 'office_name', 'district_name'}
        }
        output = handlers.get_krpoltext_text(KrPolTextInput(**clean_query))
        payload = json_safe(output)
        items = payload.get('items') or []
        attempts.append(
            {
                'query': clean_query,
                'count': len(items),
                'warnings': payload.get('warnings') or [],
                'first_record': items[0] if items else None,
            }
        )
        if items:
            chosen = {'query': clean_query, 'record': items[0]}
            break
    return {'attempts': attempts, 'selected': chosen}


def main() -> int:
    handlers = build_handlers()
    candidate_discovery = discover_candidate_context(handlers)
    candidate_context = candidate_discovery.get('selected')
    krpoltext_discovery = discover_krpoltext_context(handlers, candidate_context)
    krpoltext_context = krpoltext_discovery.get('selected')

    legislative_ref = (candidate_context or {}).get('candidate_ref') or {}
    legislative_sg_id = legislative_ref.get('sg_id') or DEFAULT_LEGISLATIVE_QUERY['sg_id']
    legislative_sg_typecode = legislative_ref.get('sg_typecode') or DEFAULT_LEGISLATIVE_QUERY['sg_typecode']
    legislative_sd_name = legislative_ref.get('sd_name') or DEFAULT_LEGISLATIVE_QUERY['sd_name']
    legislative_sgg_name = legislative_ref.get('sgg_name') or '종로구'
    legislative_district_label = legislative_ref.get('district_label') or DEFAULT_LEGISLATIVE_QUERY['district_name']
    legislative_party_name = legislative_ref.get('party_name') or (candidate_context or {}).get('candidate', {}).get('party_name') or '더불어민주당'

    list_elections_input = {'include_history': True}
    list_districts_input = {
        'sg_id': legislative_sg_id,
        'sg_typecode': legislative_sg_typecode,
        'sd_name': legislative_sd_name,
        'match_mode': 'strict',
    }
    search_input = {**DEFAULT_LEGISLATIVE_QUERY, 'limit': 5}
    candidate_lookup_input = {'candidate_ref': legislative_ref} if legislative_ref else DEFAULT_LEGISLATIVE_QUERY
    district_input = {
        'sg_id': legislative_sg_id,
        'sg_typecode': legislative_sg_typecode,
        'sd_name': legislative_sd_name,
        'sgg_name': legislative_sgg_name,
    }
    list_parties_input = {
        'sg_id': legislative_sg_id,
        'sg_typecode': legislative_sg_typecode,
    }
    history_input = {
        'party_name': legislative_party_name,
        'district_name': legislative_district_label,
        'sd_name': legislative_sd_name,
        'sg_typecode': legislative_sg_typecode,
        'year_from': 2020,
        'year_to': 2024,
    }
    krpoltext_input = (krpoltext_context or {}).get('query') or FALLBACK_KRPOLTEXT_QUERIES[0]

    tool_results = [
        run_tool(
            'list_elections',
            list_elections_input,
            lambda: handlers.list_elections(ListElectionsInput(**list_elections_input)),
            expect_nonempty_items,
        ),
        run_tool(
            'list_districts',
            list_districts_input,
            lambda: handlers.list_districts(ListDistrictsInput(**list_districts_input)),
            expect_nonempty_items,
        ),
        run_tool(
            'list_parties',
            list_parties_input,
            lambda: handlers.list_parties(ListPartiesInput(**list_parties_input)),
            expect_nonempty_items,
        ),
        run_tool(
            'search_candidates',
            search_input,
            lambda: handlers.search_candidates(SearchCandidatesInput(**search_input)),
            expect_nonempty_items,
        ),
        run_tool(
            'get_candidate_profile',
            candidate_lookup_input,
            lambda: handlers.get_candidate_profile(CandidateLookupInput(**candidate_lookup_input)),
            expect_profile,
        ),
        run_tool(
            'get_candidate_policies',
            candidate_lookup_input,
            lambda: handlers.get_candidate_policies(CandidateLookupInput(**candidate_lookup_input)),
            expect_policies,
        ),
        run_tool(
            'get_district_results',
            district_input,
            lambda: handlers.get_district_results(DistrictResultsInput(**district_input)),
            expect_nonempty_items,
        ),
        run_tool(
            'get_district_summary',
            district_input,
            lambda: handlers.get_district_summary(DistrictResultsInput(**district_input)),
            expect_summary,
        ),
        run_tool(
            'get_party_vote_share_history',
            history_input,
            lambda: handlers.get_party_vote_share_history(PartyVoteShareHistoryInput(**history_input)),
            expect_history,
        ),
        run_tool(
            'get_election_overview',
            {'sg_id': legislative_sg_id, 'sg_typecode': legislative_sg_typecode},
            lambda: handlers.get_election_overview(ElectionOverviewInput(sg_id=legislative_sg_id, sg_typecode=legislative_sg_typecode)),
            expect_overview,
        ),
        run_tool(
            'assemble_candidate_packet',
            candidate_lookup_input,
            lambda: handlers.assemble_candidate_packet(AssembleCandidatePacketInput(**candidate_lookup_input)),
            expect_packet,
        ),
        run_tool(
            'diagnose_core_api_access',
            {},
            lambda: handlers.diagnose_core_api_access(DiagnoseInput()),
            expect_diagnostics,
        ),
        run_tool(
            'diagnose_full_api_access',
            {'include_optional': True},
            lambda: handlers.diagnose_full_api_access(DiagnoseInput(include_optional=True)),
            expect_diagnostics,
        ),

        run_tool(
            'get_krpoltext_text',
            krpoltext_input,
            lambda: handlers.get_krpoltext_text(KrPolTextInput(**krpoltext_input)),
            expect_text,
        ),
    ]

    verdict_counts: dict[str, int] = {}
    for result in tool_results:
        verdict = result['verdict']
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    report = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'context': {
            'candidate_discovery': candidate_discovery,
            'krpoltext_discovery': krpoltext_discovery,
            'selected_candidate_ref': legislative_ref,
            'selected_krpoltext_record': (krpoltext_context or {}).get('record'),
        },
        'summary': {
            'tool_count': len(tool_results),
            'verdict_counts': verdict_counts,
        },
        'tools': tool_results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    print(f'Report written to {REPORT_PATH.resolve()}')
    for result in tool_results:
        print(f"[{result['verdict']}] {result['tool']}: {result['note']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

