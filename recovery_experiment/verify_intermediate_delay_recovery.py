"""Attempt an offline CLEO proof for the generated one-control-period game."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .formal import FormalStatus
from .intermediate_delay_formal import render_intermediate_delay_recovery_envelope
from .intermediate_delay_proof_profile import attach_intermediate_delay_profile


@dataclass(frozen=True)
class IntermediateDelayVerificationResult:
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]

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


def verify_intermediate_delay_theorem(
    *, output_dir: Path | None = None
) -> IntermediateDelayVerificationResult:
    """Run a new proof attempt; never convert profile reuse into verification."""

    started = time.perf_counter()
    try:
        model = render_intermediate_delay_recovery_envelope()
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "intermediate_delay_recovery.generated.envelope").write_text(model.envelope_text)
        session = _session(model.envelope_text)
        annotations = attach_intermediate_delay_profile(session)
        profiles = {entry["game_id"]: entry["profile"] for entry in annotations}
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
            "all generated one-control-period delayed-isolation obligations discharged"
            if result.all_passed
            else "one or more generated one-control-period delayed-isolation obligations remain unresolved"
        )
    except Exception as exc:
        annotations, obligations = [], []
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO intermediate-delay theorem run did not complete: {type(exc).__name__}: {exc}"
    verification = IntermediateDelayVerificationResult(
        status, reason, time.perf_counter() - started, annotations, obligations
    )
    if output_dir:
        (output_dir / "intermediate_delay_verification.json").write_text(
            json.dumps(verification.as_dict(), indent=2) + "\n"
        )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the generated one-control-period delay theorem with CLEO.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/intermediate-delay-formal")
    )
    args = parser.parse_args()
    result = verify_intermediate_delay_theorem(output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
