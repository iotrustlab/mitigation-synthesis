"""Compare one-stage model reductions on the original, offline assessment fixtures."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from .. import evaluation, formal_model
from ..attleboro import HOLD_ID, REMOTE_ID, attleboro
from ..formal_ir import Assignment as A, Stage, expr
from ..milestone2 import cost
from ..paper_v2.comparison import save, write_csv
from ..procedure import DependencyStatus as D
from .assessments import OUTPUT, device_evidence, evidence_rows, queries, write_evidence

VARIANTS = ("FULL", "NO_AUTHORITY", "COLLAPSE_DELIVERY", "COLLAPSE_PLANT", "NO_OBSERVATION", "BREAK_SHARED_IDENTITY")
METHODS = {
    "FULL": "Retain a reachable candidate meeting the complete bounded service contract; documentary claims require service evidence.",
    "NO_AUTHORITY": "Assume the modeled initiating actor present and authorized, and remove water actor wait. Preserve selectors, interlocks, communication and equipment startup times.",
    "COLLAPSE_DELIVERY": "Feed command output directly to the delivery slot. Keep separate power, mode, protection, relay, plant and meter requirements. Local Hand already copies the command.",
    "COLLAPSE_PLANT": "Replace terminal service magnitude by the service threshold when the actuator reports running (water and hydro) or the drive is powered (tank). Sample that substituted quantity using the original observer guards. Keep original safety, time and upstream enabling conditions. For eligible CHP device/process queries the observed heartbeat serves as the proxy, subject to any explicitly false process prerequisite.",
    "NO_OBSERVATION": "Project away the final observer stage and its postconditions. Check the actual physical quantity, safety and time.",
    "BREAK_SHARED_IDENTITY": "Key each shared resource by (candidate, resource) instead of resource. Preserve every observed or stipulated status for the fixed candidate. The separate placement diagnostic applies one shared-event mutation to one copy at a time.",
}


def replace_slots(stages, replacements):
    return tuple(Stage(stage.name, tuple(replacements.get(op.name, op) for op in stage.assignments))
                 for stage in stages)


def all_paths_meet(stages, initial, contract):
    """A blocked reachable prefix or one failed terminal state defeats retention."""
    states = [initial]
    for stage in stages:
        for op in stage.assignments:
            successors = []
            for state in states:
                values = op.values(state)
                if not values:
                    return False
                successors.extend({**state, op.name: value} for value in values)
            states = successors
    return all(expr(contract, state) for state in states)


def retain(query, variant):
    if query.device:
        bundle, focus = query.device
        if variant == "FULL":
            # This projection lacks physical production, safety and customer-delivery evidence.
            return False
        if variant == "COLLAPSE_PLANT" and focus in ("end_to_end", "process_ready"):
            checks, heartbeat, ready = device_evidence(bundle)
            return all(checks.values()) and heartbeat and ready is not False
        return None
    if query.candidate == HOLD_ID:
        return False if variant == "FULL" else None

    stages = query.stages
    initial = dict(query.initial)
    contract = query.contract
    slots = {}
    if variant == "NO_AUTHORITY":
        if query.domain == "attleboro":
            initial.update(ready=0, authorized=1)
            slots["request"] = A.nominal("request", "authorized")
        elif query.domain == "merwin":
            slots["request"] = A.indicator("request", "remoteMode==1")
        else:
            slots["request"] = A.nominal("request", "1")
    elif variant == "COLLAPSE_DELIVERY":
        if query.domain == "attleboro":
            if query.candidate != REMOTE_ID:
                return None
            slots["delivered"] = A.nominal("delivered", "output")
        elif query.domain == "merwin":
            slots["contact"] = A.indicator("contact", "closeCmd==1 and relay==1")
        else:
            slots["actuated"] = A.nominal("actuated", "output")
    elif variant == "COLLAPSE_PLANT":
        if query.domain == "attleboro":
            # run3 is set before q. Keep sampled safe3, then sample the weaker plant proxy.
            slots.update(q=A.nominal("q", "5*run3"), pressure=A.nominal("pressure", "30+3*q"))
        elif query.domain == "merwin":
            slots.update({f"mw{i}": A.nominal(f"mw{i}", "running") for i in (1, 2, 3)})
        else:
            # The volume bound uses the true balance. Only the service/evidence quantity is weakened.
            plant = next(s for s in stages if s.name == "plant")
            pos = next(i for i, op in enumerate(plant.assignments) if op.name == "physical")
            proxy = A.nominal("proxyFlow", "drive*minimum")
            plant = Stage(plant.name, (*plant.assignments[:pos], proxy, *plant.assignments[pos:]))
            stages = tuple(plant if s.name == "plant" else s for s in stages)
            slots.update(physical=A.indicator("physical", "start<=deadline and proxyFlow>=minimum and elapsed==horizon"),
                         reading=A("reading", (("trusted==1", "proxyFlow"), ("trusted==0", "0"), ("trusted==0", "demand"))),
                         credible=A.indicator("credible", "trusted==1 and fresh==1 and reading==proxyFlow and reading>=minimum"))
    elif variant == "NO_OBSERVATION":
        stages = tuple(s for s in stages if s.name not in ("observer", "observation", "cost"))
        contract = {
            "attleboro": "safe==1 and t<=deadline and t==ready+3 and run==1 and physical==1 and q>=5 and pressure<=90",
            "merwin": "safe==1 and service==1 and clock==deadline",
            "controlled_water": "safe==1 and physical==1 and elapsed==horizon",
        }[query.domain]
    elif variant != "FULL":
        raise ValueError(variant)
    return all_paths_meet(replace_slots(stages, slots), initial, contract)


def cloned_query(q, shared_keys, scoped_status):
    """Build an independent candidate model from its own copy of the shared statuses."""
    overrides = {k: scoped_status[q.candidate, k] for k in shared_keys}
    if q.domain == "controlled_water":
        ctx = cost.SCENARIOS[q.scenario]
        faults = {**dict(ctx.faults), **overrides}
        clone_ctx = replace(ctx, faults=tuple((k, value) for k, value in faults.items() if value != D.TRUSTED))
        plan = next(p for p in cost.plans(clone_ctx) if p.procedure.procedure_id == q.candidate)
        return replace(q, procedure=plan.procedure, stages=plan.stages)
    spec = evaluation.MUTATIONS[int(q.scenario[1:])]
    snapshot = attleboro({**spec.dependencies, **overrides}, spec.states, spec.local_ready_time)
    proc = next(p for p in snapshot.values() if p.procedure_id == q.candidate)
    return replace(q, procedure=proc, stages=formal_model.build_model(proc).stages)


def shared_identity(fixtures):
    """Pair candidates within a single recorded operating state before cloning shared nodes."""
    groups = defaultdict(list)
    for q in fixtures:
        if q.domain in ("attleboro", "controlled_water") and q.candidate != HOLD_ID:
            groups[q.family, q.scenario].append(q)
    retained, diagnostic = {}, []
    for pair in groups.values():
        if len(pair) < 2:
            continue
        shared_keys = set.intersection(*(set(q.procedure.shared_dependencies) for q in pair))
        if not shared_keys:
            continue
        scoped = {(q.candidate, k): q.procedure.required_dependencies[k].status
                  for q in pair for k in shared_keys}
        for k in shared_keys:
            if len({scoped[q.candidate, k] for q in pair}) != 1:
                raise ValueError("Inconsistent incident-level status for the same shared resource")
        for q in pair:
            retained[q.id] = retain(cloned_query(q, shared_keys, scoped), "FULL")
        changed = [k for k in shared_keys if scoped[pair[0].candidate, k] != D.TRUSTED]
        if not changed:
            continue
        if len(changed) != 1:
            raise ValueError("This diagnostic is defined for one shared event per operating state")
        resource, = changed
        placements = []
        for owner in pair:
            assignment = dict(scoped)
            for q in pair:
                if q != owner:
                    assignment[q.candidate, resource] = D.TRUSTED
            survivors = [q.candidate for q in pair if retain(cloned_query(q, shared_keys, assignment), "FULL")]
            placements.append({"affected_copy": owner.candidate, "retained": survivors})
        diagnostic.append({
            "scenario": pair[0].scenario, "resource": resource, "stipulated_status": scoped[pair[0].candidate, resource].value,
            "original_retained": [q.candidate for q in pair if retain(q, "FULL")],
            "cloned_retained_all_placements": sorted(set.intersection(*(set(p["retained"]) for p in placements))),
            "placements": placements,
        })
    return retained, diagnostic


def summarize(rows):
    applicable = [r for r in rows if r["retention"] != "INAPPLICABLE"]
    retained = [r for r in applicable if r["retention"] == "RETAINED"]
    counts = Counter(r["evidence_outcome"] for r in retained)
    return dict(applicable=len(applicable), retained=len(retained), retained_proved=counts["PROVED"],
                retained_known_failure=counts["REJECTED"], retained_unresolved=counts["UNKNOWN"],
                retained_without_support=counts["REJECTED"] + counts["UNKNOWN"],
                decisive_assessments=[r["assessment_id"] for r in retained if r["evidence_outcome"] != "PROVED"])


def results(fixtures, evidence):
    rows, summaries, by_domain = [], [], []
    indexed = {r["assessment_id"]: r for r in evidence}
    cloned, diagnostic = shared_identity(fixtures)
    for variant in VARIANTS:
        subset = []
        for q in fixtures:
            val = cloned.get(q.id) if variant == "BREAK_SHARED_IDENTITY" else retain(q, variant)
            ref = indexed[q.id]["evidence_outcome"]
            if variant == "FULL" and bool(val) != (ref == "PROVED"):
                raise ValueError(f"Full semantics disagree with proof/evidence for {q.id}")
            if val is False and ref == "PROVED":
                raise ValueError(f"Reduction removed a proved candidate: {q.id}, {variant}")
            subset.append(dict(variant=variant, assessment_id=q.id, domain=q.domain,
                               evidence_outcome=ref, retention="INAPPLICABLE" if val is None else
                               "RETAINED" if val else "NOT_RETAINED"))
        rows.extend(subset)
        summaries.append(dict(variant=variant, **summarize(subset)))
        for domain in sorted({r["domain"] for r in subset}):
            by_domain.append(dict(variant=variant, domain=domain, **summarize([r for r in subset if r["domain"] == domain])))
    return dict(unit="One supplied candidate in one original operating state.",
                decision="Retained requires a reachable endpoint and satisfaction on every execution of the specified weakened contract. The full reference is adjudicated separately from baseline votes.",
                methods=METHODS, totals=summaries, by_domain=by_domain, assessments=rows,
                clone_placement_diagnostic=diagnostic)


def figure(data):
    names = ("Full contract", "Assume actor", "Copy command", "Use actuator proxy", "Omit observation", "Clone shared IDs")
    lines = [r"% Generated by paper_v5.ablation from stage_ablation.json.", r"\begin{figure}[t]", r"\centering\footnotesize",
             r"\begin{tikzpicture}[x=2.45mm,y=4mm]", r"\node[anchor=east] at (-.6,6.35) {Contract};",
             r"\node[anchor=east] at (18,6.35) {Ret./app.};"]
    for i,(item,label) in enumerate(zip(data["totals"],names)):
        y = 5.5-i
        neg, unk = item["retained_known_failure"],item["retained_unresolved"]
        lines.append(rf"\node[anchor=east] at (-.6,{y}) {{{label}}};")
        if neg:
            lines.append(rf"\fill[black!72] (0,{y-.28:.2f}) rectangle ({neg},{y+.28:.2f});")
        if unk:
            lines.append(rf"\filldraw[fill=white,pattern=north east lines] ({neg},{y-.28:.2f}) rectangle ({neg+unk},{y+.28:.2f});")
        lines.append(rf"\node[anchor=west] at ({neg+unk+.18},{y}) {{{neg+unk}}};")
        lines.append(rf"\node[anchor=east] at (18,{y}) {{{item['retained']}/{item['applicable']}}};")
    lines.extend([r"\end{tikzpicture}", "", r"{\scriptsize Solid: known failure.\quad Hatched: unresolved.}",
        r"\caption{Assessments retained without independent end-to-end support. Bar labels count unsupported retentions against the independently reconstructed evidence basis. The right column gives all retained candidates over applicable assessments. Copying the same known status to each resource clone preserves fixed-candidate outcomes.}\label{fig:stage-ablation}",
        r"\end{figure}",""])
    return "\n".join(lines)


def write_results(output, tex=None):
    fixture = queries()
    basis = evidence_rows(fixture)
    write_evidence(basis, output)
    data = results(fixture, basis)
    save(output / "stage_ablation.json", data)
    for name, key in (("stage_ablation", "totals"), ("stage_ablation_by_domain", "by_domain")):
        rows = [{**r, "decisive_assessments": " | ".join(r["decisive_assessments"])} for r in data[key]]
        write_csv(output / (name + ".csv"), rows)
    if tex:
        tex.write_text(figure(data))
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    write_results(args.output, args.figure)
