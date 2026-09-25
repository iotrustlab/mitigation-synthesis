"""Small deterministic two-tank plant used by the recovery experiment.

All flow variables are *level-equivalent rates* in level-units per second.  This
absorbs each tank's cross-sectional area into its rates, so Euler integration is
dimensionally consistent without pretending these values come from a testbed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ModelValidationError(ValueError):
    """Raised when a plant configuration or action is outside this experiment."""


class AttackerAction(str, Enum):
    NOOP = "noop"
    FORCE_PRIMARY_OFF = "force_primary_off"
    FORCE_PRIMARY_ON = "force_primary_on"


class DefenderAction(str, Enum):
    NORMAL = "normal_operation"
    CONSERVATIVE_HOLD = "conservative_hold"
    START_CONTROLLED_SAFE_HOLD = "start_controlled_safe_hold"
    START_TAKEOVER = "start_trusted_takeover"
    START_FLOWING_TAKEOVER = "start_trusted_flowing_takeover"
    START_DELAYED_ISOLATION_FLOWING_TAKEOVER = "start_trusted_delayed_isolation_flowing_takeover"


@dataclass(frozen=True)
class PlantParameters:
    """Synthetic parameters for the abstract parallel-pump topology."""

    low_t1: float = 4.0
    high_t1: float = 11.0
    low_t2: float = 3.0
    high_t2: float = 9.0
    upstream_nominal: float = 1.5
    downstream_demand: float = 1.5
    primary_capacity: float = 1.5
    backup_capacity: float = 1.5
    min_service_flow: float = 1.2
    control_period: float = 0.5
    backup_startup_delay: float = 1.0
    isolation_delay: float = 0.0
    service_deadline: float = 1.5
    transfer_recovery_deadline: float = 1.5
    startup_inflow_rate: float = 1.0
    startup_withdrawal_rate: float = 1.2
    horizon: float = 6.0

    def validate(self) -> None:
        if not (self.low_t1 < self.high_t1 and self.low_t2 < self.high_t2):
            raise ModelValidationError("each tank needs a strictly ordered safety interval")
        nonnegative = {
            "upstream_nominal": self.upstream_nominal,
            "downstream_demand": self.downstream_demand,
            "primary_capacity": self.primary_capacity,
            "backup_capacity": self.backup_capacity,
            "min_service_flow": self.min_service_flow,
            "backup_startup_delay": self.backup_startup_delay,
            "isolation_delay": self.isolation_delay,
            "service_deadline": self.service_deadline,
            "transfer_recovery_deadline": self.transfer_recovery_deadline,
            "startup_inflow_rate": self.startup_inflow_rate,
            "startup_withdrawal_rate": self.startup_withdrawal_rate,
        }
        for name, value in nonnegative.items():
            if value < 0:
                raise ModelValidationError(f"{name} must be nonnegative")
        if self.control_period <= 0 or self.horizon <= 0:
            raise ModelValidationError("control_period and horizon must be positive")
        if self.horizon < self.control_period:
            raise ModelValidationError("horizon must contain at least one control period")

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class PlantState:
    """Runtime state, kept separate from immutable plant knowledge."""

    x1: float = 7.0
    x2: float = 6.0
    time: float = 0.0
    control_cycle: int = 0
    p1_command: bool = True
    p2_command: bool = False
    upstream_enabled: bool = True
    demand_enabled: bool = True
    isolation_commanded: bool = False
    primary_path_isolated: bool = False
    backup_start_remaining: float = 0.0
    isolation_remaining: float = 0.0
    recovery_started_at: float | None = None
    recovery_established_at: float | None = None
    flowing_startup_active: bool = False

    def copy(self) -> "PlantState":
        return PlantState(**asdict(self))


@dataclass(frozen=True)
class FlowSnapshot:
    q_in: float
    q1: float
    q2: float
    q_demand: float
    q_out: float
    q_delivered: float
    p1_effective_state: bool
    p2_effective_state: bool


@dataclass(frozen=True)
class StepRecord:
    """One interval's trace row, recorded at the end of its integration interval."""

    timestamp: float
    control_cycle: int
    x1: float
    x2: float
    p1_command: bool
    p1_effective_state: bool
    p2_command: bool
    p2_effective_state: bool
    primary_path_isolated: bool
    isolation_commanded: bool
    isolation_pending_during_interval: bool
    isolation_effective_during_interval: bool
    backup_start_pending_during_interval: bool
    q_in: float
    q1: float
    q2: float
    q_demand: float
    q_out: float
    q_delivered: float
    attacker_action: str
    defender_action: str
    safety_status: str
    service_status: str
    recovery_status: str
    interval: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TwoTankPlant:
    """Explicit T1 -> {P1, P2} -> T2 plant with a trusted P1 isolator.

    An interval is executed in this exact order: observe, attacker command,
    defender command, apply any zero-delay trusted transition, calculate flows,
    evolve the plant with forward Euler, evaluate monitors, then advance delayed
    transition clocks.  Delayed transitions therefore become effective at the
    next control boundary; a zero-delay transition is effective immediately.
    """

    def __init__(self, parameters: PlantParameters, state: PlantState | None = None):
        parameters.validate()
        self.parameters = parameters
        self.state = state.copy() if state else PlantState()
        self._validate_state(self.state)

    def _validate_state(self, state: PlantState) -> None:
        if state.time < 0 or state.control_cycle < 0:
            raise ModelValidationError("time and control_cycle must be nonnegative")
        if state.backup_start_remaining < 0 or state.isolation_remaining < 0:
            raise ModelValidationError("transition timers must be nonnegative")
        if not self.within_model_domain(state):
            raise ModelValidationError("initial tank levels must be inside the model domain")

    def within_model_domain(self, state: PlantState | None = None) -> bool:
        state = state or self.state
        p = self.parameters
        return p.low_t1 <= state.x1 <= p.high_t1 and p.low_t2 <= state.x2 <= p.high_t2

    def safety_ok(self, state: PlantState | None = None) -> bool:
        return self.within_model_domain(state)

    def apply_attacker(self, action: AttackerAction) -> None:
        if action is AttackerAction.NOOP:
            return
        if action is AttackerAction.FORCE_PRIMARY_OFF:
            self.state.p1_command = False
            return
        if action is AttackerAction.FORCE_PRIMARY_ON:
            self.state.p1_command = True
            return
        raise ModelValidationError(f"unsupported attacker action: {action}")

    def apply_defender(self, action: DefenderAction) -> None:
        state, p = self.state, self.parameters
        if action is DefenderAction.NORMAL:
            return
        if action is DefenderAction.CONSERVATIVE_HOLD:
            state.upstream_enabled = False
            state.demand_enabled = False
            if state.recovery_started_at is None:
                state.recovery_started_at = state.time
                state.recovery_established_at = state.time
            return
        if action is DefenderAction.START_CONTROLLED_SAFE_HOLD:
            if p.isolation_delay > 1e-12:
                raise ModelValidationError("controlled safe hold requires immediate trusted isolation")
            state.isolation_commanded = True
            state.isolation_remaining = 0.0
            state.p2_command = False
            state.upstream_enabled = False
            state.demand_enabled = False
            state.flowing_startup_active = False
            if state.recovery_started_at is None:
                state.recovery_started_at = state.time
                state.recovery_established_at = state.time
            return
        if action is DefenderAction.START_TAKEOVER:
            if state.recovery_started_at is None:
                state.recovery_started_at = state.time
                state.p2_command = True
                state.isolation_commanded = True
                state.backup_start_remaining = p.backup_startup_delay
                state.isolation_remaining = p.isolation_delay
            # The controlled transition holds external flow and demand at zero.
            # Once both trusted mechanisms are effective, nominal balanced flow resumes.
            if self._p2_effective() and state.primary_path_isolated:
                state.upstream_enabled = True
                state.demand_enabled = True
                if state.recovery_established_at is None:
                    state.recovery_established_at = state.time
            else:
                state.upstream_enabled = False
                state.demand_enabled = False
            return
        if action is DefenderAction.START_FLOWING_TAKEOVER:
            self._start_flowing_takeover()
            return
        if action is DefenderAction.START_DELAYED_ISOLATION_FLOWING_TAKEOVER:
            if p.isolation_delay <= 0:
                raise ModelValidationError("delayed-isolation takeover requires a positive isolation delay")
            self._start_flowing_takeover()
            return
        raise ModelValidationError(f"unsupported defender action: {action}")

    def _start_flowing_takeover(self) -> None:
        """Start P2 concurrently with isolation while preserving startup service."""

        state, p = self.state, self.parameters
        if state.recovery_started_at is None:
            state.recovery_started_at = state.time
            state.p2_command = True
            state.isolation_commanded = True
            state.backup_start_remaining = p.backup_startup_delay
            state.isolation_remaining = p.isolation_delay
            state.flowing_startup_active = True
        # Unlike controlled hold, this policy intentionally keeps source inflow
        # and downstream withdrawal active until trusted P2 becomes available.
        if self._p2_effective() and state.primary_path_isolated:
            state.flowing_startup_active = False
            state.upstream_enabled = True
            state.demand_enabled = True
            if state.recovery_established_at is None:
                state.recovery_established_at = state.time
        else:
            state.upstream_enabled = True
            state.demand_enabled = True

    def _p1_effective(self) -> bool:
        return self.state.p1_command and not self.state.primary_path_isolated

    def _p2_effective(self) -> bool:
        return self.state.p2_command and self.state.backup_start_remaining <= 1e-12

    def _apply_zero_delay_transitions(self) -> None:
        state = self.state
        if state.isolation_commanded and state.isolation_remaining <= 1e-12:
            state.primary_path_isolated = True

    def flows(self) -> FlowSnapshot:
        self._apply_zero_delay_transitions()
        state, p = self.state, self.parameters
        p1_effective = self._p1_effective()
        p2_effective = self._p2_effective()
        q1 = p.primary_capacity if p1_effective else 0.0
        q2 = p.backup_capacity if p2_effective else 0.0
        flowing_startup = state.flowing_startup_active and not (
            p2_effective and state.primary_path_isolated
        )
        q_in = (
            p.startup_inflow_rate
            if flowing_startup
            else p.upstream_nominal
            if state.upstream_enabled
            else 0.0
        )
        q_demand = (
            p.startup_withdrawal_rate
            if flowing_startup
            else p.downstream_demand
            if state.demand_enabled
            else 0.0
        )
        # qout is physical withdrawal from T2. Delivery may come from stored
        # water, so it is not capped by the instantaneous pump-transfer rate.
        q_out = q_demand
        return FlowSnapshot(
            q_in=q_in,
            q1=q1,
            q2=q2,
            q_demand=q_demand,
            q_out=q_out,
            q_delivered=q_out,
            p1_effective_state=p1_effective,
            p2_effective_state=p2_effective,
        )

    def _advance_transition_clocks(self, dt: float) -> None:
        state = self.state
        if state.backup_start_remaining > 0:
            state.backup_start_remaining = max(0.0, state.backup_start_remaining - dt)
        if state.isolation_remaining > 0:
            state.isolation_remaining = max(0.0, state.isolation_remaining - dt)
        self._apply_zero_delay_transitions()

    def step(
        self,
        attacker_action: AttackerAction,
        defender_action: DefenderAction,
        dt: float | None = None,
    ) -> StepRecord:
        """Run one control interval using the documented attacker-before-defender order."""

        dt = self.parameters.control_period if dt is None else dt
        if dt <= 0 or dt > self.parameters.control_period + 1e-12:
            raise ModelValidationError("dt must be positive and no larger than control_period")

        self.apply_attacker(attacker_action)
        self.apply_defender(defender_action)
        flow = self.flows()
        state = self.state
        isolation_effective_during_interval = state.primary_path_isolated
        isolation_pending_during_interval = state.isolation_commanded and not isolation_effective_during_interval
        backup_start_pending_during_interval = state.p2_command and not flow.p2_effective_state
        state.x1 += (flow.q_in - flow.q1 - flow.q2) * dt
        state.x2 += (flow.q1 + flow.q2 - flow.q_demand) * dt
        state.time += dt
        state.control_cycle += 1
        self._advance_transition_clocks(dt)

        safety_status = "safe" if self.safety_ok() else "unsafe"
        service_required = state.time >= self.parameters.service_deadline - 1e-12
        service_status = (
            "not_yet_required"
            if not service_required
            else ("satisfied" if flow.q_delivered >= self.parameters.min_service_flow else "violated")
        )
        if defender_action is DefenderAction.CONSERVATIVE_HOLD:
            recovery_status = "conservative_hold"
        elif defender_action is DefenderAction.START_CONTROLLED_SAFE_HOLD:
            recovery_status = "controlled_safe_hold"
        elif state.recovery_established_at is not None:
            recovery_status = "takeover_established"
        elif state.recovery_started_at is not None:
            recovery_status = "takeover_transition"
        else:
            recovery_status = "no_recovery"

        return StepRecord(
            timestamp=state.time,
            control_cycle=state.control_cycle,
            x1=state.x1,
            x2=state.x2,
            p1_command=state.p1_command,
            p1_effective_state=flow.p1_effective_state,
            p2_command=state.p2_command,
            p2_effective_state=flow.p2_effective_state,
            primary_path_isolated=state.primary_path_isolated,
            isolation_commanded=state.isolation_commanded,
            isolation_pending_during_interval=isolation_pending_during_interval,
            isolation_effective_during_interval=isolation_effective_during_interval,
            backup_start_pending_during_interval=backup_start_pending_during_interval,
            q_in=flow.q_in,
            q1=flow.q1,
            q2=flow.q2,
            q_demand=flow.q_demand,
            q_out=flow.q_out,
            q_delivered=flow.q_delivered,
            attacker_action=attacker_action.value,
            defender_action=defender_action.value,
            safety_status=safety_status,
            service_status=service_status,
            recovery_status=recovery_status,
            interval=dt,
        )
