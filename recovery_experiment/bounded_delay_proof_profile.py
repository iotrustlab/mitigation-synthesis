"""Generated clock-relative CLEO annotations for bounded delayed isolation.

The template is parameterized by integer control-period counts.  It is not a
certificate and attaching it does not assert that the generated theorem holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from .recovery_model_builder import BOUNDED_DELAY_PROOF_PROFILE_ID, BoundedIsolationSchedule


EXACT_LINEAR_ODE_TACTIC = "implyR(1); solve(1); QE"


@dataclass(frozen=True)
class GeneratedProofProfile:
    """Concrete invariant names and schedule used for one generated game."""

    profile_id: str
    schedule: BoundedIsolationSchedule
    invariant_names: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "schedule": self.schedule.as_dict(),
            "invariant_names": list(self.invariant_names),
            "tactic": EXACT_LINEAR_ODE_TACTIC,
        }


def _common(schedule: BoundedIsolationSchedule) -> str:
    timing = (
        rf"""
& ControlPeriod > 0 & IsolationDelay = 0 * ControlPeriod
& StartupDelay = {schedule.startup_periods} * ControlPeriod
& StartupDelay <= TransferDeadline & TransferDeadline > 0 & T > 0
"""
        if schedule.isolation_periods == 0
        else rf"""
& ControlPeriod > 0 & IsolationDelay = {schedule.isolation_periods} * ControlPeriod
& StartupDelay = {schedule.startup_periods} * ControlPeriod
& IsolationDelay > 0 & IsolationDelay <= StartupDelay
& StartupDelay <= TransferDeadline & TransferDeadline > 0 & T > 0
& isolationCommanded = 1 & p2Command = 1
"""
    )
    return rf"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
& qprimary >= startupInflow & qprimary >= startupWithdrawal & qbackup >= qmin
{timing.strip()}
& qin = startupInflow & demand = startupWithdrawal & qout = demand
& qdelivered = qout & qdelivered >= qmin
& interventionBudget >= isolationCost + backupCost
& isolationCost >= 0 & backupCost >= 0
""".strip()


def _remaining_margins() -> str:
    return r"""
& x1 + startupInflow * (StartupDelay - startupClock) <= H1
& x2 - startupWithdrawal * (StartupDelay - startupClock) >= L2
& x1 + startupInflow * (IsolationDelay - isolationClock) <= H1
& x1 + (startupInflow - qprimary) * (IsolationDelay - isolationClock) >= L1
& x2 + (qprimary - startupWithdrawal) * (IsolationDelay - isolationClock) <= H2
""".strip()


def pending_invariant(schedule: BoundedIsolationSchedule, interval_index: int) -> str:
    """Invariant for interval ``interval_index`` starting at ``index*T``."""

    if not 0 <= interval_index < schedule.isolation_periods:
        raise ValueError("pending interval index is outside the isolation schedule")
    start_clock = "0" if interval_index == 0 else f"{interval_index} * ControlPeriod"
    return _common(schedule) + "\n" + _remaining_margins() + rf"""
& isolated = 0 & p2 = 0
& q1 >= 0 & q1 <= qprimary & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
& isolationClock = {start_clock} & startupClock = {start_clock} & transferClock = {start_clock}
"""


def _backup_phase_count(schedule: BoundedIsolationSchedule) -> int:
    return 1 if schedule.isolation_periods <= 2 else schedule.startup_periods - schedule.isolation_periods


def _immediate_backup_invariant(schedule: BoundedIsolationSchedule) -> str:
    """Invariant for a generated immediate schedule that is not canonical 0T/2T."""

    return _common(schedule) + r"""
& x1 + startupInflow * (StartupDelay - startupClock) <= H1
& x2 - startupWithdrawal * (StartupDelay - startupClock) >= L2
& isolated = 1 & p2 = 0
& q1 = 0 & q2 = 0 & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
& startupClock = 0 & transferClock = 0
"""


def backup_pending_invariant(schedule: BoundedIsolationSchedule, interval_index: int = 0) -> str:
    """Invariant after trusted isolation and before P2 becomes effective."""

    if not 0 <= interval_index < _backup_phase_count(schedule):
        raise ValueError("backup-pending interval index is outside the recovery schedule")
    start_clock = (
        "IsolationDelay"
        if interval_index == 0
        else f"{schedule.isolation_periods + interval_index} * ControlPeriod"
    )
    return _common(schedule) + r"""
& x1 + startupInflow * (StartupDelay - startupClock) <= H1
& x2 - startupWithdrawal * (StartupDelay - startupClock) >= L2
& isolated = 1 & p2 = 0
& q1 = 0 & q2 = 0 & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
""" + f"\n& isolationClock = IsolationDelay & startupClock = {start_clock} & transferClock = {start_clock}\n"


