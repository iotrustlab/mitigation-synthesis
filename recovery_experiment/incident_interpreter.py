"""Deterministic raw-evidence interpretation for the synthetic Dr.ICS baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .candidate_context import CandidateClaim, CandidateRecoveryContext, CandidateStatus
from .incident_evidence import IncidentEvidence, Observation, ResourceObservation, ResourceStatus
from .model import AttackerAction


INTERPRETATION_RULES: dict[str, str] = {
    "latest_observation": "A strictly latest valid observation wins; different values tied at the latest timestamp remain conflicting.",
    "p1_compromise": "Suspect P1 only when a P1-targeted unauthorized-write alert and an unauthorized P1 command event both exist.",
    "primary_capability": "A supported P1 compromise yields the abstract modify_primary_pump_command candidate capability, never from a command value alone.",
    "resource_status": "A strictly latest resource status wins; tied available/unavailable status remains conflicting.",
    "command_schedule": "Only explicitly unauthorized P1 ON/OFF events form a deterministic candidate schedule.",
    "timing": "Timing claims are extracted only from timing observations; configuration may later ground a missing value but does not alter the candidate claim.",
}


class IncidentInterpreter(Protocol):
    def interpret(self, evidence: IncidentEvidence) -> CandidateRecoveryContext: ...


@dataclass(frozen=True)
class DeterministicIncidentInterpreter:
    """Rule-based interpreter used as the gold baseline for a future LLM evaluator."""

    def interpret(self, evidence: IncidentEvidence) -> CandidateRecoveryContext:
        alert_ids = tuple(alert.provenance_id for alert in evidence.alerts)
        compromise_alerts = tuple(
            alert
            for alert in evidence.alerts
            if alert.component in {"P1", "P1_command"}
            and alert.alert_type in {"unauthorized_p1_command", "unauthorized_write", "command_state_mismatch"}
        )
        unauthorized_p1_events = tuple(
            event
            for event in evidence.command_events
            if event.component in {"P1", "P1_command"} and event.authorized is False
        )
        if compromise_alerts and unauthorized_p1_events:
            evidence_ids = tuple(alert.provenance_id for alert in compromise_alerts) + tuple(
                event.provenance_id for event in unauthorized_p1_events
            )
            compromised = CandidateClaim(
                value="P1",
                status=CandidateStatus.DERIVED,
                evidence_ids=evidence_ids,
                sources=tuple(
                    sorted(
                        {
                            *("synthetic_ids" for _ in compromise_alerts),
                            *(event.command_source or "unknown_command_source" for event in unauthorized_p1_events),
                        }
                    )
                ),
                rule_ids=("p1_compromise",),
                note="alert plus unauthorized command history identifies the modeled P1 command surface",
            )
            capability = CandidateClaim(
                value="modify_primary_pump_command",
                status=CandidateStatus.DERIVED,
                evidence_ids=evidence_ids,
                sources=compromised.sources,
                rule_ids=("primary_capability",),
                note="capability is a modeled abstract action, not an ownership inference from command value",
            )
        else:
            compromised = CandidateClaim.unknown(
                "P1 compromise requires both an appropriate alert and unauthorized P1 command history"
            )
            capability = CandidateClaim.unknown(
                "attacker capability is not inferred from an isolated command value"
            )

        return CandidateRecoveryContext(
            incident_id=evidence.scenario_id,
            plant_identity=_metadata_claim(evidence, "plant_identity"),
            suspected_compromised_component=compromised,
            attacker_capability=capability,
            x1=_observation_claim(evidence.observations, "x1", _numeric),
            x2=_observation_claim(evidence.observations, "x2", _numeric),
            p1_command=_observation_claim(evidence.observations, "P1_command", _bool_command),
            p1_actual_state=_observation_claim(evidence.observations, "P1_actual", _bool_command),
            backup_operational=_resource_claim(evidence.resource_observations, "P2"),
            isolation_operational=_resource_claim(evidence.resource_observations, "isolator"),
            inflow_control_operational=_resource_claim(evidence.resource_observations, "upstream_gate"),
            demand_control_operational=_resource_claim(evidence.resource_observations, "demand_gate"),
            control_period=_observation_claim(evidence.observations, "control_period", _positive_numeric),
            isolation_delay=_observation_claim(evidence.observations, "isolation_delay", _nonnegative_numeric),
            backup_startup_delay=_observation_claim(
                evidence.observations, "backup_startup_delay", _nonnegative_numeric
            ),
            attacker_command_schedule=_schedule_claim(unauthorized_p1_events),
            relevant_alerts=CandidateClaim(
                value=alert_ids,
                status=CandidateStatus.OBSERVED,
                evidence_ids=alert_ids,
                sources=("synthetic_ids",),
                rule_ids=(),
                note="raw security and anomaly alerts are retained separately from formal conclusions",
            ),
        )


def _metadata_claim(evidence: IncidentEvidence, key: str) -> CandidateClaim:
    value = evidence.metadata.get(key)
    if value is None:
        return CandidateClaim.unknown(f"metadata field {key} is absent")
    return CandidateClaim(
        value=value,
        status=CandidateStatus.OBSERVED,
        evidence_ids=(f"metadata:{key}",),
        sources=("incident_metadata",),
        note="declared incident metadata; trusted plant identity is checked only during grounding",
    )


def _observation_claim(
    observations: Sequence[Observation], signal: str, converter
) -> CandidateClaim:
    matching = [item for item in observations if item.signal == signal]
    if not matching:
        return CandidateClaim.unknown(f"no {signal} observation is present")
    usable = [item for item in matching if item.quality.value != "invalid"]
    if not usable:
        return CandidateClaim(
            value=None,
            status=CandidateStatus.REJECTED,
            evidence_ids=tuple(item.provenance_id for item in matching),
            sources=tuple(sorted({item.source for item in matching})),
            rule_ids=("latest_observation",),
            note=f"all {signal} observations are explicitly invalid",
        )
    latest = max(item.timestamp for item in usable)
    latest_items = [item for item in usable if item.timestamp == latest]
    values: list[object] = []
    try:
        values = [converter(item.value) for item in latest_items]
    except ValueError as exc:
        return CandidateClaim(
            value=None,
            status=CandidateStatus.REJECTED,
            evidence_ids=tuple(item.provenance_id for item in latest_items),
            sources=tuple(sorted({item.source for item in latest_items})),
            rule_ids=("latest_observation",),
            note=f"{signal} latest observation is invalid: {exc}",
        )
    if len(set(values)) != 1:
        return CandidateClaim.conflicting(
            tuple(item.provenance_id for item in latest_items),
            f"different {signal} values share the latest timestamp; no precedence rule resolves the conflict",
        )
    return CandidateClaim(
        value=values[0],
        status=CandidateStatus.OBSERVED,
        evidence_ids=tuple(item.provenance_id for item in latest_items),
        sources=tuple(sorted({item.source for item in latest_items})),
        rule_ids=("latest_observation",),
        confidence=min(
            1.0 if item.quality.value == "good" else 0.5 for item in latest_items
        ),
        note=f"latest valid {signal} observation selected deterministically",
    )


def _resource_claim(observations: Sequence[ResourceObservation], resource: str) -> CandidateClaim:
    matching = [item for item in observations if item.resource == resource]
    if not matching:
        return CandidateClaim.unknown(f"no observed status is present for {resource}")
    latest = max(item.timestamp for item in matching)
    latest_items = [item for item in matching if item.timestamp == latest]
    statuses = {item.status for item in latest_items}
    if len(statuses) != 1:
        return CandidateClaim.conflicting(
            tuple(item.provenance_id for item in latest_items),
            f"different {resource} statuses share the latest timestamp",
        )
    status = next(iter(statuses))
    if status is ResourceStatus.UNKNOWN:
        return CandidateClaim(
            value=None,
            status=CandidateStatus.UNKNOWN,
            evidence_ids=tuple(item.provenance_id for item in latest_items),
            sources=tuple(sorted({item.source for item in latest_items})),
            rule_ids=("resource_status",),
            note=f"{resource} observation explicitly reports unknown status",
        )
    return CandidateClaim(
        value=status is ResourceStatus.AVAILABLE,
        status=CandidateStatus.OBSERVED,
        evidence_ids=tuple(item.provenance_id for item in latest_items),
        sources=tuple(sorted({item.source for item in latest_items})),
        rule_ids=("resource_status",),
        confidence=min(item.confidence if item.confidence is not None else 1.0 for item in latest_items),
        note=f"latest {resource} availability observation selected deterministically",
    )


def _schedule_claim(events) -> CandidateClaim:
    values: list[AttackerAction] = []
    evidence_ids: list[str] = []
    for event in sorted(events, key=lambda item: (item.timestamp, item.provenance_id)):
        command = event.command.upper()
        if command == "ON":
            values.append(AttackerAction.FORCE_PRIMARY_ON)
        elif command == "OFF":
            values.append(AttackerAction.FORCE_PRIMARY_OFF)
        else:
            return CandidateClaim(
                value=None,
                status=CandidateStatus.REJECTED,
                evidence_ids=(event.provenance_id,),
                sources=((event.command_source or "unknown_command_source"),),
                rule_ids=("command_schedule",),
                note=f"unsupported P1 command {event.command!r} cannot be mapped to the formal attacker alphabet",
            )
        evidence_ids.append(event.provenance_id)
    if not values:
        return CandidateClaim.unknown("no unauthorized P1 command events form a schedule")
    return CandidateClaim(
        value=tuple(values),
        status=CandidateStatus.DERIVED,
        evidence_ids=tuple(evidence_ids),
        sources=tuple(sorted({event.command_source or "unknown_command_source" for event in events})),
        rule_ids=("command_schedule",),
        note="only explicit unauthorized P1 ON/OFF events are retained",
    )


def _numeric(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("numeric value required")
    return float(value)


def _positive_numeric(value: object) -> float:
    parsed = _numeric(value)
    if parsed <= 0:
        raise ValueError("positive numeric value required")
    return parsed


def _nonnegative_numeric(value: object) -> float:
    parsed = _numeric(value)
    if parsed < 0:
        raise ValueError("nonnegative numeric value required")
    return parsed


def _bool_command(value: object) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.upper() in {"ON", "OFF"}:
        return value.upper() == "ON"
    raise ValueError("boolean or ON/OFF command value required")
