"""Reproduce the baseline contingency and finite water-policy comparison."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from ..milestone2.cost import COSTS, UNITS, WEIGHTS

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "results" / "milestone2"
OUTPUT = PACKAGE / "results" / "paper_v2"
BASELINES = ("B1", "B2", "B3")
OUTCOMES = ("PROVED", "REJECTED", "UNKNOWN")
DECISIONS = {"ACCEPT": "retained", "DECLINE": "not_retained",
             "UNRESOLVED": "not_retained", "INAPPLICABLE": "inapplicable"}

# These interpret the recorded mutation only when B4 fails to establish service.
# Remote has several candidates in the same mutation and supplies its own per-candidate stage.
STAGES = {
    "attleboro_hand": {"H1": "actor", "H2": "actor", "H3": "authority", "H4": "actuator",
                       "H5": "actuator", "H6": "protection", "H7": "plant", "H8": "observation",
                       "H9": "observation", "H10": "power"},
    "merwin": {"MER1": "actor", "MER2": "communication", "MER4": "auxiliary permissives",
               "MER5": "synchronization", "MER6": "delivery", "MER7": "plant", "MER8": "observation",
               "MER9": "actuator", "MER10": "dependency evidence"},
    "controlled_cost": {"C1": "controller", "C2": "actor", "C3": "power", "C4": "observation",
                        "C6": "timing", "C7": "plant"},
    "chp": {"CHP0": "process evidence", "CHP1": "backup", "CHP2": "backup", "CHP3": "backup",
            "CHP4": "device", "CHP5": "process evidence", "CHP6": "process permissives",
            "CHP7": "customer evidence", "CHP8": "dependency evidence"},
}


def load(name):
    return json.loads((SOURCE / (name + ".json")).read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def contingency(group, rows):
    result = []
    for baseline in BASELINES:
        cells = Counter((DECISIONS[r[baseline]], r["B4"]) for r in rows)
        line = {"group": group, "baseline": baseline, "assessments": len(rows)}
        for decision in ("retained", "not_retained", "inapplicable"):
            for outcome in OUTCOMES:
                line[f"{decision}_{outcome.lower()}"] = cells[decision, outcome]
        line["applicable"] = sum(r[baseline] != "INAPPLICABLE" for r in rows)
        line["proved_omission"] = cells["not_retained", "PROVED"] + cells["inapplicable", "PROVED"]
        result.append(line)
    return result


def baselines(output):
    rows = load("cross_domain_baselines")["rows"]
    remote = json.loads((SOURCE.parent / "attleboro_mutation_matrix.json").read_text())
    remote_stage = {(m["mutation"], a["procedure_id"]): a["first_stage"]
                    for m in remote for a in m["assessments"]}
    families, stages = defaultdict(list), defaultdict(list)
    details = []
    for row in rows:
        if row["B4"] not in OUTCOMES:
            raise ValueError(row["B4"])
        family, case, proc = row["family"], row["scenario"], row["procedure"]
        if row["B4"] == "PROVED":
            stage = "service established"
        elif family == "attleboro_remote_study":
            stage = remote_stage[case, proc]
        else:
            stage = STAGES[family][case]
        families[family].append(row)
        stages[stage].append(row)
        details.append({"family": family, "scenario": case, "procedure": proc, "stage": stage,
                        **{b: row[b] for b in (*BASELINES, "B4")}})
    identities = {(r["family"], r["scenario"], r["procedure"]) for r in rows}
    if len(identities) != len(rows):
        raise ValueError("Duplicate assessment identity")
    overall = contingency("all", rows)
    write_csv(output / "baseline_contingency.csv", overall)
    for filename, groups in (("baseline_by_case", families), ("baseline_by_failure_stage", stages)):
        write_csv(output / (filename + ".csv"), [record for key in sorted(groups)
                  for record in contingency(key, groups[key])])
    save(output / "baseline_contingency.json", {
        "source": "results/milestone2/cross_domain_baselines.json#rows",
        "unit": "one candidate procedure in a labeled scenario",
        "reference": "B4 end-to-end contract on research fixtures",
        "decision_groups": DECISIONS, "rows": details, "totals": overall,
        "stage_basis": "Remote uses first_stage per candidate. Other stages identify the decisive "
                       "dependency or evidence boundary in the recorded case-specific mutation.",
        "union_retained_by_reference": dict(Counter(r["B4"] for r in rows
                                           if any(r[b] == "ACCEPT" for b in BASELINES)))})


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def winner(margin):
    if margin > 0:
        return "P2"
    return "P3" if margin < 0 else "TIE"


def sensitivity(weights, delta, vectors):
    margin = dot(weights, delta)
    trials, ties = [], []
    for j, name in enumerate(WEIGHTS):
        for fraction in (Fraction(-1, 4), Fraction(-1, 10), Fraction(1, 10), Fraction(1, 4)):
            updated = list(weights)
            updated[j] *= 1 + fraction
            scores = [dot(updated, vector) for vector in vectors]
            difference = scores[1] - scores[0]
            if difference != dot(updated, delta):
                raise AssertionError("Vector scores disagree with the analytic boundary")
            trials.append({"coefficient": name, "relative_change": str(fraction),
                           "scores": list(map(str, scores)), "selection": winner(difference)})
        if delta[j] and weights[j]:
            change = Fraction(-margin, delta[j])
            target = weights[j] + change
            if target >= 0:
                tied = list(weights)
                tied[j] = target
                assert dot(tied, vectors[0]) == dot(tied, vectors[1])
                ties.append({"coefficient": name, "tie_value": str(target),
                             "relative_change": str(change / weights[j]),
                             "can_cross_in_same_direction": target > 0 or change > 0})
    crossing = [t for t in ties if t["can_cross_in_same_direction"]]
    nearest = min(crossing, key=lambda t: abs(Fraction(t["relative_change"])))
    simultaneous = Fraction(abs(margin), sum(abs(v * w) for v, w in zip(delta, weights)))
    return {"weights": list(weights), "signed_P3_minus_P2": margin, "selection": winner(margin),
            "perturbations": trials, "one_at_a_time_ties": ties, "closest_tie_with_crossing": nearest,
            "simultaneous_relative_infinity_norm_to_tie": str(simultaneous)}


def costs(output):
    proof = load("common_context_cost_proofs")
    selection = load("common_context_cost_selection")
    hard = load("common_context_cost_mutations")["rows"]
    nominal = sorted((r for r in hard if r["scenario"] == "C0"), key=lambda r: r["procedure"])
    if len(nominal) != 2 or len({r["context_sha256"] for r in nominal}) != 1:
        raise ValueError("The comparison needs both procedures in the same context")
    exact, vectors = [], []
    for row in nominal:
        expr = proof["nominal_expressions"][row["procedure"]]
        record = next(p for p in proof["profiles"] if p["profile"] == expr["profile"])
        obligation = record["record"]["obligations"]["composition"]
        if not record["validated"] or row["B4"] != "PROVED" or obligation["status"] != "PROVED":
            raise ValueError("Missing validated composition proof")
        vector = [expr["components"][c] for c in COSTS]
        vectors.append(vector)
        exact.append({"procedure": row["procedure"], "vector": vector, "profile": expr["profile"],
                      "source": "results/milestone2/common_context_cost_proofs.json",
                      "model_sha256": record["formal_model_sha256"], "composition": obligation,
                      "reachable": record["record"]["obligations"]["nonvacuity"]})
    save(output / "cost_exact_vectors.json", {"coordinate_order": COSTS, "units": UNITS,
         "context": selection["contexts"]["C0"], "context_sha256": nominal[0]["context_sha256"],
         "contract": "Tank volume within bounds throughout both mandatory phases; flow at least "
                     "minimum from deadline through horizon; fresh trusted final meter matches actual flow.",
         "vectors": exact})
    delta = [b - a for a, b in zip(*vectors)]
    assert delta == [3, 1, 1, -10]
    save(output / "cost_break_even.json", {"P3_minus_P2_coefficients": delta, "weight_order": WEIGHTS,
         "weight_units": ["policy points per " + u for u in UNITS],
         "P2_strictly_preferred": "10*wResource < 3*wService + wTime + wIntervention",
         "tie": "equality; retain both", "pareto_front": [n["procedure"] for n in nominal],
         "scope": "Nonnegative weights on a common hard contract, finite candidate set."})
    policies = {}
    for row in selection["rows"]:
        if row["scenario"] != "C0":
            continue
        weights = tuple(map(int, row["weights"]))
        scores = [dot(weights, v) for v in vectors]
        if scores != [int(row["cost_by_admissible_procedure"][n["procedure"]]) for n in nominal]:
            raise ValueError("Nominal policy scores differ from certified selection")
        policies[row["policy"]] = sensitivity(weights, delta, vectors)
    save(output / "cost_sensitivity.json", {"policies": policies,
         "method": "Exact rational arithmetic. Vary one coefficient at a time; ties are explicit. "
                   "Minimum strict crossing is an infimum. For simultaneous relative changes "
                   "the distance to the tie is |margin| / sum_i |delta_i*w_i|.",
         "interpretation": "Illustrative policy points. No distribution or stakeholder utility is assumed."})
    save(output / "cost_dependency_mutations.json", {"rows": [
         {k: r[k] for k in ("scenario", "procedure", "context_sha256", "B4", "reason")} for r in hard]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    baselines(args.output)
    costs(args.output)


if __name__ == "__main__":
    main()
