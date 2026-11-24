"""Rebuild the six representative cases from authenticated archives and evidence."""

import argparse
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from .. import formal_model
from ..formal_ir import executions, expr
from ..milestone2 import chp, hand, merwin
from ..paper_v2 import formal, formal_reports

ROOT = formal.ROOT
MATRIX = ROOT / "results/paper_v3/representative_case_matrix.json"
DOC = ROOT / "docs/REPRESENTATIVE_FORMAL_CASES_V3.md"

# Within each group, assessments and publication columns follow this order.
GROUPS = {
    "S1": ("Attleboro water", ("M0",), "Remote composition", "O1--O7", "Three scans, 6.4 L/s at tick 3", "Sampled water service at the deadline"),
    "S2": ("Attleboro water", ("M5",), "Delivery diamond", "O5--O7", "Output one, delivered zero, zero flow", "Known compromise admits suppression"),
    "S3": ("Attleboro water", ("M13",), "Widened delivery relation", "O5--O7", "Copy and suppression both feasible", "Actual delivery integrity unresolved"),
    "S4": ("Attleboro water", ("H0", "H1", "H2"), "Hand composition, disabled box, late diamond", "O2, O3, O7", "Ready at zero, absent, or ready at one", "Staffing and arrival are premises"),
    "S5": ("Merwin hydro", ("MER0", "MER6", "MER10"), "Startup composition and contact diamonds", "O5--O7", "Three samples above 1 MW or three zeros", "Pinned forcing and contact evidence"),
    "S6": ("Polish CHP", ("CHP0",), "Device lifecycle and runtime trace", "O5--O7 unbound", "Reviewed load and advancing scan counter", "Device milestone only"),
}

REASONS = {
    "M0": "The composed box covers the three required scans, sampled safety, service at the deadline and a corresponding meter reading.",
    "M5": "The stipulated compromised delivery admits a reachable suppressed command under which physical flow and its fresh reading are zero.",
    "M13": "Both a copied output and a suppressed command are feasible. The recorded incident leaves delivery integrity unresolved.",
    "H0": "The operator is ready at tick zero. Exclusive Hand selection on generator power reaches sampled service and a fresh reading at tick three.",
    "H1": "The required local operator is unavailable. The first assignment has no successor and the disabled box proves there is no complete execution.",
    "H2": "Readiness at tick one shifts the three scans to ticks two, three and four. The flow at tick three is 4 L/s, below the 5 L/s threshold. The terminal service sample is late.",
    "MER0": "Under the pinned forcing and synchronization observations, contact closes and three fresh generation samples exceed the 1 MW threshold.",
    "MER6": "The controller demands closure but stipulated inoperative contact stays open. The reduced plant reaches three zero-generation samples.",
    "MER10": "The widened breaker relation admits contact and no contact. The no-contact execution violates service, while incident integrity remains unresolved.",
    "CHP0": "The fixture records a simulated device lifecycle with an independent benign runtime observation. Process readiness, physical production and customer delivery remain unresolved.",
}


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_sources():
    """Rebuild v2 in isolation to check recorded results against archived theorem bytes."""
    names = ("canonical_semantic_cases", "proof_obligation_matrix")
    with TemporaryDirectory() as temp:
        output = Path(temp)
        formal_reports.generate(output)
        for name in names:
            filename = name + ".json"
            if (output / filename).read_bytes() != (formal.RESULTS / filename).read_bytes():
                raise ValueError(f"Published {filename} differs from its authenticated sources")
        return tuple(formal_reports.load(output / (name + ".json")) for name in names)


def claim_value(formula, state):
    # The projected case predicates are conjunctions of arithmetic comparisons.
    ir = re.sub(r"(?<![<>=!])=(?!=)", "==", formula).replace(" & ", " and ")
    return expr(ir, state)


