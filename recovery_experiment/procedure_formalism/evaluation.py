"""Reproduce the Attleboro mutation study from model executions and proof records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .attleboro import HOLD_ID, REMOTE_ID, attleboro
from .classifier import classify
from .cost_vector import remote_trace_cost
from .formal_ir import executions
from .formal_model import build_model
from .procedure import DependencyStatus as DS, ProcedureEvent, ProcedureStatus
from .verify import verified_violation


ROOT = Path(__file__).parent
RECORD = "proof_records/verification.json"
HAND_STATE = {"utility": 0, "mts_generator": 1, "generator_ready": 1, "generator_running": 1,
              "hand_selected": 1, "remote_selected": 0}


@dataclass(frozen=True)
class Mutation:
    name: str
    candidates: tuple[str, ...] = ("remote",)
    states: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    local_ready_time: int = 0


MUTATIONS = (
    Mutation("Positive Remote"),
    Mutation("MTS on generator", states={"mts_generator": 1, "generator_running": 1}),
    Mutation("Utility restored with held reset",
             states={"reset_pending": 1, "reset_request": 1, "previous_reset": 1}),
    Mutation("Communication unavailable", dependencies={"communication": DS.UNAVAILABLE}),
    Mutation("Controller output compromised", dependencies={"plc": DS.COMPROMISED}),
    Mutation("Delivery compromised", ("remote", "hand", "hold"), dependencies={"delivery": DS.COMPROMISED}),
    Mutation("Shared VFD unavailable", ("remote", "hand"), dependencies={"vfd": DS.UNAVAILABLE}),
    Mutation("Flow blocked", states={"flow_blocked": 1}),
    Mutation("Final observation stale", states={"observation_fresh": 0}),
    Mutation("Observer compromised", dependencies={"observer": DS.COMPROMISED}),
    Mutation("Local operator absent", ("hand",), HAND_STATE, {"local_operator": DS.UNAVAILABLE}),
    Mutation("Local operator late", ("hand",), HAND_STATE, local_ready_time=4),
    Mutation("Shared trip active", ("remote", "hand"), states={"trip": 1}),
    Mutation("Delivery integrity unknown", dependencies={"delivery": DS.UNKNOWN}),
    Mutation("No assured positive service", ("remote", "hand", "hold"),
             dependencies={"communication": DS.UNAVAILABLE, "local_operator": DS.UNAVAILABLE}),
)


def _availability(nodes):
    states = {node.status for node in nodes}
    if DS.UNAVAILABLE in states:
        return "DECLINE"
    if DS.UNKNOWN in states:
        return "UNRESOLVED"
    return "ACCEPT"


def baselines(procedure):
    if procedure.procedure_id == HOLD_ID:
        return dict.fromkeys(("B1", "B2", "B3"), "INAPPLICABLE")
    nodes = procedure.required_dependencies
    availability = _availability([nodes[procedure.actuator]])
    reachability = _availability(nodes.values())
    controller = "INAPPLICABLE"
    if procedure.procedure_id == REMOTE_ID:
        # Project the actual model at PLC output so downstream failures
        # cannot remove a controller execution or influence the baseline.
        upstream = (procedure.actor, procedure.interface, procedure.communication_path,
                    procedure.controller, "trip_path")
        model = build_model(procedure)
        outputs = {end["output"] for end in executions(model.stages[:2], model.initial)}
        if outputs == {1}:
            controller = "ACCEPT"
        elif any(nodes[key].status == DS.UNKNOWN for key in upstream):
            controller = "UNRESOLVED"
        else:
            controller = "DECLINE"
    return {"B1": availability, "B2": reachability, "B3": controller}


def _events(state):
    if state is None:
        return None
    evidence = state["fresh"] == 1 and Fraction(state["observed"]) >= 5 and Fraction(state["observedPressure"]) <= 90
    return {
        ProcedureEvent.REQUEST_ISSUED.value: bool(state["request"]),
        ProcedureEvent.CONTROLLER_ACCEPTED.value: bool(state["accepted"]),
        ProcedureEvent.CONTROLLER_OUTPUT_SET.value: bool(state["output"]),
        ProcedureEvent.ACTUATION_DELIVERED.value: bool(state["delivered"]),
        ProcedureEvent.ACTUATOR_RESPONDED.value: bool(state["run"]),
        ProcedureEvent.PHYSICAL_SERVICE_PRESENT.value: bool(state["physical"]),
        ProcedureEvent.SERVICE_OBSERVED.value: evidence,
        ProcedureEvent.SERVICE_ESTABLISHED.value: bool(state["established"]),
    }


def report(procedure):
    finding = classify(procedure)
    uncertainty = [node.node_id for node in procedure.required_dependencies.values()
                   if node.status == DS.UNKNOWN]
    if finding.result == ProcedureStatus.UNKNOWN:
        uncertainty.append(finding.basis)
    positive = finding.result == ProcedureStatus.PROVED
    proof_kind = "universal and nonvacuity" if positive else None
    if not positive and finding.model_hash and verified_violation(build_model(procedure)):
        proof_kind = "possible violation under unknown integrity" if uncertainty else "reachable violation"
    return {
        "procedure_id": procedure.procedure_id,
        "initial_state": dict(procedure.initial_state),
        "actor_ready_tick": procedure.actor_ready_time,
        "deadline": procedure.deadline,
        "horizon": procedure.horizon,
        "tick_seconds": 0.1,
        "dependency_states": {k: n.status.value for k, n in procedure.required_dependencies.items()},
        "dependency_state_evidence": {k: n.source_status.value for k, n in procedure.required_dependencies.items()},
        "evidence_status_by_field": {k: e.value for k, e in procedure.evidence_status_by_field.items()},
        "first_stage": finding.stage, "result": finding.result.value,
        "reason": [r.value for r in finding.reasons], "basis": finding.basis,
        "formal_model_sha256": finding.model_hash,
        "proof_record": RECORD if proof_kind else None, "proof_kind": proof_kind,
        "safety_status": finding.safety, "physical_service_status": finding.physical_service,
        "credible_service_status": finding.credible_evidence, "execution_witness": finding.witness,
        "events_on_witness": _events(finding.witness),
        "cost_vector": remote_trace_cost().as_dict() if positive and procedure.procedure_id == REMOTE_ID else None,
        "unresolved_assumptions": uncertainty,
        "scope": "Bounded research fixture. Availability, actor readiness, model parameters and observation integrity are scenario assumptions.",
    }


def evaluate():
    matrix = []
    comparison = []
    for index, mutation in enumerate(MUTATIONS):
        mutation_id = f"M{index}"
        procedures = attleboro(mutation.dependencies, mutation.states, mutation.local_ready_time)
        rows = []
        for key in mutation.candidates:
            proc = procedures[key]
            row = report(proc)
            rows.append(row)
            comparison.append({"mutation": mutation_id, "procedure": key, "procedure_id": proc.procedure_id,
                               **baselines(proc), "B4": row["result"],
                               "first_stage": row["first_stage"], "reason": row["reason"]})
        scenario = {"mutation": mutation_id, "name": mutation.name, "assessments": rows}
        if set(mutation.candidates) == set(procedures):
            scenario["selection"] = ("ASSURED_RECOVERY" if any(r["result"] == "PROVED" for r in rows)
                                     else "NO_ASSURED_RECOVERY")
        matrix.append(scenario)
    return {"attleboro_positive": matrix[0]["assessments"][0],
            "attleboro_mutation_matrix": matrix, "baseline_comparison": comparison}


def proof_summary():
    records = json.loads((ROOT / RECORD).read_text())
    historical = json.loads((ROOT / "proof_records" / "historical_regression.json").read_text())
    summary = []
    for digest, entry in sorted(records["models"].items(), key=lambda item: int(item[1]["case"][1:])):
        index = int(entry["case"][1:])
        spec = MUTATIONS[index]
        proc = attleboro(spec.dependencies, spec.states)["remote"]
        model = build_model(proc)
        accepted = verified_violation(model) if index else classify(proc).result == ProcedureStatus.PROVED
        summary.append({
            "mutation": entry["case"], "procedure_id": proc.procedure_id,
            "formal_model_sha256": digest, "archive_sha256": entry["archive_sha256"],
            "proof_obligation_kind": entry["kind"],
            "proof_record": RECORD, "validated": accepted and model.sha256 == digest,
            "obligations": entry["obligations"], "wall_seconds": entry["wall_seconds"],
        })
    return {
        "generated_models": summary, "historical_archives": historical["archives"],
        "historical_record": "proof_records/historical_regression.json",
        "command": records["command"], "cache": records["cache"], "java": records["java"],
        "z3": records["z3"], "jar_sha256": records["jar_sha256"],
        "scope": "A verified violation diamond is a negative witness. An M13 witness depends on the unresolved integrity state.",
    }


def write_results(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {**evaluate(), "proof_summary": proof_summary()}
    for stem, result in outputs.items():
        (directory / f"{stem}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    write_results(ROOT / "results")
