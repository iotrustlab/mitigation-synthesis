"""Untrusted LLM interpretation into the existing candidate-context boundary."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Protocol, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .candidate_context import CandidateClaim, CandidateRecoveryContext, CandidateStatus
from .incident_evidence import IncidentEvidence
from .model import AttackerAction
from .openai_compatible_backend import BackendResponse
from .structured_output_schema import schema_sha256


PROMPT_VERSION = "prompt-v1"
SCHEMA_VERSION = "candidate-recovery-context-v1"

PROMPT_CONTRACT = """You are an untrusted incident-evidence extraction component for Dr.ICS.
Return only the JSON object required by the supplied schema. Do not output prose or reasoning.

Use only the supplied IncidentEvidence. Do not decide safety, recovery policy, formal model,
certificate applicability, or actuator actions. Do not invent topology, trust, authority, timing,
or missing observations. An UNKNOWN claim must use null. Conflicting latest evidence must remain
CONFLICTING rather than being resolved by guesswork. Cite only exact provenance_id strings from
the input; metadata claims cite metadata:<key>. Sources must be copied from the cited evidence
(alerts use synthetic_ids; metadata uses incident_metadata).

OBSERVED means directly present in evidence. DERIVED means a narrow incident interpretation with
supporting evidence. Derive P1 compromise/capability only from relevant security evidence plus an
unauthorized P1 command event. Never infer compromise from a command value alone. Resource status
reports operational availability only; it does not establish trust or recovery authority.

Apply these evidence-only extraction rules uniformly:
- plant_identity comes only from metadata.plant_identity.
- x1, x2, P1_command, P1_actual, control_period, isolation_delay, and
  backup_startup_delay come from the same-named observation signal. Use the strictly latest
  non-invalid observation; unresolved latest-time disagreement is CONFLICTING. Map ON/OFF to
  true/false for P1_command and P1_actual.
- backup_operational, isolation_operational, inflow_control_operational, and
  demand_control_operational correspond respectively to resources P2, isolator, upstream_gate,
  and demand_gate. Map available/unavailable to true/false using the strictly latest status.
- attacker_command_schedule contains chronological unauthorized P1 ON/OFF command events only.
- relevant_alerts contains the exact IDs of the input alerts, not alert descriptions.

For OBSERVED/DERIVED put supporting IDs in evidence_ids. For CONFLICTING use null and put at least
two IDs in conflict_evidence_ids. UNKNOWN/REJECTED use null. Every sources entry must be the exact
source bound to a cited ID; alerts use synthetic_ids and metadata uses incident_metadata. Use only
these rule_ids when applicable: latest_observation, resource_status, p1_compromise,
primary_capability, command_schedule, timing. Otherwise use an empty rule_ids array. Keep note short.

