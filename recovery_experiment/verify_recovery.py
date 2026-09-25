"""Separate CLEO runner for the new recovery envelope and proof profile.

Run with the Python environment that has CLEO installed, for example:
    "$CLEO_PYTHON" -m recovery_experiment.verify_recovery
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .context import ContextValidationError
from .formal import FormalStatus, assess_takeover_readiness, render_recovery_envelope
from .proof_profile import attach_profile
from .scenarios import named_contexts


@dataclass(frozen=True)
class VerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def _parse_with_cleo(instance) -> tuple[Any, Any]:
    """Import CLEO lazily so simulation remains usable without theorem tooling."""

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
    return spec, session


def verify_context(context, *, output_dir: Path | None = None) -> VerificationResult:
    try:
        readiness = assess_takeover_readiness(context)
    except (ContextValidationError, ValueError) as exc:
        return VerificationResult(FormalStatus.INVALID_CONTEXT, str(exc), 0.0, [], [])
    if readiness.status is not FormalStatus.NOT_RUN:
        return VerificationResult(readiness.status, readiness.reason, 0.0, [], [])

    started = time.perf_counter()
    try:
        instance = render_recovery_envelope(context)
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "recovery_takeover.instantiated.envelope").write_text(instance.envelope_text)
        _, session = _parse_with_cleo(instance)
        annotations = attach_profile(session)
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
        reason = "all CLEO obligations discharged" if result.all_passed else "one or more CLEO obligations remain unresolved"
    except Exception as exc:  # A backend/parser failure is never presented as infeasibility.
        annotations, obligations = [], []
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO run did not complete: {type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    verified = VerificationResult(status, reason, elapsed, annotations, obligations)
    if output_dir:
        (output_dir / "verification.json").write_text(json.dumps(verified.as_dict(), indent=2) + "\n")
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the concrete trusted-backup recovery model with CLEO.")
    parser.add_argument("--context", choices=sorted(named_contexts()), default="baseline_feasible")
    parser.add_argument("--output-dir", type=Path, default=Path("recovery_experiment/results/formal"))
    args = parser.parse_args()
    result = verify_context(named_contexts()[args.context], output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
