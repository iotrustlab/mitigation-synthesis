"""Offline CLEO verifier for the separate delayed-isolation theorem."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .delayed_isolation_formal import render_delayed_isolation_recovery_envelope
from .delayed_isolation_proof_profile import attach_delayed_isolation_profile
from .formal import FormalStatus


@dataclass(frozen=True)
class DelayedIsolationVerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]
    milestones: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def _parse_with_cleo(envelope_text: str) -> Any:
    from cleo.envelope_format import parse_envelope
    from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string
    from cleo.session import EnvelopeSession

    spec = parse_envelope(envelope_text)
    if spec.defs_str:
        parse_defs_from_string(spec.defs_str)
    parse_formula_from_string(spec.precondition_str)
    parse_formula_from_string(spec.postcondition_str)
    parse_game_from_string(spec.game_str)
    session = EnvelopeSession(spec.game_str, spec.postcondition_str, defs_str=spec.defs_str)
    session.set_precondition(spec.precondition_str)
    return session


def _milestones(obligations: list[dict[str, Any]], all_passed: bool) -> dict[str, dict[str, Any]]:
    by_profile = {item.get("profile"): item["passed"] for item in obligations if item["kind"] == "ode"}
    arithmetic = next((item for item in obligations if item["kind"] == "arithmetic"), None)
    return {
        "A_isolation_delay_safety": {
            "specification": "two explicit P1 attacker choices preserve tank safety before isolation",
            "passed": by_profile.get("isolation_phase_one", False)
            and by_profile.get("isolation_phase_two", False),
        },
        "B_post_isolation_pre_backup_safety": {
            "specification": "safe flowing service continues after physical isolation and before P2 availability",
            "passed": by_profile.get("backup_pending_phase", False),
        },
        "C_backup_timing_and_service": {
            "specification": "P2 becomes available by TransferDeadline with actual delivery above qmin",
            "passed": bool(arithmetic and arithmetic["passed"]),
        },
        "D_mandatory_post_takeover_operation": {
            "specification": "balanced backup operation preserves safety and service for positive T",
            "passed": by_profile.get("operation_phase", False),
        },
        "E_complete_delayed_isolation_theorem": {
            "specification": "complete finite delayed-isolation recovery game",
            "passed": all_passed,
        },
    }


def verify_delayed_isolation_theorem(
    *, output_dir: Path | None = None
) -> DelayedIsolationVerificationResult:
    """Discharge the symbolic delayed-isolation theorem without runtime context input."""

    started = time.perf_counter()
    try:
        model = render_delayed_isolation_recovery_envelope()
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "delayed_isolation_recovery_takeover.instantiated.envelope").write_text(
                model.envelope_text
            )
        session = _parse_with_cleo(model.envelope_text)
        annotations = attach_delayed_isolation_profile(session)
        profiles = {annotation["game_id"]: annotation["profile"] for annotation in annotations}
        result = session.verify()
        obligations = [
            {
                "kind": record.obligation.kind,
                "game_id": record.obligation.game_id,
                "profile": profiles.get(record.obligation.game_id),
                "proof_goal": getattr(record.obligation, "kyx_formula", None),
                "tactic": getattr(record.obligation, "tactic", None),
                "passed": record.passed,
                "feedback": "" if record.passed else record.feedback,
            }
            for record in result.results
        ]
        status = FormalStatus.VERIFIED if result.all_passed else FormalStatus.UNVERIFIED
        reason = (
            "all symbolic delayed-isolation recovery obligations discharged"
            if result.all_passed
            else "one or more symbolic delayed-isolation recovery obligations remain unresolved"
        )
        milestones = _milestones(obligations, result.all_passed)
    except Exception as exc:
        annotations, obligations, milestones = [], [], {}
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO delayed-isolation theorem run did not complete: {type(exc).__name__}: {exc}"
    verification = DelayedIsolationVerificationResult(
        status, reason, time.perf_counter() - started, annotations, obligations, milestones
    )
    if output_dir:
        (output_dir / "delayed_isolation_verification.json").write_text(
            json.dumps(verification.as_dict(), indent=2) + "\n"
        )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the delayed-isolation theorem with CLEO.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/delayed-isolation-formal")
    )
    args = parser.parse_args()
    result = verify_delayed_isolation_theorem(output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
