"""Checked partial evaluation of the trace-conditioned Merwin plant.

Retain gate dynamics, turbine/generator conversion and off-grid inertia. The
rounded 100 ms forcing grid uses left-held gate orders and hydraulic pressure.
Sync decisions sample the published phase/voltage observations at poll ticks.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from io import StringIO
from math import isqrt
from pathlib import Path
import shutil
import subprocess
import time

from .proofs import BASE, EVIDENCE, ROOT, digest, object_hash
import json


S = 1_000_000
FIXTURE = ROOT / "fixtures" / "merwin_remote_forcing.csv"
TRACE_SHA256 = "7cfe891e497d6f27100f385ec7e19e4ca6d9face9077c1d1cd7ff1a14007b2fa"
CSV_FIELDS = (
    "tick",
    "gate_milli_pct",
    "pressure_milli_kpa",
    "phase_milli_deg",
    "voltage_milli_pu",
    "hcc_start",
)
RECORD = EVIDENCE / "merwin_plant_reduction.json"


def projection(trace):
    """Portable extraction from the pinned OpenPLC capture, excluding power and speed."""
    if digest(trace.read_bytes()) != TRACE_SHA256:
        raise ValueError("Unexpected Merwin trace bytes")
    out = StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    with trace.open() as handle:
        rows = list(csv.DictReader(handle))
    start = datetime.fromisoformat(rows[0]["timestamp_utc"])
    for row in rows[:260]:
        delta = datetime.fromisoformat(row["timestamp_utc"]) - start
        ticks = (delta.seconds * S + delta.microseconds + 50_000) // 100_000
        values = [
            int(Decimal(row[key]) * 1000)
            for key in ("HY_Gate_Cmd", "HY_Pressure", "HY_Phase_Diff_deg", "HY_Gen_Voltage_pu")
        ]
        writer.writerow((ticks, *values, int(row["MER_HCC_Start_Cmd"])))
    return out.getvalue()


def _trajectory(rows):
    gate = speed = settled = first_settle = 0
    samples = []
    points = {}
    for a, b in zip(rows, rows[1:]):
        pressure = a["pressure_milli_kpa"]
        command = a["gate_milli_pct"] * 1000
        root = isqrt(pressure * S * S // 9810)
        for tick in range(a["tick"] + 1, b["tick"] + 1):
            old_gate, old_speed = gate, speed
            step = max(-10 * S, min(10 * S, command - gate))
            gate = max(0, min(100 * S, (10 * gate + step) // 10))
            flow = min(100 * S, gate * root // (10 * S))
            torque = flow * pressure * 9 // 10_000_000
            # Q>0.1 uses the off-grid Euler rotor. Otherwise use the coast law.
            speed = (7996 * speed + 25 * torque) // 8000 if flow > S // 10 else 399 * speed // 400
            speed = max(0, min(150 * S, speed))
            settled = settled + 1 if abs(speed - 100 * S) < S // 2 else 0
            if settled >= 30 and first_settle == 0:
                first_settle = tick
            samples.append((tick, old_gate, command, pressure, root, gate, flow, torque, old_speed, speed))
        points[b["tick"]] = (speed, torque, gate)
    # The controller's start latch holds after the captured pulse. A poll-level
    # synchronizer checks each available fresh phase/voltage pair once at speed.
    start = next(row["tick"] for row in rows if row["hcc_start"])

    def permissible(row):
        tick = row["tick"]
        if tick < first_settle or not first_settle:
            return False
        speed = points[tick][0]
        slip = (speed - 100 * S) * 3  # Hz * 5*S
        phase = row["phase_milli_deg"] * 1000
        v = row["voltage_milli_pu"]
        return (
            1000 <= v <= 1050
            and abs(slip) < 300_000
            and abs(5 * phase + 126 * slip) < 15 * S
            and abs(phase) <= 10 * S
        )

    close = next(row for row in rows if permissible(row))
    service_ticks = [row["tick"] for row in rows if row["tick"] > close["tick"]][:3]
    return samples, {
        "start_tick": start,
        "settled_tick": first_settle,
        "sync_tick": close["tick"],
        "phase_milli_deg": close["phase_milli_deg"],
        "voltage_milli_pu": close["voltage_milli_pu"],
        "speed_at_sync": points[close["tick"]][0],
        "max_open_speed": max(s[-1] for s in samples),
        "max_gate": max(s[5] for s in samples),
        "service_ticks": service_ticks,
        "mechanical_micro_mw": [points[t][1] for t in service_ticks],
        "horizon_ticks": rows[-1]["tick"],
    }


@lru_cache(maxsize=1)
def trajectory():
    with FIXTURE.open() as handle:
        rows = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(handle)]
    if not rows or rows[0]["tick"] != 0 or any(a["tick"] >= b["tick"] for a, b in zip(rows, rows[1:])):
        raise ValueError("Invalid hydro sample clock")
    return _trajectory(rows)


def certificate():
    """Refute any inconsistent step of the proposed integer trajectory with SMT."""
    samples, facts = trajectory()
    # Independent formulation with Euclidean integer floor and exact integer sqrt bounds.
    definition = """(set-logic ALL)
