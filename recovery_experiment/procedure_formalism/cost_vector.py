"""Post-admissibility cost comparisons on a common bounded service contract."""

from __future__ import annotations

import hashlib
import json
import string
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from enum import Enum
from fractions import Fraction
from math import isclose, isfinite
from pathlib import Path
from typing import Mapping

from .procedure import EvidenceStatus, ProcedureStatus, RecoveryProcedure


@dataclass(frozen=True)
class CostComponent:
    value: float | None
    unit: str
    provenance: str
    measurement_horizon_s: float
    evidence_status: EvidenceStatus

    def __post_init__(self) -> None:
        if not self.unit.strip() or not self.provenance.strip():
            raise ValueError("Cost components require a unit and provenance")
        if not isfinite(self.measurement_horizon_s) or self.measurement_horizon_s <= 0:
            raise ValueError("Measurement horizon must be finite and positive")
        if not isinstance(self.evidence_status, EvidenceStatus):
            raise ValueError("Expected an evidence status")
        if (self.value is None) != (self.evidence_status == EvidenceStatus.UNKNOWN):
            raise ValueError("Unmeasured values must carry UNKNOWN evidence")
        if self.value is not None and (not isfinite(self.value) or self.value < 0):
            raise ValueError("Cost values must be finite and nonnegative")


@dataclass(frozen=True)
class RecoveryCostVector:
    service_deficit: CostComponent
    restoration_delay: CostComponent
    human_effort: CostComponent
    intervention_count: CostComponent
    resource_use: CostComponent
    evidence_gap_duration: CostComponent

    def as_dict(self) -> dict:
        return asdict(self)


COMPONENT_NAMES = tuple(field.name for field in fields(RecoveryCostVector))


@dataclass(frozen=True)
class CostContext:
    """IDs describe a common scenario, including exogenous dependency assumptions."""

    initial_state_id: str
    environment_id: str
    service_contract: str
    safety_contract: str
    deadline_s: float
    horizon_s: float

    def __post_init__(self) -> None:
        if not all(text.strip() for text in (
            self.initial_state_id, self.environment_id, self.service_contract, self.safety_contract
        )):
            raise ValueError("Comparison requires identified context and contracts")
        if not (isfinite(self.horizon_s) and 0 < self.deadline_s <= self.horizon_s):
            raise ValueError("Expected a positive deadline within a finite horizon")


@dataclass(frozen=True)
class CostCandidate:
    procedure_id: str
    status: ProcedureStatus
    context: CostContext
    vector: RecoveryCostVector
    provides_required_service: bool
    formal_model_sha256: str | None

    def __post_init__(self) -> None:
        if not self.procedure_id or not isinstance(self.status, ProcedureStatus):
            raise ValueError("Expected procedure identity and classification")
        if self.status == ProcedureStatus.PROVED and (
            not isinstance(self.formal_model_sha256, str) or len(self.formal_model_sha256) != 64
            or any(c not in string.hexdigits for c in self.formal_model_sha256)
        ):
            raise ValueError("A proved cost candidate must identify its verified formal model")
        if type(self.provides_required_service) is not bool:
            raise ValueError("Required service evidence must be explicit")
        if any(not isclose(getattr(self.vector, name).measurement_horizon_s,
                           self.context.horizon_s, rel_tol=1e-12, abs_tol=0.0)
               for name in COMPONENT_NAMES):
            raise ValueError("Measurement horizons must match the procedure context")


def fixture_candidate(procedure: RecoveryProcedure, snapshot: Mapping[str, RecoveryProcedure],
                      tick_seconds: float, vector: RecoveryCostVector) -> CostCandidate:
    """Join measured cost to this procedure's checked proof in a shared incident snapshot."""
    from .classifier import classify

    if not any(proc is procedure for proc in snapshot.values()):
        raise ValueError("Procedure is outside this incident snapshot")
    if procedure.deadline is None or procedure.horizon is None or tick_seconds <= 0:
        raise ValueError("Unknown or invalid procedure time contract")
    nodes, actors = {}, {}
    for entry in snapshot.values():
        if entry.case_id != procedure.case_id or entry.initial_state != procedure.initial_state:
            raise ValueError("Mixed case or initial state in incident snapshot")
        for key, node in entry.required_dependencies.items():
            if key in nodes and nodes[key] != node:
                raise ValueError("Inconsistent shared dependency in snapshot")
            nodes[key] = node
        if entry.actor:
            if entry.actor in actors and actors[entry.actor] != entry.actor_ready_time:
                raise ValueError("Inconsistent actor readiness in snapshot")
            actors[entry.actor] = entry.actor_ready_time

    def digest(data):
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    environment = {
        "case": procedure.case_id, "actors": actors, "tick_seconds": tick_seconds,
        "resources": {key: asdict(node) for key, node in nodes.items()},
    }
    context = CostContext(
        digest(dict(procedure.initial_state)), digest(environment), procedure.service_definition,
        procedure.safety_definition, round(procedure.deadline * tick_seconds, 12),
        round(procedure.horizon * tick_seconds, 12),
    )
    proof = classify(procedure)
    service = proof.physical_service == "PROVED" and proof.credible_evidence == "PROVED"
    return CostCandidate(procedure.procedure_id, proof.result, context, vector, service, proof.model_hash)