def audit_finite(case):
    """Classify terminal projections on the exact finite assignments used to emit dL."""
    initial = {key: Fraction(value) for key, value in case.initial.items()}
    if not claim_value(case.gamma, initial):
        raise ValueError(f"{case.name} has no supplied valuation for its premise")
    terminal = executions(case.stages, initial)
    hydro = case.name.startswith("MER")
    fields = ("closeCmd", "contact", "tick1", "tick2", "tick3", "mw1", "mw2", "mw3", "observed1", "observed2",
              "observed3", "clock") if hydro else (
        "ready", "output", "delivered", "tick1", "tick2", "tick3", "flow1", "flow2", "flow3", "q",
        "pressure", "observed", "observedPressure", "t")
    paths = []
    for state in terminal:
        evidence = bool(claim_value(case.evidence, state))
        match = bool(claim_value(case.correspondence, state))
        paths.append({
            "values": {key: str(state[key]) for key in fields},
            "on_time": bool(claim_value(case.boundary, state)),
            "safe": bool(state["safe"]), "physical": bool(state["service" if hydro else "physical"]),
            "evidence_produced": evidence, "evidence_implies_correspondence": not evidence or match,
            "complete_contract": bool(expr(merwin.POST if hydro else formal_model.POST, state)),
        })
    if case.name == "H1":
        first = case.stages[0].assignments[0]
        if first.values(initial) or paths:
            raise ValueError("Absent Hand actor must block the first assignment")
        progress = {"blocked_assignment": first.name, "terminal_paths": 0}
    else:
        progress = formal.audit_prefixes(case)
        if progress["terminal_paths"] != len(paths):
            raise ValueError("Prefix and terminal audits disagree")
    return {"premise_valuation": {k: str(v) for k, v in initial.items()},
            "prefix_check": progress, "terminal_executions": paths}


def row(status, reason, *, proofs=(), finite=False):
    evidence = {"theorems": list(proofs)}
    if finite:
        evidence["finite_check"] = "finite_model_check"
    return {"status": status, "reason": reason, "evidence": evidence}


def program_fragment(case, description):
    selected = {"request", "received", "accepted", "output", "delivered", "drive", "tick1", "tick2", "tick3",
                "physical", "established", "closeCmd", "contact", "rawMW1", "mw1", "service", "credible"}
    return {"description": description, "stages": [
        {"stage": stage.name, "guarded_relations": [op.relation() for op in stage.assignments if op.name in selected]}
        for stage in case.stages if any(op.name in selected for op in stage.assignments)]}


def projected_obligations(code, finite, proofs, fixed):
    cost = row("INAPPLICABLE", "This facility case has no common-context cost contract.")
    if fixed:
        results = {r["obligation"]: row("PROVED", r["justification"], proofs=[r["theorem"]],
                                        finite=r["obligation"] == "O3") for r in fixed if r["obligation"] != "O8"}
        results["O6"]["reason"] = "The full-program box proves both production of E and E implying correspondence with the physical measurements."
        return {**results, "O8": cost}
    if code == "CHP0":
        reasons = ["Service premises have no CHP process-state binding.", "No executable CHP process or supply model is bound.",
                   "No process timeline or persistent failure model is bound.", "No physical process safety model is bound.",
                   "No heat or electrical production model is bound.", "The fixture provides no measurements of physical or customer delivery.",
                   "The complete process and customer-service contract has no model."]
        return {**{f"O{i}": row("UNBOUND_EVIDENCE" if i == 6 else "UNBOUND_MODEL", reason)
                   for i, reason in enumerate(reasons, 1)}, "O8": cost}

    o1 = row("PROVED", "The concrete initial valuation satisfies every conjunct of the encoded premise.", finite=True)
    if code == "H1":
        theorem, = proofs
        blocked = row("REFUTED", "The unavailable operator disables the first assignment. No execution or explicit failure reaches assessment.",
                      proofs=[theorem], finite=True)
        return {"O1": o1, "O2": blocked, "O3": blocked,
                **{f"O{i}": row("INAPPLICABLE", "The failed execution prerequisite precludes assessment. A vacuous box gives no assurance.",
                                proofs=[theorem]) for i in range(4, 8)}, "O8": cost}

    specific = next(p for p in proofs if p.endswith("_specific_witness"))
    violation = next(p for p in proofs if p.endswith("_violation"))
    terminal = finite["terminal_executions"]
    late = code == "H2"
    def projection(key, positive, negative, counterproof=None):
        holds = all(s[key] for s in terminal)
        return row("PROVED" if holds else "REFUTED", positive if holds else negative, finite=True,
                   proofs=[counterproof] if not holds and counterproof else [])
    results = {
        "O1": o1, "O2": row("PROVED", "The specific reachable terminal state implies an execution.", proofs=[specific]),
        "O3": projection("on_time", "Every admitted semantic prefix has a successor and every path reaches the scheduled boundary.",
                         "All scans execute, but the clock reaches four against deadline three. There is no explicit persistent failure.", specific),
        "O4": projection("safe", "The safety accumulator holds on every reachable finite terminal state.", "An admitted path violates sampled safety."),
        "O5": projection("physical", "The terminal physical predicate holds at tick four. O3 records the missed deadline.",
                         "An admitted complete execution has no physical service and no explicit persistent-failure exception.", specific),
        "O6": projection("evidence_produced", "At tick four the observer produces matching credible service evidence. O3 records the missed deadline.",
                         "Credible service evidence is absent on a reachable branch. An accurate reading of zero does not establish production.",
                         specific if code in ("M5", "M13") else None),
        "O7": projection("complete_contract", "The bound full contract holds.", REASONS["H2"] if late else
                         "The checked negated-contract diamond refutes universal composition in this model.", violation),
        "O8": cost,
    }
    if not all(s["evidence_implies_correspondence"] for s in terminal):
        raise ValueError(f"Unexpected correspondence failure in {code}")
    return results


