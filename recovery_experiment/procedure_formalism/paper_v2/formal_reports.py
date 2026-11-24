"""Generate the obligation matrix and six canonical records from checked proof files."""

import argparse
import json
from pathlib import Path

from ..milestone2 import cost, hand, merwin
from ..milestone2.proofs import JAR_SHA256, digest, read_record
from .formal import EVIDENCE, RESULTS, ROOT, audit_prefixes, nominal_cases, profiles, remote, witness_cases


def load(path):
    return json.loads(path.read_text())


def relative(path):
    return str(path.relative_to(ROOT))


def proof_source(folder, archive, record, model, names, negative=False):
    archive_path = folder / "models" / (archive + ".kyx")
    source = archive_path.read_bytes()
    entries = model.entries(negative)
    if (source != model.archive(violation=negative).encode() or record["archive_sha256"] != digest(source)
            or record["return_code"] != 0 or record["status"] != "PROVED" or set(entries) != set(record["obligations"])):
        raise ValueError(f"Archive/record mismatch for {archive}")
    sources = {}
    for key in names:
        row = record["obligations"][key]
        path = folder / "proof_records" / archive / (key + ".kyp")
        raw = path.read_bytes()
        if (row["status"] != "PROVED" or digest(raw) != row["proof_sha256"] or
                entries[key].strip().encode() not in raw or f'Lemma "user/{model.title(key)}".'.encode() not in raw):
            raise ValueError(f"Proof/entry mismatch for {archive}.{key}")
        sources[key] = {"formal_artifact": relative(archive_path), "theorem": model.title(key),
                        "proof_record": relative(path), "proof_sha256": row["proof_sha256"],
                        "archive_sha256": record["archive_sha256"], "tactic_ms": row["duration_ms"]}
    return sources


def historical_sources():
    verification = load(ROOT / "proof_records/verification.json")
    if verification["jar_sha256"] != JAR_SHA256:
        raise ValueError("Unrecognized historical prover release")
    out = {}
    for i in (0, 5, 13):
        model = remote(i)
        code = f"M{i}"
        rec = verification["models"][model.sha256]
        out[code] = proof_source(ROOT, code, rec, model, rec["obligations"], negative=i != 0)
    plan2, plan3 = cost.plans(cost.Context())
    for case, profile in (("H0", hand.profiles()[0]), ("MER0", merwin.profile(0)),
                          ("MER6", merwin.profile(6)), ("MER10", merwin.profile(10)),
                          ("P2", cost.proof_profile(plan2)), ("P3", cost.proof_profile(plan3)),
                          ("Hand mutations", hand.profiles()[1])):
        rec = read_record(profile)
        if rec is None:
            raise ValueError(f"Unverified historical {case}")
        out[case] = proof_source(ROOT / "milestone2/evidence", profile.name, rec, profile, rec["obligations"])
    return out


CLAIMS = {
    "O1": "At least one valuation satisfies the incident assumptions.",
    "O2": "An execution reaches the end of the specified bounded program from each admitted initial state.",
    "O3": "Admitted semantic prefixes extend to the scheduled boundary in the nominal model.",
    "O4": "All covered physical states meet the case safety contract.",
    "O5": "Physical service holds over the domain-specific sample set or service interval.",
    "O6": "The procedure produces credible observations matching the measured physical values.",
    "O7": "Every completed execution meets safety, physical service and evidence requirements on time.",
    "O8": "The exact component costs and weighted identity hold for all nonnegative coefficients.",
}


