"""Regenerate the paper tables and JSON using the checked measurement records."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median

from . import chp, cost, hand, merwin, scalability
from .proofs import BASE, EVIDENCE, RESULTS, ROOT, digest, object_hash, read_record
from ..attleboro import attleboro
from ..formal_model import build_model
from ..verify import verified

OLD = ROOT.parent / "results"
DOCS = ROOT.parent / "docs"
MODES = ("B1", "B2", "B3")
BASELINE = OLD / "milestone2_baseline_reproduction.json"


def load(path):
    return json.loads(path.read_text())


def dump(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def remote_rows():
    indexed = {(group["mutation"], row["procedure_id"]): row for group in load(OLD / "attleboro_mutation_matrix.json")
               for row in group["assessments"]}
    rows = []
    for comparison in load(OLD / "baseline_comparison.json"):
        scenario, procedure = comparison["mutation"], comparison["procedure_id"]
        r = indexed[scenario, procedure]
        rows.append(dict(scenario=scenario, procedure=procedure, **{k: comparison[k] for k in ("B1","B2","B3","B4")},
                         safety=r["safety_status"], service=r["physical_service_status"], observation=r["credible_service_status"],
                         reason=r["basis"], first_stage=r["first_stage"]))
    return rows


def combine(families):
    rows = []
    for family, data in families.items():
        for row in data:
            labels = {key: row[key] for key in (*MODES, "B4")}
            if set(labels[k] for k in MODES) - {"ACCEPT","DECLINE","INAPPLICABLE","UNRESOLVED"}:
                raise ValueError(f"Unknown weak baseline {labels}")
            final = labels["B4"]
            if final not in {"PROVED","REJECTED","UNKNOWN"}:
                raise ValueError(f"Unknown full classification {final}")
            first = next((key for key in MODES if labels[key] in ("DECLINE","UNRESOLVED")),
                         "B4" if final != "PROVED" else None)
            rows.append(dict(family=family, scenario=row["scenario"], procedure=row["procedure"], **labels,
                             first_abstraction_detecting_problem=first, final_classification=final,
                             safety=row["safety"], service=row["service"], observation=row["observation"],
                             reason=row["reason"]))
    return rows


def counts(rows):
    final = Counter(r["B4"] for r in rows)
    return {
        "scenarios": len({(r["family"],r["scenario"]) for r in rows}), "procedure_assessments": len(rows),
        "retained": {mode: sum(r[mode] == "ACCEPT" for r in rows) for mode in MODES},
        "retained_without_end_to_end_assurance": {
            mode: sum(r[mode] == "ACCEPT" and r["B4"] != "PROVED" for r in rows) for mode in MODES},
        "retained_by_any_weaker_without_assurance": sum(
            any(r[k] == "ACCEPT" for k in MODES) and r["B4"] != "PROVED" for r in rows),
        "end_to_end": {s: final[s] for s in ("PROVED","REJECTED","UNKNOWN")},
    }


def nominal_metrics(label, record):
    obligations = record["obligations"]
    def duration(*keys):
        return sum(obligations[k].get("duration_ms", 0) for k in keys if k in obligations)
    return {
        "procedure": label, "archive_sha256": record["archive_sha256"], "obligations": len(obligations),
        "proved": sum(o["status"] == "PROVED" for o in obligations.values()),
        "unresolved": sum(o["status"] != "PROVED" for o in obligations.values()),
        "proof_wall_seconds": record["wall_seconds"], "archive_bytes": record["archive_bytes"],
        "archive_render_ns": record["model_generation_ns"], "plant_state_count":record["plant_states"],
        "dependency_controlled_signals":record["dependencies"], "horizon":record["horizon"],
        "tactic_ms": {"controller": duration("controller","stage_controller","actor_controller"),
                      "plant": duration("plant","stage_plant"), "composition":duration("end_to_end","composition")},
        "obligations_detail": obligations,
    }


def measurements(outputs, profiles, baseline):
    remote = build_model(attleboro()["remote"])
    if not verified(remote):
        raise ValueError("Canonical Remote profile is unresolved")
    observed = baseline["new_obligations"]["M0"]
    if observed["archive_sha256"] != remote.sha256:
        raise ValueError("Replayed Remote archive differs from the current model")
    r = dict(observed, archive_bytes=baseline["remote_archive_bytes"], model_generation_ns=baseline["remote_archive_render_ns"],
             dependencies=len(remote.procedure.required_dependencies), plant_states=3, horizon="3 x 100 ms")
    cases = [(remote.procedure.procedure_id,r)]
    nominal_ids = [hand.HAND_PROFILE, outputs["merwin_proof_summary"]["profile"]]
    selected = outputs["common_context_cost_proofs"]["nominal_expressions"]
    labels = {details["profile"]:name for name, details in selected.items()}
    nominal_ids.extend(labels)
    for profile, record in profiles:
        if profile.name in nominal_ids:
            cases.append((labels.get(profile.name,profile.name), record))
    if len(cases) != 5:
        raise ValueError("Expected five deep proof cases")
    rows = [nominal_metrics(name, r) for name,r in cases]
    reduction = outputs["merwin_proof_summary"]["numerical_certificate"]
    for row in rows:
        if row["procedure"].startswith("merwin-"):
            row["plant_arithmetic_certificate"] = {k:reduction[k] for k in ("checked_scans","wall_seconds","status","smt_sha256")}
    checks = [o for _, r in profiles for o in r["obligations"].values()]
    return {"rows":rows, "new_dL_obligations":len(checks),
            "new_dL_obligations_proved":sum(o["status"]=="PROVED" for o in checks),
            "deep_nominal_obligation_count":sum(r["obligations"] for r in rows),
            "accounting":"Per-archive wall time includes JVM startup and proof export. Tactic times exclude startup. Render times cover archive serialization after profile construction. Counts of signals are distinct dependency-mediated resource outputs in the nominal path. Plant coordinates follow each abstraction. The Merwin arithmetic reduction is measured separately."}


def scale_summary(scale):
    rows = scale["rows"]
    times = [r["solver_wall_ns"]/1e6 for r in rows]
    return {
        "cells": len(rows), "candidate_assessments":sum(r["candidates"] for r in rows),
        "solver_queries":sum(r["obligations"] for r in rows),
        "unknown_candidate_assessments":sum(r["outcomes"].count("UNKNOWN") for r in rows),
        "largest_joint_branch_count":max(r["joint_branch_count"] for r in rows),
        "model_bytes_range":[min(r["model_bytes"] for r in rows),max(r["model_bytes"] for r in rows)],
        "solver_wall_ms_range":[min(times),max(times)],"solver_wall_ms_median":median(times),
        "timeouts_or_solver_failures":sum(r["return_code"] != 0 or "timeout" in r["solver_answers"] for r in rows),
    }


def _provenance(records, timestamp, configuration):
    pairs = sorted({(r["archive_sha256"],r["proof_profile_sha256"]) for r in records})
    return dict(source_commit=BASE,timestamp=timestamp,
                formal_model_sha256=object_hash([p[0] for p in pairs]) if pairs else None,
                proof_profile_sha256=object_hash([p[1] for p in pairs]) if pairs else None,
                tool_versions={"KeYmaera X":"5.1.1","Z3":"4.15.4","Java":"17.0.21.1","CLEO":"unused in new dL studies"},
                configuration=configuration, profile_bindings=[dict(archive_sha256=a,profile_sha256=p) for a,p in pairs])


def generate(directory=RESULTS):
    from . import reuse
    outputs = {}
    groups = {}
    for module in (hand,cost,merwin,chp):
        payloads = module.reports()
        ps = module.profiles() if hasattr(module,"profiles") else ()
        pairs = [(p, read_record(p)) for p in ps]
        if any(r is None for _,r in pairs):
            raise ValueError(f"Missing or mismatched proof record for {module.__name__}")
        outputs.update(payloads)
        groups[module.__name__.split(".")[-1]] = pairs
    baseline = load(BASELINE)
    families = dict(attleboro_remote_study=remote_rows(), attleboro_hand=outputs["attleboro_hand_mutations"]["rows"],
                    controlled_cost=outputs["common_context_cost_mutations"]["rows"],
                    merwin=outputs["merwin_mutations"]["rows"], chp=outputs["chp_fail_closed_results"]["rows"])
    rows = combine(families)
    outputs["cross_domain_baselines"] = {"rows":rows, "detection_rule":"First applicable B1/B2/B3 reporting DECLINE or UNRESOLVED, then B4 if positive service lacks assurance."}
    outputs["rq1_summary"] = {"overall":counts(rows), "per_family":{f:counts([r for r in rows if r["family"]==f]) for f in families},
                              "unit":"A scenario is a labeled mutation or evidence query. An assessment is one candidate evaluated in that scenario. Repeated starting states and shared trace bundles are counted as queries, not independent trials."}
    pairs = [pair for subset in groups.values() for pair in subset]
    outputs["rq2_summary"] = measurements(outputs,pairs,baseline)
    selection=outputs["common_context_cost_selection"]
    outputs["rq3_summary"] = {"expressions":selection["nominal_expressions"],"units":selection["units"],
                              "weight_order":selection["weight_order"],"selections":selection["rows"],
                              "nominal_hard_results":[r for r in families["controlled_cost"] if r["scenario"]=="C0"],
                              "source_scope":"Controlled research benchmark with fixed common water contract."}
    scale = scalability.report()
    outputs["scalability_results"] = dict(summary=scale_summary(scale), cells=scale["rows"],
                                           measurement_configuration=scale["configuration"],
                                           solver_sha256=scale["solver_sha256"])
    outputs["proof_reuse_results"] = reuse.report()
    records=[r for _,r in pairs]
    meta_time=max([r["timestamp"] for r in records]+[scale["timestamp"]])
    remote_records = list(baseline["new_obligations"].values())
    cfg={"metadata":"Timestamp from the evidence capture. Aggregate hashes bind sorted archive/profile pairs. A null binding denotes observational assessment.",
         "scope":"Offline research fixtures. All paths relative to the repository or package.",
         "source":"source_commit identifies the unchanged starting artifact. The manifest fingerprints experiment sources added since that commit."}
    files={}
    for stem,payload in outputs.items():
        scoped = records + remote_records
        for prefix, group in (("attleboro_","hand"),("common_context_","cost"),("merwin_","merwin"),("chp_","chp"),("rq3_","cost")):
            if stem.startswith(prefix):
                scoped=[r for _,r in groups[group]]
                break
        meta=_provenance(scoped,meta_time,cfg)
        if stem=="scalability_results":
            meta.update(formal_model_sha256=object_hash([r["model_sha256"] for r in scale["rows"]]),
                        proof_profile_sha256=object_hash(scale["configuration"]), timestamp=scale["timestamp"],
                        profile_bindings=[],tool_versions=scale["tool_versions"])
        if stem.startswith("chp_"):
            meta.update(tool_versions={"assessment":"deterministic Python lifecycle checks"},profile_bindings=[])
        files[stem+".json"] = dump({**meta,**payload})

    source_files=[f for f in ROOT.rglob("*") if f.is_file() and EVIDENCE not in f.parents
                  and "__pycache__" not in f.parts and f.suffix in (".py",".csv",".json")]
    assets={str(f.relative_to(ROOT)):digest(f.read_bytes()) for f in sorted(EVIDENCE.rglob("*")) if f.is_file()}
    manifest={**_provenance(records+remote_records,meta_time,cfg),
              "experiment_sources":{str(f.relative_to(ROOT)):digest(f.read_bytes()) for f in sorted(source_files)},
              "evidence_files":assets,"results":{name:digest(data) for name,data in sorted(files.items())},
              "baseline_reproduction_sha256":digest(BASELINE.read_bytes()),
              "preserved_historical_inventory_sha256":baseline["inventory_sha256"]}
    files["milestone2_manifest.json"]=dump(manifest)
    directory.mkdir(parents=True,exist_ok=True)
    for name,data in files.items():
        (directory/name).write_bytes(data)
    return outputs


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS)
    args=parser.parse_args()
    generate(args.output)