@dataclass(frozen=True)
class Weight:
    """Apply weight * (value / reference_value), a dimensionless preference."""

    weight: float
    reference_value: float
    reference_unit: str

    def __post_init__(self) -> None:
        if not isfinite(self.weight) or self.weight <= 0:
            raise ValueError("Declared weights must be finite and positive")
        if not self.reference_unit.strip() or not isfinite(self.reference_value) or self.reference_value <= 0:
            raise ValueError("Expected a positive finite reference value and unit")


class Comparison(str, Enum):
    NOT_ADMISSIBLE = "NOT_ADMISSIBLE"
    DIFFERENT_CONTEXT = "NOT_COMPARABLE_UNDER_COMMON_CONTEXT"
    INCOMPLETE = "INSUFFICIENT_MEASUREMENTS"
    LEFT = "LEFT_PREFERRED"
    RIGHT = "RIGHT_PREFERRED"
    TIE = "EQUAL"
    TRADEOFF = "PARETO_INCOMPARABLE"


def _eligibility(left: CostCandidate, right: CostCandidate) -> Comparison | None:
    if left.context != right.context:
        return Comparison.DIFFERENT_CONTEXT
    if left.status != ProcedureStatus.PROVED or right.status != ProcedureStatus.PROVED:
        return Comparison.NOT_ADMISSIBLE
    if not (left.provides_required_service and right.provides_required_service):
        return Comparison.NOT_ADMISSIBLE
    return None


def pareto_compare(left: CostCandidate, right: CostCandidate) -> Comparison:
    """All six components are minimized. One strict improvement gives dominance."""
    blocked = _eligibility(left, right)
    if blocked:
        return blocked
    lower = higher = False
    for name in COMPONENT_NAMES:
        a, b = getattr(left.vector, name), getattr(right.vector, name)
        if a.unit != b.unit:
            raise ValueError(f"Incompatible units for {name}")
        if a.value is None or b.value is None:
            return Comparison.INCOMPLETE
        lower |= a.value < b.value
        higher |= a.value > b.value
    if lower and higher:
        return Comparison.TRADEOFF
    if lower:
        return Comparison.LEFT
    if higher:
        return Comparison.RIGHT
    return Comparison.TIE


def weighted_compare(left: CostCandidate, right: CostCandidate,
                     preferences: Mapping[str, Weight]) -> Comparison:
    """Compare only the explicitly weighted dimensions after unit normalization."""
    blocked = _eligibility(left, right)
    if blocked:
        return blocked
    if not preferences or set(preferences).difference(COMPONENT_NAMES):
        raise ValueError("Declare a preference for each selected cost dimension")
    difference = Fraction(0)
    for name, scale in sorted(preferences.items()):
        a, b = getattr(left.vector, name), getattr(right.vector, name)
        if a.unit != scale.reference_unit or b.unit != scale.reference_unit:
            raise ValueError(f"Reference unit disagrees with measurement for {name}")
        if a.value is None or b.value is None:
            return Comparison.INCOMPLETE
        delta = Fraction(str(a.value)) - Fraction(str(b.value))
        difference += Fraction(str(scale.weight)) * delta / Fraction(str(scale.reference_value))
    if difference < 0:
        return Comparison.LEFT
    if difference > 0:
        return Comparison.RIGHT
    return Comparison.TIE


TRACE_SAMPLES = Path(__file__).with_name("fixtures") / "nominal_remote_cost_samples.json"


def remote_trace_cost() -> RecoveryCostVector:
    """Measure the first three published synthetic scans using their recorded tags."""
    trace = json.loads(TRACE_SAMPLES.read_text())
    rows = trace["rows"]
    dt = trace["scan_period_s"]
    horizon = round(len(rows) * dt, 12)
    target = trace["service_min_flow_L_s"]
    deficit = sum(max(0.0, target - float(row["ATT_Actual_Flow"])) * dt / 1000 for row in rows)
    def timestamp(row):
        return datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))

    first_credited = next((row for row in rows if row["ATT_Service_Established"] == "1"), None)
    latency = (timestamp(first_credited) - timestamp(rows[0])).total_seconds() if first_credited else None
    starts = sum(a["ATT_Run_FB"] == "0" and b["ATT_Run_FB"] == "1" for a, b in zip(rows, rows[1:]))
    evidence_gap = sum(dt for r in rows if r["ATT_Actual_Service"] == "1" and r["ATT_Service_Established"] == "0")

    def measurement(value: float | None, unit: str, basis: str) -> CostComponent:
        status = EvidenceStatus.UNKNOWN if value is None else EvidenceStatus.OBSERVED_IN_TRACE
        return CostComponent(value, unit, "nominal_remote ticks 0–2. " + basis, horizon, status)

    return RecoveryCostVector(
        service_deficit=measurement(round(deficit, 12), "m3", "Sum of fixture flow shortfall below 5 L/s times the scan period."),
        restoration_delay=measurement(latency, "s", "Elapsed between first row and first credited-service row."),
        human_effort=measurement(None, "person*h", "Active work duration is unmeasured."),
        intervention_count=measurement(starts, "count", "Drive starts counted by rising run-feedback edges."),
        resource_use=measurement(None, "kWh", "Motor energy use is unmeasured."),
        evidence_gap_duration=measurement(evidence_gap, "s", "Credited-service tag false while physical service tag true."),
    )
