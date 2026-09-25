"""Typed construction of the supported two-tank flowing-recovery games.

This is deliberately a small intermediate representation, not a generic
industrial-process language.  It captures only the recovery phases already
modeled in this experiment and renders finite CLEO games with no repetition
operator.  Existing verified envelopes remain their own canonical artifacts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import Enum
from fractions import Fraction

from .context import ContextValidationError, RecoveryContext


IMMEDIATE_BUILT_MODEL_ID = "built-immediate-flowing-takeover-v1"
INTERMEDIATE_DELAY_MODEL_ID = "built-one-control-period-isolation-flowing-takeover-v1"
TWO_PERIOD_DELAY_BUILT_MODEL_ID = "built-two-control-period-isolation-flowing-takeover-v1"
INTERMEDIATE_DELAY_POLICY_ID = "trusted-one-control-period-isolation-flowing-backup-takeover-v1"
INTERMEDIATE_DELAY_PROOF_PROFILE_ID = "one-control-period-clock-relative-margins-v1"
BOUNDED_DELAY_POLICY_ID = "trusted-bounded-isolation-flowing-backup-takeover-v1"
BOUNDED_DELAY_PROOF_PROFILE_ID = "bounded-isolation-clock-relative-margins-v1"
BUILDER_ID = "parallel-pump-recovery-model-builder"
BUILDER_VERSION = "bounded-schedules-v1"


class BuildStatus(str, Enum):
    CONSTRUCTED = "FORMAL_PROBLEM_CONSTRUCTED"
    INVALID_CONTEXT = "INVALID_INCIDENT_CONTEXT"
    UNSUPPORTED_CONFIGURATION = "UNSUPPORTED_INCIDENT_CONFIGURATION"


class IsolationMode(str, Enum):
    IMMEDIATE = "immediate_effective_isolation"
    ONE_CONTROL_PERIOD = "one_control_period_isolation_delay"
    TWO_CONTROL_PERIOD = "two_control_period_isolation_delay"
    BOUNDED_DELAY = "bounded_control_period_isolation_delay"


class PhaseKind(str, Enum):
    ATTACKER_COMMAND = "attacker_command_choice"
    ISOLATION_REQUEST = "isolation_requested"
    ISOLATION_PENDING_EVOLUTION = "isolation_pending_physical_evolution"
    EFFECTIVE_ISOLATION = "effective_isolation_transition"
    BACKUP_PENDING_EVOLUTION = "backup_startup_physical_evolution"
    BACKUP_AVAILABLE = "backup_availability_transition"
    POST_TAKEOVER_OPERATION = "mandatory_post_takeover_operation"


class ActionOwner(str, Enum):
    ATTACKER = "demon"
    DEFENDER = "trusted_defender"
    PHYSICAL = "continuous_plant"


class IsolationState(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "requested_pending"
    EFFECTIVE = "physically_effective"


class BackupState(str, Enum):
    NOT_COMMANDED = "not_commanded"
    STARTING = "startup_pending"
    AVAILABLE = "available"


@dataclass(frozen=True)
class TankSafetyMargins:
    """The symbolic endpoint conditions derived from the phase durations."""

    upper_t1_through_startup: str
    lower_t1_while_primary_effective: str | None
    lower_t2_through_startup: str
    upper_t2_while_primary_effective: str | None

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(
            item
            for item in (
                self.upper_t1_through_startup,
                self.lower_t1_while_primary_effective,
                self.lower_t2_through_startup,
                self.upper_t2_while_primary_effective,
            )
            if item is not None
        )


@dataclass(frozen=True)
class BoundedIsolationSchedule:
    """Exact integer timing shape for one finite recovery game."""

    control_period: float
    isolation_periods: int
    startup_periods: int

    def validate(self) -> None:
        if self.control_period <= 0:
            raise ValueError("control period must be positive")
        if self.isolation_periods < 0:
            raise ValueError("isolation periods must be nonnegative")
        if self.startup_periods <= self.isolation_periods:
            raise ValueError("startup periods must exceed isolation periods")

    @property
    def isolation_delay(self) -> float:
        return self.isolation_periods * self.control_period

    @property
    def startup_delay(self) -> float:
        return self.startup_periods * self.control_period

    def as_dict(self) -> dict[str, int | float]:
        return {
            "control_period": self.control_period,
            "isolation_periods": self.isolation_periods,
            "startup_periods": self.startup_periods,
        }


@dataclass(frozen=True)
class RecoveryPhase:
    """One mandatory finite recovery stage and its physical authority facts."""

    name: str
    kind: PhaseKind
    owner: ActionOwner
    isolation_state: IsolationState
    backup_state: BackupState
    attacker_commandable: bool
    primary_physically_effective: bool
    duration: str | None
    entry_updates: tuple[str, ...]
    dynamics: tuple[str, ...]
    exit_conditions: tuple[str, ...]
    safety_obligations: tuple[str, ...]
    service_obligations: tuple[str, ...]


@dataclass(frozen=True)
class ParallelPumpRecoverySpec:
    """Typed input to the finite recovery-game renderer."""

    plant_model_id: str
    recovery_policy_id: str
    isolation_mode: IsolationMode
    schedule: BoundedIsolationSchedule
    immediate_certificate_id: str | None
    proof_profile_id: str
    context: RecoveryContext
    margins: TankSafetyMargins

    @property
    def isolation_delay(self) -> str:
        return "0" if self.schedule.isolation_periods == 0 else "IsolationDelay"

    @property
    def control_periods_before_isolation(self) -> int:
        """Compatibility view for the existing phase/rendering implementation."""

        return self.schedule.isolation_periods

    @property
    def startup_control_periods(self) -> int:
        return self.schedule.startup_periods


@dataclass(frozen=True)
class GeneratedRecoveryProblem:
    status: BuildStatus
    spec: ParallelPumpRecoverySpec | None
    phases: tuple[RecoveryPhase, ...]
    envelope_text: str | None
    canonical_equivalent: bool
    matching_verified_artifact: bool
    reasons: tuple[str, ...]

    @property
    def formal_model_id(self) -> str | None:
        return None if self.spec is None else self.spec.plant_model_id

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "formal_model_id": self.formal_model_id,
            "recovery_policy_id": None if self.spec is None else self.spec.recovery_policy_id,
            "isolation_mode": None if self.spec is None else self.spec.isolation_mode.value,
            "schedule": None if self.spec is None else self.spec.schedule.as_dict(),
            "matching_verified_artifact": self.matching_verified_artifact,
            "canonical_equivalent": self.canonical_equivalent,
            "margins": [] if self.spec is None else list(self.spec.margins.as_tuple()),
            "phases": [
                {
                    "name": phase.name,
                    "kind": phase.kind.value,
                    "owner": phase.owner.value,
                    "isolation_state": phase.isolation_state.value,
                    "backup_state": phase.backup_state.value,
                    "attacker_commandable": phase.attacker_commandable,
                    "primary_physically_effective": phase.primary_physically_effective,
                    "duration": phase.duration,
                    "entry_updates": list(phase.entry_updates),
                    "dynamics": list(phase.dynamics),
                    "exit_conditions": list(phase.exit_conditions),
                    "safety_obligations": list(phase.safety_obligations),
                    "service_obligations": list(phase.service_obligations),
                }
                for phase in self.phases
            ],
            "reasons": list(self.reasons),
        }


def _same(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _margins(mode: IsolationMode) -> TankSafetyMargins:
    if mode is IsolationMode.IMMEDIATE:
        return TankSafetyMargins(
            "x1 + startupInflow * StartupDelay <= H1",
            None,
            "x2 - startupWithdrawal * StartupDelay >= L2",
            None,
        )
    return TankSafetyMargins(
        "x1 + startupInflow * StartupDelay <= H1",
        "x1 + (startupInflow - qprimary) * IsolationDelay >= L1",
        "x2 - startupWithdrawal * StartupDelay >= L2",
        "x2 + (qprimary - startupWithdrawal) * IsolationDelay <= H2",
    )


def _attacker_phase(name: str, isolation: IsolationState, effective: bool) -> RecoveryPhase:
    return RecoveryPhase(
        name=name,
        kind=PhaseKind.ATTACKER_COMMAND,
        owner=ActionOwner.ATTACKER,
        isolation_state=isolation,
        backup_state=BackupState.STARTING if isolation is not IsolationState.NOT_REQUESTED else BackupState.NOT_COMMANDED,
        attacker_commandable=True,
        primary_physically_effective=effective,
        duration=None,
        entry_updates=("Demon chooses p1 in {0, 1}",),
        dynamics=(),
        exit_conditions=("p1 = 0 | p1 = 1",),
        safety_obligations=("binary P1 command is represented before its next physical interval",),
        service_obligations=(),
    )


def _phase_plan(spec: ParallelPumpRecoverySpec) -> tuple[RecoveryPhase, ...]:
    common_safety = spec.margins.as_tuple()
    startup_service = ("qdelivered = qout", "qdelivered >= qmin")
    if spec.isolation_mode is IsolationMode.IMMEDIATE:
        return (
            _attacker_phase("initial_primary_command", IsolationState.NOT_REQUESTED, False),
            RecoveryPhase(
                "immediate_effective_isolation",
                PhaseKind.EFFECTIVE_ISOLATION,
                ActionOwner.DEFENDER,
                IsolationState.EFFECTIVE,
                BackupState.STARTING,
                True,
                False,
                "0",
                ("isolated := 1", "p2 := 0", "P2 startup begins"),
                (),
                ("q1 = 0",),
                common_safety,
                startup_service,
            ),
            RecoveryPhase(
                "backup_startup",
                PhaseKind.BACKUP_PENDING_EVOLUTION,
                ActionOwner.PHYSICAL,
                IsolationState.EFFECTIVE,
                BackupState.STARTING,
                True,
                False,
                "StartupDelay",
                ("qin := startupInflow", "qout := startupWithdrawal", "q2 := 0"),
                ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
                ("startupClock = StartupDelay", "transferClock <= TransferDeadline"),
                common_safety,
                startup_service,
            ),
            _attacker_phase("post_isolation_primary_command", IsolationState.EFFECTIVE, False),
            RecoveryPhase(
                "backup_available",
                PhaseKind.BACKUP_AVAILABLE,
                ActionOwner.DEFENDER,
                IsolationState.EFFECTIVE,
                BackupState.AVAILABLE,
                True,
                False,
                "0",
                ("p2 := 1", "qin := qbackup", "qout := qbackup"),
                (),
                ("q2 = qbackup",),
                ("safe(x1, x2)",),
                ("qdelivered >= qmin",),
            ),
            RecoveryPhase(
                "mandatory_post_takeover_operation",
                PhaseKind.POST_TAKEOVER_OPERATION,
                ActionOwner.PHYSICAL,
                IsolationState.EFFECTIVE,
                BackupState.AVAILABLE,
                True,
                False,
                "T > 0",
                ("operationClock := 0",),
                ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
                ("operationClock = T",),
                ("safe(x1, x2)",),
                ("qdelivered >= qmin",),
            ),
        )

    pending: list[RecoveryPhase] = []
    for index in range(spec.control_periods_before_isolation):
        if index:
            pending.append(_attacker_phase(f"pending_primary_command_{index + 1}", IsolationState.PENDING, True))
        pending.append(
            RecoveryPhase(
                f"isolation_pending_interval_{index + 1}",
                PhaseKind.ISOLATION_PENDING_EVOLUTION,
                ActionOwner.PHYSICAL,
                IsolationState.PENDING,
                BackupState.STARTING,
                True,
                True,
                "ControlPeriod",
                (),
                ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
                ("isolationClock advances one control period",),
                common_safety,
                startup_service,
            )
        )
    backup_pending_phases = (
        (
            RecoveryPhase(
                "backup_pending_after_isolation",
                PhaseKind.BACKUP_PENDING_EVOLUTION,
                ActionOwner.PHYSICAL,
                IsolationState.EFFECTIVE,
                BackupState.STARTING,
                True,
                False,
                "StartupDelay-IsolationDelay",
                (),
                ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
                ("startupClock = StartupDelay", "transferClock <= TransferDeadline"),
                common_safety,
                startup_service,
            ),
        )
        if spec.schedule.isolation_periods <= 2
        else tuple(
            RecoveryPhase(
                f"backup_pending_interval_{index + 1}",
                PhaseKind.BACKUP_PENDING_EVOLUTION,
                ActionOwner.PHYSICAL,
                IsolationState.EFFECTIVE,
                BackupState.STARTING,
                True,
                False,
                "ControlPeriod",
                (),
                ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
                (f"startupClock advances backup control period {index + 1}",),
                common_safety,
                startup_service,
            )
            for index in range(spec.schedule.startup_periods - spec.schedule.isolation_periods)
        )
    )
    return (
        _attacker_phase("initial_primary_command", IsolationState.NOT_REQUESTED, True),
        RecoveryPhase(
            "isolation_requested_and_backup_started",
            PhaseKind.ISOLATION_REQUEST,
            ActionOwner.DEFENDER,
            IsolationState.PENDING,
            BackupState.STARTING,
            True,
            True,
            "0",
            ("isolationCommanded := 1", "isolated := 0", "p2Command := 1", "p2 := 0"),
            (),
            ("P1 remains physically effective until IsolationDelay",),
            common_safety,
            startup_service,
        ),
        *pending,
        RecoveryPhase(
            "effective_isolation",
            PhaseKind.EFFECTIVE_ISOLATION,
            ActionOwner.DEFENDER,
            IsolationState.EFFECTIVE,
            BackupState.STARTING,
            True,
            False,
            "0",
            ("isolated := 1", "q1 := 0"),
            (),
            ("q1 = 0 despite subsequent P1 commands",),
            common_safety,
            startup_service,
        ),
        _attacker_phase("post_isolation_primary_command", IsolationState.EFFECTIVE, False),
        *backup_pending_phases,
        RecoveryPhase(
            "backup_available",
            PhaseKind.BACKUP_AVAILABLE,
            ActionOwner.DEFENDER,
            IsolationState.EFFECTIVE,
            BackupState.AVAILABLE,
            True,
            False,
            "0",
            ("p2 := 1", "qin := qbackup", "qout := qbackup"),
            (),
            ("q2 = qbackup",),
            ("safe(x1, x2)",),
            ("qdelivered >= qmin",),
        ),
        RecoveryPhase(
            "mandatory_post_takeover_operation",
            PhaseKind.POST_TAKEOVER_OPERATION,
            ActionOwner.PHYSICAL,
            IsolationState.EFFECTIVE,
            BackupState.AVAILABLE,
            True,
            False,
            "T > 0",
            ("operationClock := 0",),
            ("x1' = qin-q1-q2", "x2' = q1+q2-qout"),
            ("operationClock = T",),
            ("safe(x1, x2)",),
            ("qdelivered >= qmin",),
        ),
    )


def _choice(with_flow: bool) -> str:
    off = "{ p1 := 0; q1 := 0; }" if with_flow else "{ p1 := 0; }"
    on = "{ p1 := 1; q1 := qprimary; }" if with_flow else "{ p1 := 1; }"
    return f"""        {{
            {off}
            ++
            {on}
        }}^@;"""


def _render_immediate(spec: ParallelPumpRecoverySpec, phases: tuple[RecoveryPhase, ...]) -> str:
    canonical = spec.schedule.isolation_periods == 0 and spec.schedule.startup_periods == 2
    title = (
        "State-dependent flowing trusted backup takeover recovery"
        if canonical
        else f"Immediate-isolation {spec.schedule.startup_periods}-control-period flowing trusted backup takeover recovery"
    )
    guideline = (
        "    Offline theorem for a fixed takeover policy with continued startup inflow and downstream withdrawal.\n"
        "    Stored water serves demand during startup; P2 restores the transfer path by TransferDeadline."
        if canonical
        else "    Generated immediate-isolation recovery game with a bounded integer backup-startup schedule."
    )
    timing_variables = "" if canonical else "        Real ControlPeriod; Real IsolationDelay;\n"
    timing_constraints = (
        ""
        if canonical
        else (
            "    & ControlPeriod > 0 & IsolationDelay = 0 * ControlPeriod\n"
            f"    & StartupDelay = {spec.schedule.startup_periods} * ControlPeriod\n"
        )
    )
    startup_safety_domain = "" if not canonical else "            & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2\n"
    rendered: list[str] = []
    for phase in phases:
        if phase.kind is PhaseKind.ATTACKER_COMMAND:
            rendered.append(_choice(False))
        elif phase.kind is PhaseKind.EFFECTIVE_ISOLATION:
            rendered.append(
                """        isolated := 1;
        p2 := 0;
        qin := startupInflow;
        demand := startupWithdrawal;
        qout := demand;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := qout;
        ? qdelivered >= qmin;
        startupClock := 0;
        transferClock := 0;"""
            )
        elif phase.kind is PhaseKind.BACKUP_PENDING_EVOLUTION:
            rendered.append(
                f"""        startup_ode: {{
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            startupClock' = 1,
            transferClock' = 1
{startup_safety_domain}            & qdelivered >= qmin
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        }};
        ? startupClock >= StartupDelay;
        ? transferClock <= TransferDeadline;"""
            )
        elif phase.kind is PhaseKind.BACKUP_AVAILABLE:
            rendered.append(
                """        isolated := 1;
        p2 := 1;
        qin := qbackup;
        demand := qbackup;
        qout := demand;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := qout;
        interventionBudget := interventionBudget - (isolationCost + backupCost);
        ? qdelivered >= qmin;
        operationClock := 0;"""
            )
        elif phase.kind is PhaseKind.POST_TAKEOVER_OPERATION:
            rendered.append(
                """        operation_ode: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            transferClock' = 0,
            operationClock' = 1
            & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
            & qdelivered >= qmin & operationClock <= T
        };
        ? operationClock >= T;"""
            )
    game = "\n".join(rendered)
    return f'''envelope "{title}"

Guideline
{guideline}

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real isolated;
        Real qin; Real qout; Real demand; Real qprimary; Real qbackup; Real qmin;
        Real q1; Real q2; Real qdelivered;
        Real startupInflow; Real startupWithdrawal;
        Real startupClock; Real transferClock; Real operationClock;
        Real StartupDelay; Real TransferDeadline; Real T;
{timing_variables}        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
    & qprimary >= 0 & qbackup >= qmin
{timing_constraints}    & StartupDelay > 0 & TransferDeadline > 0 & StartupDelay <= TransferDeadline & T > 0
    & x1 + startupInflow * StartupDelay <= H1
    & x2 - startupWithdrawal * StartupDelay >= L2
    & isolationCost >= 0 & backupCost >= 0
    & interventionBudget >= isolationCost + backupCost

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolated = 1 & p2 = 1
    & q1 = 0 & q1 = (1-isolated) * p1 * qprimary
    & q2 = qbackup & q2 = p2 * qbackup
    & qin = qbackup & demand = qbackup & qout = demand
    & qdelivered = qout & qdelivered >= qmin
    & startupClock = StartupDelay
    & transferClock = StartupDelay & transferClock <= TransferDeadline
    & operationClock = T
    & interventionBudget >= 0

game
    {{
{game}
    }}
'''


def _pending_ode(label: str, upper_bound: str) -> str:
    return f'''        {label}: {{
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            isolationClock' = 1,
            startupClock' = 1,
            transferClock' = 1
            & isolationClock <= {upper_bound}
            & startupClock <= StartupDelay & transferClock <= TransferDeadline
        }};
        ? isolationClock >= {upper_bound};'''


def _pending_phase_label(schedule: BoundedIsolationSchedule, index: int) -> str:
    """Retain reviewed labels for 1T/2T; number every phase in new schedules."""

    if schedule.isolation_periods == 1:
        return "isolation_phase"
    if schedule.isolation_periods == 2:
        return "isolation_phase_one" if index == 1 else "isolation_phase_two"
    return f"isolation_phase_{index}"


def _pending_phase_bound(schedule: BoundedIsolationSchedule, index: int) -> str:
    """Force the nth pending ODE to finish at its next control boundary."""

    if index == schedule.isolation_periods:
        return "IsolationDelay"
    if index == 1:
        return "ControlPeriod"
    return f"{index} * ControlPeriod"


def _backup_phase_label(schedule: BoundedIsolationSchedule, index: int) -> str:
    if schedule.isolation_periods <= 2:
        return "backup_pending_phase"
    return f"backup_pending_phase_{index}"


def _backup_phase_bound(schedule: BoundedIsolationSchedule, index: int) -> str:
    backup_periods = schedule.startup_periods - schedule.isolation_periods
    if schedule.isolation_periods <= 2 or index == backup_periods:
        return "StartupDelay"
    return f"{schedule.isolation_periods + index} * ControlPeriod"


def _render_delayed(spec: ParallelPumpRecoverySpec, phases: tuple[RecoveryPhase, ...]) -> str:
    rendered: list[str] = []
    pending_seen = 0
    backup_seen = 0
    for phase in phases:
        if phase.kind is PhaseKind.ATTACKER_COMMAND:
            rendered.append(_choice(phase.primary_physically_effective))
        elif phase.kind is PhaseKind.ISOLATION_REQUEST:
            rendered.append(
                """        isolationCommanded := 1;
        isolated := 0;
        p2Command := 1;
        p2 := 0;
        qin := startupInflow;
        demand := startupWithdrawal;
        qout := demand;
        q2 := p2 * qbackup;
        qdelivered := qout;
        ? qdelivered >= qmin;
        isolationClock := 0;
        startupClock := 0;
        transferClock := 0;"""
            )
        elif phase.kind is PhaseKind.ISOLATION_PENDING_EVOLUTION:
            pending_seen += 1
            bound = _pending_phase_bound(spec.schedule, pending_seen)
            label = _pending_phase_label(spec.schedule, pending_seen)
            rendered.append(_pending_ode(label, bound))
        elif phase.kind is PhaseKind.EFFECTIVE_ISOLATION:
            rendered.append("""        isolated := 1;
        q1 := 0;""")
        elif phase.kind is PhaseKind.BACKUP_PENDING_EVOLUTION:
            backup_seen += 1
            label = _backup_phase_label(spec.schedule, backup_seen)
            bound = _backup_phase_bound(spec.schedule, backup_seen)
            rendered.append(
                f"""        {label}: {{
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            startupClock' = 1,
            transferClock' = 1
            & startupClock <= {bound} & transferClock <= TransferDeadline
        }};
        ? startupClock >= {bound};
        ? transferClock <= TransferDeadline;"""
            )
        elif phase.kind is PhaseKind.BACKUP_AVAILABLE:
            rendered.append(
                """        p2 := 1;
        qin := qbackup;
        demand := qbackup;
        qout := demand;
        q1 := 0;
        q2 := p2 * qbackup;
        qdelivered := qout;
        interventionBudget := interventionBudget - (isolationCost + backupCost);
        ? qdelivered >= qmin;
        operationClock := 0;"""
            )
        elif phase.kind is PhaseKind.POST_TAKEOVER_OPERATION:
            rendered.append(
                """        operation_phase: {
            x1' = qin - q1 - q2,
            x2' = q1 + q2 - qout,
            operationClock' = 1
            & operationClock <= T
        };
        ? operationClock >= T;"""
            )
    game = "\n".join(rendered)
    title = (
        "Delayed-isolation flowing trusted backup takeover recovery"
        if spec.isolation_mode is IsolationMode.TWO_CONTROL_PERIOD
        else "One-control-period isolation flowing trusted backup takeover recovery"
        if spec.isolation_mode is IsolationMode.ONE_CONTROL_PERIOD
        else f"{spec.schedule.isolation_periods}-control-period isolation flowing trusted backup takeover recovery"
    )
    guideline = (
        """    Offline theorem for an attacker that can choose P1 at two control boundaries before
    physical isolation becomes effective. P2 startup begins concurrently with isolation."""
        if spec.control_periods_before_isolation == 2
        else "    Offline theorem for an attacker that controls P1 for one control boundary before physical isolation becomes effective. P2 startup begins concurrently with isolation."
        if spec.control_periods_before_isolation == 1
        else f"    Offline theorem for an attacker that controls P1 at {spec.schedule.isolation_periods} control boundaries before physical isolation becomes effective. P2 startup begins concurrently with isolation."
    )
    return f'''envelope "{title}"

Guideline
{guideline}

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real p2Command; Real isolated; Real isolationCommanded;
        Real qin; Real qout; Real demand; Real qprimary; Real qbackup; Real qmin;
        Real q1; Real q2; Real qdelivered;
        Real startupInflow; Real startupWithdrawal;
        Real isolationClock; Real startupClock; Real transferClock; Real operationClock;
        Real ControlPeriod; Real IsolationDelay; Real StartupDelay; Real TransferDeadline; Real T;
        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
    L1 < H1 & L2 < H2
    & L1 >= 0 & L2 >= 0
    & L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
    & qprimary >= startupInflow & qprimary >= startupWithdrawal & qbackup >= qmin
    & ControlPeriod > 0
    & IsolationDelay = {spec.control_periods_before_isolation} * ControlPeriod
    & StartupDelay = {spec.startup_control_periods} * ControlPeriod
    & IsolationDelay > 0 & IsolationDelay <= StartupDelay
    & StartupDelay <= TransferDeadline & T > 0
    & x1 + startupInflow * StartupDelay <= H1
    & x1 + (startupInflow - qprimary) * IsolationDelay >= L1
    & x2 - startupWithdrawal * StartupDelay >= L2
    & x2 + (qprimary - startupWithdrawal) * IsolationDelay <= H2
    & isolationCost >= 0 & backupCost >= 0
    & interventionBudget >= isolationCost + backupCost

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolationCommanded = 1 & isolated = 1
    & p2Command = 1 & p2 = 1
    & q1 = 0
    & q2 = qbackup & q2 = p2 * qbackup
    & qin = qbackup & demand = qbackup & qout = demand
    & qdelivered = qout & qdelivered >= qmin
    & isolationClock = IsolationDelay
    & startupClock = StartupDelay
    & transferClock = StartupDelay & transferClock <= TransferDeadline
    & operationClock = T
    & interventionBudget >= 0

game
    {{
{game}
    }}
'''


def _render(spec: ParallelPumpRecoverySpec, phases: tuple[RecoveryPhase, ...]) -> str:
    if spec.isolation_mode is IsolationMode.IMMEDIATE:
        return _render_immediate(spec, phases)
    return _render_delayed(spec, phases)


def _canonical_equivalent(mode: IsolationMode, rendered: str) -> bool:
    if mode is IsolationMode.IMMEDIATE:
        from .state_dependent_formal import render_state_dependent_recovery_envelope

        return _normalize(rendered) == _normalize(render_state_dependent_recovery_envelope().envelope_text)
    if mode is IsolationMode.TWO_CONTROL_PERIOD:
        from .delayed_isolation_formal import render_delayed_isolation_recovery_envelope

        return _normalize(rendered) == _normalize(render_delayed_isolation_recovery_envelope().envelope_text)
    return False


def _exact_period_count(total: float, period: float) -> int | None:
    """Return an integer schedule count without rounding an arbitrary delay."""

    try:
        ratio = Fraction(str(total)) / Fraction(str(period))
    except (ValueError, ZeroDivisionError):
        return None
    return ratio.numerator if ratio.denominator == 1 else None


def _mode_for_schedule(schedule: BoundedIsolationSchedule) -> IsolationMode:
    if schedule.isolation_periods == 0:
        return IsolationMode.IMMEDIATE
    if schedule.isolation_periods == 1:
        return IsolationMode.ONE_CONTROL_PERIOD
    if schedule.isolation_periods == 2:
        return IsolationMode.TWO_CONTROL_PERIOD
    return IsolationMode.BOUNDED_DELAY


def _schedule_identity(schedule: BoundedIsolationSchedule) -> tuple[str, str, str | None, str]:
    """Map only reviewed shapes to their legacy identities and profiles."""

    if schedule.isolation_periods == 0 and schedule.startup_periods == 2:
        return (
            IMMEDIATE_BUILT_MODEL_ID,
            "trusted-flowing-backup-takeover-v1",
            "two-tank-flowing-takeover-state-dependent-v1",
            "state_dependent_proof_profile.attach_state_dependent_profile",
        )
    if schedule.isolation_periods == 1 and schedule.startup_periods == 3:
        return (
            INTERMEDIATE_DELAY_MODEL_ID,
            INTERMEDIATE_DELAY_POLICY_ID,
            "one-control-period-flowing-takeover-reviewed-v1",
            INTERMEDIATE_DELAY_PROOF_PROFILE_ID,
        )
    if schedule.isolation_periods == 2 and schedule.startup_periods == 3:
        return (
            TWO_PERIOD_DELAY_BUILT_MODEL_ID,
            "trusted-delayed-isolation-flowing-backup-takeover-v1",
            "two-tank-flowing-takeover-delayed-isolation-v1",
            "delayed-isolation-clock-relative-margins-v2",
        )
    return (
        f"built-{schedule.isolation_periods}of{schedule.startup_periods}-control-period-isolation-flowing-takeover-v1",
        BOUNDED_DELAY_POLICY_ID,
        None,
        BOUNDED_DELAY_PROOF_PROFILE_ID,
    )


def build_recovery_problem(context: RecoveryContext) -> GeneratedRecoveryProblem:
    """Build one supported finite recovery game from a validated incident.

    Accepted schedules use exact integer counts ``n >= 0`` and ``m > n`` for
    ``IsolationDelay=n*ControlPeriod`` and ``StartupDelay=m*ControlPeriod``.
    A newly generated schedule never inherits verification or certification.
    """

    try:
        context.validate()
    except (ContextValidationError, ValueError, TypeError) as exc:
        return GeneratedRecoveryProblem(
            BuildStatus.INVALID_CONTEXT, None, (), None, False, False, (str(exc),)
        )
    p = context.plant
    isolation_periods = _exact_period_count(p.isolation_delay, p.control_period)
    startup_periods = _exact_period_count(p.backup_startup_delay, p.control_period)
    if isolation_periods is None or startup_periods is None:
        return GeneratedRecoveryProblem(
            BuildStatus.UNSUPPORTED_CONFIGURATION,
            None,
            (),
            None,
            False,
            False,
            ("isolation and startup delays must be exact integer numbers of control periods",),
        )
    schedule = BoundedIsolationSchedule(p.control_period, isolation_periods, startup_periods)
    try:
        schedule.validate()
    except ValueError as exc:
        return GeneratedRecoveryProblem(
            BuildStatus.UNSUPPORTED_CONFIGURATION,
            None,
            (),
            None,
            False,
            False,
            (str(exc),),
        )
    mode = _mode_for_schedule(schedule)
    model_id, policy_id, certificate_id, profile_id = _schedule_identity(schedule)
    spec = ParallelPumpRecoverySpec(
        model_id,
        policy_id,
        mode,
        schedule,
        certificate_id,
        profile_id,
        context,
        _margins(mode),
    )
    phases = _phase_plan(spec)
    rendered = _render(spec, phases)
    equivalent = _canonical_equivalent(mode, rendered)
    verified_artifact = mode in {IsolationMode.IMMEDIATE, IsolationMode.TWO_CONTROL_PERIOD} and equivalent
    reasons = (
        "generated from the typed two-tank phase representation",
        "canonical reviewed artifact is structurally identical" if equivalent else "no reviewed artifact is associated by the builder",
    )
    return GeneratedRecoveryProblem(BuildStatus.CONSTRUCTED, spec, phases, rendered, equivalent, verified_artifact, reasons)