def assessment(group, variant, code, model, fixed, hydro, trace):
    source = variant["source_record"]
    proofs = variant["proofs"]
    references = {p["theorem"]: {"model": p["formal_artifact"], "record": p["proof_record"]} for p in proofs}
    finite = audit_finite(model) if model else None
    obligations = projected_obligations(code, finite, references, fixed)
    record = {
        "case_id": group["case"], "subcase": code, "domain": GROUPS[group["case"]][0],
        "procedure": model.procedure.procedure_id if model else chp.RELOAD,
        "initial_state": variant["input_state"], "dependency_assignment": variant["dependencies"],
        "hybrid_program_or_relevant_fragment": group["program_fragment"],
        "classification": variant["classification"], "classification_reason": REASONS[code],
        "claim_supported": REASONS[code], "claim_not_supported": group["claim_boundary"],
        "classification_scope": "Incident evidence for the stipulated research fixture.",
        "obligation_scope": "Encoded fixed procedure and its admitted assignments." if model else "Physical process and customer-service claim.",
        "obligations": obligations, "obligations_attempted": variant["attempted_dL_obligations"],
        "obligations_proved": variant["proved_dL_obligations"],
        "proof_record": references, "proof_hash": {p["proof_record"]: p["proof_sha256"] for p in proofs},
        "model_hash": {p["formal_artifact"]: p["archive_sha256"] for p in proofs},
        "assessment_record": source, "assessment_sha256": file_hash(ROOT / source),
        "counterexample_or_witness": variant["witness"],
    }
    if model:
        record.update(
            hybrid_program_or_relevant_fragment=program_fragment(model, group["program_fragment"]),
            premise=model.gamma, evidence_status="UNRESOLVED_INTEGRITY" if code in ("M13", "MER10") else "BOUND_FIXTURE_ASSUMPTIONS",
            finite_model_check=finite,
            safety_property="safe=1 (sampled gate, speed and relay-permitted contact)" if hydro else
                            "safe=1 (initial and all three sampled flow, pressure, trip and pH conditions)",
            physical_service_property="service=1 (running, closed contact and MW >= 1 at all three ordered samples)" if hydro else
                                      "physical=1 (q >= 5 L/s, pressure <= 90 psi, trip clear and normal pH)",
            observation_property={"production": model.evidence, "correspondence_given_production": model.correspondence},
            deadline_or_horizon={"clock_unit": "100 ms", "deadline_tick": int(model.initial["deadline"]),
                                 "scheduled_boundary": model.boundary},
        )
        if code == "H1":
            record["counterexample_or_witness"] = {"disabled_stage": "actor", "first_assignment": "request", "terminal_paths": 0}
        if hydro:
            path = "milestone2/evidence/merwin_plant_reduction.json"
            record["plant_reduction"] = {"source": path, "sha256": file_hash(ROOT / path)}
    else:
        bundle = trace["bundles"][chp.NOMINAL]
        for key, value in obligations.items():
            if key != "O8":
                value["evidence"]["trace"] = "trace_evidence"
        record.update(premise="Reviewed compatible backup and witnessed benign runtime in the selected device fixture.",
                      safety_property=None, physical_service_property="Physical CHP output and delivery of customer heat or electricity (unbound).",
                      observation_property="Credible process-output and customer-supply measurements (unbound).",
                      deadline_or_horizon=None, evidence_status="OBSERVED_IN_TRACE",
                      milestones={k: variant[k] for k in ("device", "process", "customer_service")},
                      trace_evidence={"record": str(chp.EVIDENCE.relative_to(ROOT)), "sha256": file_hash(chp.EVIDENCE),
                                      "bundle": chp.NOMINAL, "input_sha256": bundle["input_sha256"], "probe": bundle["probe"],
                                      "cyber_trust": bundle["terminal"]["cyber_trust"]})
    return record


