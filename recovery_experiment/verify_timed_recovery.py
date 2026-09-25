"""CLEO runner for the versioned, explicitly timed fixed-takeover theorem."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .context import ContextValidationError
from .formal import FormalStatus
from .scenarios import named_contexts
from .timed_formal import assess_timed_takeover_readiness, render_timed_recovery_envelope
from .timed_proof_profile import attach_timed_profile


@dataclass(frozen=True)
class TimedVerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]
    milestones: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def _parse_with_cleo(instance) -> tuple[Any, Any]:
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


def _milestones(obligations: list[dict[str, Any]], all_passed: bool) -> dict[str, dict[str, Any]]:
    ode_results = [item for item in obligations if item["kind"] == "ode"]
    arithmetic = next((item for item in obligations if item["kind"] == "arithmetic"), None)
    return {
        "A_timed_startup_safety": {
            "specification": "exact StartupDelay ODE with safe zero-flow startup",
            "passed": bool(ode_results) and ode_results[0]["passed"],
        },
        "B_delivery_by_deadline": {
            "specification": "postcondition includes qdelivered >= qmin and recoveryClock <= RecoveryDeadline",
            "passed": bool(arithmetic and arithmetic["passed"]),
        },
        "C_mandatory_operation": {
            "specification": "exact positive operation interval ending with safety and delivery",
            "passed": len(ode_results) == 2 and ode_results[1]["passed"],
        },
        "D_complete_fixed_policy": {
            "specification": "all generated obligations for the complete finite recovery game",
            "passed": all_passed,
        },
    }


def verify_timed_context(context, *, output_dir: Path | None = None) -> TimedVerificationResult:
    try:
        readiness = assess_timed_takeover_readiness(context)
    except (ContextValidationError, ValueError) as exc:
        return TimedVerificationResult(FormalStatus.INVALID_CONTEXT, str(exc), 0.0, [], [], {})
    if readiness.status is not FormalStatus.NOT_RUN:
        return TimedVerificationResult(readiness.status, readiness.reason, 0.0, [], [], {})

    started = time.perf_counter()
    try:
        instance = render_timed_recovery_envelope(context)
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "timed_recovery_takeover.instantiated.envelope").write_text(instance.envelope_text)
        _, session = _parse_with_cleo(instance)
        annotations = attach_timed_profile(session)
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
            "all timed-theorem obligations discharged"
            if result.all_passed
            else "one or more timed-theorem obligations remain unresolved"
        )
        milestones = _milestones(obligations, result.all_passed)
    except Exception as exc:
        annotations, obligations, milestones = [], [], {}
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO timed-theorem run did not complete: {type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    verified = TimedVerificationResult(status, reason, elapsed, annotations, obligations, milestones)
    if output_dir:
        (output_dir / "timed_verification.json").write_text(json.dumps(verified.as_dict(), indent=2) + "\n")
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the explicitly timed fixed takeover theorem with CLEO.")
    parser.add_argument("--context", choices=sorted(named_contexts()), default="baseline_feasible")
    parser.add_argument("--output-dir", type=Path, default=Path("recovery_experiment/results/timed-formal"))
    args = parser.parse_args()
    result = verify_timed_context(named_contexts()[args.context], output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
