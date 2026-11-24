"""Perfect-information water recovery game over the proved two-phase tank endpoints."""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from .. import verify
from ..milestone2 import cost
from ..milestone2.proofs import JAR_SHA256, Obligation, Profile, digest, read_record

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "game_evidence"
STATE = ("initialVolume", "upB", "upC", "feed", "seeB", "seeC", "start", "q", "active",
         "atStart", "atEnd", "elapsed", "reading", "fresh", "trusted")
# KeYmaera X 5.1.1 spells program dual ^@. In a diamond an ordinary union
# belongs to Angel; dual of a union of assignments gives Demon the choice.
AVAILABLE = ((1, 1, 1), (0, 1, 1), (1, 0, 1))
POWER_LOSS = (1, 1, 0)
CHOICES = ("P2", "P3", "hold")


def options(branches):
    return "{" + " ++ ".join("{" + b + "}" for b in branches) + "}"


def game_profile():
    ctx = cost.Context()
    gamma = f"initialVolume={ctx.initial_volume}"
    observe = "seeB:=upB*feed; seeC:=upC*feed;"
    moves = {
        "P2": f"?seeB=1; start:={ctx.auto_delay}; q:={ctx.auto_capacity}*upB*feed;",
        "P3": f"?seeC=1; start:={ctx.manual_delay}; q:={ctx.manual_capacity}*upC*feed;",
        "hold": "start:=0; q:=0;",
    }
    plant = (f"active:={ctx.horizon}-start; atStart:=initialVolume+{ctx.inflow}*start; "
             f"atEnd:=atStart+({ctx.inflow}-q)*active; elapsed:=start+active; "
             "reading:=q; fresh:=1; trusted:=1;")
    safety = " & ".join(f"{ctx.lower}<={v} & {v}<={ctx.upper}" for v in ("initialVolume", "atStart", "atEnd"))
    service = (f"start<={ctx.deadline} & q>={ctx.minimum} & elapsed={ctx.horizon} & "
               f"reading=q & fresh=1 & trusted=1 & reading>={ctx.minimum}")
    contract = f"({safety} & {service})"

    def formula(states, choices, positive=True):
        disturbances = [f"upB:={b}; upC:={c}; feed:={f};" for b, c, f in states]
        program = f"{options(disturbances)}^@; {observe} {options(moves[c] for c in choices)}; {plant}"
        modal = f"<{program}>{contract}"
        return f"{gamma} -> " + (modal if positive else f"!({modal})")

    obligations = (
        ("adaptive_win", formula(AVAILABLE, CHOICES)),
        ("shared_power_no_win", formula((*AVAILABLE, POWER_LOSS), CHOICES, False)),
        ("fixed_P2_no_win", formula(AVAILABLE, ("P2",), False)),
        ("fixed_P3_no_win", formula(AVAILABLE, ("P3",), False)),
    )
    return Profile("water_game", tuple(Obligation(key, STATE, f, "implyR(1); chase(1); QE") for key, f in obligations),
                   3, 1, "two exact phases ending at 4 seconds")


