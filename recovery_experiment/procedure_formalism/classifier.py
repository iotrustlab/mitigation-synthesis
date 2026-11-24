"""Classify a bounded positive-service request from its procedure and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from .attleboro import HAND_ID, HOLD_ID, REMOTE_ID
from .formal_ir import expr
from .formal_model import POST, build_model
from .procedure import DependencyStatus, EvidenceStatus, ProcedureStatus, RecoveryProcedure
from .verify import verified


class Reason(str, Enum):
    ACTOR_UNAVAILABLE = "ACTOR_UNAVAILABLE"
    ACTOR_LATE = "ACTOR_LATE"
    AUTHORITY_FAILED = "AUTHORITY_FAILED"
    INTERFACE_UNAVAILABLE = "INTERFACE_UNAVAILABLE"
    COMMUNICATION_UNAVAILABLE = "COMMUNICATION_UNAVAILABLE"
    COMMUNICATION_COMPROMISED = "COMMUNICATION_COMPROMISED"
    CONTROLLER_COMPROMISED = "CONTROLLER_COMPROMISED"
    OUTPUT_STAGE_COMPROMISED = "OUTPUT_STAGE_COMPROMISED"
    ACTUATOR_UNAVAILABLE = "ACTUATOR_UNAVAILABLE"
    POWER_UNAVAILABLE = "POWER_UNAVAILABLE"
    TRIP_ACTIVE = "TRIP_ACTIVE"
    PLANT_MODEL_MISSING = "PLANT_MODEL_MISSING"
    OBSERVER_COMPROMISED = "OBSERVER_COMPROMISED"
    OBSERVATION_STALE = "OBSERVATION_STALE"
    SERVICE_NOT_ESTABLISHED = "SERVICE_NOT_ESTABLISHED"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    FORMAL_PROOF_UNRESOLVED = "FORMAL_PROOF_UNRESOLVED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


# Order follows the request-to-service path when several prerequisites fail.
FAILURE_STAGES = {
    "remote_operator": ("actor", Reason.ACTOR_UNAVAILABLE),
    "local_operator": ("actor", Reason.ACTOR_UNAVAILABLE),
    "ows": ("interface", Reason.INTERFACE_UNAVAILABLE),
    "hand_panel": ("interface", Reason.INTERFACE_UNAVAILABLE),
    "communication": ("communication", Reason.COMMUNICATION_UNAVAILABLE),
    "plc": ("controller", Reason.DEPENDENCY_UNAVAILABLE),
    "delivery": ("delivery", Reason.DEPENDENCY_UNAVAILABLE),
    "trip_path": ("protection", Reason.DEPENDENCY_UNAVAILABLE),
    "motor_power": ("power", Reason.POWER_UNAVAILABLE),
    "vfd": ("actuator", Reason.ACTUATOR_UNAVAILABLE),
    "pump": ("actuator", Reason.ACTUATOR_UNAVAILABLE),
    "water_path": ("plant", Reason.DEPENDENCY_UNAVAILABLE),
    "observer": ("observation", Reason.DEPENDENCY_UNAVAILABLE),
}

COMPROMISE_REASONS = {
    "communication": ("communication", Reason.COMMUNICATION_COMPROMISED),
    "plc": ("controller", Reason.CONTROLLER_COMPROMISED),
    "delivery": ("delivery", Reason.OUTPUT_STAGE_COMPROMISED),
    "observer": ("observation", Reason.OBSERVER_COMPROMISED),
}


@dataclass(frozen=True)
class Assessment:
    result: ProcedureStatus
    stage: str
    reasons: tuple[Reason, ...]
    basis: str
    model_hash: str | None = None
    safety: str = "UNASSESSED"
    physical_service: str = "UNASSESSED"
    credible_evidence: str = "UNASSESSED"
    witness: dict | None = None


def _unavailable(proc):
    nodes = proc.required_dependencies
    for key in dict.fromkeys((*FAILURE_STAGES, *nodes)):
        if key in nodes and nodes[key].status == DependencyStatus.UNAVAILABLE:
            stage, reason = FAILURE_STAGES.get(key, ("dependency", Reason.DEPENDENCY_UNAVAILABLE))
            return stage, reason, key
    return None


def _authority_denied(proc):
    s = proc.initial_state
    if not s["authorized"]:
        return True
    if proc.procedure_id == REMOTE_ID:
        pending = s["reset_pending"] and not (s["reset_request"] and not s["previous_reset"])
        return (not s["utility"] or s["mts_generator"] or s["generator_running"] or
                pending or not s["remote_selected"] or s["hand_selected"])
    return not s["hand_selected"] or s["remote_selected"]


def _failure_reason(proc):
    for key, (stage, reason) in COMPROMISE_REASONS.items():
        node = proc.required_dependencies.get(key)
        if node and node.status == DependencyStatus.COMPROMISED:
            return stage, reason
    if not proc.initial_state["observation_fresh"]:
        return "observation", Reason.OBSERVATION_STALE
    return "plant", Reason.SERVICE_NOT_ESTABLISHED


def _snapshot(execution):
    # Preserve rational endpoints exactly in machine-readable witnesses.
    return {k: (int(v) if v.denominator == 1 else str(v)) if isinstance(v, Fraction) else v
            for k, v in execution.items()}


def classify(proc: RecoveryProcedure) -> Assessment:
    rejected, unknown = ProcedureStatus.REJECTED, ProcedureStatus.UNKNOWN
    if proc.procedure_id == HOLD_ID:
        return Assessment(rejected, "service contract", (Reason.SERVICE_NOT_ESTABLISHED,),
                          "Hold supplies no positive water-service contract.")
    if proc.procedure_id not in (REMOTE_ID, HAND_ID):
        reason = Reason.PLANT_MODEL_MISSING if proc.plant_model is None else Reason.FORMAL_PROOF_UNRESOLVED
        return Assessment(unknown, "model", (reason,), "No end-to-end proof profile for this procedure.")
    gap = _unavailable(proc)
    model = None
    model_error = "Missing or unsupported plant model."
    if proc.plant_model is not None:
        try:
            model = build_model(proc)
        except (KeyError, ValueError, NotImplementedError) as exc:
            model_error = str(exc)
    digest = model.sha256 if model is not None else None
    if gap:
        stage, reason, key = gap
        return Assessment(rejected, stage, (reason,), f"Required dependency {key} is unavailable.", digest)
    if proc.plant_model is None:
        return Assessment(unknown, "plant", (Reason.PLANT_MODEL_MISSING,), model_error)
    hard_unknown = [key for key in ("authority_requirements", "controller_transition",
                    "plant_model", "observation_relation", "freshness_requirement",
                    "safety_definition", "service_definition", "initial_state", "deadline")
                    if proc.evidence_status_by_field[key] == EvidenceStatus.UNKNOWN]
    hard_unknown.extend(n.node_id for n in proc.required_dependencies.values()
                        if n.source_status == EvidenceStatus.UNKNOWN)
    if hard_unknown or None in (proc.deadline, proc.horizon, proc.actor_ready_time):
        return Assessment(unknown, "evidence", (Reason.EVIDENCE_INSUFFICIENT,),
                          "Unresolved theorem inputs: " + ", ".join(hard_unknown or ["timing"]))
    if model is None:
        return Assessment(unknown, "model", (Reason.FORMAL_PROOF_UNRESOLVED,), model_error)
    if proc.actor_ready_time > proc.deadline:
        return Assessment(rejected, "actor", (Reason.ACTOR_LATE, Reason.DEADLINE_MISSED),
                          "Actor readiness is after the service deadline.", digest)
    if proc.initial_state["trip"] == 1:
        return Assessment(rejected, "protection", (Reason.TRIP_ACTIVE,),
                          "Shared protection trip excludes this start procedure.", digest)
    if _authority_denied(proc):
        return Assessment(rejected, "authority", (Reason.AUTHORITY_FAILED,),
                          "The declared actor or mode/power/reset guard excludes this start.", digest)

    witness = None
    unsafe = missing_flow = missing_evidence = False
    first_execution = None
    for state in model.executions():
        if first_execution is None:
            first_execution = state
        unsafe |= not state["safe"]
        missing_flow |= not state["physical"]
        missing_evidence |= not state["established"]
        if witness is None and not expr(POST, state):
            witness = _snapshot(state)

    if first_execution is not None and witness is None and verified(model):
        return Assessment(ProcedureStatus.PROVED, "service established", (),
                          "All bound universal, stage and progress obligations passed.", digest,
                          "PROVED", "PROVED", "PROVED", _snapshot(first_execution))
    uncertain = [n.node_id for n in proc.required_dependencies.values()
                 if n.status == DependencyStatus.UNKNOWN]
    if uncertain:
        return Assessment(unknown, "dependency evidence", (Reason.EVIDENCE_INSUFFICIENT,),
                          "Actual dependency state unresolved: " + ", ".join(uncertain), digest,
                          witness=witness)
    if witness is not None:
        stage, reason = _failure_reason(proc)
        if Fraction(witness["t"]) > proc.deadline:
            stage, reason = "deadline", Reason.DEADLINE_MISSED
        return Assessment(rejected, stage, (reason,),
                          "A concrete execution in the declared fixture violates the service contract.",
                          digest, "VIOLATED" if unsafe else "HOLDS_IN_ENUMERATION",
                          "VIOLATED" if missing_flow else "HOLDS_IN_ENUMERATION",
                          "VIOLATED" if missing_evidence else "HOLDS_IN_ENUMERATION", witness)
    return Assessment(unknown, "proof", (Reason.FORMAL_PROOF_UNRESOLVED,),
                      "No matching closed proof and reachable service witness.", digest)
