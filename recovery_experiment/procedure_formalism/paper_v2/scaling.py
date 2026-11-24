"""Measure and replay the one-tick dependency benchmark on Linux."""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import zipfile
from collections import defaultdict
from itertools import product
from pathlib import Path
from time import perf_counter_ns

from ..milestone2.scalability import CONFIG, decisions, encode, structure
from ..procedure import DependencyStatus

PACKAGE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PACKAGE / "results" / "paper_v2"
NODES = (8, 16, 32, 64, 128, 256, 512)
CANDIDATES = (1, 2, 4, 8, 16)
PERCENT = (0, 10, 25, 50)
SEED = 20261123
WARMUPS, REPEATS = 5, 30
RAW = "dependency_scalability_repetitions.csv"
SUMMARY = "dependency_scalability_v2.json"
ENVIRONMENT = "environment_manifest.json"
FIELDS = ("phase", "round", "nodes", "candidates", "percent", "sharing",
          "model_bytes", "model_sha256", "joint_branch_count", "queries",
          "solver_answers", "verdicts", "returncode", "spec_ns", "encoding_ns", "solver_ns",
          "decision_ns", "end_to_end_ns", "solver_peak_rss_kib")


def design():
    """Reference curves, a complete cross-section, and balanced node strata."""
    cells = set()

    def add(n, k, pct, sharing):
        cells.add((n, k, pct, "low" if k == 1 else sharing))

    for i, n in enumerate(NODES):
        for k in (1, 4, 16):
            add(n, k, 25, "high")
        feasible = [k for k in CANDIDATES if k <= n]
        for j, pct in enumerate(PERCENT):
            for h, sharing in enumerate(("low", "high")):
                add(n, feasible[(i + j + h) % len(feasible)], pct, sharing)
    for k, pct, sharing in product(CANDIDATES, PERCENT, ("low", "high")):
        add(64, k, pct, sharing)
    return sorted(cells)


def schedule():
    cells = design()
    shuffle = random.Random(SEED)
    for phase, rounds in (("warmup", WARMUPS), ("measured", REPEATS)):
        for rep in range(1, rounds + 1):
            order = cells.copy()
            shuffle.shuffle(order)
            for cell in order:
                yield phase, rep, cell
    for rep in range(1, 4):
        for n, k in product((8, 64, 512), (1, 16)):
            yield "memory", rep, (n, k, 25, "low" if k == 1 else "high")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def capture_environment(z3, java, jar, cpu, proof_cpu, game_cpu):
    # Select only public hardware and software characteristics.
    cpu_fields = json.loads(subprocess.check_output(["lscpu", "-J"], text=True))["lscpu"]
    hardware = {v["field"].rstrip(":"): v["data"] for v in cpu_fields}
    with zipfile.ZipFile(jar) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode().splitlines()
    java_output = subprocess.run([java, "-version"], capture_output=True, text=True, check=True)
    legacy = json.loads((PACKAGE / "milestone2/evidence/legacy_regressions.json").read_text())
    return {
        "host": {"cpu_model": hardware["Model name"], "architecture": platform.machine(),
                 "logical_cpus": os.cpu_count(), "cores_per_socket": int(hardware["Core(s) per socket"]),
                 "sockets": int(hardware["Socket(s)"]), "threads_per_core": int(hardware["Thread(s) per core"]),
                 "visible_ram_bytes": os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
                 "os": platform.freedesktop_os_release()["PRETTY_NAME"], "kernel": platform.release(),
                 "sharing": "Shared host; benchmarks on distinct physical cores; other load uncontrolled."},
        "tools": {"python": platform.python_version(),
                  "z3": subprocess.check_output([z3, "-version"], text=True).strip(), "z3_sha256": sha(z3.read_bytes()),
                  "java": (java_output.stderr or java_output.stdout).splitlines()[:2],
                  "keymaera_x": next(l.split(": ", 1)[1] for l in manifest if l.startswith("Implementation-Version: ")),
                  "prover_jar_sha256": sha(jar.read_bytes()),
                  "cleo_historical": legacy["tool_versions"]["cleo"]},
        "dependency_benchmark": {"logical_cpu": cpu, "workers": 1, "solver_threads": 1,
                                 "clock": "perf_counter_ns", "solver_process": "new per cell repetition",
                                 "cache_policy": "The Z3 process and its memory are fresh. OS page caches were not flushed; page residency was uncontrolled."},
        "formal_proof_benchmark": {"fixed_procedure_logical_cpu": proof_cpu, "adaptive_game_logical_cpu": game_cpu,
                                   "workers_per_series": 1, "timing_series": "Fixed cases run sequentially on one core. The optional game series ran concurrently on a different physical core.", "jvm_active_processors": 1, "jvm_gc": "SerialGC",
                                   "heap_mib": {"initial": 128, "maximum": 1024},
                                   "cache_policy": "Fresh JVM and KeYmaera X user home per archive invocation. OS page caches were not flushed; page residency was uncontrolled.",
                                   "cleo_scope": "Historical regression environment only."}
    }


