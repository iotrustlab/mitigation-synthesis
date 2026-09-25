"""CLEO annotations for the state-dependent flowing-takeover theorem."""

from __future__ import annotations


STARTUP_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& x1 + startupInflow * StartupDelay <= H1
& x2 - startupWithdrawal * StartupDelay >= L2
& isolated = 1 & p2 = 0
& qin = startupInflow & demand = startupWithdrawal & qout = demand
& q1 = 0 & q1 = (1-isolated) * p1 * qprimary
& q2 = 0 & q2 = p2 * qbackup
& qdelivered = qout & qdelivered >= qmin
& (p1 = 0 | p1 = 1)
& startupInflow >= 0 & startupWithdrawal >= qmin & qmin > 0
& qprimary >= 0 & qbackup >= qmin
& StartupDelay > 0 & TransferDeadline > 0 & StartupDelay <= TransferDeadline
& startupClock = 0 & transferClock = 0
& interventionBudget >= isolationCost + backupCost
& isolationCost >= 0 & backupCost >= 0
& T > 0
""".strip()


OPERATION_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & p2 = 1
& qin = qbackup & demand = qbackup & qout = demand
& q1 = 0 & q1 = (1-isolated) * p1 * qprimary
& q2 = qbackup & q2 = p2 * qbackup
& qdelivered = qout & qdelivered >= qmin
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& startupClock = StartupDelay & transferClock = StartupDelay & transferClock <= TransferDeadline
& interventionBudget >= 0
& isolationCost >= 0 & backupCost >= 0
& T > 0 & operationClock = 0
""".strip()


def attach_state_dependent_profile(session) -> list[dict[str, str]]:
    """Attach distinct startup and balanced-operation ODE profiles."""

    needed = session.get_needed_annotations()
    attached: list[dict[str, str]] = []
    for entry in needed:
        if entry["kind"] != "ode":
            raise RuntimeError(f"unexpected state-dependent annotation: {entry['kind']}")
        profile = "startup" if "startupClock" in entry["game_str"] else "operation"
        session.set_invariant(
            entry["game_id"], STARTUP_INVARIANT if profile == "startup" else OPERATION_INVARIANT
        )
        session.set_tactic(entry["game_id"], "master; QE")
        attached.append({"game_id": entry["game_id"], "kind": "ode", "profile": profile})
    if {entry["profile"] for entry in attached} != {"startup", "operation"}:
        raise RuntimeError("state-dependent model must expose one startup and one operation ODE")
    return attached
