"""Measure complete KeYmaera X archive runs with a fresh JVM and cache per run."""

import argparse
import csv
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import signal
from statistics import median
import subprocess
import tempfile
import threading
from time import perf_counter_ns

from ..milestone2.proofs import JAR_SHA256

PACKAGE = Path(__file__).resolve().parents[1]
RESULTS = PACKAGE / "results" / "paper_v2"
EVIDENCE = PACKAGE / "milestone2" / "evidence"
ARCHIVES = {
    "remote": PACKAGE / "models" / "M0.kyx",
    "hand": EVIDENCE / "models" / "attleboro-local-hand-end-to-end-recovery-v1.kyx",
    "merwin": EVIDENCE / "models" / "merwin-hcc-remote-auto-end-to-end-recovery-v1.kyx",
    "p2": EVIDENCE / "models" / "cost_P2_42979f75cf.kyx",
    "p3": EVIDENCE / "models" / "cost_P3_758f611e41.kyx",
}
GAME = PACKAGE / "paper_v2" / "game_evidence"
FIXED = tuple(ARCHIVES)
ARCHIVES["game"] = GAME / "models" / "water_game.kyx"
FIELDS = ("case", "round", "order", "obligations", "proved", "setup_ms",
          "tactic_ms", "wall_ms", "composition_ms", "exports_match", "return_code",
          "restricted_optional_lemmas", "status")
SEED = 72821
Z3_SHA256 = "1bfaf5bbe81fd0b7800500ee08eef426aaabe18f8b9c4c4c32adffcd72f86cd5"
PROVED_LINE = re.compile(r"^PROVED ([\w-]+): tactic=.*?duration=(\d+)\[ms\]")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def expected_exports(case):
    archive = ARCHIVES[case]
    if case == "game":
        directory = GAME / "proof_records" / archive.stem
        record = json.loads((GAME / "proof_index.json").read_text())["record"]
        if record["archive_sha256"] != digest(archive):
            raise ValueError("Game archive differs from its proof record")
        obligations = record["obligations"]
    else:
        directory = (PACKAGE if case == "remote" else EVIDENCE) / "proof_records" / archive.stem
        summaries = json.loads((PACKAGE / "results" / "milestone2" / "rq2_summary.json").read_text())["rows"]
        source = next((row for row in summaries if row["archive_sha256"] == digest(archive)), None)
        if source is None:
            raise ValueError(f"Archive identity differs from the published reference for {case}")
        obligations = source["obligations_detail"]
    result = {}
    for path in directory.glob("*.kyp"):
        title = re.search(rb'^Lemma "user/([\w-]+)"\.', path.read_bytes(), re.M)
        fingerprint = digest(path)
        recorded = obligations.get(path.stem, {})
        if not title or recorded.get("status") != "PROVED" or fingerprint != recorded.get("proof_sha256"):
            raise ValueError(f"Invalid reference proof export for {case} {path.stem}")
        result[title[1].decode()] = fingerprint
    entries = set(re.findall(r'^ArchiveEntry "([\w-]+)"', archive.read_text(), re.M))
    if not entries or set(result) != entries:
        raise ValueError(f"Missing reference proof exports for {case}")
    return result


def measure(case, round_id, order, java, jar, z3):
    expected = expected_exports(case)
    with tempfile.TemporaryDirectory(prefix="proof-timing-") as directory:
        work = Path(directory)
        (work / ".keymaerax").mkdir()
        (work / ".keymaerax" / "solver").symlink_to(z3)
        (work / "solver").symlink_to(z3)
        (work / "tool.jar").symlink_to(jar)
        shutil.copyfile(ARCHIVES[case], work / "model.kyx")
        cmd = [java, f"-Duser.home={work}", "-XX:ActiveProcessorCount=1", "-XX:+UseSerialGC",
               "-Xms128m", "-Xmx1024m", "-Xss20M", "-jar", "tool.jar", "-launch", "-prove",
               "model.kyx", "-tool", "z3", "-z3path", "solver", "-timeout", "60", "-out", "result.kyp"]
        # Inherit CPU affinity but discard unrelated JVM option overrides.
        env = {k: v for k, v in os.environ.items() if k not in
               ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")}
        durations = {}
        setup_ns = None
        restricted = False
        started = perf_counter_ns()
        with subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=env, start_new_session=True, text=True) as proc:
            watchdog = threading.Timer(120 + 60 * len(expected), os.killpg,
                                       args=(proc.pid, signal.SIGKILL))
            watchdog.start()
            try:
                for line in proc.stdout:
                    if setup_ns is None and line.startswith("Proving ") and "model.kyx#" in line:
                        setup_ns = perf_counter_ns() - started
                    restricted |= "Continuing with restricted functionality" in line
                    match = PROVED_LINE.match(line)
                    if match:
                        durations[match[1]] = int(match[2])
                return_code = proc.wait()
                wall_ns = perf_counter_ns() - started
            finally:
                watchdog.cancel()
        exports = {}
        for path in work.glob("result*.kyp"):
            title = re.search(rb'^Lemma "user/([\w-]+)"\.', path.read_bytes(), re.M)
            if title:
                exports[title[1].decode()] = digest(path)
    proved = len(expected.keys() & durations.keys())
    success = return_code == 0 and setup_ns is not None and set(durations) == set(expected) and exports == expected
    composition = next((ms for key, ms in durations.items()
                        if key.endswith(("_end_to_end", "_composition"))), None)
    return dict(case=case, round=round_id, order=order, obligations=len(expected), proved=proved,
                setup_ms=round(setup_ns / 1e6, 3) if setup_ns is not None else None,
                tactic_ms=sum(durations.values()), wall_ms=round(wall_ns / 1e6, 3),
                composition_ms=composition, exports_match=int(exports == expected), return_code=return_code,
                restricted_optional_lemmas=int(restricted), status="PROVED" if success else "INCOMPLETE")