def build_matrix():
    canonical, matrix = checked_sources()
    models = {c.name: c for c in formal.nominal_cases()[:3]}
    models.update({c.name: c for c, _ in formal.witness_cases()})
    models["H1"] = formal.water_case("H1", formal_model.build_model(hand.CASES[1].snapshot()["hand"]))
    trace = formal_reports.load(chp.EVIDENCE)
    groups = []
    for group in canonical:
        label = group["case"]
        domain, order, artifact, hard, witness, boundary = GROUPS[label]
        if set(order) != group["variants"].keys():
            raise ValueError(f"Subcases in {label} differ from the published records")
        variants = []
        for code in order:
            fixed = [r for r in matrix["fixed_procedure_rows"] if r["case"] == code]
            variants.append(assessment(group, group["variants"][code], code, models.get(code), fixed, code.startswith("MER"), trace))
        groups.append({"case_id": label, "domain": domain, "assessments": variants,
                       "table": {"formal_artifact": artifact, "hard_obligations": hard, "witness": witness,
                                 "result": [v["classification"] for v in variants], "claim_boundary": boundary}})
    return {
        "schema_version": 3,
        "method": "Nominal rows cite checked dL theorems. A finite_model_check evaluates the exact rational guarded assignments that emit each archive. Each obligation identifies its method. Relative paths start at procedure_formalism.",
        "scope": "Obligation statuses concern the bound model. Classification concerns the incident under its stated evidence. REFUTED O7 on a widened relation can coexist with UNKNOWN incident integrity. No service theorem was attempted for CHP.",
        "timing": "O3 binds the assessment clock. O5 and O6 describe terminal physical service and corresponding evidence. O7 is the full deadline-bearing contract. An actual delivery failure state is distinct from a recorded persistent control-flow failure.",
        "obligations_attempted_and_proved": "These lists name checked dL archive entries, including diamonds proving counterexamples. They are distinct from the statuses of the corresponding assurance goals.",
        "cases": groups,
    }


def render_table(matrix):
    lines = [r"% Generated from representative_case_matrix.json by paper_v3.representative.",
             r"\begin{table*}[t]", r"\caption{Proofs, witnesses and claim boundaries for the six representative cases. Results use the evidence stipulated for each subcase.}\label{tab:canonical}",
             r"\small\setlength{\tabcolsep}{3.5pt}",
             r"\begin{tabularx}{\textwidth}{@{}l Y l Y l Y@{}}", r"\toprule",
             r"Case & Formal artifact & Hard obligations & Witness or counterexample & Result & Claim boundary \\", r"\midrule"]
    styles = {"PROVED": r"\proved{}", "REJECTED": r"\rejected{}", "UNKNOWN": r"\undecided{}"}
    for g in matrix["cases"]:
        t = g["table"]
        codes = [a["subcase"] for a in g["assessments"]]
        # A stack keeps each status aligned with its subcase without a wide column.
        result = r"\begin{tabular}[t]{@{}l@{}}" + r"\\".join(
            code + " " + styles[value] for code, value in zip(codes, t["result"])) + r"\end{tabular}"
        cells = [g["case_id"], t["formal_artifact"], t["hard_obligations"], t["witness"], result, t["claim_boundary"]]
        lines.append(" & ".join(cells) + r" \\")
    return "\n".join([*lines, r"\bottomrule", r"\end{tabularx}", r"\end{table*}", ""])


