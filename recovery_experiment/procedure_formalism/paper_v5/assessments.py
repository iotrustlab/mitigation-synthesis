"""Reconstruct the 68 fixed queries from proof exports, model premises and device traces."""
import argparse
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .. import evaluation, formal_model, verify
from ..attleboro import HOLD_ID, REMOTE_ID, attleboro
from ..formal_ir import executions, expr
from ..milestone2 import chp, cost, hand, merwin, proofs
from ..paper_v2.comparison import load, save, write_csv
from ..procedure import DependencyStatus as D

ROOT = evaluation.ROOT
OUTPUT = ROOT / "results/paper_v5"
POS = "formal universal proof"
NEG = "reachable formal counterexample"
FALSE = "known false prerequisite"
MISSING = "source-backed missing evidence"
MODEL = "open proof or missing model"
TRACE = "trace-backed device witness"
LIMITS = {
    "attleboro": "Water service is bounded to the modeled sampled deadline and operator conditions.",
    "merwin": "Generation is bounded to the supplied startup trajectory and synchronization observations.",
    "controlled_water": "The guarantee uses the common tank context, mandatory durations and final meter.",
    "chp": "The device evidence does not establish safe process restart or delivered customer service.",
}


@dataclass
class Query:
    family: str
    domain: str
    scenario: str
    candidate: str
    procedure: object = None
    initial: dict | None = None
    stages: tuple = ()
    contract: str = ""
    source: str = ""
    profile: object = None
    device: tuple | None = None

    @property
    def identity(self):
        return self.family, self.scenario, self.candidate

    @property
    def id(self):
        return "/".join(self.identity)


def queries():
    result = []
    for i, mutation in enumerate(evaluation.MUTATIONS):
        snapshot = attleboro(mutation.dependencies, mutation.states, mutation.local_ready_time)
        for key in mutation.candidates:
            proc = snapshot[key]
            model = formal_model.build_model(proc) if proc.procedure_id != HOLD_ID else None
            result.append(Query("attleboro_remote_study", "attleboro", f"M{i}", proc.procedure_id,
                                proc, model.initial if model else None, model.stages if model else (),
                                formal_model.POST, f"evaluation.py#MUTATIONS[{i}]", model))
    positive, negative, _ = hand.profiles()
    for i, mutation in enumerate(hand.CASES):
        model = formal_model.build_model(mutation.snapshot()["hand"])
        result.append(Query("attleboro_hand", "attleboro", f"H{i}", hand.HAND_PROFILE, model.procedure,
                            model.initial, model.stages, formal_model.POST, f"milestone2/hand.py#CASES[{i}]",
                            positive if not i else negative))
    for scenario, ctx in cost.SCENARIOS.items():
        for plan in cost.plans(ctx):
            initial = {**plan.initial, **dict.fromkeys(cost.WEIGHTS, 1)}
            result.append(Query("controlled_cost", "controlled_water", scenario, plan.procedure.procedure_id,
                                plan.procedure, initial, plan.stages, cost.HARD,
                                f"milestone2/cost.py#SCENARIOS[{scenario}]", cost.proof_profile(plan)))
    if not merwin.checked_reduction():
        raise ValueError("Invalid Merwin reduction certificate")
    for i in range(len(merwin.CASES)):
        proc, initial, stages = merwin.model(i)
        result.append(Query("merwin", "merwin", f"MER{i}", proc.procedure_id, proc, initial, stages, merwin.POST,
                            f"milestone2/merwin.py#CASES[{i}]", merwin.profile(i) if i in (*merwin.DEEP, 3) else None))
    raw = json.loads(chp.EVIDENCE.read_text())["bundles"]
    for i, (_, bundle, focus) in enumerate(chp.QUERIES):
        result.append(Query("chp", "chp", f"CHP{i}", chp.RELOAD,
                            source=f"milestone2/chp_device_evidence.json#bundles.{bundle}",
                            device=(raw[bundle], focus)))
    return result


