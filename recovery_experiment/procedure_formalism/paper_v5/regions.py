"""Exact finite checks of the bounded water schedules and hydro service polls."""

import argparse
import csv
import json
from dataclasses import replace
from fractions import Fraction
from itertools import product
from pathlib import Path

from .. import formal_model, verify
from ..formal_ir import executions, expr
from ..milestone2 import hand, merwin
from ..milestone2.merwin_reduction import checked_reduction
from ..milestone2.proofs import proved
from ..paper_v2.formal import remote


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/paper_v5"
CHECKED = "SERVICE_PROVED"
VIOLATED = "SERVICE_DEADLINE_VIOLATED"
UNSUPPORTED = "UNSUPPORTED_PARAMETER_REGION"
FLOWS = (4, 5, Fraction(32, 5), 7)


def water_schedule(model, scans):
    """Keep the first n existing plant updates and attach the original final observer."""
    if not 1 <= scans <= formal_model.SCANS:
        raise ValueError("The archived water program contains only three scans")
    stages = []
    aliases = {"q": "flow", "pressure": "p", "run": "run", "safe": "safe", "t": "tick"}
    for stage in model.stages:
        slots = stage.assignments
        if stage.name == "plant":
            end = next(i for i, op in enumerate(slots) if op.name == f"tick{scans}")
            first_alias = next(i for i, op in enumerate(slots) if op.name == "q")
            slots = slots[:end + 1] + slots[first_alias:]
        adapted = []
        for op in slots:
            # The five aliases in the archived program read its third hydraulic update.
            if op.name in aliases:
                original = aliases[op.name] + str(formal_model.SCANS)
                if op.alternatives != ((None, original),):
                    raise ValueError(f"Unexpected terminal binding for {op.name}")
                op = replace(op, alternatives=((None, aliases[op.name] + str(scans)),))
            if op.name in ("physical", "established"):
                alternatives = tuple((guard.replace(">=5", ">=minimumFlow"), value)
                                     for guard, value in op.alternatives)
                if alternatives == op.alternatives:
                    raise ValueError(f"No threshold in {op.name}")
                op = replace(op, alternatives=alternatives)
            adapted.append(op)
        stages.append(replace(stage, assignments=tuple(adapted)))
    return tuple(stages)


def water_report():
    systems = {"M0": remote(0), **{f"H{i}": formal_model.build_model(hand.CASES[i].snapshot()["hand"])
                                  for i in (0, 1, 2)}}
    if not verify.verified(systems["M0"]) or not all(proved(p) for p in hand.profiles()):
        raise ValueError("Water model or proof record differs from the verified archive")
    post = formal_model.POST.replace("q>=5", "q>=minimumFlow").replace("ready+3", "ready+scanCount")
    rows = []
    for case, model in systems.items():
        for scans in range(1, formal_model.SCANS + 2):
            program = water_schedule(model, scans) if scans <= formal_model.SCANS else None
            for deadline, minimum in product((2, 3, 4), FLOWS):
                row = {"case": case, "mandatory_scans": scans, "ready_tick": int(model.initial["ready"]),
                       "deadline_tick": deadline, "minimum_flow_lps": str(minimum), "terminal_tick": None,
                       "flow_lps": None, "pressure_psi": None, "safe": None, "fresh_matching_reading": None,
                       "result": UNSUPPORTED}
                if program is not None:
                    initial = dict(model.initial, deadline=deadline, minimumFlow=minimum, scanCount=scans)
                    states = executions(program, initial)
                    if not states:
                        row["result"] = "PREMISE_INAPPLICABLE"
                    else:
                        # Nominal resources make the complete reachable endpoint unique.
                        state, = states
                        matches = (state["trusted"] == state["fresh"] == 1 and state["observed"] == state["q"]
                                   and state["observedPressure"] == state["pressure"])
                        row.update(terminal_tick=int(state["t"]), flow_lps=str(state["q"]),
                                   pressure_psi=str(state["pressure"]), safe=bool(state["safe"]),
                                   fresh_matching_reading=matches,
                                   result=CHECKED if expr(post, state) else VIOLATED)
                rows.append(row)
    return {
        "units": {"scan": "100 ms", "deadline_origin": "request origin", "threshold": "L/s", "pressure": "psi"},
        "scope": "Nominal resources, initially stopped pump, zero initial flow and one trusted meter read at the selected terminal scan. H1 independently disables the actor.",
        "method": "Exhaustive exact rational guarded assignments for shortened schedules and a substituted minimum flow. Only the original 3-scan, 5 L/s, deadline-3 contracts have the cited dL exports. H2 has a late witness, H1 a disabled execution.",
        "sources": ["formal_model.py", "models/M0.kyx", "proof_records/M0/end_to_end.kyp",
                    "milestone2/evidence/models/attleboro-local-hand-end-to-end-recovery-v1.kyx",
                    "results/milestone2/attleboro_hand_mutations.json"],
        "boundary": {
            "domain": "positive minimum m; enabled nominal Remote or Hand; n in {1,2,3}; r is operator ready tick",
            "flow_at_scan_n_lps": "10*(1-(3/5)^(n-1))", "sample_capacities_lps": ["0", "4", "32/5"],
            "service": "n>=2 and m<=flow_at_scan_n_lps and r+n<=deadline",
            "earliest_eligible_assessment": {"0<m<=4": "r+2", "4<m<=32/5": "r+3",
                                             "32/5<m": "no supported schedule meets the minimum"},
            "longer_schedule": UNSUPPORTED,
        },
        "results": rows,
    }