def positive_matrix(current, original):
    rows = []
    for case in nominal_cases():
        code = case.name
        historical = original[code]
        costed = code in ("P2", "P3")
        e2e = "composition" if costed else "end_to_end"
        binding = {"O1": (current[code]["O1_premises"], "Concrete premise witness."),
                   "O2": (historical["nonvacuity" if costed else "execution_witness"],
                          "Diamond with stronger terminal service postcondition."),
                   "O3": (current[code]["O3_boundary"], "Deadline box and exhaustive semantic-prefix successor check."),
                   "O4": (historical[e2e], "Safety conjunct of the bound composition proof."),
                   "O5": (historical[e2e], "Physical-service conjunct of the bound composition proof."),
                   "O6": (current[code]["O6_correspondence"], "Full-program box for evidence and its matching readings."),
                   "O7": (historical[e2e], "Bound end-to-end box.")}
        if costed:
            binding["O8"] = (historical[e2e], "Weighted identity and components in the bound end-to-end box.")
        for label, claim in CLAIMS.items():
            row = {"case": code, "procedure": case.procedure.procedure_id, "obligation": label, "paper_claim": claim}
            if label in binding:
                ref, inference = binding[label]
                row.update(ref, status="PROVED", justification=inference, unresolved_reason=None)
            else:
                row.update(status="NOT_APPLICABLE", formal_artifact=None, proof_record=None, tactic_ms=None,
                           unresolved_reason="No common-context cost contract specified.")
            if label == "O3":
                row["prefix_totality"] = audit_prefixes(case)
            if costed and label in ("O4", "O5", "O8"):
                row["continuous_phase_lemma"] = historical["rate_integral"]
            if code == "MER0" and label in ("O3", "O4", "O5", "O7"):
                row["plant_reduction"] = "milestone2/evidence/merwin_plant_reduction.json"
            rows.append(row)
    return rows


