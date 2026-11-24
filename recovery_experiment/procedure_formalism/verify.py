"""Replay the generated dL obligations and check content-bound proof records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from .formal_model import build_model

ROOT = Path(__file__).resolve().parent
RECORD = ROOT / "proof_records" / "verification.json"
TIMEOUT = 60
CASES = (0, 1, 2, 4, 5, 7, 8, 9, 13)
COMMAND = ("java -Duser.home=WORKSPACE -Xss20M -jar tool.jar -launch -prove model.kyx "
           "-tool z3 -z3path solver -timeout 60 -out result.kyp")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _matches(model, negative, root=ROOT):
    """Fail closed on missing/partial/stale records or a different model."""
    try:
        index = json.loads((root / "proof_records" / "verification.json").read_text())
        row = index["models"][model.sha256]
        expected_case = row["case"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", expected_case):
            return False
        allowed_kinds = {"violation", "possible_violation"} if negative else {"recovery"}
        if row["kind"] not in allowed_kinds or row["return_code"] != 0:
            return False
        archive = model.archive(violation=negative).encode()
        if ((root / "models" / f"{expected_case}.kyx").read_bytes() != archive
                or row["archive_sha256"] != _digest(archive) or row["status"] != "PROVED"):
            return False
        obligations = model.entries(negative)
        if row["obligations"].keys() != obligations.keys():
            return False
        for name, proof in row["obligations"].items():
            path = root / "proof_records" / expected_case / f"{name}.kyp"
            data = path.read_bytes()
            if (proof["status"] != "PROVED" or _digest(data) != proof["proof_sha256"]
                    or f'Lemma "user/{model.title(name)}".'.encode() not in data
                    or obligations[name].strip().encode() not in data):
                return False
        return True
    except (OSError, TypeError, KeyError, ValueError):
        return False


def verified(model):
    return _matches(model, False)


def verified_violation(model):
    return _matches(model, True)


def _version(command):
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    return (run.stdout or run.stderr).splitlines()[0].strip()


def _solve(model, case, negative, jar, z3, java, work, output):
    text = model.archive(violation=negative)
    archived = output / "models" / f"{case}.kyx"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text(text)
    cwd = work / case
    cwd.mkdir()
    (cwd / "model.kyx").write_text(text)
    (cwd / "tool.jar").symlink_to(jar)
    (cwd / "solver").symlink_to(z3)
    command = [java, f"-Duser.home={work}", "-Xss20M", "-jar", "tool.jar",
               "-launch", "-prove", "model.kyx", "-tool", "z3", "-z3path", "solver",
               "-timeout", str(TIMEOUT), "-out", "result.kyp"]
    started = time.monotonic()
    obligations = model.entries(negative)
    failure = "TOOLCHAIN_FAILURE"
    try:
        run = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                             timeout=TIMEOUT * len(obligations) + 120)
        stdout = run.stdout + run.stderr
        rc = run.returncode
        if "TIMEOUT " in stdout:
            failure = "TOOL_TIMEOUT"
        elif "UNPROVED " in stdout:
            failure = "INVARIANT_INSUFFICIENT"
        elif "QE" in stdout and "FAILED " in stdout:
            failure = "ARITHMETIC_FAILURE"
    except subprocess.TimeoutExpired:
        stdout, rc, failure = "", -1, "TOOL_TIMEOUT"
    wall = round(time.monotonic() - started, 3)
    # Only machine-readable proved lines and original .kyp proofs are persisted.
    # The CLI transcript also contains private scratch locations.
    durations = {name: int(ms) for name, ms in re.findall(
        r"^PROVED ([\w-]+): tactic=.*?duration=(\d+)\[ms\]", stdout, re.M)}
    version = re.search(r"KeYmaera X Prover ([\w.]+)", stdout)
    ids = {model.title(name): name for name in obligations}
    proofs = {}
    for file in cwd.glob("result*.kyp"):
        data = file.read_bytes()
        match = re.search(rb'^Lemma "user/([\w-]+)"\.', data, re.M)
        if match:
            title = match[1].decode()
            name = ids.get(title)
            if name and title in durations:
                dest = output / "proof_records" / case / f"{name}.kyp"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                proofs[name] = {"status": "PROVED", "duration_ms": durations[title],
                                "proof_sha256": _digest(data)}
    for name in obligations.keys() - proofs.keys():
        proofs[name] = {"status": "UNKNOWN", "blocker": failure}
    status = "PROVED" if rc == 0 and all(r["status"] == "PROVED" for r in proofs.values()) else "UNKNOWN"
    return {
        "case": case, "procedure_id": model.procedure.procedure_id,
        "archive_sha256": _digest(text.encode()), "status": status,
        "kind": "possible_violation" if case == "M13" else "violation" if negative else "recovery",
        "return_code": rc, "wall_seconds": wall, "obligations": proofs,
        "prover": "KeYmaera X " + (version[1] if version else "unknown"),
        "optional_lemma_initialization_restricted": "Continuing with restricted functionality" in stdout,
    }


def replay(jar, z3, java, output):
    from .attleboro import attleboro
    from .evaluation import MUTATIONS

    index = {"command": COMMAND, "command_workspace": "private temporary directory",
             "cache": "Fresh isolated user home per replay; derived-lemma cache shared across cases.",
             "java": _version([java, "-version"]), "z3": _version([str(z3), "-version"]),
             "jar_sha256": _digest(jar.read_bytes()), "models": {}}
    with tempfile.TemporaryDirectory(prefix="procedure-proof-") as folder:
        work = Path(folder)
        # The CLI checks its argument both relative to cwd and the KeYmaera home.
        # Keeping the same relative name in both yields portable original .kyp files.
        config = work / ".keymaerax"
        config.mkdir()
        (config / "solver").symlink_to(z3)
        for i in CASES:
            spec = MUTATIONS[i]
            proc = attleboro(statuses=spec.dependencies, initial_state=spec.states)["remote"]
            model = build_model(proc)
            row = _solve(model, f"M{i}", bool(i), jar, z3, java, work, output)
            index["models"][model.sha256] = row
            print(f'M{i}: {row["status"]} ({row["wall_seconds"]} s)', flush=True)
    target = output / "proof_records" / "verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return all(item["status"] == "PROVED" for item in index["models"].values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, default=Path(os.environ.get("KEYMAERAX_JAR", "keymaerax.jar")))
    parser.add_argument("--z3", type=Path, default=Path(shutil.which("z3") or "z3"))
    parser.add_argument("--java", default=shutil.which("java") or "java")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    return 0 if replay(args.jar.resolve(), args.z3.resolve(), args.java, args.output_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
