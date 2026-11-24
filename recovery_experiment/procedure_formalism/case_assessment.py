"""Regenerate the representation-only assessments and bounded trace cost report."""

from __future__ import annotations

import json
from pathlib import Path

from .attleboro import HAND_ID, REMOTE_ID, attleboro
from .cost_vector import Comparison, TRACE_SAMPLES, fixture_candidate, remote_trace_cost
from .domain_cases import (
    CHP_HOLD, HYDRO_HOLD, LOCAL_AUTO, LOCAL_MANUAL, NO_ASSURANCE, RELOAD, REMOTE_AUTO, RESET,
    chp_procedures, merwin_procedures,
)
from .procedure import EvidenceStatus, ProcedureStatus


RESULTS = Path(__file__).with_name("results")

MERWIN_GAPS = (
    "No bounded formal model joins actor authority, synchronization, breaker contact and same-row generation.",
    "Actor readiness, a service deadline and observer freshness are unspecified.",
    "Representative dynamics lack site-specific unit parameters and safety bounds.",
)
CHP_GAPS = (
    "No physical CHP model, restart permissives or process-readiness observation.",
    "Backup assurance, device trust and the means of customer supply are unresolved.",
    "No bounded service deadline or process observation contract.",
)
MERWIN_WITNESSES = {
    LOCAL_MANUAL: ("runs/local_manual", "Manual synchronization and close followed by same-row generation."),
    LOCAL_AUTO: ("runs/local_auto", "Contact at 107.615039 s and sustained same-row generation at 108.127814 s."),
    REMOTE_AUTO: ("runs/remote_auto", "HCC start followed by representative contact and same-row generation."),
}
CHP_WITNESSES = {
    RESET: ("runs/siemens_compatible_openplc and runs/wago_nonbootable_openplc",
            "Simulated Siemens-like reset and loss of device logs. The WAGO-like device remained unbootable."),
    RELOAD: ("runs/siemens_compatible_openplc",
             "Simulated reviewed reload followed by two increasing counter reads on a disposable runtime."),
}


def schema_assessment(procedures, case_tree, gaps, witnesses):
    """Store the shared node declarations once. Each procedure retains its exact bindings."""
    result = {"source_case_tree": case_tree, "dependency_catalog": {}, "procedures": []}
    for procedure in procedures:
        schema = procedure.as_dict()
        dependencies = schema.pop("required_dependencies")
        result["dependency_catalog"].update(dependencies)
        schema["required_dependencies"] = list(dependencies)
        witness = witnesses.get(procedure.procedure_id)
        row = {
            "procedure_id": procedure.procedure_id, "schema": schema,
            "dependency_states": {key: node["status"] for key, node in dependencies.items()},
            "result": ProcedureStatus.UNKNOWN.value,
            "reason": "FORMAL_PROOF_UNRESOLVED" if procedure.plant_model else "PLANT_MODEL_MISSING",
            "formal_model_sha256": None, "proof_record": None, "cost_vector": None,
            "safety_status": "UNKNOWN", "service_status": "UNKNOWN", "unresolved_assumptions": gaps,
            "trace_witness": None if witness is None else {
                "bundle": witness[0], "observation": witness[1], "evidence_status": EvidenceStatus.OBSERVED_IN_TRACE.value,
            },
        }
        if procedure.procedure_id in (HYDRO_HOLD, CHP_HOLD):
            row["service_status"] = "NO_POSITIVE_SERVICE_CLAIM"
            row["reason"] = "EVIDENCE_INSUFFICIENT"
        if procedure.case_id == "polish-chp":
            row["device_logic_execution"] = "OBSERVED_ON_DISPOSABLE_RUNTIME" if procedure.procedure_id == RELOAD else "NOT_ESTABLISHED"
            row["process_readiness"] = row["physical_chp_output"] = row["customer_service"] = "UNKNOWN"
            if procedure.procedure_id == NO_ASSURANCE:
                row["reason"] = "EVIDENCE_INSUFFICIENT"
                row["portfolio_outcome"] = "NO_ASSURED_PROCESS_RECOVERY"
        result["procedures"].append(row)
    return result


def cost_report(positive):
    if positive["procedure_id"] != REMOTE_ID:
        raise ValueError("The cost trace belongs to the nominal Attleboro Remote fixture")
    from .evaluation import report

    snapshot = attleboro()
    nominal = snapshot["remote"]
    authoritative = report(nominal)
    if positive != authoritative:
        raise ValueError("Assessment is stale or belongs to a different procedure, model or context")
    source = json.loads(TRACE_SAMPLES.read_text())
    if positive["tick_seconds"] != source["scan_period_s"] or positive["horizon"] != len(source["rows"]):
        raise ValueError("Proof and trace have different time bases or horizons")
    measured = remote_trace_cost()
    admitted = fixture_candidate(nominal, snapshot, source["scan_period_s"], measured)
    status = admitted.status
    vector = measured.as_dict()
    del source["rows"]
    return {
        "procedure_id": REMOTE_ID, "result": status.value, "formal_model_sha256": positive["formal_model_sha256"],
        "proof_record": positive["proof_record"], "source": source, "cost_vector": vector,
        "eligible_for_cost_comparison": status == ProcedureStatus.PROVED and admitted.provides_required_service,
        "initial_state_id": admitted.context.initial_state_id, "environment_id": admitted.context.environment_id,
        "service_definition": admitted.context.service_contract, "safety_definition": admitted.context.safety_contract,
        "deadline_s": admitted.context.deadline_s, "horizon_s": admitted.context.horizon_s,
        "restoration_delay_origin": "Timestamp of first recorded row (tick 0), distinct from the three completed scans.",
        "trace_scope": "First three synthetic scans. Each row represents one 0.1 s interval for integration.",
        "comparison": {
            "procedures": [REMOTE_ID, HAND_ID], "result": Comparison.DIFFERENT_CONTEXT.value,
            "reason": "Exclusive selector positions exclude simultaneous admissibility under one fixed mode. "
                      "No end-to-end Local Hand service proof has been supplied in this study.",
        },
    }


def schema_reports():
    return {
        "merwin_schema_assessment.json": schema_assessment(
            merwin_procedures(), "e825cc0af6459044a5aef1ac84d6845ac4756b1e", MERWIN_GAPS, MERWIN_WITNESSES,
        ),
        "chp_schema_assessment.json": schema_assessment(
            chp_procedures(), "3bbe96d73b2a450ac238f58504c8a1ff6cf91ee7", CHP_GAPS, CHP_WITNESSES,
        ),
    }


def generate(results_dir: Path = RESULTS):
    positive = json.loads((results_dir / "attleboro_positive.json").read_text())
    outputs = {**schema_reports(), "cost_vectors.json": cost_report(positive)}
    for name, report in outputs.items():
        (results_dir / name).write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    generate()