def distribution(values):
    values = sorted(values)
    return {"median": median(values), "p95": values[math.ceil(0.95 * len(values)) - 1],
            "min": values[0], "max": values[-1]}


def scheduled(series, rounds):
    rng = random.Random(SEED)
    for round_id in range(1, rounds + 1):
        order = list(FIXED) if series == "fixed" else ["game"]
        rng.shuffle(order)
        for index, case in enumerate(order, 1):
            yield case, round_id, index


def summarize(raw, target):
    with raw.open(newline="") as source:
        rows = list(csv.DictReader(source))
    if set(ARCHIVES) != {r["case"] for r in rows} or any(r["status"] != "PROVED" for r in rows):
        raise ValueError("Timing report requires complete verified cases")
    rounds = len(rows) // len(ARCHIVES)
    expected_order = list(scheduled("fixed", rounds)) + list(scheduled("game", rounds))
    if [(r["case"], int(r["round"]), int(r["order"])) for r in rows] != expected_order:
        raise ValueError("Raw measurements are incomplete or out of order")
    cases = {}
    for case, path in ARCHIVES.items():
        entries = expected_exports(case)
        data = [r for r in rows if r["case"] == case]
        for r in data:
            if (int(r["return_code"]) or r["exports_match"] != "1" or
                    int(r["obligations"]) != len(entries) or int(r["proved"]) != len(entries) or
                    not 0 < float(r["setup_ms"]) < float(r["wall_ms"]) or
                    not 0 <= int(r["tactic_ms"]) <= float(r["wall_ms"]) or
                    bool(r["composition_ms"]) != (case != "game")):
                raise ValueError(f"Inconsistent run in {case} round {r['round']}")
        cases[case] = {"archive": path.relative_to(PACKAGE).as_posix(),
                       "archive_bytes": path.stat().st_size, "archive_sha256": digest(path),
                       "obligations": len(entries), "successes": len(data),
                       "optional_lemma_initialization_restricted_runs":
                           sum(int(r["restricted_optional_lemmas"]) for r in data),
                       "proof_export_sha256": entries,
                       **{k: distribution(float(r[k]) for r in data) for k in
                          ("setup_ms", "tactic_ms", "wall_ms", "composition_ms") if data[0][k]}}
    report = {"protocol": "The fixed-procedure series shuffles its five archives per round. "
              "The separate game worker runs its single archive the same number of times on a distinct core. "
              "The overlapping streams share a host. The CSV groups fixed and game runs separately, "
              "preserving order within each. "
              "Each invocation has a new JVM, working directory, isolated prover home and lemma cache. "
              "OS page cache is uncontrolled. Identical proof exports are checked after timing.",
              "environment": "environment_manifest.json", "fixed_procedure_reference_commit":
                  "fa719386e782766f01a8db770d7b128ccba3ad99",
              "game_proof_record": "paper_v2/game_evidence/proof_index.json",
              "order_seed": SEED, "rounds": rounds, "runs": len(rows), "warmups": 0,
              "jvm_parameters": ["-XX:ActiveProcessorCount=1", "-XX:+UseSerialGC", "-Xms128m", "-Xmx1024m", "-Xss20M"],
              "solver": "KeYmaera X 5.1.1 with Z3 4.15.4 with one logical CPU per sequential worker",
              "timeout_seconds_per_obligation": 60, "arithmetic_preprocessing":
                  "Merwin times cover the fixed, checked reduction in the archived dL case. Independent "
                  "finite-step arithmetic certificate generation and CLEO are outside these measurements.",
              "statistic": "Median uses the mean of middle observations for even n. "
                  "p95 uses the nearest rank ceil(0.95 n), equal to the maximum for n=10.",
              "metrics": {"setup_ms": "Elapsed from process launch to receipt of first Proving model.kyx# line, "
                          "including initialization and archive parsing; this is an observable setup boundary.",
                          "tactic_ms": "Sum of KeYmaera X reported tactic durations for all entries in this invocation.",
                          "composition_ms": "Tactic duration of the fixed procedure's end-to-end composition entry. "
                                            "This field is empty for the game archive.",
                          "wall_ms": "Process launch through exit including setup, tactics and proof export. "
                          "Independent verification of exported bytes occurs after exit."},
              "raw_sha256": digest(raw), "jar_sha256": JAR_SHA256, "z3_sha256": Z3_SHA256, "cases": cases}
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def write_table(report_path, destination):
    report = json.loads(report_path.read_text())
    names = {"remote": "Water Remote", "hand": "Water Hand", "merwin": "Hydro HCC",
             "p2": "Controlled P2", "p3": "Controlled P3", "game": "Water game"}
    lines = [
        r"\begin{table}[t]",
        r"\caption{Cold proof times per bounded archive (seconds).}\label{tab:proof-timing-v2}",
        r"\centering\footnotesize",
        r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}lrrrrr@{}}",
        r"\toprule",
        r"Archive & Entries & Setup & \multicolumn{2}{c}{Tactics} & Total \\",
        r" & & Median & Median & p95 & Median \\",
        r"\midrule",
    ]
    for case, name in names.items():
        row = report["cases"][case]
        values = [row["setup_ms"]["median"], row["tactic_ms"]["median"],
                  row["tactic_ms"]["p95"], row["wall_ms"]["median"]]
        cells = [name, str(row["obligations"])] + [f"{ms / 1000:.2f}" for ms in values]
        lines.append(" & ".join(cells) + r" \\")
    lines.extend([
        r"\bottomrule", r"\end{tabular*}\par\smallskip",
        r"\begin{minipage}{\columnwidth}\footnotesize",
        f'All entries closed in each of {report["rounds"]} runs per archive. '
        "Setup extends from JVM launch to the first proof entry. "
        "Tactic time sums the entries, and total wall time includes setup and proof export. "
        + ("The nearest-rank p95 is the largest observed tactic sum for this sample."
           if report["rounds"] < 20 else "The p95 uses the nearest-rank estimator."),
        r"\end{minipage}", r"\end{table}",
    ])
    destination.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--table", type=Path, help="optional manuscript table generated from the report")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--series", choices=("fixed", "game"), help="measure one sequential proof series")
    mode.add_argument("--combine", nargs=2, metavar=("FIXED_CSV", "GAME_CSV"), type=Path,
                      help="join the two raw series and generate the report")
    mode.add_argument("--summarize", action="store_true", help="regenerate from saved observations")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--jar", type=Path, default=os.environ.get("KEYMAERAX_JAR"))
    parser.add_argument("--z3", type=Path, default=shutil.which("z3"))
    parser.add_argument("--cpu", type=int, help="permitted logical CPU for this sequential benchmark")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "formal_proof_timing_repetitions.csv"
    target = args.output / "formal_proof_timing_v2.json"
    if args.series:
        if not args.java or not args.jar or not args.z3 or args.rounds < 1:
            parser.error("Provide the pinned Java, JAR and Z3 and a positive round count")
        if digest(args.jar) != JAR_SHA256 or digest(args.z3) != Z3_SHA256:
            parser.error("Tool digest differs from benchmark configuration")
        available = os.sched_getaffinity(0)
        cpu = args.cpu if args.cpu is not None else min(available)
        if cpu not in available:
            parser.error("Selected logical CPU is unavailable")
        os.sched_setaffinity(0, {cpu})
        path = args.output / f"proof_timing_{args.series}.csv"
        # Preserve previous measurements, including an interrupted series.
        with path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            for case, round_id, index in scheduled(args.series, args.rounds):
                row = measure(case, round_id, index, args.java, args.jar.resolve(), args.z3.resolve())
                writer.writerow(row)
                stream.flush()
                print(f"Round {round_id} {case}: {row['status']}, {row['wall_ms']} ms", flush=True)
                if row["status"] != "PROVED":
                    raise RuntimeError("Incomplete proof or timing boundary; see raw measurement")
        return
    if args.combine:
        # Validate a provisional join before publishing any result. The CSV order
        # records the order within each separate worker, not global start times.
        with tempfile.TemporaryDirectory(dir=args.output) as scratch:
            joined = Path(scratch) / raw.name
            checked = Path(scratch) / target.name
            with joined.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                for part in args.combine:
                    with part.open(newline="") as source:
                        reader = csv.DictReader(source)
                        if tuple(reader.fieldnames or ()) != FIELDS:
                            raise ValueError("Unexpected raw proof timing columns")
                        writer.writerows(reader)
            summarize(joined, checked)
            if raw.exists() and raw.read_bytes() != joined.read_bytes():
                parser.error("Destination contains a different proof timing observation")
            joined.replace(raw)
    summarize(raw, target)
    if args.table:
        write_table(target, args.table)


if __name__ == "__main__":
    main()
