"""Finite-horizon accounting for comparing already admissible recovery candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .context import RecoveryCostParameters
from .experiment import ExperimentResult


@dataclass(frozen=True)
class RecoveryCost:
    service_loss: float
    recovery_duration: float
    intervention_cost: float
    backup_usage: float
    total: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def calculate_cost(
    result: ExperimentResult,
    strategy: str,
    weights: RecoveryCostParameters,
    *,
    service_target: float | None = None,
) -> RecoveryCost:
    """Compute J over a common horizon; safety/service admissibility is separate.

    Service loss counts every interval's shortfall to make a permitted temporary
    startup interruption visible in the cost, even when it occurs before the
    hard service deadline.  Omitting ``service_target`` preserves the historic
    per-plant ``min_service_flow`` accounting.  Selection passes its external
    incident demand explicitly, so curtailing a policy cannot erase demand.
    """

    target = result.parameters.min_service_flow if service_target is None else service_target
    if target < 0:
        raise ValueError("service_target must be nonnegative")

    service_loss = sum(
        max(0.0, target - record.q_delivered) * record.interval
        for record in result.records
    )
    if result.final_state.recovery_started_at is None:
        recovery_duration = result.parameters.horizon
    elif result.final_state.recovery_established_at is None:
        recovery_duration = result.parameters.horizon - result.final_state.recovery_started_at
    else:
        recovery_duration = (
            result.final_state.recovery_established_at - result.final_state.recovery_started_at
        )
    intervention_cost = (
        weights.conservative_intervention_cost
        if strategy in {"conservative_recovery", "controlled_safe_hold"}
        else weights.takeover_intervention_cost
        if strategy in {
            "trusted_backup_takeover",
            "trusted_flowing_backup_takeover",
            "trusted_delayed_isolation_flowing_backup_takeover",
        }
        else 0.0
    )
    backup_usage = sum(record.q2 * record.interval for record in result.records)
    total = (
        weights.service_loss_weight * service_loss
        + weights.recovery_time_weight * recovery_duration
        + weights.intervention_weight * intervention_cost
        + weights.backup_usage_weight * backup_usage
    )
    return RecoveryCost(service_loss, recovery_duration, intervention_cost, backup_usage, total)