def render_doc(matrix):
    lines = [
        "# Representative formal cases", "",
        "The [case matrix](../results/paper_v3/representative_case_matrix.json) records ten fixture assessments in six groups. The decision concerns the evidence for the stipulated incident. The O1–O8 columns concern the bound model. In particular, M13 and MER10 admit both a successful and an adverse execution while leaving the actual incident unresolved.", "",
        "| Case | Assessment | O1 | O2 | O3 | O4 | O5 | O6 | O7 | O8 | Incident |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for group in matrix["cases"]:
        for a in group["assessments"]:
            cells = [group["case_id"], a["subcase"], *(r["status"] for r in a["obligations"].values()), a["classification"]]
            lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "## How to read the obligations", "",
                  "O1 has a concrete valuation for the encoded premises. O2 checks that the fixed procedure can execute. O3 combines continuation at every admitted semantic prefix with arrival at the required boundary or persistent failure. O4 checks sampled safety. O5 checks the terminal physical service predicate on executions without an explicit persistent failure. O6 checks both production of credible evidence and its correspondence to the physical measurement. O7 checks the original, deadline-bearing composition. O8 applies to the separate cost fixtures.", "",
                  "For nominal M0, H0 and MER0, O4, O5 and O7 refer to conjuncts of the same composed proof. O6 also has a checked full-program projection that explicitly asserts evidence production. O3 joins a checked boundary box to the complete finite-prefix audit. For enabled mutations, each component marked PROVED by finite model checking was evaluated on every reachable exact rational terminal state. Each failed universal goal has an admitted counterexample. The JSON distinguishes dL proof records, finite checks, and trace evidence. Model hashes digest the complete archive. Proof hashes digest the individual theorem records.", ""])
    for group in matrix["cases"]:
        lines.extend([f"## {group['case_id']} · {group['domain']}", ""])
        for a in group["assessments"]:
            refs = a["proof_record"]
            if a["subcase"] in ("M0", "H0", "MER0"):
                theorem = next(t for t in refs if t.endswith("_end_to_end"))
            else:
                theorem = next((t for t in refs if t.endswith(("_specific_witness", "_disabled"))), None)
            citation = (f"[Checked theorem](../{refs[theorem]['record']})" if theorem else
                        f"[Device observations](../{a['trace_evidence']['record']})")
            lines.append(f"**{a['subcase']} · {a['classification']}.** {a['classification_reason']} {citation}.")
            lines.append("")
        if group["case_id"] == "S4":
            lines.extend(["H1 has a concrete initial valuation, but its actor resource disables the first transition. H1’s postcondition rows are inapplicable after O2 fails. H2 reaches the positive terminal O5 and O6 predicates at tick four. O3 and the bound O7 contract require tick three.", ""])
        elif group["case_id"] in ("S2", "S3", "S5"):
            lines.extend(["On the zero-output path, the trustworthy observer reports zero. The evidence implication holds, but the required positive evidence is absent.", ""])
    lines.extend(["## Reproduction", "",
                  "From the implementation repository, run the following command. The optional table argument writes the proof-to-claim table into the adjacent paper checkout.", "",
                  "```sh", "python3 -m recovery_experiment.procedure_formalism.paper_v3.representative --table ../redundancy-analysis-paper-dsn-27/figures/proof-claims-v3.tex", "```", ""])
    return "\n".join(lines)


def generate(output=MATRIX, doc=DOC, table=None):
    matrix = build_matrix()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    doc.write_text(render_doc(matrix))
    if table:
        table.write_text(render_table(matrix))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=MATRIX)
    parser.add_argument("--doc", type=Path, default=DOC)
    parser.add_argument("--table", type=Path)
    args = parser.parse_args()
    generate(args.output, args.doc, args.table)
