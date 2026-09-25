"""Hand-authored proof annotations valid for the concrete recovery template."""

from __future__ import annotations


STARTUP_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& isolated = 1 & p2 = 0 & qin = 0 & qd = 0
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& StartupDelay >= 0 & startupClock >= 0
& interventionBudget >= isolationCost + backupCost
& isolationCost >= 0 & backupCost >= 0
& T > 0 & Tmin > 0 & Tmin <= T
""".strip()


LOOP_INVARIANT = r"""
L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& isolated = 1 & p2 = 1 & qin = qbackup & qd = qbackup
& (p1 = 0 | p1 = 1)
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& interventionBudget >= 0
& isolationCost >= 0 & backupCost >= 0
& T > 0 & Tmin > 0 & Tmin <= T
""".strip()


OPERATION_ODE_INVARIANT = LOOP_INVARIANT + r"""
& operationClock >= 0
""".strip()


def attach_profile(session) -> list[dict[str, str]]:
    """Attach annotations based on actual CLEO obligation metadata, not position."""

    needed = session.get_needed_annotations()
    attached: list[dict[str, str]] = []
    for entry in needed:
        game_id, kind, game_str = entry["game_id"], entry["kind"], entry["game_str"]
        if kind == "loop":
            session.set_invariant(game_id, LOOP_INVARIANT)
            attached.append({"game_id": game_id, "kind": kind, "profile": "operation"})
        elif kind == "ode":
            profile = "startup" if "startupClock" in game_str else "operation"
            session.set_invariant(
                game_id, STARTUP_INVARIANT if profile == "startup" else OPERATION_ODE_INVARIANT
            )
            # `master` handles the dualized (Demon-controlled-duration) ODEs.
            # `dW` alone applies only to box ODE modalities.
            session.set_tactic(game_id, "master")
            attached.append({"game_id": game_id, "kind": kind, "profile": profile})
        else:
            raise RuntimeError(f"unexpected CLEO annotation kind: {kind}")
    return attached
