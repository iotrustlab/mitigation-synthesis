"""Offline CLEO checks for the six-second common recovery horizon.

These checks instantiate the existing symbolic theorems with their unchanged
games.  They are not runtime authorization and do not replace either reviewed
certificate manifest.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .common_horizon import derive_common_formal_horizon, render_controlled_hold_horizon_envelope
from .formal import FormalStatus
from .parameterized_formal import PARAMETERIZED_PLANT_MODEL_ID, PARAMETERIZED_POLICY_ID
from .parameterized_proof_profile import attach_parameterized_profile
from .scenarios import named_contexts
from .state_dependent_concrete import render_state_dependent_context_envelope
from .state_dependent_formal import STATE_DEPENDENT_PLANT_MODEL_ID, STATE_DEPENDENT_POLICY_ID
from .state_dependent_proof_profile import attach_state_dependent_profile


@dataclass(frozen=True)
class HorizonPolicyVerification:
    policy: str
    status: FormalStatus
    reason: str
    elapsed_seconds: float
    annotations: list[dict[str, str]]
    obligations: list[dict[str, Any]]


@dataclass(frozen=True)
class CommonHorizonVerificationResult:
    formal_horizon: dict[str, float]
    policies: tuple[HorizonPolicyVerification, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "formal_horizon": self.formal_horizon,
            "policies": [
                asdict(policy) | {"status": policy.status.value} for policy in self.policies
            ],
        }


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


def _verify(
    policy: str, envelope_text: str, attach_profile, output_dir: Path | None
) -> HorizonPolicyVerification:
    started = time.perf_counter()
    try:
        if output_dir:
            (output_dir / f"{policy}.six-second.envelope").write_text(envelope_text)
        session = _parse_with_cleo(envelope_text)
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
        reason = (
            "all concrete six-second recovery obligations discharged"
            if result.all_passed
            else "one or more concrete six-second recovery obligations remain unresolved"
        )
    except Exception as exc:
        annotations, obligations = [], []
        status = FormalStatus.UNVERIFIED
        reason = f"CLEO common-horizon run did not complete: {type(exc).__name__}: {exc}"
    return HorizonPolicyVerification(
        policy, status, reason, time.perf_counter() - started, annotations, obligations
    )


def verify_common_horizon(
    *, output_dir: Path | None = None
) -> CommonHorizonVerificationResult:
    """Verify both canonical theorem games at the baseline six-second horizon."""

    baseline = named_contexts()["baseline_feasible"]
    horizon = derive_common_formal_horizon(baseline.plant, baseline.plant.horizon)
    controlled_context = replace(
        baseline,
        plant_model_id=PARAMETERIZED_PLANT_MODEL_ID,
        recovery_policy_id=PARAMETERIZED_POLICY_ID,
    )
    flowing_context = replace(
        baseline,
        plant_model_id=STATE_DEPENDENT_PLANT_MODEL_ID,
        recovery_policy_id=STATE_DEPENDENT_POLICY_ID,
    )
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    controlled = _verify(
        "controlled_hold",
        render_controlled_hold_horizon_envelope(controlled_context, horizon),
        attach_parameterized_profile,
        output_dir,
    )
    flowing = _verify(
        "flowing_takeover",
        render_state_dependent_context_envelope(
            flowing_context, operation_duration=horizon.post_takeover_operation_duration
        ).envelope_text,
        attach_state_dependent_profile,
        output_dir,
    )
    report = CommonHorizonVerificationResult(horizon.as_dict(), (controlled, flowing))
    if output_dir:
        (output_dir / "common_horizon_verification.json").write_text(
            json.dumps(report.as_dict(), indent=2) + "\n"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify both fixed recovery policies over the baseline six-second horizon."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("recovery_experiment/results/common-horizon-formal")
    )
    args = parser.parse_args()
    result = verify_common_horizon(output_dir=args.output_dir)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if all(policy.status is FormalStatus.VERIFIED for policy in result.policies) else 1


if __name__ == "__main__":
    raise SystemExit(main())
