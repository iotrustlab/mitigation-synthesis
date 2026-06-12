"""
Local runner for the attack envelope draft.

Run from the repository root with:
    .external/cleo/.venv/bin/python mitigation_synthesis/water_attack.py

The uncommented code is the question/parsing harness.
The commented section mirrors the collaborator-provided solution scaffold.
"""

from pathlib import Path
import sys

from cleo.envelope_format import parse_envelope
from cleo.session import EnvelopeSession


DEFAULT_ENVELOPE_PATH = Path(__file__).resolve().with_name("attack.envelope")
ENVELOPE_PATH = (
    Path(sys.argv[1]).resolve()
    if len(sys.argv) > 1
    else DEFAULT_ENVELOPE_PATH
)

text = ENVELOPE_PATH.read_text()
spec = parse_envelope(text)


def make_session() -> EnvelopeSession:
    session = EnvelopeSession(
        spec.game_str,
        spec.postcondition_str,
        defs_str=spec.defs_str,
    )
    session.set_precondition(spec.precondition_str)
    return session


# --- Subvalues and Tactics (fill in as developed) ---

# safety = r"""
# safe(x1, x2)
# & !unsafe(x1, x2)
# & attackTimer >= 0
# & ometric >= 0
# & rmetric >= 0
# & isBinary(P1) & isBinary(V1) & isBinary(P2) & isBinary(V2)
# """
#
# main_loop_inv = safety + r"""
# & L1 <= H1 & L2 <= H2
# & f1 >= 0 & f2 >= 0
# & T > 0 & Tmin > 0 & Tmin <= T
# & AttackTime >= 0
# & c1 >= 0 & c2 >= 0
# & op1 >= 0 & ov1 >= 0 & op2 >= 0 & ov2 >= 0
# """
#
# ode_inv = main_loop_inv
#
# session = make_session()
# session.set_invariant("a", main_loop_inv)
# session.set_invariant("aw", ode_inv)
# session.set_tactic("aw", "unfold; dW(1); QE")

# --- Final verification (can comment out during development) ---

# if __name__ == "__main__":
#     try:
#         result = session.verify()
#     except ValueError as exc:
#         print(f"Missing annotation: {exc}")
#         print("Needed annotations:")
#         for n in session.get_needed_annotations():
#             print(f"  {n['game_id']}: {n['kind']} - {n['game_str'][:80]}")
#         raise SystemExit(1)
#
#     for r in result.results:
#         status = "PASS" if r.passed else "FAIL"
#         print(
#             f"  {status} {r.obligation.kind} [{r.obligation.game_id}]",
#             "" if r.passed else r.feedback[:120],
#         )


if __name__ == "__main__":
    from cleo.parser import (
        parse_defs_from_string,
        parse_formula_from_string,
        parse_game_from_string,
    )

    if spec.defs_str:
        parse_defs_from_string(spec.defs_str)
    parse_formula_from_string(spec.precondition_str)
    parse_formula_from_string(spec.postcondition_str)
    parse_game_from_string(spec.game_str)

    print(f"{ENVELOPE_PATH} parses correctly")
