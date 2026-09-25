"""Builder-generated formal models for bounded isolation schedules."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .context import RecoveryContext
from .model import PlantParameters, TwoTankPlant
from .recovery_model_builder import (
    BOUNDED_DELAY_POLICY_ID,
    BuildStatus,
    BoundedIsolationSchedule,
    GeneratedRecoveryProblem,
    build_recovery_problem,
)


BOUNDED_DELAY_PLANT_MODEL_ID = "bounded-isolation-state-dependent-two-tank-v1"


@dataclass(frozen=True)
class BoundedDelayFormalModel:
    model_id: str
    schedule: BoundedIsolationSchedule
    envelope_text: str
    certified_conditions: tuple[str, ...]


def symbolic_shape_context(schedule: BoundedIsolationSchedule) -> RecoveryContext:
    """Create only the timing shape; all theorem values remain symbolic."""

    schedule.validate()
    plant = replace(
        PlantParameters(),
        control_period=schedule.control_period,
        isolation_delay=schedule.isolation_delay,
        backup_startup_delay=schedule.startup_delay,
        transfer_recovery_deadline=schedule.startup_delay,
    )
    return RecoveryContext.from_plant(TwoTankPlant(plant))


def _conditions(schedule: BoundedIsolationSchedule) -> tuple[str, ...]:
    delay_conditions = (
        "P1 is Demon-controlled at exactly 0 control boundaries because trusted isolation is immediately effective",
        "x1 + startupInflow*StartupDelay <= H1 and x2 - startupWithdrawal*StartupDelay >= L2",
    ) if schedule.isolation_periods == 0 else (
        f"P1 is Demon-controlled at exactly {schedule.isolation_periods} control boundaries before trusted physical isolation",
        "x1 + startupInflow*StartupDelay <= H1 and x1 + (startupInflow-qprimary)*IsolationDelay >= L1",
        "x2 - startupWithdrawal*StartupDelay >= L2 and x2 + (qprimary-startupWithdrawal)*IsolationDelay <= H2",
    )
    return (
        "L1 <= x1 <= H1 and L2 <= x2 <= H2 with L1,L2 >= 0",
        f"ControlPeriod > 0, IsolationDelay = {schedule.isolation_periods}*ControlPeriod, and StartupDelay = {schedule.startup_periods}*ControlPeriod",
        "qprimary >= startupInflow and qprimary >= startupWithdrawal",
        *delay_conditions,
        "startupWithdrawal >= qmin > 0, qbackup >= qmin, and StartupDelay <= TransferDeadline",
        "trusted physical isolation becomes effective after the exact bounded schedule while P2 starts at time zero",
        "post-takeover qin = demand = qout = qbackup and budget covers isolation plus backup activation",
    )


def build_bounded_delay_formal_model(schedule: BoundedIsolationSchedule) -> BoundedDelayFormalModel:
    """Render a bounded-schedule game from the shared recovery builder."""

    schedule.validate()
    if schedule.isolation_periods == 0 and schedule.startup_periods == 2:
        raise ValueError("the reviewed 0T/2T shape uses its existing state-dependent proof profile")
    generated: GeneratedRecoveryProblem = build_recovery_problem(symbolic_shape_context(schedule))
    if generated.status is not BuildStatus.CONSTRUCTED or generated.envelope_text is None:
        raise RuntimeError(f"bounded-delay builder did not construct a formal problem: {generated.reasons}")
    if generated.spec is None or generated.spec.schedule != schedule:
        raise RuntimeError("bounded-delay builder selected an unexpected timing shape")
    return BoundedDelayFormalModel(
        model_id=generated.formal_model_id or "unavailable",
        schedule=schedule,
        envelope_text=generated.envelope_text,
        certified_conditions=_conditions(schedule),
    )