def device_evidence(bundle):
    inputs, terminal = bundle["inputs"], bundle["terminal"]
    events = {row["action"]: row["accepted"] for row in bundle["events"]}
    checks = {
        "engineering access": inputs["engineering_access"], "reset": events["reset"],
        "bootable": terminal["device_bootable"], "backup available": inputs["backup_available"],
        "backup compatible": inputs["backup_compatible"], "backup reviewed": inputs["backup_reviewed"],
        "load accepted": events["load_backup"], "logic loaded": terminal["logic_loaded"],
        "runtime started": events["start_runtime"], "runtime executing": terminal["runtime_executing"],
    }
    probe = bundle["probe"] or {}
    heartbeat = (all(checks.values()) and terminal["runtime_evidence"] == "CONFIRMED"
                 and probe.get("status") == "CONFIRMED" and probe["compile_success"]
                 and probe["scan_count_after"] > probe["scan_count_before"] >= 0)
    return checks, bool(heartbeat), terminal["process_ready"]


@lru_cache(None)
def validated_profile(profile):
    if not proofs.proved(profile):
        raise ValueError(f"No matching proved archive for {profile.name}")


def theorem(query, name):
    if query.family == "attleboro_remote_study":
        validator = verify.verified_violation if name == "violation" else verify.verified
        if not validator(query.profile):
            raise ValueError(f"Unverified {query.id}/{name}")
        return f"proof_records/{query.scenario}/{name}.kyp"
    validated_profile(query.profile)
    path = f"milestone2/evidence/proof_records/{query.profile.name}/{name}.kyp"
    if not (ROOT / path).is_file():
        raise ValueError(path)
    return path


def adjudicate(query):
    """Derive a verdict before joining the published B1--B4 columns."""
    basis_artifact = query.source
    corroboration = []
    if query.device is not None:
        bundle, focus = query.device
        checks, heartbeat, ready = device_evidence(bundle)
        if heartbeat:
            corroboration.append(TRACE)
        failed = [guard for guard, value in checks.items() if not value]
        if failed or ready is False:
            return "REJECTED", FALSE, basis_artifact, ", ".join(failed or ["process readiness"]) + " is false.", corroboration
        if not heartbeat:
            raise ValueError("Expected observed benign runtime in unresolved CHP queries")
        if focus == "cyber_trust":
            assert bundle["terminal"]["hostile_influence"] is None
            return "UNKNOWN", MISSING, basis_artifact, "The heartbeat supplies no evidence settling persistence.", corroboration
        if focus == "customer_supply":
            assert next(p for p in chp.chp_procedures() if p.procedure_id == chp.RELOAD).initial_state["customer_supply_mechanism"] is None
            return "UNKNOWN", MISSING, basis_artifact, "The external supply mechanism has no bound evidence.", corroboration
        return "UNKNOWN", MODEL, basis_artifact, "Device execution is observed. Process readiness and dynamics remain unbound.", corroboration

    proc = query.procedure
    if proc.procedure_id == HOLD_ID:
        assert proc.actuator is None and proc.service_definition == "No positive water-service claim."
        return "REJECTED", FALSE, "attleboro.py#attleboro.hold", "Passive hold issues no positive actuation demand for the requested service.", []
    states = executions(query.stages, query.initial)
    disposition = [expr(query.contract, s) for s in states]
    unavailable = [k for k, n in proc.required_dependencies.items() if n.status == D.UNAVAILABLE]
    uncertain = [k for k, n in proc.required_dependencies.items() if n.status == D.UNKNOWN]
    if unavailable:
        if states:
            raise ValueError("Unavailable required stage has an execution")
        if query.family == "attleboro_hand":
            corroboration.append(theorem(query, query.scenario + "_disabled"))
        return "REJECTED", FALSE, basis_artifact, "Unavailable required resource: " + ", ".join(unavailable) + ".", corroboration
    if not states:
        raise ValueError("Unexplained empty execution set")
    if all(disposition):
        name = "composition" if query.domain == "controlled_water" else "end_to_end"
        witness = "nonvacuity" if query.domain == "controlled_water" else "execution_witness"
        corroboration.append(theorem(query, witness))
        if query.domain == "merwin":
            corroboration.append("milestone2/evidence/merwin_plant_reduction.json")
        return "PROVED", POS, theorem(query, name), "A reachable execution and universal safety, service and evidence proof meet the bounded contract.", corroboration
    if uncertain:
        if not any(disposition):
            raise ValueError("Check whether unknown integrity actually decides this case")
        corroboration.append(theorem(query, "violation"))
        return "UNKNOWN", MISSING, basis_artifact, "Both service and a violation are possible; incident integrity is unresolved for " + ", ".join(uncertain) + ".", corroboration

    if query.family == "attleboro_remote_study":
        if query.candidate == REMOTE_ID and verify.verified_violation(query.profile):
            return "REJECTED", NEG, theorem(query, "violation"), "A reachable execution violates the full water contract.", []
        p = query.initial
        if p["tripInput"]:
            reason = "Active protection excludes a start."
        elif p["ready"] > p["deadline"]:
            reason = "Actor readiness follows the deadline."
        elif query.candidate != REMOTE_ID and (not p["hand"] or p["remote"]):
            reason = "The required exclusive Hand selector setting is false."
        else:
            raise ValueError(f"Unexplained water rejection {query.id}")
        return "REJECTED", FALSE, basis_artifact, reason, []
    if query.profile is not None:
        name = query.scenario + "_violation" if query.family == "attleboro_hand" else "violation"
        return "REJECTED", NEG, theorem(query, name), "A reachable complete execution violates the specified contract.", []
    if query.domain == "merwin" and (not query.initial["auxNormal"] or not query.initial["syncAvailable"]):
        reason = "The required auxiliary permissive is false." if not query.initial["auxNormal"] else "The synchronization window is unavailable."
        return "REJECTED", FALSE, basis_artifact, reason, []
    raise ValueError(f"Missing independent evidence for {query.id}")