def hydro_capacity(state, indices):
    """Maximum inclusive positive threshold satisfying the whole observed suffix."""
    ticks = [int(state[f"tick{i}"]) for i in indices]
    if (not state["safe"] or not state["running"] or not state["contact"] or not state["trusted"]
            or state["clock"] != state["deadline"] or state["contactClock"] > ticks[0]
            or any(a >= b for a, b in zip(ticks, ticks[1:]))):
        return Fraction(0)
    if not all(state[f"fresh{i}"] and state[f"observed{i}"] == state[f"mw{i}"] for i in indices):
        return Fraction(0)
    return min(state[f"mw{i}"] for i in indices)


def hydro_report():
    if not checked_reduction():
        raise ValueError("Pinned Merwin reduction did not authenticate")
    rows = []
    branches = {}
    for i in (0, 6, 8, 10):
        if not proved(merwin.profile(i)):
            raise ValueError(f"Missing or changed proof record for MER{i}")
        _, initial, stages = merwin.model(i)
        states = executions(stages, initial)
        if not states:
            raise ValueError(f"No terminal execution for MER{i}")
        case = f"MER{i}"
        branches[case] = [{"contact": int(s["contact"]), "running": int(s["running"]), "safe": int(s["safe"]),
                           "ticks": [int(s[f"tick{j}"]) for j in (1, 2, 3)],
                           "generation_mw": [str(s[f"mw{j}"]) for j in (1, 2, 3)],
                           "fresh": [int(s[f"fresh{j}"]) for j in (1, 2, 3)],
                           "readings_mw": [str(s[f"observed{j}"]) for j in (1, 2, 3)]} for s in states]
        for count in (1, 2, 3, 4):
            common = {"case": case, "required_polls": count, "deadline_tick": initial["deadline"]}
            def interval(low, high, status):
                return {**common, "minimum_mw_exclusive": str(low),
                        "maximum_mw_inclusive": None if high is None else str(high), "result": status}
            if count > len(branches[case][0]["ticks"]):
                rows.append(interval(0, None, UNSUPPORTED))
                continue
            capacities = [hydro_capacity(s, range(4 - count, 4)) for s in states]
            lowest, highest = min(capacities), max(capacities)
            if lowest > 0:
                rows.append(interval(0, lowest, CHECKED))
            if highest > lowest:
                rows.append(interval(lowest, highest, "UNKNOWN_CONTACT_INTEGRITY"))
            rows.append(interval(highest, None, "SERVICE_CONTRACT_VIOLATED"))
    return {
        "scope": "Pinned startup trajectory, same terminal poll, positive requested generation in MW.",
        "method": "Exact rational contract projection of all guarded executions. An inclusive upper endpoint is the minimum generation over the required suffix when safe, running, in contact, correctly timed, and freshly observed. Otherwise the branch supports no positive threshold. A null upper bound is unbounded.",
        "poll_selection": "Last k consecutive service polls ending at the original horizon. k=4 is unsupported.",
        "sources": ["milestone2/merwin.py", "milestone2/merwin_reduction.py",
                    "milestone2/fixtures/merwin_remote_forcing.csv", "milestone2/evidence/merwin_plant_reduction.json",
                    "results/milestone2/merwin_proof_summary.json", "results/milestone2/merwin_mutations.json"],
        "forcing_region": {"status": "UNSUPPORTED_BY_CURRENT_MODEL",
                           "reason": "The reduction binds one input series and synchronization observation sequence. No justified uncertainty intervals or correlations bind new input trajectories."},
        "branches": branches, "results": rows,
    }


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, report in (("attleboro_service_region", water_report()), ("merwin_threshold_region", hydro_report())):
        (output / (name + ".json")).write_text(json.dumps(report, indent=2) + "\n")
        with (output / (name + ".csv")).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(report["results"][0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(report["results"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    generate(parser.parse_args().output)