def run_cell(z3, cell, memory):
    n, k, percent, sharing = cell
    begin = perf_counter_ns()
    resources, procedures = structure(*cell)
    specified = perf_counter_ns()
    model, sizes = encode(resources, procedures)
    encoded = perf_counter_ns()
    command = [z3, "-in", "-smt2", "-T:10", f"smt.random_seed={SEED}", "smt.threads=1"]
    if memory:
        command = [shutil.which("time"), "-f", "%M", *command]
    try:
        run = subprocess.run(command, input=model, capture_output=True, timeout=12)
        answers, rc = run.stdout.decode().splitlines(), run.returncode
    except subprocess.TimeoutExpired:
        answers, rc = [], -1
    solved = perf_counter_ns()
    outcomes = decisions(answers, k)
    finished = perf_counter_ns()
    compact = {"unsat": "U", "sat": "S", "unknown": "?", "timeout": "T"}
    encoded_answers = "".join(compact.get(line, "!") for line in answers)
    rss = int(run.stderr.strip()) if memory and rc == 0 else ""
    return (n, k, percent, sharing, len(model), sha(model), sizes["joint_branch_count"], 2 * k,
            encoded_answers, ",".join(outcomes), rc, specified - begin, encoded - specified, solved - encoded,
            finished - solved, finished - begin, rss)


def measure(args):
    os.sched_setaffinity(0, {args.cpu})
    if shutil.which("time") is None:
        raise RuntimeError("GNU time is required for the separate peak-RSS probes")
    args.output.mkdir(parents=True, exist_ok=True)
    dump(args.output / ENVIRONMENT, capture_environment(args.z3, args.java, args.jar, args.cpu, args.proof_cpu, args.game_cpu))
    with (args.output / RAW).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(FIELDS)
        for phase, rep, cell in schedule():
            writer.writerow((phase, rep, *run_cell(args.z3, cell, phase == "memory")))


def summarize(values):
    values = sorted(values)
    # With 30 independent observations order statistics 10 and 21 give a
    # distribution-free 95.72% interval for the median under stationarity.
    return {"median": statistics.median(values), "p95": values[math.ceil(.95 * len(values)) - 1],
            "minimum": values[0], "maximum": values[-1],
            "median_order_interval": [values[9], values[20]]}


