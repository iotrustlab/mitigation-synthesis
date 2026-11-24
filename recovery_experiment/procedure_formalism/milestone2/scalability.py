"""Factorial experiment on the size and cost of a finite dependency encoding."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from itertools import product
import json
from math import prod
from pathlib import Path
import shutil
import subprocess
from time import perf_counter_ns

from ..dependency_semantics import transition
from ..formal_ir import Assignment
from ..procedure import (DependencyKind, DependencyNode, DependencyStatus, EvidenceStatus,
                         RecoveryProcedure, field_evidence)
from .proofs import BASE, EVIDENCE, digest, object_hash

GRID = tuple(product((8, 16, 32, 64), (1, 2, 4, 8), (0, 10, 25, 50), ("low", "medium", "high")))
COMMAND = "z3 -in -smt2 -T:10"
RECORD = EVIDENCE / "scalability_measurements.json"
CONFIG = {"timeout_seconds": 10, "logic": "QF_LRA", "command": COMMAND, "clock": "perf_counter_ns",
          "plant": "Initially empty, a delivered unit fills one unit of volume over one tick. A trusted observer reads final volume.",
          "query_order": ["reachable initial state and execution", "violation of safety, positive service or evidence"],
          "sharing": "Rotate each node's owners, with 1, ceil(K/2), or K owners respectively.",
          "compromise": "First round-half-up(N*percentage/100) nodes in deterministic node order."}


def structure(nodes, count, percent, sharing):
    ids = tuple(f"candidate{i}" for i in range(count))
    fanout = {"low": 1, "medium": (count + 1) // 2, "high": count}[sharing]
    changed = (nodes * percent + 50) // 100
    resources = {}
    for i in range(nodes):
        name = f"d{i}"
        owners = tuple(ids[(i + j) % count] for j in range(fanout))
        status = DependencyStatus.COMPROMISED if i < changed else DependencyStatus.TRUSTED
        resources[name] = DependencyNode(name, DependencyKind.OUTPUT_STAGE, status, "controlled benchmark",
                                         owners, EvidenceStatus.RESEARCH_AUTHORED, "factorial design",
                                         "Enable bit in {0,1}.", "One sampled value per shared resource.")
    procedures = []
    for identity in ids:
        required = {k: v for k, v in resources.items() if identity in v.required_by}
        procedures.append(RecoveryProcedure(
            procedure_id=identity, case_id="dependency-scaling", version="1", actor=None, role="fixed request",
            actor_ready_time=0, authority_requirements=("issued authorized request",), interface=None,
            communication_path=None, controller=None, controller_guard="Request enabled.",
            controller_transition="Request one unit of volume.", output_stage=next(iter(required)),
            delivered_actuation_relation="One unit is delivered iff every required enable bit is set.",
            actuator=None, plant_model="one-step material balance", observer=None,
            observation_relation="Trusted exact observation of final volume.", freshness_requirement="Final tick.",
            service_definition="Final volume and observed volume each equal one.", safety_definition="Volume in [0,1].",
            initial_state={"volume": 0}, deadline=1, horizon=1, required_dependencies=required,
            shared_dependencies=tuple(k for k, v in required.items() if len(v.required_by) > 1),
            attacker_effects={k: v.threat_effect for k, v in required.items()}, cost_vector_definition=(),
            source_references=("generated controlled benchmark",), evidence_status_by_field=field_evidence(EvidenceStatus.RESEARCH_AUTHORED),
        ))
    return resources, procedures


def encode(resources, procedures):
    lines = ["(set-logic QF_LRA)", "(set-option :print-success false)"]
    choices = {}
    for name, node in resources.items():
        values = transition(node, Assignment.nominal(name, "1")).values({})
        choices[name] = len(values)
        lines.append(f"(declare-const {name} Real)")
        terms = " ".join(f"(= {name} {v})" for v in values)
        lines.append(f"(assert (or {terms}))")
    for i, p in enumerate(procedures):
        enabled = " ".join(f"(= {k} 1)" for k in p.required_dependencies)
        lines.extend((f"(define-fun flow{i} () Real (ite (and {enabled}) 1 0))",
                      f"(define-fun volume{i} () Real (+ 0 (* 1 flow{i})))",
                      f"(define-fun observed{i} () Real volume{i})",
                      "(check-sat)", "(push 1)",
                      f"(assert (not (and (<= 0 volume{i}) (<= volume{i} 1) (= volume{i} 1) (= observed{i} volume{i}))))",
                      "(check-sat)", "(pop 1)"))
    return ("\n".join(lines) + "\n").encode(), {
        "joint_branch_count": prod(choices.values()),
        "candidate_branch_counts": [prod(choices[k] for k in p.required_dependencies) for p in procedures],
        "dependency_references": sum(len(p.required_dependencies) for p in procedures),
        "compromised_nodes": sum(v.status == DependencyStatus.COMPROMISED for v in resources.values()),
        "actual_fanout": max(len(v.required_by) for v in resources.values()),
    }


def decisions(answers, count):
    if len(answers) != 2 * count:
        return ["UNKNOWN"] * count
    return [("PROVED" if violation == "unsat" else "REJECTED" if violation == "sat" else "UNKNOWN")
            if reachable == "sat" else "UNKNOWN"
            for reachable, violation in zip(answers[::2], answers[1::2])]


def measure(z3, record=RECORD):
    rows = []
    for params in GRID:
        start = perf_counter_ns()
        resources, procedures = structure(*params)
        spec_ns = perf_counter_ns() - start
        start = perf_counter_ns()
        model, size = encode(resources, procedures)
        render_ns = perf_counter_ns() - start
        start = perf_counter_ns()
        try:
            run = subprocess.run([z3, "-in", "-smt2", "-T:10"], input=model, capture_output=True, timeout=12)
            answers = run.stdout.decode().splitlines()
            rc = run.returncode
        except subprocess.TimeoutExpired:
            answers, rc = ["timeout"], -1
        solver_ns = perf_counter_ns() - start
        start = perf_counter_ns()
        outcome = decisions(answers, len(procedures)) if rc == 0 else ["UNKNOWN"] * len(procedures)
        classification_ns = perf_counter_ns() - start
        n, k, pct, sharing = params
        rows.append(dict(nodes=n, candidates=k, percent=pct, sharing=sharing, **size,
                         obligations=2*k, model_bytes=len(model), model_sha256=digest(model),
                         solver_answers=answers, solver_output_sha256=object_hash(answers),
                         return_code=rc, outcomes=outcome, spec_generation_ns=spec_ns,
                         model_generation_ns=render_ns, solver_wall_ns=solver_ns, classification_ns=classification_ns))
    record.parent.mkdir(parents=True, exist_ok=True)
    result = dict(source_commit=BASE, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  configuration=CONFIG, tool_versions={"z3": subprocess.check_output([z3,"-version"], text=True).strip()},
                  solver_sha256=digest(Path(z3).read_bytes()), rows=rows)
    record.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


def report(record=RECORD):
    result = json.loads(record.read_text())
    if result["source_commit"] != BASE or result["configuration"] != CONFIG or len(result["rows"]) != len(GRID):
        raise ValueError("Stale scalability measurements")
    for params, row in zip(GRID, result["rows"]):
        model, size = encode(*structure(*params))
        key = tuple(row[k] for k in ("nodes","candidates","percent","sharing"))
        answers = row["solver_answers"]
        expected = decisions(answers, params[1]) if row["return_code"] == 0 else ["UNKNOWN"] * params[1]
        if (key != params or row["model_sha256"] != digest(model) or row["model_bytes"] != len(model)
                or row["solver_output_sha256"] != object_hash(answers) or row["outcomes"] != expected
                or any(row[k] != v for k, v in size.items())):
            raise ValueError(f"Stale scalability cell {params}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--z3", default=shutil.which("z3"))
    parser.add_argument("--record", type=Path, default=RECORD)
    args = parser.parse_args()
    measure(args.z3, args.record)
