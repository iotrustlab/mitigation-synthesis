"""Provenance-aware candidate interpretations, before trusted grounding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CandidateStatus(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    CONFIGURED = "CONFIGURED"
    GROUNDED = "GROUNDED"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"
    REJECTED = "REJECTED"


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(_json_value(item) for item in value)
    return value


@dataclass(frozen=True)
class CandidateClaim:
    """One interpreted value plus its evidence and deterministic rule trace."""

    value: object | None
    status: CandidateStatus
    evidence_ids: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    confidence: float | None = None
    conflict_evidence_ids: tuple[str, ...] = ()
    note: str = ""

    @classmethod
    def unknown(cls, note: str) -> "CandidateClaim":
        return cls(None, CandidateStatus.UNKNOWN, note=note)

    @classmethod
    def conflicting(cls, evidence_ids: tuple[str, ...], note: str) -> "CandidateClaim":
        return cls(
            None,
            CandidateStatus.CONFLICTING,
            conflict_evidence_ids=evidence_ids,
            note=note,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "value": _json_value(self.value),
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "sources": list(self.sources),
            "rule_ids": list(self.rule_ids),
            "confidence": self.confidence,
            "conflict_evidence_ids": list(self.conflict_evidence_ids),
            "note": self.note,
        }


@dataclass(frozen=True)
class CandidateRecoveryContext:
    """Everything the deterministic interpreter may claim before trust grounding."""

    incident_id: str
    plant_identity: CandidateClaim
    suspected_compromised_component: CandidateClaim
    attacker_capability: CandidateClaim
    x1: CandidateClaim
    x2: CandidateClaim
    p1_command: CandidateClaim
    p1_actual_state: CandidateClaim
    backup_operational: CandidateClaim
    isolation_operational: CandidateClaim
    inflow_control_operational: CandidateClaim
    demand_control_operational: CandidateClaim
    control_period: CandidateClaim
    isolation_delay: CandidateClaim
    backup_startup_delay: CandidateClaim
    attacker_command_schedule: CandidateClaim
    relevant_alerts: CandidateClaim

    def fields(self) -> dict[str, CandidateClaim]:
        return {
            "plant_identity": self.plant_identity,
            "suspected_compromised_component": self.suspected_compromised_component,
            "attacker_capability": self.attacker_capability,
            "x1": self.x1,
            "x2": self.x2,
            "p1_command": self.p1_command,
            "p1_actual_state": self.p1_actual_state,
            "backup_operational": self.backup_operational,
            "isolation_operational": self.isolation_operational,
            "inflow_control_operational": self.inflow_control_operational,
            "demand_control_operational": self.demand_control_operational,
            "control_period": self.control_period,
            "isolation_delay": self.isolation_delay,
            "backup_startup_delay": self.backup_startup_delay,
            "attacker_command_schedule": self.attacker_command_schedule,
            "relevant_alerts": self.relevant_alerts,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "incident_id": self.incident_id,
            "fields": {name: claim.as_dict() for name, claim in self.fields().items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