def report(directory):
    cells = {}
    observed = defaultdict(list)
    memory = defaultdict(list)
    failures = 0
    for cell in design():
        resources, procedures = structure(*cell)
        model, sizes = encode(resources, procedures)
        # Independent oracle on one-tick delivery: every required enable must
        # be trusted to exclude an allowed zero. Each initial state is feasible.
        expected = "".join("SS" if any(r.status == DependencyStatus.COMPROMISED for r in p.required_dependencies.values())
                           else "SU" for p in procedures)
        n, k, percent, sharing = cell
        cells[cell] = dict(nodes=n, candidates=k, percent=percent, sharing=sharing,
                           model_bytes=len(model), model_sha256=sha(model), queries=2*k,
                           expected_solver_answers=expected,
                           expected_verdicts=["PROVED" if v == "U" else "REJECTED" for v in expected[1::2]], **sizes)
    with (directory / RAW).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Unexpected scaling CSV fields")
        for (phase, rep, cell), row in zip(schedule(), reader, strict=True):
            n, k, pct, sharing = cell
            metadata = cells[cell]
            if (row["phase"], int(row["round"]), int(row["nodes"]), int(row["candidates"]),
                int(row["percent"]), row["sharing"]) != (phase, rep, n, k, pct, sharing):
                raise ValueError("Inconsistent benchmark schedule")
            for key in ("model_bytes", "model_sha256", "queries", "joint_branch_count"):
                if row[key] != str(metadata[key]):
                    raise ValueError(f"Encoding differs for {cell} in {key}")
            if (row["returncode"] != "0" or row["solver_answers"] != metadata["expected_solver_answers"]
                    or row["verdicts"].split(",") != metadata["expected_verdicts"]):
                failures += 1
                continue
            stages = [int(row[key]) for key in ("spec_ns", "encoding_ns", "solver_ns", "decision_ns")]
            if min(stages) < 0 or sum(stages) != int(row["end_to_end_ns"]):
                raise ValueError("Stage clocks disagree")
            if phase == "measured":
                observed[cell].append(row)
            elif phase == "memory":
                memory[cell].append(int(row["solver_peak_rss_kib"]))
    if failures:
        raise ValueError(f"{failures} solver executions failed, timed out, or disagreed with the one-tick oracle")
    for cell, metadata in cells.items():
        rows = observed[cell]
        if len(rows) != REPEATS:
            raise ValueError("Missing measured repetitions")
        for column in ("spec_ns", "encoding_ns", "solver_ns", "decision_ns", "end_to_end_ns"):
            metadata[column] = summarize([int(r[column]) for r in rows])
        if cell in memory:
            metadata["solver_peak_rss_kib_probes"] = memory[cell]
    data = {
        "method": {
            "workload": CONFIG["plant"], "queries": CONFIG["query_order"], "compromise": CONFIG["compromise"],
            "design": "At each node size, all-to-all references at 25% compromise for K=1,4,16; additionally rotate candidate counts over four compromise levels and two sharing levels. At 64 nodes cross all factors. Single-candidate fanout is identical and represented once.",
            "seed": SEED, "seed_use": "Fixed SMT search seed; seed Python random.Random once to shuffle cell order independently in each successive warmup and measured round. Workload graph within a cell is fixed.",
            "solver": "One fresh, single-threaded Z3 process per cell repetition, incremental push/pop within that process. Clock includes startup, input and output.",
            "timing": "perf_counter_ns from typed specification construction through verdict construction. Report generation, record hashing and serialization are outside the timed section.",
            "warmups_per_cell": WARMUPS, "measured_repetitions_per_cell": REPEATS,
            "statistics": "Median and nearest-rank p95 per cell. Secondary median interval is [10th, 21st] of 30 observations (95.72% under stationary independent sampling).",
            "peak_memory": "Three additional GNU time maximum-RSS probes for the solver child in KiB at 8,64,512 nodes with one or 16 candidates at 25% compromise. Probes excluded from all clocks in the summary.",
            "answers": "Pairs per candidate; S=sat, U=unsat. First checks feasibility; second seeks a contract violation.",
            "branch_counts": "Joint or per-candidate feasible valuations before projecting to service. Solvers need not enumerate them."
        },
        "raw_csv_sha256": sha((directory / RAW).read_bytes()),
        "summary": {"cells": len(cells), "measured_runs": len(cells)*REPEATS,
                    "warmup_runs": len(cells)*WARMUPS, "memory_probes": sum(map(len, memory.values())),
                    "measured_queries": REPEATS*sum(c["queries"] for c in cells.values()), "solver_failures_all_phases": failures,
                    "node_levels": list(NODES), "candidate_levels": list(CANDIDATES), "compromise_levels_percent": list(PERCENT),
                    "encoding_bytes_range": [min(c["model_bytes"] for c in cells.values()),max(c["model_bytes"] for c in cells.values())]},
        "cells": list(cells.values())
    }
    dump(directory / SUMMARY, data)