def operation_invariant() -> str:
    return r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & isolationCommanded = 1 & p2Command = 1 & p2 = 1
& qin = qbackup & demand = qbackup & qout = demand
& q1 = 0
& q2 = qbackup & q2 = p2 * qbackup
& qdelivered = qout & qdelivered >= qmin
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& startupClock = StartupDelay & transferClock = StartupDelay & transferClock <= TransferDeadline
& isolationClock = IsolationDelay
& interventionBudget >= 0 & isolationCost >= 0 & backupCost >= 0
& T > 0 & operationClock = 0
""".strip()


def _immediate_operation_invariant() -> str:
    """Post-takeover invariant for generated immediate envelopes only."""

    return r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & p2 = 1
& qin = qbackup & demand = qbackup & qout = demand
& q1 = 0
& q2 = qbackup & q2 = p2 * qbackup
& qdelivered = qout & qdelivered >= qmin
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& startupClock = StartupDelay & transferClock = StartupDelay & transferClock <= TransferDeadline
& interventionBudget >= 0 & isolationCost >= 0 & backupCost >= 0
& T > 0 & operationClock = 0
""".strip()


def generated_profile(
    schedule: BoundedIsolationSchedule,
    *,
    profile_id: str = BOUNDED_DELAY_PROOF_PROFILE_ID,
) -> GeneratedProofProfile:
    schedule.validate()
    return GeneratedProofProfile(
        profile_id,
        schedule,
        tuple(
            [f"isolation_pending_phase_{index + 1}" for index in range(schedule.isolation_periods)]
            + [
                "backup_pending_phase"
                if _backup_phase_count(schedule) == 1
                else f"backup_pending_phase_{index + 1}"
                for index in range(_backup_phase_count(schedule))
            ]
            + ["operation_phase"]
        ),
    )


def attach_bounded_delay_profile(
    session,
    schedule: BoundedIsolationSchedule,
    *,
    profile_id: str = BOUNDED_DELAY_PROOF_PROFILE_ID,
) -> list[dict[str, str]]:
    """Attach one generated invariant for every mandatory ODE phase."""

    profile = generated_profile(schedule, profile_id=profile_id)
    attached: list[dict[str, str]] = []
    pending_index = 0
    backup_index = 0
    for entry in session.get_needed_annotations():
        if entry["kind"] != "ode":
            raise RuntimeError(f"unexpected bounded-delay annotation: {entry['kind']}")
        game = entry["game_str"]
        if "operationClock" in game:
            invariant = _immediate_operation_invariant() if schedule.isolation_periods == 0 else operation_invariant()
            name = "operation_phase"
        elif schedule.isolation_periods == 0 and "startupClock" in game:
            if backup_index:
                raise RuntimeError("generated immediate model exposed too many backup-pending ODEs")
            invariant, name = _immediate_backup_invariant(schedule), "backup_pending_phase"
            backup_index += 1
        elif "isolationClock" in game:
            if pending_index >= schedule.isolation_periods:
                raise RuntimeError("generated game exposed too many isolation-pending ODEs")
            invariant = pending_invariant(schedule, pending_index)
            pending_index += 1
            name = f"isolation_pending_phase_{pending_index}"
        elif "startupClock" in game:
            if backup_index >= _backup_phase_count(schedule):
                raise RuntimeError("generated game exposed too many backup-pending ODEs")
            invariant = backup_pending_invariant(schedule, backup_index)
            backup_index += 1
            name = (
                "backup_pending_phase"
                if _backup_phase_count(schedule) == 1
                else f"backup_pending_phase_{backup_index}"
            )
        else:
            raise RuntimeError("generated bounded-delay model exposed an unknown ODE phase")
        session.set_invariant(entry["game_id"], invariant)
        session.set_tactic(entry["game_id"], EXACT_LINEAR_ODE_TACTIC)
        attached.append({"game_id": entry["game_id"], "kind": "ode", "profile": name})
    if pending_index != schedule.isolation_periods:
        raise RuntimeError("generated game did not expose every required isolation-pending ODE")
    if backup_index != _backup_phase_count(schedule):
        raise RuntimeError("generated game did not expose every required backup-pending ODE")
    if {entry["profile"] for entry in attached} != set(profile.invariant_names):
        raise RuntimeError("generated proof profile does not match the formal model phase schedule")
    return attached
