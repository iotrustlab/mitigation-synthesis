"""Offline device-to-service evidence queries on the pinned Polish CHP fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ..domain_cases import RELOAD, chp_procedures


TREE = "3bbe96d73b2a450ac238f58504c8a1ff6cf91ee7"
SOURCE = "sector-energy/poland-2025-chp-recovery"
EVIDENCE = Path(__file__).with_name("chp_device_evidence.json")
NOMINAL = "siemens_compatible_openplc"
QUERIES = (
    ("Reviewed backup and benign device execution", NOMINAL, "end_to_end"),
    ("Backup absent", "backup_absent_openplc", "end_to_end"),
    ("Backup incompatible", "backup_incompatible_fixture", "end_to_end"),
    ("Backup unreviewed", "backup_unreviewed_fixture", "end_to_end"),
    ("Controller nonbootable", "wago_nonbootable_openplc", "end_to_end"),
    ("Process readiness unresolved after device execution", NOMINAL, "process_ready"),
    ("Process explicitly unready", "process_not_ready_openplc", "end_to_end"),
    ("External customer-supply mechanism unresolved", NOMINAL, "customer_supply"),
    ("Persistence unresolved after device execution", NOMINAL, "cyber_trust"),
)


def capture(case_dir):
    """Project only the evidence fields used by the experiment from pinned files."""
    import yaml  # Only needed when auditing the upstream fixture.

    bundles = {}
    for name in sorted({bundle for _, bundle, _ in QUERIES}):
        folder = case_dir / "runs" / name
        meta = json.loads((folder / "meta.json").read_text())
        raw = {key: (folder / f"{key}.json").read_bytes() for key in ("events", "runtime", "assessment")}
        scenario_path = case_dir / "scenarios" / (meta["scenario_id"] + ".yaml")
        raw["scenario"] = scenario_path.read_bytes()
        scenario = yaml.safe_load(raw["scenario"])
        digests = {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
        if digests["scenario"] != meta["scenario_sha256"]:
            raise ValueError("The scenario bytes disagree with the recorded bundle identity")
        events = json.loads(raw["events"])
        seen = events[-1]["after"]
        probe = json.loads(raw["runtime"]).get("probe")
        bundles[name] = {
            "input_sha256": digests, "profile": scenario["profile"],
            "source_label": scenario["evidence_label"], "inputs": scenario["research_inputs"],
            "events": [{"action": e["action"], "accepted": e["accepted"], "reason": e["reason"]} for e in events],
            "terminal": {key: seen[key] for key in ("device_bootable", "logic_loaded", "runtime_executing",
                         "runtime_evidence", "cyber_trust", "process_ready", "hostile_influence")},
            "assessment": json.loads(raw["assessment"]),
            "probe": {key: probe[key] for key in ("status", "compile_success", "scan_count_before",
                                                  "scan_count_after")} if isinstance(probe, dict) else None,
        }
    return {"case_tree": TREE, "case_directory": SOURCE, "bundles": bundles}


def _assess(index, question, name, data, focus="end_to_end"):
    procedure = next(p for p in chp_procedures() if p.procedure_id == RELOAD)
    inputs = data["inputs"]
    present = inputs["backup_available"]
    compatible = inputs["backup_compatible"]
    reviewed = inputs["backup_reviewed"]
    terminal = data["terminal"]
    events = {event["action"]: event for event in data["events"]}
    reset = events["reset"]["accepted"] and terminal["device_bootable"]
    validated = present and compatible and reviewed
    loaded = reset and validated and events["load_backup"]["accepted"] and terminal["logic_loaded"]
    booted = loaded and events["start_runtime"]["accepted"] and terminal["runtime_executing"]
    probe = data["probe"]
    heartbeat = bool(booted and terminal["runtime_evidence"] == "CONFIRMED" and probe
                     and probe["status"] == "CONFIRMED" and probe["compile_success"]
                     and probe["scan_count_after"] > probe["scan_count_before"] >= 0)
    ready = terminal["process_ready"]
    if ready is not None and ready is not False:
        raise ValueError("The supplied fixture supports only unknown or explicitly false process readiness")
    b1 = "ACCEPT" if terminal["device_bootable"] else "DECLINE"
    b2 = "ACCEPT" if terminal["device_bootable"] and inputs["engineering_access"] and present else "DECLINE"
    b3 = "ACCEPT" if heartbeat else "UNRESOLVED" if booted else "DECLINE"
    if not booted:
        status, detail = "REJECTED", "REJECTED"
        reason = next(e["reason"] for e in data["events"] if not e["accepted"])
    elif ready is False:
        status, detail, reason = "REJECTED", "REJECTED", "PROCESS_EXPLICITLY_NOT_READY"
    else:
        status, detail, reason = "UNKNOWN", "UNKNOWN_MODEL", "PROCESS_MODEL_AND_PERMISSIVES_ABSENT"
        if focus == "customer_supply" and procedure.initial_state["customer_supply_mechanism"] is None:
            detail, reason = "UNKNOWN_EVIDENCE", "CUSTOMER_SUPPLY_MECHANISM_UNKNOWN"
        elif focus == "cyber_trust" and terminal["cyber_trust"] == "unknown" and terminal["hostile_influence"] is None:
            detail, reason = "UNKNOWN_EVIDENCE", "PERSISTENT_INFLUENCE_UNRESOLVED"
    device = "REJECTED"
    if booted:
        device = "ESTABLISHED" if heartbeat else "SIMULATED" if terminal["runtime_evidence"] == "SIMULATED" else "UNCONFIRMED"
    return {
        "scenario": f"CHP{index}", "question": question, "procedure": procedure.procedure_id,
        "B1": b1, "B2": b2, "B3": b3, "B4": status, "result_detail": detail, "reason": reason,
        "safety": "UNKNOWN", "service": "UNKNOWN", "observation": "UNKNOWN",
        "device_recovery": device,
        "device_scope": "Bounded reset/reload lifecycle plus disposable benign logic execution",
        "process_recovery": "REJECTED" if ready is False else "UNKNOWN",
        "customer_service": "UNKNOWN", "cyber_trust": terminal["cyber_trust"].upper(),
        "evidence_bundle": name, "evidence_label": data["source_label"],
        "milestones": {"reset_completed": reset, "bootable_after_reset": terminal["device_bootable"],
                       "available_compatible_reviewed_backup": validated, "backup_loaded": loaded,
                       "runtime_started": booted, "heartbeat_confirmed": heartbeat, "process_ready": ready,
                       "physical_heat_and_power_output": None, "external_customer_supply": None},
        "published_device_lifecycle_assessment": data["assessment"]["device_recovery"],
        "published_benign_runtime_assessment": data["assessment"]["benign_runtime_execution"],
        "formal_process_model": procedure.plant_model,
    }


def reports():
    data = json.loads(EVIDENCE.read_bytes())
    rows = [_assess(i, query, name, data["bundles"][name], focus) for i, (query, name, focus) in enumerate(QUERIES)]
    return {"chp_fail_closed_results": {
        "rows": rows, "source_case_tree": TREE, "case_directory": SOURCE,
        "source_projection_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
        "scenario_queries": len(rows), "distinct_bundles": len(data["bundles"]),
        "basis": "Offline trace evidence and a bounded lifecycle decision. No physical CHP theorem.",
    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit the saved field projection against a pinned CHP case directory")
    parser.add_argument("case_directory", type=Path)
    args = parser.parse_args()
    if capture(args.case_directory) != json.loads(EVIDENCE.read_text()):
        parser.exit(1, "Evidence projection mismatch\n")
    print("CHP lifecycle projection matched all six pinned bundles.")