def write_figure(directory, destination):
    """Typeset only the matched series used in the paper."""
    data = json.loads((directory / SUMMARY).read_text())
    methods = data["method"]
    selected = {(row["candidates"], row["nodes"]): row["end_to_end_ns"]
                for row in data["cells"] if row["percent"] == 25
                and (row["candidates"], row["sharing"]) in ((1, "low"), (16, "high"))}
    peak = max(row["p95"] / 1e6 for row in selected.values())
    step = 10 if peak <= 80 else 20
    ceiling = math.ceil(peak / step) * step
    lines = [
        r"\begin{figure}[t]", r"\centering", r"\footnotesize",
        r"\begin{tikzpicture}[x=0.98cm,y=" + f"{3.28 / ceiling:.6f}" + r"cm,",
        r"  one/.style={black!65,semithick},many/.style={black,thick},",
        r"  percentile/.style={dash pattern=on 3pt off 1.7pt}]",
    ]
    for y in range(0, ceiling + 1, step):
        lines.append(rf"\draw[black!18] (0,{y}) -- (6,{y});")
        lines.append(rf"\node[left,font=\scriptsize] at (0,{y}) {{{y}}};")
    lines.append(rf"\draw (0,{ceiling}) -- (0,0) -- (6,0);")
    for x, n in enumerate(NODES):
        lines.append(rf"\node[below,font=\scriptsize] at ({x},0) {{{n}}};")
    for count, style, mark in ((1, "one", "+"), (16, "many", "*")):
        for stat, extra in (("p95", ",percentile"), ("median", "")):
            series = " ".join(f"({x},{selected[count,n][stat] / 1e6:.3f})" for x, n in enumerate(NODES))
            lines.append(rf"\draw[{style}{extra}] plot[mark={mark},mark size=1.25pt] coordinates {{{series}}};")
    lines += [
        rf"\node[rotate=90,font=\footnotesize] at (-.73,{ceiling / 2:g}) {{Classification time (ms)}};",
        r"\node[below=9pt,font=\footnotesize] at (3,0) {Dependency nodes};",
        r"\end{tikzpicture}", "",
        r"{\scriptsize $+$ 1 candidate\qquad $\bullet$ 16 candidates\qquad Solid: median\quad Dashed: p95}",
        r"\caption{End-to-end dependency classification at fixed physical complexity. Each point uses "
        + str(methods["measured_repetitions_per_cell"])
        + " runs after " + str(methods["warmups_per_cell"])
        + r" warmups, with a fresh Z3 process per run, one material-balance step, 25\% compromised dependencies, and every candidate using every node.}\label{fig:scaling-v2}",
        r"\end{figure}"
    ]
    host = json.loads((directory / ENVIRONMENT).read_text())["host"]
    first, last = selected[16, NODES[0]], selected[16, NODES[-1]]
    model_name = host["cpu_model"].split(" 16-Core Processor")[0]
    lines += [
        "",
        r"\textit{Dependency-encoding time.} "
        + f"We varied node count, candidate count, the compromised fraction, and resource sharing across {data['summary']['cells']} cells. "
        + f"On one logical CPU of a shared {model_name} host ({host['os']}, {host['visible_ram_bytes']/2**30:.1f}~GiB RAM), "
        + f"{data['summary']['measured_runs']:,} measured classifications made {data['summary']['measured_queries']:,} solver queries. "
        + "Each candidate contributes a feasibility query and a search for a contract violation. "
        + r"Figure~\ref{fig:scaling-v2} includes specification generation, encoding, solver startup and execution, and classification. "
        + f"With 16 candidates, median time rose from {first['median']/1e6:.2f} to {last['median']/1e6:.2f}~ms "
        + f"and p95 from {first['p95']/1e6:.2f} to {last['p95']/1e6:.2f}~ms. "
        + "In this slice the candidates share all enable conditions and use the same one-step plant. "
        + r"Table~\ref{tab:proof-timing-v2} reports the separate cost of checking the case proofs.",
    ]
    destination.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("measure", "report", "environment"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--z3", type=Path, default=shutil.which("z3"))
    parser.add_argument("--java", type=Path, default=shutil.which("java"))
    parser.add_argument("--jar", type=Path, default=os.environ.get("KEYMAERAX_JAR"))
    parser.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    parser.add_argument("--figure", type=Path, help="Optional output TeX figure from the recorded timings")
    parser.add_argument("--proof-cpu", type=int, help="Recorded affinity of the separate proof experiment")
    parser.add_argument("--game-cpu", type=int, help="Recorded affinity of the additional game timing series")
    args = parser.parse_args()
    if args.mode in ("measure", "environment"):
        if not all((args.z3, args.java, args.jar)):
            parser.error("Measurement requires Z3, Java and a KeYmaera X jar")
    if args.mode == "environment":
        dump(args.output / ENVIRONMENT, capture_environment(args.z3, args.java, args.jar, args.cpu, args.proof_cpu, args.game_cpu))
    else:
        if args.mode == "measure":
            measure(args)
        report(args.output)
        if args.figure:
            write_figure(args.output, args.figure)
