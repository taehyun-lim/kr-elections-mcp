from __future__ import annotations

from datetime import date

from .errors import ApiAuthorizationError, ApiNotAppliedError, ApiRequestError, ConfigurationError
from .models import CandidateRef, DiagnosticCheck, DiagnosticStatus, DiagnosticsReport, ProvenanceRecord
from .nec_api import NecApiClient
from .redact import redact_api_key
from .results_api import ResultsApiClient


DIAGNOSTIC_CANDIDATE_NAME = "\uC724\uC11D\uC5F4"


class DiagnosticsService:
    def __init__(self, nec_client: NecApiClient, results_client: ResultsApiClient) -> None:
        self.nec_client = nec_client
        self.results_client = results_client

    def diagnose_core_api_access(self) -> DiagnosticsReport:
        checks: list[DiagnosticCheck] = []
        elections = self._run_check("elections", lambda: self.nec_client.list_elections(include_history=True))
        checks.append(elections)

        election_items = elections.details.get("items") if elections.status == DiagnosticStatus.OK else None
        sample_election = self._pick_sample_election(election_items)

        if sample_election:
            sg_id = sample_election["sg_id"]
            sg_typecode = sample_election["sg_typecode"]
            districts = self._run_check(
                "districts",
                lambda: self.nec_client.list_districts(sg_id=sg_id, sg_typecode=sg_typecode),
            )
            checks.append(districts)
        else:
            checks.append(self._empty("districts", "Skipped because elections could not be resolved."))
            sg_id = None
            sg_typecode = None

        candidate_search = self._run_check(
            "candidate_search",
            lambda: self.nec_client.search_candidates(candidate_name=DIAGNOSTIC_CANDIDATE_NAME, limit=3),
        )
        checks.append(candidate_search)

        search_items = candidate_search.details.get("items") if candidate_search.status == DiagnosticStatus.OK else None
        sample_candidate = search_items[0] if search_items else None
        if sample_candidate:
            candidate_ref = CandidateRef(**sample_candidate["candidate_ref"])
            checks.append(
                self._run_check(
                    "candidate_profile",
                    lambda: self.nec_client.get_candidate_profile(candidate_ref=candidate_ref),
                )
            )
            checks.append(
                self._run_check(
                    "candidate_policies",
                    lambda: self.nec_client.get_candidate_policies(candidate_ref=candidate_ref),
                )
            )
        else:
            checks.append(self._empty("candidate_profile", "No sample candidate was available."))
            checks.append(self._empty("candidate_policies", "No sample candidate was available."))

        if sample_election:
            checks.append(
                self._run_check(
                    "winner_results",
                    lambda: self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode),
                )
            )
            checks.append(
                self._run_check(
                    "district_tally",
                    lambda: self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode),
                )
            )
        else:
            checks.append(self._empty("winner_results", "No sample election was available."))
            checks.append(self._empty("district_tally", "No sample election was available."))

        return DiagnosticsReport(checks=checks)

    def diagnose_full_api_access(self) -> DiagnosticsReport:
        report = self.diagnose_core_api_access()
        elections_check = next((check for check in report.checks if check.name == "elections"), None)
        sample_election = None
        if elections_check and elections_check.status == DiagnosticStatus.OK:
            items = elections_check.details.get("items") or []
            sample_election = self._pick_sample_election(items)
        if sample_election:
            extra_check = self._run_check(
                "turnout",
                lambda: self.nec_client.fetch_turnout_rows(
                    sg_id=sample_election["sg_id"],
                    sg_typecode=sample_election["sg_typecode"],
                ),
            )
        else:
            extra_check = self._empty("turnout", "Skipped because no sample election was available.")
        report.checks.append(extra_check)
        return report

    def _run_check(self, name: str, fn) -> DiagnosticCheck:
        try:
            value = fn()
        except ConfigurationError as exc:
            return DiagnosticCheck(name=name, status=DiagnosticStatus.ERROR, message=self._redact_message(str(exc)))
        except ApiNotAppliedError as exc:
            return DiagnosticCheck(name=name, status=DiagnosticStatus.NOT_APPLIED, message=self._redact_message(str(exc)))
        except ApiAuthorizationError as exc:
            return DiagnosticCheck(name=name, status=DiagnosticStatus.UNAUTHORIZED, message=self._redact_message(str(exc)))
        except ApiRequestError as exc:
            return DiagnosticCheck(name=name, status=DiagnosticStatus.ERROR, message=self._redact_message(str(exc)))
        except Exception as exc:  # pragma: no cover
            return DiagnosticCheck(name=name, status=DiagnosticStatus.ERROR, message=self._redact_message(str(exc)))

        normalized = self._normalize_value(value)
        if not normalized:
            return DiagnosticCheck(
                name=name,
                status=DiagnosticStatus.EMPTY,
                message="The endpoint responded but returned no sample data.",
                details={"items": []},
                provenance=[self._provenance(name)],
            )
        return DiagnosticCheck(
            name=name,
            status=DiagnosticStatus.OK,
            message="The endpoint returned sample data.",
            details={"items": normalized},
            provenance=[self._provenance(name)],
        )

    def _redact_message(self, message: str) -> str:
        settings = getattr(self.nec_client, "settings", None)
        api_key_candidates = getattr(settings, "api_key_candidates", None)
        known_values: list[str] = []
        if callable(api_key_candidates):
            try:
                known_values = [candidate.value for candidate in api_key_candidates() if getattr(candidate, "value", None)]
            except Exception:  # pragma: no cover
                known_values = []
        return redact_api_key(message, known_values=known_values)

    @staticmethod
    def _pick_sample_election(items):
        if not items:
            return None

        def election_stamp(item):
            election_date = "".join(character for character in str(item.get("election_date") or "") if character.isdigit())
            sg_id = "".join(character for character in str(item.get("sg_id") or "") if character.isdigit())
            return election_date or sg_id

        today_stamp = date.today().strftime("%Y%m%d")
        completed_items = [item for item in items if (stamp := election_stamp(item)) and stamp <= today_stamp]
        pool = completed_items or items
        return max(
            pool,
            key=lambda item: (
                election_stamp(item),
                str(item.get("sg_id") or ""),
                str(item.get("sg_typecode") or ""),
            ),
        )

    @staticmethod
    def _normalize_value(value):
        if isinstance(value, tuple):
            return [DiagnosticsService._normalize_value(item) for item in value]
        if isinstance(value, list):
            return [item.model_dump() if hasattr(item, "model_dump") else item for item in value]
        if hasattr(value, "model_dump"):
            return [value.model_dump()]
        return [value]

    @staticmethod
    def _empty(name: str, message: str) -> DiagnosticCheck:
        return DiagnosticCheck(name=name, status=DiagnosticStatus.EMPTY, message=message, details={"items": []})

    @staticmethod
    def _provenance(name: str) -> ProvenanceRecord:
        return ProvenanceRecord(source_name="diagnostics", entity_type="diagnostic", source_ref=name, access_method="tool")






