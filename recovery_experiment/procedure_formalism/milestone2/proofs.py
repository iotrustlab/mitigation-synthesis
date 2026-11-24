"""Portable proof profiles using the original finite-stage KeYmaera X runner."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from time import perf_counter_ns
from types import SimpleNamespace

from .. import verify

BASE = "c817476a8f1e92a7d801652e583d4e8d0a23096a"
ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
RESULTS = ROOT.parent / "results" / "milestone2"
FAMILIES = ("hand", "cost", "merwin")
TIMEOUT = verify.TIMEOUT
JAR_SHA256 = "c72cb700992e4c9fbf052113917e039ced43fa6c512493fe5473964e18b691bb"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def object_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


@dataclass(frozen=True)
class Obligation:
    name: str
    variables: tuple[str, ...]
    formula: str
    tactic: str = "implyR(1); chase(1); QE"

    def __post_init__(self):
        if (not re.fullmatch(r"[\w-]+", self.name) or not self.formula.strip() or not self.tactic.strip()
                or any(not re.fullmatch(r"[a-zA-Z]\w*", x) for x in self.variables)):
            raise ValueError("Invalid proof obligation")

    @classmethod
    def from_entry(cls, name, entry):
        match = re.search(r'ProgramVariables\s+(.*?)\s*End\.\s*Problem\s+(.*?)\s*End\.\s*Tactic "[^"]+"\s+(.*?)\s*End\.', entry, re.S)
        if not match:
            raise ValueError("Unsupported archive entry")
        declarations, formula, tactic = match.groups()
        return cls(name, tuple(re.findall(r"Real (\w+);", declarations)), formula.strip(), tactic.strip())


@dataclass(frozen=True)
class Profile:
    name: str
    obligations: tuple[Obligation, ...]
    dependencies: int
    plant_states: int
    horizon: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.name) or not self.obligations:
            raise ValueError("Expected identified, nonempty proof profile")
        if len({o.name for o in self.obligations}) != len(self.obligations):
            raise ValueError("Duplicate obligation name")

    @property
    def procedure(self):
        return SimpleNamespace(procedure_id=self.name)

    @property
    def profile_hash(self):
        return object_hash({"name": self.name, "tactics": [(o.name, o.tactic) for o in self.obligations],
                            "command": verify.COMMAND, "jar_sha256": JAR_SHA256})

    def title(self, name):
        return f"{self.name}_{name}"

    def entries(self, negative=False):
        entries = {}
        for o in self.obligations:
            declarations = " ".join(f"Real {v};" for v in sorted(set(o.variables)))
            entries[o.name] = (f'ArchiveEntry "{self.title(o.name)}"\nProgramVariables\n'
                               f'  {declarations}\nEnd.\nProblem\n  {o.formula}\nEnd.\n'
                               f'Tactic "Bounded proof"\n  {o.tactic}\nEnd.\nEnd.\n')
        return entries

    def archive(self, *, violation=False):
        return f"/* Recovery experiment {self.name}. Base {BASE}. */\n" + "\n".join(self.entries().values())

    @property
    def sha256(self):
        return digest(self.archive().encode())


def read_record(profile, root=None):
    root = Path(root) if root is not None else EVIDENCE
    try:
        row = json.loads((root / "records" / f"{profile.name}.json").read_text())
        if (row["case"] != profile.name or row["source_commit"] != BASE
                or row["proof_profile_sha256"] != profile.profile_hash
                or row["archive_sha256"] != profile.sha256 or row["jar_sha256"] != JAR_SHA256
                or (root / "models" / f"{profile.name}.kyx").read_bytes() != profile.archive().encode()):
            return None
        entries = profile.entries()
        if set(entries) != set(row["obligations"]):
            return None
        for name, o in row["obligations"].items():
            if o["status"] == "PROVED":
                raw = (root / "proof_records" / profile.name / f"{name}.kyp").read_bytes()
                if (digest(raw) != o["proof_sha256"] or entries[name].strip().encode() not in raw or
                        f'Lemma "user/{profile.title(name)}".'.encode() not in raw):
                    return None
        if row["status"] == "PROVED" and (row["return_code"] != 0 or any(
                o["status"] != "PROVED" for o in row["obligations"].values())):
            return None
        return row
    except (OSError, KeyError, TypeError, ValueError):
        return None


def proved(profile):
    record = read_record(profile)
    return record is not None and record["status"] == "PROVED"


def run(family, output, jar, z3, java, only=()):
    if digest(jar.read_bytes()) != JAR_SHA256:
        raise ValueError("KeYmaera X JAR differs from the pinned release")
    module = importlib.import_module(f"{__package__}.{family}")
    started = perf_counter_ns()
    profiles = module.profiles()
    construction_ns = perf_counter_ns() - started
    if set(only) - {p.name for p in profiles}:
        raise ValueError("Requested profile is absent")
    env = {"java": verify._version([java, "-version"]), "z3": verify._version([str(z3), "-version"]),
           "cleo": "not used", "jar_sha256": JAR_SHA256}
    out = Path(output)
    (out / "records").mkdir(parents=True, exist_ok=True)
    success = True
    with tempfile.TemporaryDirectory(prefix="dsn-proofs-") as scratch:
        work = Path(scratch)
        (work / ".keymaerax").mkdir()
        (work / ".keymaerax" / "solver").symlink_to(z3)
        for p in profiles:
            if only and p.name not in only:
                continue
            start = perf_counter_ns()
            archive_bytes = len(p.archive().encode())
            generation = perf_counter_ns() - start
            row = verify._solve(p, p.name, False, jar, z3, java, work, out)
            row.update(env, kind="experiment", timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       proof_profile_sha256=p.profile_hash, source_commit=BASE, command=verify.COMMAND,
                       configuration="Fresh isolated prover home per family replay, 60 s per obligation.",
                       model_generation_ns=generation, family_profile_construction_ns=construction_ns, archive_bytes=archive_bytes, dependencies=p.dependencies,
                       plant_states=p.plant_states, horizon=p.horizon)
            path = out / "records" / f"{p.name}.json"
            path.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
            valid = read_record(p, out) is not None and row["status"] == "PROVED"
            success &= valid
            print(f"{p.name}: {row['status']} ({row['wall_seconds']} s), validated={valid}", flush=True)
    return success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", choices=FAMILIES)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    parser.add_argument("--jar", type=Path, default=Path(os.environ.get("KEYMAERAX_JAR", "keymaerax.jar")))
    parser.add_argument("--z3", type=Path, default=Path(shutil.which("z3") or "z3"))
    parser.add_argument("--java", default=shutil.which("java") or "java")
    args = parser.parse_args()
    return 0 if run(args.family, args.output, args.jar.resolve(), args.z3.resolve(), args.java, args.only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
