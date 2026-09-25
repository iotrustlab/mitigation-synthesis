"""Offline CLEO proof runner for the controlled-safe-hold theorem."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .controlled_safe_hold_formal import render_controlled_safe_hold_envelope
from .controlled_safe_hold_proof_profile import attach_controlled_safe_hold_profile
from .formal import FormalStatus


@dataclass(frozen=True)
class ControlledSafeHoldVerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    formal_model_id: str
    proof_profile_id: str
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]
    milestones: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def _session(envelope_text: str) -> Any:
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
    ode = next((obligation for obligation in obligations if obligation["kind"] == "ode"), None)
    arithmetic = next((obligation for obligation in obligations if obligation["kind"] == "arithmetic"), None)
    return {
        "A_attacker_before_isolation": {
            "specification": "the game universally considers both P1 commands before immediate isolation",
            "passed": bool(arithmetic and arithmetic["passed"]),
        },
        "B_mandatory_safe_hold": {
            "specification": "one positive-duration hold ODE preserves closed tank safety without safety in its domain",
            "passed": bool(ode and ode["passed"]),
        },
        "C_external_demand_service_curtailment": {
            "specification": "external demand remains positive while actual delivery is zero for the hold duration",
            "passed": all_passed,
        },
        "D_budgeted_independent_hold": {
            "specification": "budget remains nonnegative after independent isolation and hold-control cost",
            "passed": all_passed,
        },
    }


def verify_controlled_safe_hold_theorem(
    *, output_dir: Path | None = None
) -> ControlledSafeHoldVerificationResult:
    """Attempt the offline symbolic proof; this never authorizes a runtime context."""

    started = time.perf_counter()
    model = render_controlled_safe_hold_envelope()
    try:
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "controlled_safe_hold.generated.envelope").write_text(model.envelope_text)
        session = _session(model.envelope_text)
        annotations = attach_controlled_safe_hold_profile(session)
        result = session.verify()
        obligations = [
            {
                "kind": record.obligation.kind,
                "game_id": record.obligation.game_id,
                "passed": record.passed,
                "feedback": "" if record.passed else record.feedback,
            }
            for record in result.results
        ]
        status = FormalStatus.VERIFIED if result.all_passed else FormalStatus.UNVERIFIED
        reason = (
            "all controlled-safe-hold symbolic obligations discharged"
            if result.all_passed
            else "one or more controlled-safe-hold symbolic obligations remain unresolved"
        )
        milestones = _milestones(obligations, result.all_passed)
    except Exception as exc:
        annotations, obligations, milestones = [], [], {}
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO controlled-safe-hold theorem run did not complete: {type(exc).__name__}: {exc}"
    verification = ControlledSafeHoldVerificationResult(
        status,
        reason,
        time.perf_counter() - started,
        model.model_id,
        annotations[0]["profile"] if annotations else "unattached",
        annotations,
        obligations,
        milestones,
    )
    if output_dir:
        (output_dir / "controlled_safe_hold_verification.json").write_text(
            json.dumps(verification.as_dict(), indent=2) + "\n"
        )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the controlled-safe-hold theorem with CLEO.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/controlled-safe-hold")
    )
    args = parser.parse_args()
    result = verify_controlled_safe_hold_theorem(output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
