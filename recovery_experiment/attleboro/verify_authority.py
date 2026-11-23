"""Recheck the two scoped Attleboro authority theorems with KeYmaera X.

The proof is offline evidence. A successful run does not issue a Dr.ICS runtime
certificate, establish physical service, or authorize a plant action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


MODEL = Path(__file__).with_name("remote_authority.kyx")
ENTRIES = (
    "Generator or utility loss blocks remote start demand",
    "Utility return without a new reset blocks remote start demand",
)
WITNESS_MODEL = Path(__file__).with_name("remote_authority_nonvacuity.kyx")
WITNESS_ENTRIES = (
    "Attleboro bad power branch is reachable witness 2026",
    "Attleboro held reset branch is reachable witness 2026",
)
ARCHIVES = {
    "authority": (MODEL, ENTRIES, "remote_authority",
                  "controller remote authority after one scan, for two precondition classes only"),
    "nonvacuity": (WITNESS_MODEL, WITNESS_ENTRIES, "remote_authority_nonvacuity",
                    "two concrete preconditions and reachable one-scan poststates"),
}


def verify(jar: Path, z3: Path, output_dir: Path, timeout_seconds: int = 60,
           archive: str = "authority") -> dict[str, object]:
    model, entries, stem, scope = ARCHIVES[archive]
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob(f"{stem}-*.kyp"):
        stale.unlink()
    prefix = output_dir / f"{stem}.kyp"
    try:
        model_argument = str(model.relative_to(Path.cwd()))
    except ValueError:
        model_argument = str(model)
    command = [
        "java", "-Xss20M", "-jar", str(jar), "-launch", "-prove", model_argument,
        "-tool", "z3", "-z3path", str(z3), "-timeout", str(timeout_seconds),
        "-verbose", "-out", str(prefix),
    ]
    try:
        run = subprocess.run(
            command, text=True, capture_output=True, check=False,
            timeout=max(240, len(entries) * timeout_seconds + 120),
        )
        transcript = run.stdout + run.stderr
        return_code = run.returncode
    except subprocess.TimeoutExpired as exc:
        transcript = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        transcript += (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        transcript += "\nKeYmaera X process timed out.\n"
        return_code = -1
    transcript = transcript.rstrip() + "\n"
    (output_dir / f"{stem}_prover.log").write_text(transcript)
    proved = set(re.findall(r"^PROVED (.+?): tactic=", transcript, re.MULTILINE))
    failed = set(re.findall(r"^(?:UNPROVED|FAILED) (.+?):", transcript, re.MULTILINE))
    artifacts = sorted(path for path in output_dir.glob(f"{stem}-*.kyp") if path.is_file())
    status = (
        "VERIFIED"
        if return_code == 0 and set(entries) <= proved
        and len(artifacts) == len(entries) and all(path.stat().st_size > 0 for path in artifacts)
        else "UNVERIFIED"
    )
    version = re.search(r"KeYmaera X Prover ([^\n]+)", transcript)
    result = {
        "status": status,
        "archive": archive,
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "proof_scope": scope,
        "prover": "KeYmaera X " + version.group(1) if version else "KeYmaera X version not reported",
        "arithmetic_backend": "Z3",
        "return_code": return_code,
        "entries": {entry: "PROVED" if entry in proved else "FAILED" if entry in failed else "NO_RESULT" for entry in entries},
        "proof_artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts
        },
    }
    (output_dir / f"{stem}_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove scoped Attleboro remote-authority properties.")
    parser.add_argument("--jar", type=Path, default=Path(os.environ.get("KEYMAERAX_JAR", "keymaerax.jar")))
    parser.add_argument("--z3", type=Path, default=Path(shutil.which("z3") or "z3"))
    parser.add_argument("--output-dir", type=Path, default=Path("recovery_experiment/attleboro/proof_records"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--archive", choices=tuple(ARCHIVES), default="authority")
    args = parser.parse_args()
    if not args.jar.is_file() or not args.z3.is_file() or args.timeout_seconds <= 0:
        parser.error("existing --jar, --z3, and positive --timeout-seconds are required")
    result = verify(args.jar.resolve(), args.z3.resolve(), args.output_dir,
                    args.timeout_seconds, args.archive)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