Allowed candidate vocabulary is intentionally narrow: compromised component is P1 or null;
attacker capability is modify_primary_pump_command or null; schedule entries are
force_primary_on/force_primary_off. Preserve exact numeric observations and exact alert IDs.
"""


@dataclass(frozen=True)
class CandidateProvenanceAudit:
    """Best-effort provenance metrics, including for rejected model output."""

    total_references: int
    valid_references: int
    fabricated_ids: tuple[str, ...]
    missing_support_claims: tuple[str, ...]
    unsupported_claims: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "total_references": self.total_references,
            "valid_references": self.valid_references,
            "fabricated_ids": list(self.fabricated_ids),
            "missing_support_claims": list(self.missing_support_claims),
            "unsupported_claims": list(self.unsupported_claims),
        }


class CandidateValidationError(ValueError):
    """Raised when model output is not a safe CandidateRecoveryContext.

    When validation fails after a server response, ``backend_response`` keeps
    the raw output available to the offline evaluation report.  It never
    contains the configured API key.
    """

    def __init__(
        self,
        message: str,
        *,
        backend_response: BackendResponse | None = None,
    ) -> None:
        super().__init__(message)
        self.backend_response = backend_response


class StructuredChatBackend(Protocol):
    def complete_json(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema_name: str,
        json_schema: Mapping[str, object],
    ) -> BackendResponse: ...


@dataclass(frozen=True)
class LLMInterpretation:
    candidate: CandidateRecoveryContext
    backend_response: BackendResponse
    prompt_version: str
    prompt_hash: str
    candidate_schema_version: str
    canonical_schema_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.as_dict(),
            "backend_response": self.backend_response.as_dict(),
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "candidate_schema_version": self.candidate_schema_version,
            "canonical_schema_hash": self.canonical_schema_hash,
        }


@dataclass(frozen=True)
class LLMIncidentInterpreter:
    """Model-independent interpreter using a structured OpenAI-compatible backend."""

    backend: StructuredChatBackend

    def interpret(self, evidence: IncidentEvidence) -> CandidateRecoveryContext:
        return self.interpret_with_trace(evidence).candidate

    def interpret_with_trace(self, evidence: IncidentEvidence) -> LLMInterpretation:
        schema = candidate_response_schema()
        response = self.backend.complete_json(
            _messages_for(evidence),
            schema_name="drics_candidate_recovery_context",
            json_schema=schema,
        )
        try:
            candidate = parse_candidate_response(response.content, evidence)
        except CandidateValidationError as exc:
            raise CandidateValidationError(
                str(exc), backend_response=response
            ) from exc
        return LLMInterpretation(
            candidate,
            response,
            PROMPT_VERSION,
            prompt_contract_hash(),
            SCHEMA_VERSION,
            schema_hash(schema),
        )


def prompt_contract_hash() -> str:
    return hashlib.sha256(PROMPT_CONTRACT.encode("utf-8")).hexdigest()


def schema_hash(schema: Mapping[str, object] | None = None) -> str:
    return schema_sha256(candidate_response_schema() if schema is None else schema)


def candidate_response_schema() -> dict[str, object]:
    """Return the authoritative CandidateRecoveryContext acceptance schema."""

    string_or_null = {"type": ["string", "null"]}
    number_or_null = {"type": ["number", "null"]}
    boolean_or_null = {"type": ["boolean", "null"]}
    schedule_or_null = {
        "anyOf": [
            {
                "type": "array",
                "items": {"enum": ["force_primary_off", "force_primary_on"]},
            },
            {"type": "null"},
        ]
    }
    alerts_or_null = {
        "anyOf": [
            {"type": "array", "items": {"type": "string"}},
            {"type": "null"},
        ]
    }
    fields = {
        "plant_identity": _claim_schema(string_or_null),
        "suspected_compromised_component": _claim_schema(
            {"enum": ["P1", None]}
        ),
        "attacker_capability": _claim_schema(
            {"enum": ["modify_primary_pump_command", None]}
        ),
        "x1": _claim_schema(number_or_null),
        "x2": _claim_schema(number_or_null),
        "p1_command": _claim_schema(boolean_or_null),
        "p1_actual_state": _claim_schema(boolean_or_null),
        "backup_operational": _claim_schema(boolean_or_null),
        "isolation_operational": _claim_schema(boolean_or_null),
        "inflow_control_operational": _claim_schema(boolean_or_null),
        "demand_control_operational": _claim_schema(boolean_or_null),
        "control_period": _claim_schema(number_or_null),
        "isolation_delay": _claim_schema(number_or_null),
        "backup_startup_delay": _claim_schema(number_or_null),
        "attacker_command_schedule": _claim_schema(schedule_or_null),
        "relevant_alerts": _claim_schema(alerts_or_null),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["incident_id", "fields"],
        "properties": {
            "incident_id": {"type": "string"},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "required": list(fields),
                "properties": fields,
            },
        },
    }


def _claim_schema(value_schema: Mapping[str, object]) -> dict[str, object]:
    properties: dict[str, object] = {
        "value": dict(value_schema),
        "status": {
            "enum": [
                CandidateStatus.OBSERVED.value,
                CandidateStatus.DERIVED.value,
                CandidateStatus.UNKNOWN.value,
                CandidateStatus.CONFLICTING.value,
                CandidateStatus.REJECTED.value,
            ]
        },
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "sources": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "rule_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "confidence": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
        "conflict_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
        "note": {"type": "string", "maxLength": 1024},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _messages_for(evidence: IncidentEvidence) -> tuple[dict[str, str], ...]:
    return (
        {"role": "system", "content": PROMPT_CONTRACT},
        {
            "role": "user",
            "content": "Interpret this IncidentEvidence JSON:\n" + evidence.to_json(),
        },
    )


def parse_candidate_response(text: str, evidence: IncidentEvidence) -> CandidateRecoveryContext:
    try:
        document = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, CandidateValidationError) as exc:
        raise CandidateValidationError(f"model response is not JSON: {exc}") from exc
    _validate_canonical_candidate_document(document)
    if not isinstance(document, dict):
        raise CandidateValidationError("model response must be a JSON object")
    if set(document) != {"incident_id", "fields"}:
        raise CandidateValidationError("model response must contain only incident_id and fields")
    if document["incident_id"] != evidence.scenario_id:
        raise CandidateValidationError("model response incident_id does not match the input evidence")
    fields = document.get("fields")
    if not isinstance(fields, dict):
        raise CandidateValidationError("fields must be an object")
    expected_fields = tuple(CandidateRecoveryContext.__dataclass_fields__)[1:]
    if set(fields) != set(expected_fields):
        missing = sorted(set(expected_fields) - set(fields))
        extra = sorted(set(fields) - set(expected_fields))
        raise CandidateValidationError(f"candidate field set mismatch; missing={missing}, extra={extra}")

    evidence_index = _evidence_source_index(evidence)
    allowed_ids = _allowed_evidence_ids(evidence)
    claims = {
        name: _parse_claim(name, fields[name], evidence_index, allowed_ids[name])
        for name in expected_fields
    }
    _validate_field_values(claims, evidence)
    _validate_supported_claim_bindings(claims, evidence)
    _validate_security_derivations(claims, evidence)
    return CandidateRecoveryContext(evidence.scenario_id, **claims)


@lru_cache(maxsize=1)
def _canonical_candidate_validator() -> Draft202012Validator:
    """Compile the unchanged canonical schema once using an explicit draft."""

    schema = candidate_response_schema()
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:  # A broken trusted contract is not model output.
        raise RuntimeError(f"canonical CandidateRecoveryContext schema is invalid: {exc}") from exc
    return Draft202012Validator(schema)


def _validate_canonical_candidate_document(document: object) -> None:
    errors = sorted(
        _canonical_candidate_validator().iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            tuple(str(part) for part in error.absolute_schema_path),
        ),
    )
    if not errors:
        return
    error = errors[0]
    path = _json_instance_path(tuple(error.absolute_path))
    raise CandidateValidationError(
        "canonical CandidateRecoveryContext schema validation failed "
        f"at {path}: {error.message}"
    )


def _json_instance_path(parts: tuple[object, ...]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and part.replace("_", "a").isalnum() and not part[:1].isdigit():
            path += f".{part}"
        else:
            path += f"[{json.dumps(part)}]"
    return path


def _parse_claim(
    name: str,
    raw: object,
    evidence_index: Mapping[str, str],
    allowed_ids: set[str],
) -> CandidateClaim:
    if not isinstance(raw, dict):
        raise CandidateValidationError(f"{name} claim must be an object")
    expected = {
        "value",
        "status",
        "evidence_ids",
        "sources",
        "rule_ids",
        "confidence",
        "conflict_evidence_ids",
        "note",
    }
    if set(raw) != expected:
        raise CandidateValidationError(f"{name} claim has missing or extra properties")
    try:
        status = CandidateStatus(raw["status"])
    except (TypeError, ValueError) as exc:
        raise CandidateValidationError(f"{name} has unsupported status") from exc
    if status in {CandidateStatus.CONFIGURED, CandidateStatus.GROUNDED}:
        raise CandidateValidationError(f"{name} cannot claim trusted status {status.value}")
    evidence_ids = _string_tuple(raw["evidence_ids"], f"{name}.evidence_ids")
    conflict_ids = _string_tuple(raw["conflict_evidence_ids"], f"{name}.conflict_evidence_ids")
    sources = _string_tuple(raw["sources"], f"{name}.sources")
    rule_ids = _string_tuple(raw["rule_ids"], f"{name}.rule_ids")
    cited_ids = set(evidence_ids) | set(conflict_ids)
    fabricated = sorted(cited_ids - set(evidence_index))
    if fabricated:
        raise CandidateValidationError(f"{name} cites fabricated evidence IDs: {fabricated}")
    unrelated = sorted(cited_ids - allowed_ids)
    if unrelated:
        raise CandidateValidationError(
            f"{name} cites evidence IDs that do not support that field: {unrelated}"
        )
    expected_sources = {evidence_index[item] for item in cited_ids}
    if set(sources) != expected_sources:
        raise CandidateValidationError(
            f"{name} sources do not exactly match its cited evidence IDs; "
            f"expected={sorted(expected_sources)}, actual={sorted(set(sources))}"
        )
    allowed_rules = _allowed_rule_ids(name)
    unsupported_rules = sorted(set(rule_ids) - allowed_rules)
    if unsupported_rules:
        raise CandidateValidationError(
            f"{name} cites unsupported interpretation rules: {unsupported_rules}"
        )
    confidence = raw["confidence"]
    if confidence is not None and (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(float(confidence))
        or not 0 <= float(confidence) <= 1
    ):
        raise CandidateValidationError(f"{name}.confidence must be null or between zero and one")
    note = raw["note"]
    if not isinstance(note, str):
        raise CandidateValidationError(f"{name}.note must be a string")
    if len(note) > 1024:
        raise CandidateValidationError(f"{name}.note must not exceed 1024 characters")
    value = raw["value"]
    if status in {CandidateStatus.UNKNOWN, CandidateStatus.CONFLICTING, CandidateStatus.REJECTED} and value is not None:
        raise CandidateValidationError(f"{name} status {status.value} requires a null value")
    if status in {CandidateStatus.OBSERVED, CandidateStatus.DERIVED} and value is None:
        raise CandidateValidationError(f"{name} status {status.value} requires a value")
    if status in {CandidateStatus.OBSERVED, CandidateStatus.DERIVED} and not evidence_ids:
        raise CandidateValidationError(f"{name} supported claim requires evidence IDs")
    if status is CandidateStatus.CONFLICTING and len(conflict_ids) < 2:
        raise CandidateValidationError(f"{name} conflicting claim requires at least two conflict evidence IDs")
    return CandidateClaim(
        value=value,
        status=status,
        evidence_ids=evidence_ids,
        sources=sources,
        rule_ids=rule_ids,
        confidence=None if confidence is None else float(confidence),
        conflict_evidence_ids=conflict_ids,
        note=note,
    )


def _validate_field_values(
    claims: dict[str, CandidateClaim], evidence: IncidentEvidence
) -> None:
    def nullable_bool(name: str) -> None:
        value = claims[name].value
        if value is not None and type(value) is not bool:
            raise CandidateValidationError(f"{name} value must be boolean or null")

    def nullable_number(name: str, *, positive: bool = False) -> None:
        value = claims[name].value
        if value is None:
            return
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise CandidateValidationError(f"{name} value must be a finite number or null")
        if (positive and float(value) <= 0) or (not positive and float(value) < 0):
            qualifier = "positive" if positive else "nonnegative"
            raise CandidateValidationError(f"{name} value must be {qualifier}")
        claims[name] = _replace_value(claims[name], float(value))

    for name in (
        "p1_command",
        "p1_actual_state",
        "backup_operational",
        "isolation_operational",
        "inflow_control_operational",
        "demand_control_operational",
    ):
        nullable_bool(name)
    for name in ("x1", "x2"):
        value = claims[name].value
        if value is not None:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise CandidateValidationError(f"{name} value must be a finite number or null")
            claims[name] = _replace_value(claims[name], float(value))
    nullable_number("control_period", positive=True)
    nullable_number("isolation_delay")
    nullable_number("backup_startup_delay")

    if claims["plant_identity"].value is not None and not isinstance(claims["plant_identity"].value, str):
        raise CandidateValidationError("plant_identity value must be a string or null")
    if claims["suspected_compromised_component"].value not in {None, "P1"}:
        raise CandidateValidationError("suspected_compromised_component is outside the candidate vocabulary")
    if claims["attacker_capability"].value not in {None, "modify_primary_pump_command"}:
        raise CandidateValidationError("attacker_capability is outside the candidate vocabulary")

    schedule = claims["attacker_command_schedule"].value
    if schedule is not None:
        if not isinstance(schedule, list):
            raise CandidateValidationError("attacker_command_schedule value must be an array or null")
        try:
            actions = tuple(AttackerAction(item) for item in schedule)
        except (TypeError, ValueError) as exc:
            raise CandidateValidationError("attacker_command_schedule contains an unsupported action") from exc
        if any(action is AttackerAction.NOOP for action in actions):
            raise CandidateValidationError("LLM schedule may contain only explicit unauthorized ON/OFF actions")
        claims["attacker_command_schedule"] = _replace_value(claims["attacker_command_schedule"], actions)

    alerts = claims["relevant_alerts"].value
    if alerts is not None:
        parsed_alerts = _string_tuple(alerts, "relevant_alerts.value")
        valid_alerts = {item.provenance_id for item in evidence.alerts}
        invalid_alerts = sorted(set(parsed_alerts) - valid_alerts)
        if invalid_alerts:
            raise CandidateValidationError(
                f"relevant_alerts value contains non-alert evidence IDs: {invalid_alerts}"
            )
        if set(parsed_alerts) != set(claims["relevant_alerts"].evidence_ids):
            raise CandidateValidationError(
                "relevant_alerts value and evidence_ids must identify the same alerts"
            )
        claims["relevant_alerts"] = _replace_value(claims["relevant_alerts"], parsed_alerts)


def _validate_security_derivations(
    claims: Mapping[str, CandidateClaim], evidence: IncidentEvidence
) -> None:
    security_alert_ids = {
        alert.provenance_id
        for alert in evidence.alerts
        if alert.component in {"P1", "P1_command"}
        and alert.alert_type
        in {"unauthorized_p1_command", "unauthorized_write", "command_state_mismatch"}
    }
    unauthorized_command_ids = {
        event.provenance_id
        for event in evidence.command_events
        if event.component in {"P1", "P1_command"} and event.authorized is False
    }
    for name in ("suspected_compromised_component", "attacker_capability"):
        claim = claims[name]
        if claim.status not in {CandidateStatus.OBSERVED, CandidateStatus.DERIVED}:
            continue
        if claim.status is not CandidateStatus.DERIVED:
            raise CandidateValidationError(f"{name} must be DERIVED, not OBSERVED")
        cited = set(claim.evidence_ids)
        if not cited & security_alert_ids or not cited & unauthorized_command_ids:
            raise CandidateValidationError(
                f"{name} requires both relevant security-alert and unauthorized-command evidence"
            )


def _validate_supported_claim_bindings(
    claims: Mapping[str, CandidateClaim], evidence: IncidentEvidence
) -> None:
    """Bind every claim that could pass grounding to the latest raw record.

    UNKNOWN, CONFLICTING, and REJECTED remain fail-closed interpretations.  A
    positive OBSERVED/DERIVED value, however, must not be able to cite a real
    record while changing its content or selecting a stale record.
    """

    supported = {CandidateStatus.OBSERVED, CandidateStatus.DERIVED}
    plant = claims["plant_identity"]
    if plant.status in supported:
        if plant.status is not CandidateStatus.OBSERVED:
            raise CandidateValidationError("plant_identity must be OBSERVED, not DERIVED")
        expected = evidence.metadata.get("plant_identity")
        if plant.value != expected or set(plant.evidence_ids) != {"metadata:plant_identity"}:
            raise CandidateValidationError(
                "plant_identity value/provenance does not match metadata.plant_identity"
            )

    observation_fields = {
        "x1": ("x1", _wire_number),
        "x2": ("x2", _wire_number),
        "p1_command": ("P1_command", _wire_bool_command),
        "p1_actual_state": ("P1_actual", _wire_bool_command),
        "control_period": ("control_period", _wire_number),
        "isolation_delay": ("isolation_delay", _wire_number),
        "backup_startup_delay": ("backup_startup_delay", _wire_number),
    }
    for field, (signal, converter) in observation_fields.items():
        claim = claims[field]
        if claim.status not in supported:
            continue
        if claim.status is not CandidateStatus.OBSERVED:
            raise CandidateValidationError(f"{field} must be OBSERVED, not DERIVED")
        matching = [
            item
            for item in evidence.observations
            if item.signal == signal and item.quality.value != "invalid"
        ]
        if not matching:
            raise CandidateValidationError(f"{field} has no usable supporting observation")
        latest = max(item.timestamp for item in matching)
        latest_items = [item for item in matching if item.timestamp == latest]
        try:
            values = {converter(item.value) for item in latest_items}
        except ValueError as exc:
            raise CandidateValidationError(
                f"{field} latest observation cannot support a value: {exc}"
            ) from exc
        if len(values) != 1:
            raise CandidateValidationError(
                f"{field} asserts a value despite conflicting latest observations"
            )
        if claim.value != next(iter(values)) or set(claim.evidence_ids) != {
            item.provenance_id for item in latest_items
        }:
            raise CandidateValidationError(
                f"{field} value/provenance does not match the latest observation"
            )

    resource_fields = {
        "backup_operational": "P2",
        "isolation_operational": "isolator",
        "inflow_control_operational": "upstream_gate",
        "demand_control_operational": "demand_gate",
    }
    for field, resource in resource_fields.items():
        claim = claims[field]
        if claim.status not in supported:
            continue
        if claim.status is not CandidateStatus.OBSERVED:
            raise CandidateValidationError(f"{field} must be OBSERVED, not DERIVED")
        matching = [
            item for item in evidence.resource_observations if item.resource == resource
        ]
        if not matching:
            raise CandidateValidationError(f"{field} has no supporting resource observation")
        latest = max(item.timestamp for item in matching)
        latest_items = [item for item in matching if item.timestamp == latest]
        statuses = {item.status.value for item in latest_items}
        if len(statuses) != 1 or "unknown" in statuses:
            raise CandidateValidationError(
                f"{field} asserts a value despite conflicting/unknown latest resource status"
            )
        expected_value = next(iter(statuses)) == "available"
        if claim.value is not expected_value or set(claim.evidence_ids) != {
            item.provenance_id for item in latest_items
        }:
            raise CandidateValidationError(
                f"{field} value/provenance does not match the latest resource status"
            )

    schedule = claims["attacker_command_schedule"]
    if schedule.status in supported:
        if schedule.status is not CandidateStatus.DERIVED:
            raise CandidateValidationError(
                "attacker_command_schedule must be DERIVED from command events"
            )
        events = sorted(
            (
                item
                for item in evidence.command_events
                if item.component in {"P1", "P1_command"}
                and item.authorized is False
            ),
            key=lambda item: (item.timestamp, item.provenance_id),
        )
        expected_actions: list[AttackerAction] = []
        for event in events:
            command = event.command.upper()
            if command not in {"ON", "OFF"}:
                raise CandidateValidationError(
                    "attacker_command_schedule cannot assert a value for an unsupported command"
                )
            expected_actions.append(
                AttackerAction.FORCE_PRIMARY_ON
                if command == "ON"
                else AttackerAction.FORCE_PRIMARY_OFF
            )
        if schedule.value != tuple(expected_actions) or schedule.evidence_ids != tuple(
            item.provenance_id for item in events
        ):
            raise CandidateValidationError(
                "attacker_command_schedule value/provenance does not match unauthorized P1 events"
            )

    alerts = claims["relevant_alerts"]
    if alerts.status in supported:
        if alerts.status is not CandidateStatus.OBSERVED:
            raise CandidateValidationError("relevant_alerts must be OBSERVED, not DERIVED")
        expected_alerts = tuple(item.provenance_id for item in evidence.alerts)
        if alerts.value != expected_alerts or alerts.evidence_ids != expected_alerts:
            raise CandidateValidationError(
                "relevant_alerts must preserve all input alert IDs in input order"
            )


def _wire_number(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("finite numeric value required")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("finite numeric value required")
    return parsed


def _wire_bool_command(value: object) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.upper() in {"ON", "OFF"}:
        return value.upper() == "ON"
    raise ValueError("boolean or ON/OFF value required")


def _replace_value(claim: CandidateClaim, value: object) -> CandidateClaim:
    return CandidateClaim(
        value,
        claim.status,
        claim.evidence_ids,
        claim.sources,
        claim.rule_ids,
        claim.confidence,
        claim.conflict_evidence_ids,
        claim.note,
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CandidateValidationError(f"{field} must be an array of nonempty strings")
    if len(value) != len(set(value)):
        raise CandidateValidationError(f"{field} must not contain duplicate values")
    return tuple(value)


def audit_candidate_provenance(
    text: str, evidence: IncidentEvidence
) -> CandidateProvenanceAudit:
    """Audit rejected output without repairing it or making it acceptable."""

    try:
        document = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, CandidateValidationError):
        return CandidateProvenanceAudit(0, 0, (), (), ("response:not_valid_json",))
    if not isinstance(document, dict) or not isinstance(document.get("fields"), dict):
        return CandidateProvenanceAudit(0, 0, (), (), ("response:missing_fields_object",))

    index = _evidence_source_index(evidence)
    allowed = _allowed_evidence_ids(evidence)
    total = 0
    valid = 0
    fabricated: set[str] = set()
    missing: set[str] = set()
    unsupported: set[str] = set()
    for name, raw in document["fields"].items():
        if name not in allowed or not isinstance(raw, dict):
            unsupported.add(str(name))
            continue
        ids: list[str] = []
        for key in ("evidence_ids", "conflict_evidence_ids"):
            value = raw.get(key)
            if isinstance(value, list):
                ids.extend(item for item in value if isinstance(item, str))
        total += len(ids)
        valid += sum(item in index for item in ids)
        fabricated.update(item for item in ids if item not in index)
        if raw.get("status") in {
            CandidateStatus.OBSERVED.value,
            CandidateStatus.DERIVED.value,
        } and not (
            isinstance(raw.get("evidence_ids"), list) and raw["evidence_ids"]
        ):
            missing.add(name)
        if any(item in index and item not in allowed[name] for item in ids):
            unsupported.add(name)
        cited_valid = {item for item in ids if item in index}
        raw_sources = raw.get("sources")
        if not isinstance(raw_sources, list) or set(
            item for item in raw_sources if isinstance(item, str)
        ) != {index[item] for item in cited_valid}:
            unsupported.add(name)
    return CandidateProvenanceAudit(
        total,
        valid,
        tuple(sorted(fabricated)),
        tuple(sorted(missing)),
        tuple(sorted(unsupported)),
    )


def _reject_json_constant(value: str) -> object:
    raise CandidateValidationError(f"non-finite JSON constant is not allowed: {value}")


def _evidence_source_index(evidence: IncidentEvidence) -> dict[str, str]:
    """Bind each provenance ID to its actual source before grounding."""

    index: dict[str, str] = {}

    def add(provenance_id: str, source: str) -> None:
        if provenance_id in index:
            raise CandidateValidationError(
                f"duplicate or colliding evidence provenance ID: {provenance_id}"
            )
        index[provenance_id] = source

    for item in evidence.observations:
        add(item.provenance_id, item.source)
    for item in evidence.alerts:
        add(item.provenance_id, "synthetic_ids")
    for item in evidence.command_events:
        add(item.provenance_id, item.command_source or "unknown_command_source")
    for item in evidence.resource_observations:
        add(item.provenance_id, item.source)
    for key in evidence.metadata:
        add(f"metadata:{key}", "incident_metadata")
    return index


def _allowed_evidence_ids(evidence: IncidentEvidence) -> dict[str, set[str]]:
    observations: dict[str, set[str]] = {}
    for item in evidence.observations:
        observations.setdefault(item.signal, set()).add(item.provenance_id)
    resources: dict[str, set[str]] = {}
    for item in evidence.resource_observations:
        resources.setdefault(item.resource, set()).add(item.provenance_id)
    alerts = {item.provenance_id for item in evidence.alerts}
    security_alerts = {
        item.provenance_id
        for item in evidence.alerts
        if item.component in {"P1", "P1_command"}
        and item.alert_type
        in {"unauthorized_p1_command", "unauthorized_write", "command_state_mismatch"}
    }
    unauthorized_p1 = {
        item.provenance_id
        for item in evidence.command_events
        if item.component in {"P1", "P1_command"} and item.authorized is False
    }
    compromise = security_alerts | unauthorized_p1
    return {
        "plant_identity": (
            {"metadata:plant_identity"}
            if "plant_identity" in evidence.metadata
            else set()
        ),
        "suspected_compromised_component": compromise,
        "attacker_capability": compromise,
        "x1": observations.get("x1", set()),
        "x2": observations.get("x2", set()),
        "p1_command": observations.get("P1_command", set()),
        "p1_actual_state": observations.get("P1_actual", set()),
        "backup_operational": resources.get("P2", set()),
        "isolation_operational": resources.get("isolator", set()),
        "inflow_control_operational": resources.get("upstream_gate", set()),
        "demand_control_operational": resources.get("demand_gate", set()),
        "control_period": observations.get("control_period", set()),
        "isolation_delay": observations.get("isolation_delay", set()),
        "backup_startup_delay": observations.get("backup_startup_delay", set()),
        "attacker_command_schedule": unauthorized_p1,
        "relevant_alerts": alerts,
    }


def _allowed_rule_ids(field: str) -> set[str]:
    if field in {"suspected_compromised_component"}:
        return {"p1_compromise"}
    if field in {"attacker_capability"}:
        return {"primary_capability"}
    if field == "attacker_command_schedule":
        return {"command_schedule"}
    if field in {
        "backup_operational",
        "isolation_operational",
        "inflow_control_operational",
        "demand_control_operational",
    }:
        return {"resource_status"}
    if field in {
        "x1",
        "x2",
        "p1_command",
        "p1_actual_state",
        "control_period",
        "isolation_delay",
        "backup_startup_delay",
    }:
        return {"latest_observation", "timing"}
    return set()
