"""Offline CLEO verifier for the symbolic trusted-backup takeover theorem."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .formal import FormalStatus
from .parameterized_formal import render_parameterized_recovery_envelope
from .parameterized_proof_profile import attach_parameterized_profile


@dataclass(frozen=True)
class ParameterizedVerificationResult:
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
    odes = [item for item in obligations if item["kind"] == "ode"]
    arithmetic = next((item for item in obligations if item["kind"] == "arithmetic"), None)
    return {
        "A_symbolic_startup_safety": {
            "specification": "all safe symbolic initial tank states survive exact zero-flow startup",
            "passed": bool(odes) and odes[0]["passed"],
        },
        "B_symbolic_delivery_deadline": {
            "specification": "symbolic capacity and timing assumptions imply required delivery by deadline",
            "passed": bool(arithmetic and arithmetic["passed"]),
        },
        "C_symbolic_mandatory_operation": {
            "specification": "all certified initial states survive the positive balanced operating interval",
            "passed": len(odes) == 2 and odes[1]["passed"],
        },
        "D_parameterized_fixed_policy": {
            "specification": "complete symbolic finite recovery game",
            "passed": all_passed,
        },
    }


def verify_parameterized_theorem(
    *, output_dir: Path | None = None
) -> ParameterizedVerificationResult:
    """Discharge the offline symbolic theorem once; this never inspects runtime context."""

    started = time.perf_counter()
    try:
        model = render_parameterized_recovery_envelope()
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "parameterized_recovery_takeover.instantiated.envelope").write_text(
                model.envelope_text
            )
        session = _parse_with_cleo(model.envelope_text)
        annotations = attach_parameterized_profile(session)
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
            "all symbolic recovery obligations discharged"
            if result.all_passed
            else "one or more symbolic recovery obligations remain unresolved"
        )
        milestones = _milestones(obligations, result.all_passed)
    except Exception as exc:
        annotations, obligations, milestones = [], [], {}
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO parameterized-theorem run did not complete: {type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    verification = ParameterizedVerificationResult(
        status, reason, elapsed, annotations, obligations, milestones
    )
    if output_dir:
        (output_dir / "parameterized_verification.json").write_text(
            json.dumps(verification.as_dict(), indent=2) + "\n"
        )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the offline parameterized takeover theorem with CLEO.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/parameterized-formal")
    )
    args = parser.parse_args()
    result = verify_parameterized_theorem(output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