def evidence_rows(fixtures):
    reported = {(r["family"], r["scenario"], r["procedure"]): r for r in load("cross_domain_baselines")["rows"]}
    if len(fixtures) != 68 or set(q.identity for q in fixtures) != reported.keys():
        raise ValueError("Assessment identities differ from the original comparison")
    rows = []
    for q in fixtures:
        status, basis, artifact, claim, extra = adjudicate(q)
        row = reported[q.identity]
        if row["B4"] != status:
            raise ValueError(f"Evidence mismatch for {q.id}: {status} vs {row['B4']}")
        rows.append(dict(assessment_id=q.id, domain=q.domain, scenario=q.scenario, candidate=q.candidate,
                         **{k: row[k] for k in ("B1", "B2", "B3", "B4")}, evidence_outcome=status,
                         classification_basis=basis, supporting_artifact=artifact, supporting_context=q.source,
                         additional_evidence=extra, claim_supported=claim, claim_not_supported=LIMITS[q.domain]))
    return rows


def write_evidence(rows, output):
    output.mkdir(parents=True, exist_ok=True)
    save(output / "assessment_evidence_basis.json", {
        "method": "Adjudicate from matching proof exports, explicit fixture guards and saved device observations, then compare with the B columns. Independence is from baseline votes, not from the underlying model or from experimental design.",
        "basis_counts": dict(Counter(r["classification_basis"] for r in rows)),
        "device_witness_count": sum(TRACE in r["additional_evidence"] for r in rows),
        "rows": rows,
    })
    write_csv(output / "assessment_evidence_basis.csv", [
        {**row, "additional_evidence": " | ".join(row["additional_evidence"])} for row in rows])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    write_evidence(evidence_rows(queries()), parser.parse_args().output)
