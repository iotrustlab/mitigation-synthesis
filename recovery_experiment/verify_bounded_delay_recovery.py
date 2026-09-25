"""Run offline CLEO proof attempts for builder-generated bounded schedules."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .bounded_delay_formal import build_bounded_delay_formal_model
from .bounded_delay_proof_profile import attach_bounded_delay_profile, generated_profile
from .formal import FormalStatus
from .recovery_model_builder import BoundedIsolationSchedule


@dataclass(frozen=True)
class BoundedDelayVerificationResult:
    status: FormalStatus
    reason: str
    schedule: BoundedIsolationSchedule
    formal_model_id: str
    proof_profile: dict[str, object]
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["schedule"] = self.schedule.as_dict()
        return data


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


def verify_bounded_delay_theorem(
    schedule: BoundedIsolationSchedule,
    *,
    output_dir: Path | None = None,
) -> BoundedDelayVerificationResult:
    """Attempt a proof without issuing a certificate or changing runtime policy."""

    schedule.validate()
    if schedule.isolation_periods == 0 and schedule.startup_periods == 2:
        raise ValueError("the reviewed 0T/2T shape uses its existing state-dependent verifier")
    started = time.perf_counter()
    model = build_bounded_delay_formal_model(schedule)
    profile = generated_profile(schedule)
    try:
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "bounded_delay_recovery.generated.envelope").write_text(model.envelope_text)
        session = _session(model.envelope_text)
        annotations = attach_bounded_delay_profile(session, schedule)
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
            "all generated bounded-delay obligations discharged"
            if result.all_passed
            else "one or more generated bounded-delay obligations remain unresolved"
        )
    except Exception as exc:
        annotations, obligations = [], []
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO bounded-delay theorem run did not complete: {type(exc).__name__}: {exc}"
    verification = BoundedDelayVerificationResult(
        status,
        reason,
        schedule,
        model.model_id,
        profile.as_dict(),
        time.perf_counter() - started,
        annotations,
        obligations,
    )
    if output_dir:
        (output_dir / "bounded_delay_verification.json").write_text(
            json.dumps(verification.as_dict(), indent=2) + "\n"
        )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one generated bounded delayed-isolation theorem.")
    parser.add_argument("--isolation-periods", type=int, required=True)
    parser.add_argument("--startup-periods", type=int, required=True)
    parser.add_argument("--control-period", type=float, default=0.5)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/bounded-delay-formal")
    )
    args = parser.parse_args()
    schedule = BoundedIsolationSchedule(args.control_period, args.isolation_periods, args.startup_periods)
    result = verify_bounded_delay_theorem(schedule, output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.status is FormalStatus.VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