def prove(output, jar, z3, java):
    if digest(jar.read_bytes()) != JAR_SHA256:
        raise ValueError("Unexpected KeYmaera X release")
    profile = game_profile()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="water-game-") as folder:
        scratch = Path(folder)
        (scratch / ".keymaerax").mkdir()
        (scratch / ".keymaerax" / "solver").symlink_to(z3)
        rec = verify._solve(profile, profile.name, False, jar, z3, java, scratch, output)
    rec.pop("kind")
    index = {"modality": "dGL diamond", "profile": profile.name, "profile_sha256": profile.profile_hash,
             "jar_sha256": JAR_SHA256, "solver_sha256": digest(z3.read_bytes()), "record": rec}
    (output / "proof_index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return rec["status"] == "PROVED"


def report(evidence, result_path):
    profile = game_profile()
    index = json.loads((evidence / "proof_index.json").read_text())
    record = index["record"]
    archive = evidence / "models" / (profile.name + ".kyx")
    if (archive.read_text() != profile.archive() or profile.sha256 != record["archive_sha256"]
            or index["profile_sha256"] != profile.profile_hash or index["jar_sha256"] != JAR_SHA256
            or record["return_code"] != 0 or record["status"] != "PROVED"
            or set(record["obligations"]) != set(profile.entries())):
        raise ValueError("Game archive or prover record differs from the source")
    for key, entry in profile.entries().items():
        export = (evidence / "proof_records" / profile.name / (key + ".kyp")).read_bytes()
        item = record["obligations"][key]
        if (item["status"] != "PROVED" or item["proof_sha256"] != digest(export)
                or entry.strip().encode() not in export or f'Lemma "user/{profile.title(key)}".'.encode() not in export):
            raise ValueError(f"Game proof export does not certify {key}")

    # Explicit finite policy and physical endpoints. Cross-check the successful
    # branches against the nominal executable plans and their ODE certificates.
    ctx = cost.Context()
    moves = {"P2": (ctx.auto_delay, ctx.auto_capacity), "P3": (ctx.manual_delay, ctx.manual_capacity),
             "hold": (0, 0)}
    endpoints, profiles = {}, {}
    for name, (start, q) in moves.items():
        at_start = ctx.initial_volume + ctx.inflow * start
        at_end = at_start + (ctx.inflow - q) * (ctx.horizon - start)
        endpoints[name] = dict(start=start, atStart=at_start, atEnd=at_end, elapsed=ctx.horizon,
                               q=q, fresh=1, trusted=1, reading=q)
    for name, plan in zip(("P2", "P3"), cost.plans(ctx)):
        fixed = cost.proof_profile(plan)
        evidence_row = read_record(fixed)
        if not evidence_row or any(evidence_row["obligations"][k]["status"] != "PROVED"
                                   for k in ("rate_integral", "composition", "nonvacuity")):
            raise ValueError("Missing controlled tank proof")
        for execution in plan.terminal():
            if any(execution[k] != v for k, v in endpoints[name].items()):
                raise ValueError("Game endpoint differs from the fixed procedure")
        profiles[name] = {"profile": fixed.name, "archive_sha256": fixed.sha256,
                          "rate_integral_proof_sha256": evidence_row["obligations"]["rate_integral"]["proof_sha256"]}
    policy = []
    for b, c, feed in (*AVAILABLE, POWER_LOSS):
        available = [name for name, enabled in zip(("P2", "P3"), (b * feed, c * feed)) if enabled]
        legal = [*available, "hold"]
        winners = []
        for action in legal:
            e = endpoints[action]
            safe = all(ctx.lower <= v <= ctx.upper for v in (ctx.initial_volume, e["atStart"], e["atEnd"]))
            if safe and e["start"] <= ctx.deadline and e["q"] >= ctx.minimum and e["reading"] == e["q"]:
                winners.append(action)
        if winners != available:
            raise ValueError("Legal policy disagrees with the service contract")
        policy.append({"upB": b, "upC": c, "feed": feed, "observed": [b * feed, c * feed],
                       "legal_actions": legal, "winning_actions": winners})
    output = {"model": "Perfect-information finite dGL tank game with constant-rate endpoint maps",
              "reference_doi": "10.1145/2817824", "archive_sha256": profile.sha256,
              "proofs": record["obligations"], "fixed_procedure_bridges": profiles,
              "units": {"start": "s", "atStart": "L", "atEnd": "L", "elapsed": "s", "q": "L/s", "reading": "L/s"},
              "strategy_table": policy, "completed_action_endpoints": endpoints,
              "assumptions": "Known current resource state, isolated primary, healthy pipe and meter, nominal capacities and delays, no later resource changes. Normal attack choices leave at least one powered path available.",
              "scope": "Qualitative winning safety and service strategy under this disturbance alphabet. Preference among two winning actions is outside this game."}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prove", "report"))
    p.add_argument("--output", type=Path, default=EVIDENCE, help="Proof evidence directory")
    p.add_argument("--result", type=Path, default=ROOT.parent / "results/paper_v2/adaptive_game.json")
    p.add_argument("--jar", type=Path, default=os.environ.get("KEYMAERAX_JAR"))
    p.add_argument("--z3", type=Path, default=shutil.which("z3"))
    p.add_argument("--java", default=shutil.which("java"))
    a = p.parse_args()
    if a.mode == "prove":
        if not all((a.jar, a.z3, a.java)):
            p.error("prove requires KeYmaera X, Z3, and Java")
        if not prove(a.output, a.jar.resolve(), a.z3.resolve(), a.java):
            raise SystemExit(1)
    report(a.output, a.result)
