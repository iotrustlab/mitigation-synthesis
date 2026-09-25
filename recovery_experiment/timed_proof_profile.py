"""Proof annotations for the non-vacuous, finite timed takeover theorem."""

from __future__ import annotations


STARTUP_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & p2 = 0 & qin = 0 & qd = 0
& q1 = 0 & q1 = (1-isolated) * p1 * qprimary
& q2 = 0 & q2 = p2 * qbackup & qdelivered = 0
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& StartupDelay > 0 & StartupDelay <= RecoveryDeadline
& startupClock = 0 & recoveryClock = 0
& interventionBudget >= isolationCost + backupCost
& isolationCost >= 0 & backupCost >= 0
& T > 0
""".strip()


OPERATION_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2 & L1 >= 0 & L2 >= 0
& isolated = 1 & p2 = 1 & qin = qbackup & qd = qbackup
& q1 = 0 & q1 = (1-isolated) * p1 * qprimary
& q2 = qbackup & q2 = p2 * qbackup
& qdelivered = q2 & qdelivered = qd & qdelivered >= qmin
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& startupClock = StartupDelay & recoveryClock = StartupDelay & recoveryClock <= RecoveryDeadline
& interventionBudget >= 0
& isolationCost >= 0 & backupCost >= 0
& T > 0 & operationClock = 0
""".strip()


def attach_timed_profile(session) -> list[dict[str, str]]:
    """The versioned timed game has exactly startup and mandatory-operation ODEs."""

    needed = session.get_needed_annotations()
    attached: list[dict[str, str]] = []
    for entry in needed:
        if entry["kind"] != "ode":
            raise RuntimeError(f"unexpected timed-model annotation: {entry['kind']}")
        profile = "startup" if "startupClock" in entry["game_str"] else "operation"
        session.set_invariant(
            entry["game_id"], STARTUP_INVARIANT if profile == "startup" else OPERATION_INVARIANT
        )
        # `master` reduces the Angel ODE to its exact-duration arithmetic goal;
        # QE discharges that remaining existential arithmetic obligation.
        session.set_tactic(entry["game_id"], "master; QE")
        attached.append({"game_id": entry["game_id"], "kind": "ode", "profile": profile})
    if {entry["profile"] for entry in attached} != {"startup", "operation"}:
        raise RuntimeError("timed model must expose one startup and one operation ODE")
    return attached