def canonical_records(current, original):
    remotes = load(ROOT / "results/attleboro_mutation_matrix.json")
    remote_rows = {r["mutation"]: next(a for a in r["assessments"] if a["procedure_id"] == remote(0).procedure.procedure_id)
                   for r in remotes if r["mutation"] in ("M0", "M5", "M13")}
    source_dir = ROOT / "results/milestone2"
    hands = {r["scenario"]: r for r in load(source_dir / "attleboro_hand_mutations.json")["rows"]}
    hydros = {r["scenario"]: r for r in load(source_dir / "merwin_mutations.json")["rows"] if r["procedure"] == merwin.ID}
    chp = next(r for r in load(source_dir / "chp_fail_closed_results.json")["rows"] if r["scenario"] == "CHP0")
    interpretations = [
        ("S1", "M0", "Trusted output is copied to the drive; the stopped pump advances through three mandatory scans.",
         "Sampled safety, request-to-water service and matching observations at deadline.",
         "Continuous hydraulics, sustained customer supply, current-site meter integrity and staffing are outside this model."),
        ("S2", "M5", "After controller acceptance, choose a persistent delivered bit from {0,1}.",
         "An allowed suppressed delivery has output one, delivered zero and actual and observed flow zero at the deadline.",
         "The counterexample refutes the specified universal guarantee. It does not estimate frequency or imply all executions fail."),
        ("S3", "M13", "Union the nominal output-copy relation with the bounded adverse delivery relation.",
         "A violating delivery is possible in the widened model. The nominal alternative remains permitted.",
         "Actual delivery integrity is unknown. A possible adverse choice cannot settle which incident occurred."),
        ("S4", "H0 H1 H2", "Local readiness and selector govern the panel; powered pump, trip path and observer are shared.",
         "Ready at tick zero establishes service. An absent actor disables the procedure. One tick late reaches service after the deadline.",
         "No installed-site staffing or response-time bound follows from the authority record."),
        ("S5", "MER0 MER6 MER10", "Close demand, actual electrical contact and generated MW occupy distinct slots.",
         "Nominal contact and coupled generation establish three credible samples. With known failed contact generation stays zero. Unknown integrity permits that adverse outcome.",
         "The theorem uses a reduced sampled plant, pinned forcing and synchronization readings, and an ideal grid after contact."),
        ("S6", "CHP0", "Reset, boot eligibility, reviewed backup load and benign logic execution reach a device milestone.",
         "The bounded fixture lifecycle has an independent benign execution witness.",
         "Process readiness, physical output, cyber trust and customer supply lack a complete contract or measurements."),
    ]
    variants = {}
    for key in ("M0", "M5", "M13"):
        r = remote_rows[key]
        witness_keys = ("accepted","output","delivered","flow1","flow2","flow3","pressure","observed","trusted","fresh","t")
        variants[key] = {"input_state": r["initial_state"], "dependencies": r["dependency_states"],
                         "witness": {k:r["execution_witness"][k] for k in witness_keys}, "classification":r["result"],
                         "source_record":"results/attleboro_mutation_matrix.json"}
    for key in ("H0","H1","H2"):
        r = hands[key]
        variants[key] = {"input_state":{**r["initial_state"],"ready_tick":r["ready_tick"],"deadline_tick":r["deadline_tick"]},
                         "dependencies":r["dependency_states"],"witness":r["witness"],"classification":r["B4"],
                         "source_record":"results/milestone2/attleboro_hand_mutations.json"}
    for key in ("MER0","MER6","MER10"):
        r = hydros[key]
        variants[key] = {"input_state":merwin.model(int(key[3:]))[1],"dependencies":r["dependency_states"],
                         "witness":r["execution"],"classification":r["B4"],
                         "source_record":"results/milestone2/merwin_mutations.json"}
    variants["CHP0"] = {"input_state":chp["evidence_bundle"],"dependencies":chp["milestones"],
                        "witness":{"fixture_device":chp["published_device_lifecycle_assessment"],
                                   "benign_logic":chp["published_benign_runtime_assessment"]},
                        "classification":chp["B4"],"device":chp["device_recovery"],
                        "process":chp["process_recovery"],"customer_service":chp["customer_service"],
                        "source_record":"results/milestone2/chp_fail_closed_results.json"}
    for key, variant in variants.items():
        if key in ("M0", "H0", "MER0"):
            variant["proofs"] = [*original[key].values(), *current[key].values()]
        elif key == "H1":
            variant["proofs"] = [original["Hand mutations"]["H1_disabled"]]
        elif key == "CHP0":
            variant["proofs"] = []
            variant["missing_obligations"] = ["Physical plant safety", "Process execution and service", "Credible customer delivery"]
        elif key == "H2":
            variant["proofs"] = [original["Hand mutations"]["H2_violation"], *current[key].values()]
        else:
            variant["proofs"] = [*original[key].values(), *current[key].values()]
        variant["attempted_dL_obligations"] = [r["theorem"] for r in variant["proofs"]]
        variant["proved_dL_obligations"] = list(variant["attempted_dL_obligations"])
    return [{"case":label,"program_fragment":fragment,"what_is_established":supported,"claim_boundary":stop,
             "variants":{k:variants[k] for k in keys.split()}} for label,keys,fragment,supported,stop in interpretations]


def generate(output):
    idx = load(EVIDENCE / "proof_index.json")
    if idx["jar_sha256"] != JAR_SHA256:
        raise ValueError("Unrecognized prover release")
    current = {}
    for profile in profiles():
        rec = idx["profiles"][profile.name]
        current[profile.name.removeprefix("v2_")] = proof_source(EVIDENCE, profile.name, rec, profile, rec["obligations"])
    old = historical_sources()
    matrix = positive_matrix(current, old)
    extra = {case.name: {"witness_postcondition": post, "prefix_totality":audit_prefixes(case),
                         **current[case.name]["specific_witness"]} for case, post in witness_cases()}
    result = {"interpretation":"Rows reuse some theorems. Tactic milliseconds belong to the identified theorem, and must not be summed across rows.",
              "fixed_procedure_rows": matrix, "specific_reachability_witnesses": extra,
              "new_dL_theorems":sum(len(entries) for entries in current.values())}
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in (("proof_obligation_matrix",result),("canonical_semantic_cases",canonical_records(current,old))):
        (output / (name+".json")).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=RESULTS)
    generate(parser.parse_args().output)
