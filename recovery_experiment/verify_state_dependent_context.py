"""CLEO runner for a concrete state inside the state-dependent recovery region."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .context import ContextValidationError, RecoveryContext
from .formal import FormalStatus
from .state_dependent_concrete import (
    assess_state_dependent_readiness,
    render_state_dependent_context_envelope,
)
from .state_dependent_proof_profile import attach_state_dependent_profile


@dataclass(frozen=True)
class StateDependentConcreteVerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def _parse_with_cleo(instance) -> Any:
    from cleo.envelope_format import parse_envelope
    from cleo.parser import parse_defs_from_string, parse_formula_from_string, parse_game_from_string
    from cleo.session import EnvelopeSession

    spec = parse_envelope(instance.envelope_text)
    if spec.defs_str:
        parse_defs_from_string(spec.defs_str)
    parse_formula_from_string(spec.precondition_str)
    parse_formula_from_string(spec.postcondition_str)
    parse_game_from_string(spec.game_str)
    session = EnvelopeSession(spec.game_str, spec.postcondition_str, defs_str=spec.defs_str)
    session.set_precondition(spec.precondition_str)
    return session


def verify_state_dependent_context(
    context: RecoveryContext, *, output_dir: Path | None = None
) -> StateDependentConcreteVerificationResult:
    """Independently discharge a concrete instantiation; no manifest is consulted."""

    try:
        readiness = assess_state_dependent_readiness(context)
    except (ContextValidationError, ValueError) as exc:
        return StateDependentConcreteVerificationResult(FormalStatus.INVALID_CONTEXT, str(exc), 0.0, [], [])
    if readiness.status is not FormalStatus.NOT_RUN:
        return StateDependentConcreteVerificationResult(readiness.status, readiness.reason, 0.0, [], [])

    started = time.perf_counter()
    try:
        instance = render_state_dependent_context_envelope(context)
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "state_dependent_recovery_takeover.concrete.envelope").write_text(
                instance.envelope_text
            )
        session = _parse_with_cleo(instance)
        annotations = attach_state_dependent_profile(session)
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
            "all concrete state-dependent recovery obligations discharged"
            if result.all_passed
            else "one or more concrete state-dependent recovery obligations remain unresolved"
        )
    except Exception as exc:
        annotations, obligations = [], []
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO concrete state-dependent run did not complete: {type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    verified = StateDependentConcreteVerificationResult(status, reason, elapsed, annotations, obligations)
    if output_dir:
        (output_dir / "state_dependent_concrete_verification.json").write_text(
            json.dumps(verified.as_dict(), indent=2) + "\n"
        )
    return verified


def main() -> int:
    from .state_dependent_evaluation import state_dependent_evaluation_contexts

    parser = argparse.ArgumentParser(description="Verify one concrete flowing-startup recovery context with CLEO.")
    parser.add_argument("--context", choices=sorted(state_dependent_evaluation_contexts()), default="safe_recoverable")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/state-dependent-concrete")
    )
    args = parser.parse_args()
    result = verify_state_dependent_context(
        state_dependent_evaluation_contexts()[args.context], output_dir=args.output_dir
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