(define-fun clamp ((x Int) (lo Int) (hi Int)) Int (ite (< x lo) lo (ite (> x hi) hi x)))
(define-fun valid ((g Int)(c Int)(p Int)(r Int)(gn Int)(f Int)(m Int)(v Int)(vn Int)) Bool
(and (>= r 0) (<= (* r r 9810) (* p 1000000000000)) (< (* p 1000000000000) (* (+ r 1) (+ r 1) 9810))
 (= gn (clamp (+ g (div (clamp (- c g) (- 10000000) 10000000) 10)) 0 100000000))
 (= f (clamp (div (* gn r) 10000000) 0 100000000))
 (= m (div (* 9 p f) 10000000))
 (= vn (clamp (ite (> f 100000) (div (+ (* 7996 v) (* 25 m)) 8000) (div (* 399 v) 400)) 0 150000000))
 (<= 0 gn) (<= gn 100000000) (<= 0 vn) (<= vn 110000000)))
(assert (not (and
"""
    # Link successive states explicitly, including the initial stopped state.
    checks = []
    prior_gate = prior_speed = settled = 0
    for tick, g, c, p, r, gn, f, m, v, vn in samples:
        checks.append(
            f"(and (= {g} {prior_gate}) (= {v} {prior_speed}) (valid {g} {c} {p} {r} {gn} {f} {m} {v} {vn}))"
        )
        checks.append(f"(and (<= {gn} {facts['max_gate']}) (<= {vn} {facts['max_open_speed']}))")
        if tick <= facts["start_tick"]:
            checks.append(f"(and (= {c} 0) (= {vn} 0) (= {gn} 0))")
        new_count = settled + 1 if abs(vn - 100 * S) < S // 2 else 0
        checks.append(f"(= {new_count} (ite (and (> {vn} 99500000) (< {vn} 100500000)) (+ {settled} 1) 0))")
        if tick <= facts["settled_tick"]:
            expects = ">=" if tick == facts["settled_tick"] else "<"
            checks.append(f"({expects} {new_count} 30)")
        prior_gate, prior_speed, settled = gn, vn, new_count

    def number(n):
        return f"(- {-n})" if n < 0 else str(n)

    # Check the first successful joint controller/relay poll and the exact
    # service observations consumed by the dL stage summaries.
    with FIXTURE.open() as handle:
        rows = [{k: int(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    by_tick = {sample[0]: sample for sample in samples}
    for i, row in enumerate(rows):
        tick = row["tick"]
        if tick <= facts["start_tick"]:
            checks.append(f"(= {row['hcc_start']} {int(tick == facts['start_tick'])})")
        if tick < facts["settled_tick"] or tick > facts["sync_tick"]:
            continue
        v = by_tick[tick][-1]
        slip = f"(* 3 (- {v} 100000000))"
        phase = number(row["phase_milli_deg"])
        volt = row["voltage_milli_pu"]
        pred = f"(+ (* 5000 {phase}) (* 126 {slip}))"
        window = (
            f"(and (< (- 300000) {slip} 300000) (<= 1000 {volt} 1050) "
            f"(< (- 15000000) {pred} 15000000) (<= (- 10000) {phase} 10000))"
        )
        if tick < facts["sync_tick"]:
            checks.append(f"(not {window})")
        else:
            checks.extend(
                (
                    window,
                    f"(= {facts['speed_at_sync']} {v})",
                    f"(= {facts['voltage_milli_pu']} {volt})",
                    f"(= {number(facts['phase_milli_deg'])} {phase})",
                )
            )
            for n, (sample_tick, torque) in enumerate(
                zip(facts["service_ticks"], facts["mechanical_micro_mw"]), 1
            ):
                observed_tick = rows[i + n]["tick"]
                checks.extend(
                    (f"(= {sample_tick} {observed_tick})", f"(= {torque} {by_tick[observed_tick][7]})")
                )
    checks.append(f"(= {facts['horizon_ticks']} {samples[-1][0]})")
    return definition + "\n".join(checks) + "\n)))\n(check-sat)\n", facts


def verify_reduction(solver, output=RECORD):
    script, facts = certificate()
    start = time.perf_counter()
    run = subprocess.run(
        [solver, "-in"], input=script, text=True, capture_output=True, check=True, timeout=120
    )
    wall = round(time.perf_counter() - start, 6)
    if run.stdout.strip() != "unsat":
        raise ValueError("Plant trajectory contains an unresolved arithmetic or safety step")
    rec = {
        "source_commit": BASE,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "z3 -in",
        "configuration": "QF integer arithmetic on fully instantiated steps",
        "z3": subprocess.check_output([solver, "-version"], text=True).strip(),
        "status": "unsat",
        "smt_sha256": digest(script.encode()),
        "input_sha256": digest(FIXTURE.read_bytes()),
        "source_trace_sha256": TRACE_SHA256,
        "result_sha256": object_hash(facts),
        "wall_seconds": wall,
        "checked_scans": facts["horizon_ticks"],
        "trajectory": facts,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return rec


def checked_reduction():
    try:
        rec = json.loads(RECORD.read_text())
        script, facts = certificate()
        return (
            rec["status"] == "unsat"
            and rec["smt_sha256"] == digest(script.encode())
            and rec["input_sha256"] == digest(FIXTURE.read_bytes())
            and rec["result_sha256"] == object_hash(facts)
            and rec["trajectory"] == facts
            and rec["source_commit"] == BASE
        )
    except (OSError, ValueError, KeyError):
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Rebuild forcing CSV from the pinned source trace")
    parser.add_argument("--z3", default=shutil.which("z3") or "z3")
    parser.add_argument("--output", type=Path, default=RECORD)
    args = parser.parse_args()
    if args.project:
        FIXTURE.write_text(projection(args.project))
    receipt = verify_reduction(args.z3, args.output)
    print(receipt["status"], receipt["checked_scans"], receipt["wall_seconds"])
