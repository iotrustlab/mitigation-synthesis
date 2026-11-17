"""Check the Attleboro use-case traces against the scoped authority abstraction.

This is trace correspondence, not a proof that the IEC 61131-3 program refines
the KeYmaera X game. Synthetic traces are checked scan by scan. OpenPLC traces
are sampled after multiple scans, so only pointwise controller outputs are
checked; their initial retained latch is treated as observed, not assumed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


SOURCE_FILES = {
    "controller_st": "implementations/openplc/st/attleboro_controller.st",
    "simulator_st": "implementations/openplc/st/attleboro_simulator.st",
    "tag_contract": "tag_contract.yaml",
    "backend_map": "implementations/openplc/configs/openplc_map.yaml",
    "scenario_set": "scenarios/cases.yaml",
    "reference_core": "model/core.py",
    "reference_runner": "model/run.py",
    "live_driver": "model/live.py",
}
TRIP_INPUTS = (
    "ATT_EStop", "ATT_High_Temp", "ATT_High_Pressure_Switch",
    "ATT_pH_Out_Of_Range", "ATT_Flooded",
)
REQUIRED_TAGS = frozenset({
    "ATT_Utility_Available", "ATT_MTS_Generator", "ATT_Generator_Running",
    "ATT_Selector_Remote", "ATT_SCADA_Start_Request", "ATT_Reset_Request",
    "ATT_Trip", "ATT_Reset_Pending", "ATT_Remote_Eligible", "ATT_Remote_Start",
    *TRIP_INPUTS,
})


@dataclass(frozen=True)
class CorrespondenceResult:
    scenario: str
    backend: str
    status: str
    checked_rows: int
    checked_latch_transitions: int
    bad_power_rows: int
    restored_pending_rows: int
    enforcement_bypass_rows: int
    initial_latch_basis: str
    source_commit: str | None
    source_hashes: dict[str, str]
    startup_initialization: str | None
    mismatches: tuple[str, ...]
    scope: str = (
        "controller authority and start outputs only; no hydraulic service, "
        "Hand-path, current-site, or ST-to-dGL refinement claim"
    )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _bit(row: dict[str, str], tag: str, number: int) -> bool:
    value = row[tag]
    if value not in {"0", "1"}:
        raise ValueError(f"row {number}: {tag} must be 0 or 1, got {value!r}")
    return value == "1"


def _verify_sources(meta: dict[str, object], usecase_dir: Path) -> None:
    recorded = meta.get("artifact_sha256")
    if not isinstance(recorded, dict):
        raise ValueError("bundle lacks artifact_sha256 source bindings")
    for name, expected in recorded.items():
        relative = SOURCE_FILES.get(name)
        if relative is None or not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"unsupported or invalid source binding {name!r}")
        path = usecase_dir / relative
        if not path.is_file():
            raise ValueError(f"source binding missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"source binding changed: {relative}")
    if "controller_st" not in recorded or "tag_contract" not in recorded:
        raise ValueError("controller and tag-contract hashes are required")


def inspect_bundle(usecase_dir: Path, bundle_dir: Path) -> CorrespondenceResult:
    """Inspect one immutable bundle against the source-bound scan abstraction."""

    meta = json.loads((bundle_dir / "meta.json").read_text())
    if not isinstance(meta, dict):
        raise ValueError("bundle metadata must be a JSON object")
    if meta.get("usecase_id") != "attleboro-interconnection-2019-design-slice":
        raise ValueError("bundle has a different use-case identity")
    backend = meta.get("backend_type")
    if backend not in {"synthetic", "openplc"}:
        raise ValueError(f"unsupported backend {backend!r}")
    if meta.get("contract_version") != "0.1.0":
        raise ValueError("unsupported tag-contract version")
    _verify_sources(meta, usecase_dir)
    recorded = meta["artifact_sha256"]
    if backend == "synthetic" and not {"reference_core", "reference_runner"} <= set(recorded):
        raise ValueError("synthetic bundle lacks reference-model and runner bindings")
    if backend == "openplc" and "live_driver" not in recorded:
        raise ValueError("OpenPLC bundle lacks live-driver binding")

    with (bundle_dir / "tags.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_TAGS <= set(reader.fieldnames):
            missing = sorted(REQUIRED_TAGS - set(reader.fieldnames or ()))
            raise ValueError(f"bundle lacks authority tags: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("bundle has no controller observations")

    mismatches: list[str] = []
    previous_request: bool | None = False if backend == "synthetic" else None
    previous_pending: bool | None = False if backend == "synthetic" else None
    latch_checks = bad_power_rows = restored_pending_rows = bypass_rows = 0
    for number, row in enumerate(rows, start=1):
        bits = {tag: _bit(row, tag, number) for tag in REQUIRED_TAGS}
        bad_power = (
            not bits["ATT_Utility_Available"]
            or bits["ATT_MTS_Generator"]
            or bits["ATT_Generator_Running"]
        )
        trip = any(bits[tag] for tag in TRIP_INPUTS)
        if bits["ATT_Trip"] != trip:
            mismatches.append(f"row {number}: combined hardwired trip disagrees with protection inputs")
        pending = bits["ATT_Reset_Pending"]
        request = bits["ATT_Reset_Request"]
        if bad_power:
            bad_power_rows += 1
            if not pending:
                mismatches.append(f"row {number}: power loss did not set reset pending")
        if backend == "synthetic":
            assert previous_request is not None and previous_pending is not None
            expected_pending = (
                True if bad_power else
                False if request and not previous_request else
                previous_pending
            )
            latch_checks += 1
            if pending != expected_pending:
                mismatches.append(f"row {number}: reset latch differs from one-scan transition")
        # A live poll can skip PLC scans and reset pulses; it cannot establish
        # a one-scan latch transition from adjacent CSV rows.

        if (
            bits["ATT_Utility_Available"] and not bits["ATT_MTS_Generator"]
            and not bits["ATT_Generator_Running"] and pending and not request
        ):
            restored_pending_rows += 1
        eligible = (
            bits["ATT_Utility_Available"] and not bits["ATT_MTS_Generator"]
            and not bits["ATT_Generator_Running"] and not pending
            and bits["ATT_Selector_Remote"] and not bits["ATT_Trip"]
        )
        if bits["ATT_Remote_Eligible"] != eligible:
            mismatches.append(f"row {number}: remote eligibility differs from controller guard")
        start = eligible and bits["ATT_SCADA_Start_Request"]
        if bits["ATT_Remote_Start"] != start:
            mismatches.append(f"row {number}: remote start differs from eligibility-gated request")
        delivered = row.get("ATT_Delivered_Remote_Start")
        if delivered in {"0", "1"} and (delivered == "1") != bits["ATT_Remote_Start"]:
            bypass_rows += 1
        previous_request, previous_pending = request, pending

    return CorrespondenceResult(
        scenario=str(meta.get("scenario", bundle_dir.name)),
        backend=backend,
        status="MISMATCH" if mismatches else "MATCHED",
        checked_rows=len(rows),
        checked_latch_transitions=latch_checks,
        bad_power_rows=bad_power_rows,
        restored_pending_rows=restored_pending_rows,
        enforcement_bypass_rows=bypass_rows,
        initial_latch_basis=(
            "declared synthetic Machine initialization: reset_pending=False, previous_reset=False"
            if backend == "synthetic" else
            "observed first live row; prior startup scans and reset edge are not inferred"
        ),
        source_commit=meta.get("repo_commit") if isinstance(meta.get("repo_commit"), str) else None,
        source_hashes=dict(recorded),
        startup_initialization=meta.get("initialization") if isinstance(meta.get("initialization"), str) else None,
        mismatches=tuple(mismatches),
    )


def _source_checkout(usecase_dir: Path) -> tuple[str | None, bool | None]:
    """Identify the containing Git commit only when this use-case subtree is clean."""

    commit = subprocess.run(
        ["git", "-C", str(usecase_dir), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False,
    )
    if commit.returncode != 0:
        return None, None
    status = subprocess.run(
        ["git", "-C", str(usecase_dir), "status", "--porcelain", "--", "."],
        text=True, capture_output=True, check=False,
    )
    clean = status.returncode == 0 and not status.stdout.strip()
    return commit.stdout.strip() if clean else None, clean


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Attleboro authority trace correspondence.")
    parser.add_argument("--usecase-dir", required=True, type=Path)
    parser.add_argument("--bundle-dir", type=Path, help="One bundle; defaults to all local-reference and live bundles")
    parser.add_argument("--output", type=Path, help="Write the full correspondence receipt as JSON")
    args = parser.parse_args()
    root = args.usecase_dir.resolve()
    bundles = [args.bundle_dir.resolve()] if args.bundle_dir else sorted(
        path for parent in (root / "runs").iterdir() if parent.is_dir()
        for path in (parent.iterdir() if parent.name == "local-reference" else (parent,))
        if path.is_dir() and (path / "meta.json").exists()
    )
    try:
        if not bundles:
            raise ValueError("no Attleboro bundles were found")
        results = [inspect_bundle(root, bundle) for bundle in bundles]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID_BUNDLE", "reason": str(exc)}, indent=2))
        return 2
    source_commit, source_clean = _source_checkout(root)
    receipt = {
        "status": "MATCHED" if all(r.status == "MATCHED" for r in results) else "MISMATCH",
        "source_bundle_commit": source_commit,
        "source_usecase_subtree_clean": source_clean,
        "checked_bundles": len(results),
        "checked_rows": sum(r.checked_rows for r in results),
        "checked_latch_transitions": sum(r.checked_latch_transitions for r in results),
        "enforcement_bypass_rows": sum(r.enforcement_bypass_rows for r in results),
        "bundles": [r.as_dict() for r in results],
    }
    rendered = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if all(r.status == "MATCHED" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
