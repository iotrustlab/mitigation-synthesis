"""Distinct dL projections of the published fixed-procedure programs."""

import argparse
from dataclasses import dataclass
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .. import verify
from ..attleboro import attleboro
from ..evaluation import MUTATIONS
from ..formal_ir import hybrid_program
from ..formal_model import build_model
from ..milestone2 import cost, hand, merwin
from ..milestone2.proofs import JAR_SHA256, Obligation, Profile, digest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "paper_v2" / "formal_evidence"
RESULTS = ROOT / "results" / "paper_v2"


@dataclass
class Case:
    name: str
    initial: dict
    stages: tuple
    procedure: object
    boundary: str
    evidence: str
    correspondence: str
    weights: tuple = ()

    @property
    def gamma(self):
        terms = [f"{k}={v}" for k, v in self.initial.items()]
        return " & ".join(terms + [f"{w}>=0" for w in self.weights])

    def modal(self, label, post, diamond=False):
        ops = [op for stage in self.stages for op in stage.assignments]
        start, end = ("<", ">") if diamond else ("[", "]")
        formula = f"({self.gamma}) -> {start}{hybrid_program(ops)}{end} ({post})"
        return Obligation(label, (*self.initial, *self.weights, *(op.name for op in ops)), formula)

    def nominal_obligations(self):
        witness = {**self.initial, **dict.fromkeys(self.weights, 0)}
        setup = " ".join(f"{k}:={v};" for k, v in witness.items())
        return (
            Obligation("O1_premises", tuple(witness), f"<{setup}> ({self.gamma})", "chase(1); QE"),
            self.modal("O3_boundary", self.boundary),
            self.modal("O6_correspondence", f"({self.evidence} -> ({self.correspondence})) & {self.evidence}"),
        )


def remote(i):
    mutation = MUTATIONS[i]
    return build_model(attleboro(statuses=mutation.dependencies, initial_state=mutation.states)["remote"])


def water_case(name, model):
    return Case(name, model.initial, model.stages, model.procedure, "t=deadline & t=ready+3",
                "established=1", "physical=1 & trusted=1 & fresh=1 & observed=q & observedPressure=pressure")


def hydro_case(i):
    proc, initial, stages = merwin.model(i)
    readings = [f"fresh{k}=1 & observed{k}=mw{k} & mw{k}>=1" for k in range(1, 4)]
    return Case(f"MER{i}", initial, stages, proc, "clock=deadline & contactClock<=tick1 & tick1<tick2 & tick2<tick3",
                "credible=1", " & ".join(["service=1", "trusted=1", *readings]))


def cost_case(plan):
    return Case("P2" if plan.procedure.procedure_id == cost.A_ID else "P3",
                plan.initial, plan.stages, plan.procedure, "elapsed=horizon & active>=0 & start>=0",
                "credible=1", "trusted=1 & fresh=1 & reading=q & q>=minimum", cost.WEIGHTS)


def nominal_cases():
    return [water_case("M0", remote(0)), water_case("H0", build_model(hand.CASES[0].snapshot()["hand"])),
            hydro_case(0), *(cost_case(p) for p in cost.plans(cost.Context()))]


def witness_cases():
    suppressed = "output=1 & delivered=0 & q=0 & observed=0 & t=deadline & established=0"
    return [
        (water_case("M5", remote(5)), suppressed),
        (water_case("M13", remote(13)), suppressed),
        (water_case("H2", build_model(hand.CASES[2].snapshot()["hand"])), "ready=1 & t>deadline & physical=1"),
        (hydro_case(6), "closeCmd=1 & contact=0 & mw1=0 & mw2=0 & mw3=0 & service=0"),
        (hydro_case(10), "closeCmd=1 & contact=0 & mw1=0 & mw2=0 & mw3=0 & service=0"),
    ]


def profiles():
    result = []
    for case in nominal_cases():
        result.append(Profile("v2_"+case.name, case.nominal_obligations(),
                              len(case.procedure.required_dependencies), 0, "case boundary"))
    for case, post in witness_cases():
        result.append(Profile("v2_"+case.name, (case.modal("specific_witness", post, True),),
                              len(case.procedure.required_dependencies), 0, "case boundary"))
    return result


def audit_prefixes(case):
    """Check successors for every reachable *semantic* finite-assignment prefix."""
    # Arbitrary policy coefficients appear exclusively in the final unguarded J assignment.
    # Their value does not control any predecessor or the availability of a successor.
    states = [{**{n: Fraction(v) for n, v in case.initial.items()}, **dict.fromkeys(case.weights, Fraction(0))}]
    final_assignment = case.stages[-1].assignments[-1]
    seen = 0
    widths = []
    for stage in case.stages:
        for op in stage.assignments:
            if case.weights:
                weight_tokens = set(re.findall(r"\b\w+\b", op.relation())) & set(case.weights)
                if weight_tokens and (op is not final_assignment or op.name != "J" or
                                      len(op.alternatives) != 1 or op.alternatives[0][0] is not None):
                    raise ValueError("Symbolic weights affect branching")
            successors = []
            for state in states:
                seen += 1
                values = op.values(state)
                if not values:
                    raise ValueError(f"Feasible prefix silently blocks at {case.name}.{op.name}")
                successors.extend({**state, op.name: v} for v in values)
            states = successors
        widths.append({"stage": stage.name, "prefixes_at_exit": len(states)})
    return {"reachable_prefixes_checked": seen, "blocked_prefixes": 0, "terminal_paths": len(states),
            "stage_widths": widths, "scope": "All valuations allowed by this case's guarded semantic assignments."}


def replay(output, jar, z3, java):
    if digest(jar.read_bytes()) != JAR_SHA256:
        raise ValueError("Incorrect KeYmaera X release")
    output.mkdir(parents=True, exist_ok=True)
    records = {}
    with tempfile.TemporaryDirectory(prefix="formal-v2-") as folder:
        tmp = Path(folder)
        config = tmp / ".keymaerax"
        config.mkdir()
        (config / "solver").symlink_to(z3)
        for profile in profiles():
            rec = verify._solve(profile, profile.name, False, jar, z3, java, tmp, output)
            rec.pop("kind")
            records[profile.name] = rec
            print(profile.name, rec["status"], rec["wall_seconds"], flush=True)
    index = {"jar_sha256": JAR_SHA256, "solver_sha256": digest(z3.read_bytes()),
             "input_snapshot": "fa719386e782766f01a8db770d7b128ccba3ad99",
             "java_version": verify._version([java, "-version"]),
             "solver_version": verify._version([str(z3), "-version"]),
             "toolchain": "KeYmaera X 5.1.1 / Z3. One fresh isolated cache for these projection and witness proofs.",
             "profiles": records}
    (output / "proof_index.json").write_text(json.dumps(index, indent=2, sort_keys=True)+"\n")
    return all(r["status"] == "PROVED" for r in records.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jar", type=Path, default=Path(os.environ.get("KEYMAERAX_JAR", "keymaerax.jar")))
    parser.add_argument("--z3", type=Path, default=Path(shutil.which("z3") or "z3"))
    parser.add_argument("--java", default=shutil.which("java") or "java")
    args = parser.parse_args()
    raise SystemExit(0 if replay(args.output, args.jar.resolve(), args.z3.resolve(), args.java) else 1)
