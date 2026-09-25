"""Generated one-control-period delayed-isolation formal recovery problem.

The envelope is constructed by ``recovery_model_builder`` rather than kept as
another handwritten canonical artifact.  It has no certificate by default.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .context import RecoveryContext
from .model import PlantParameters, TwoTankPlant
from .recovery_model_builder import (
    INTERMEDIATE_DELAY_MODEL_ID,
    INTERMEDIATE_DELAY_POLICY_ID,
    INTERMEDIATE_DELAY_PROOF_PROFILE_ID,
    BuildStatus,
    build_recovery_problem,
)


INTERMEDIATE_DELAY_PLANT_MODEL_ID = "one-control-period-isolation-state-dependent-two-tank-v1"


@dataclass(frozen=True)
class IntermediateDelayFormalModel:
    model_id: str
    envelope_text: str
    certified_conditions: tuple[str, ...]


def _symbolic_shape_context() -> RecoveryContext:
    """Supply timing shape only; the resulting theorem remains symbolic."""

    plant = replace(
        PlantParameters(),
        isolation_delay=0.5,
        backup_startup_delay=1.5,
        transfer_recovery_deadline=1.5,
    )
    return RecoveryContext.from_plant(TwoTankPlant(plant))


def render_intermediate_delay_recovery_envelope() -> IntermediateDelayFormalModel:
    """Render the one-control-period P1 influence game from typed phases."""

    generated = build_recovery_problem(_symbolic_shape_context())
    if generated.status is not BuildStatus.CONSTRUCTED or generated.envelope_text is None:
        raise RuntimeError(f"intermediate-delay builder did not construct a formal problem: {generated.reasons}")
    if generated.formal_model_id != INTERMEDIATE_DELAY_MODEL_ID:
        raise RuntimeError("intermediate-delay builder selected an unexpected formal model")
    return IntermediateDelayFormalModel(
        model_id=INTERMEDIATE_DELAY_MODEL_ID,
        envelope_text=generated.envelope_text,
        certified_conditions=(
            "L1 <= x1 <= H1 and L2 <= x2 <= H2 with L1,L2 >= 0",
            "P1 is Demon-controlled for exactly one ControlPeriod before trusted physical isolation",
            "ControlPeriod > 0, IsolationDelay = ControlPeriod, and StartupDelay = 3*ControlPeriod",
            "qprimary >= startupInflow and qprimary >= startupWithdrawal",
            "x1 + startupInflow*StartupDelay <= H1 and x1 + (startupInflow-qprimary)*IsolationDelay >= L1",
            "x2 - startupWithdrawal*StartupDelay >= L2 and x2 + (qprimary-startupWithdrawal)*IsolationDelay <= H2",
            "startupWithdrawal >= qmin > 0, qbackup >= qmin, and StartupDelay <= TransferDeadline",
            "trusted physical isolation becomes effective after one control period while P2 starts at time zero",
            "post-takeover qin = demand = qout = qbackup and budget covers isolation plus backup activation",
        ),
    )

