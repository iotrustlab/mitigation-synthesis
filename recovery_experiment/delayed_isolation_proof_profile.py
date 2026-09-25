"""CLEO ODE annotations for the delayed-isolation flowing takeover theorem."""

from __future__ import annotations


DELAYED_ISOLATION_PROOF_PROFILE_ID = "delayed-isolation-clock-relative-margins-v2"


INITIAL_RECOVERY_MARGINS = r"""
& x1 + startupInflow * StartupDelay <= H1
& x1 + (startupInflow - qprimary) * IsolationDelay >= L1
& x2 - startupWithdrawal * StartupDelay >= L2
& x2 + (qprimary - startupWithdrawal) * IsolationDelay <= H2
""".strip()


COMMON = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
& qprimary >= startupInflow & qprimary >= startupWithdrawal & qbackup >= qmin
& ControlPeriod > 0 & IsolationDelay = 2 * ControlPeriod & StartupDelay = 3 * ControlPeriod
& IsolationDelay > 0 & IsolationDelay <= StartupDelay
& StartupDelay <= TransferDeadline & TransferDeadline > 0 & T > 0
& isolationCommanded = 1 & p2Command = 1
& qin = startupInflow & demand = startupWithdrawal & qout = demand
& qdelivered = qout & qdelivered >= qmin
& interventionBudget >= isolationCost + backupCost
& isolationCost >= 0 & backupCost >= 0
""".strip()


DELAY_REMAINING_SAFETY = r"""
& x1 + startupInflow * (StartupDelay - startupClock) <= H1
& x2 - startupWithdrawal * (StartupDelay - startupClock) >= L2
& x1 + startupInflow * (IsolationDelay - isolationClock) <= H1
& x1 + (startupInflow - qprimary) * (IsolationDelay - isolationClock) >= L1
& x2 + (qprimary - startupWithdrawal) * (IsolationDelay - isolationClock) <= H2
""".strip()


# ``INITIAL_RECOVERY_MARGINS`` holds only at time zero. These clock-relative
# margins are the inductive facts that survive each Demon-selected P1 interval.
EXACT_LINEAR_ODE_TACTIC = "implyR(1); solve(1); QE"


PHASE_ONE_INVARIANT = COMMON + DELAY_REMAINING_SAFETY + r"""
& isolated = 0 & p2 = 0
& q1 >= 0 & q1 <= qprimary & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
& isolationClock = 0 & startupClock = 0 & transferClock = 0
"""


PHASE_TWO_INVARIANT = COMMON + DELAY_REMAINING_SAFETY + r"""
& isolated = 0 & p2 = 0
& q1 >= 0 & q1 <= qprimary & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
& isolationClock = ControlPeriod & startupClock = ControlPeriod & transferClock = ControlPeriod
"""


BACKUP_PENDING_INVARIANT = COMMON + r"""
& x1 + startupInflow * (StartupDelay - startupClock) <= H1
& x2 - startupWithdrawal * (StartupDelay - startupClock) >= L2
& isolated = 1 & p2 = 0
& q1 = 0 & q2 = 0 & q2 = p2 * qbackup
& (p1 = 0 | p1 = 1)
& isolationClock = IsolationDelay & startupClock = IsolationDelay & transferClock = IsolationDelay
"""


OPERATION_INVARIANT = r"""
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


def attach_delayed_isolation_profile(session) -> list[dict[str, str]]:
    """Attach one invariant to each mandatory transition and operation ODE."""

    needed = session.get_needed_annotations()
    attached: list[dict[str, str]] = []
    for entry in needed:
        if entry["kind"] != "ode":
            raise RuntimeError(f"unexpected delayed-isolation annotation: {entry['kind']}")
        game = entry["game_str"]
        if "operationClock" in game:
            invariant, profile_name = OPERATION_INVARIANT, "operation_phase"
        elif "isolationClock <= ControlPeriod" in game:
            invariant, profile_name = PHASE_ONE_INVARIANT, "isolation_phase_one"
        elif "isolationClock <= IsolationDelay" in game:
            invariant, profile_name = PHASE_TWO_INVARIANT, "isolation_phase_two"
        elif "startupClock" in game:
            invariant, profile_name = BACKUP_PENDING_INVARIANT, "backup_pending_phase"
        else:
            raise RuntimeError("delayed-isolation model exposed an unknown ODE phase")
        session.set_invariant(entry["game_id"], invariant)
        session.set_tactic(entry["game_id"], EXACT_LINEAR_ODE_TACTIC)
        attached.append({"game_id": entry["game_id"], "kind": "ode", "profile": profile_name})
    if {entry["profile"] for entry in attached} != {
        "isolation_phase_one",
        "isolation_phase_two",
        "backup_pending_phase",
        "operation_phase",
    }:
        raise RuntimeError("delayed-isolation model must expose all four mandatory ODE phases")
    return attached
