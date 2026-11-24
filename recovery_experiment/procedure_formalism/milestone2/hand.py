"""Local Hand experiments on the historical, sampled research fixture."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from ..attleboro import SOURCE_VERSION, attleboro
from ..classifier import classify
from ..evaluation import HAND_STATE, baselines
from ..formal_ir import expr, hybrid_program
from ..formal_model import POST, build_model
from ..procedure import DependencyStatus as DS
from .proofs import Obligation, Profile, proved, read_record


HAND_PROFILE = "attleboro-local-hand-end-to-end-recovery-v1"


@dataclass(frozen=True)
class Mutation:
    label: str
    status: tuple[str, DS] | None = None
    state: tuple[str, int] | None = None
    ready: int = 0

    def snapshot(self):
        statuses = dict((self.status,)) if self.status else {}
        inputs = {**HAND_STATE, **(dict((self.state,)) if self.state else {})}
        return attleboro(statuses=statuses, initial_state=inputs, local_ready_time=self.ready)


CASES = (
    Mutation("Nominal Hand on generator"),
    Mutation("Local actor absent", ("local_operator", DS.UNAVAILABLE)),
    Mutation("Actor ready one tick after request origin", ready=1),
    Mutation("Hand selector off", state=("hand_selected", 0)),
    Mutation("Shared VFD unavailable", ("vfd", DS.UNAVAILABLE)),
    Mutation("Shared pump unavailable", ("pump", DS.UNAVAILABLE)),
    Mutation("Shared hardwired trip active", state=("trip", 1)),
    Mutation("Forward flow blocked", state=("flow_blocked", 1)),
    Mutation("Sample stale", state=("observation_fresh", 0)),
    Mutation("Observer integrity compromised", ("observer", DS.COMPROMISED)),
    Mutation("Shared motor power unavailable", ("motor_power", DS.UNAVAILABLE)),
)


def _all_ops(model):
    return tuple(op for stage in model.stages for op in stage.assignments)


def _initial_formula(model):
    return " & ".join(f"{name}={value}" for name, value in model.initial.items())


def _nominal_profile():
    model = build_model(CASES[0].snapshot()["hand"])
    obligations = tuple(Obligation.from_entry(name, entry) for name, entry in model.entries().items())
    return Profile(HAND_PROFILE, obligations, len(model.procedure.required_dependencies), 3, "3 ticks of 100 ms")


def _mutation_obligation(index, model):
    slots = _all_ops(model)
    variables = tuple((*model.initial, *(a.name for a in slots)))
    if any(node.status == DS.UNAVAILABLE for node in model.procedure.required_dependencies.values()):
        # This negative box proves that the required transition has no execution.
        return Obligation(f"H{index}_disabled", variables,
                          f"({_initial_formula(model)}) -> [{hybrid_program(slots)}] (0=1)")
    return Obligation.from_entry(f"H{index}_violation", model.entries(violation=True)["violation"])


def _selector_pairs(model):
    """Project the actual nominal physical drive guard onto both selector bits."""
    drive = next(a for a in _all_ops(model) if a.name == "drive")
    return [(remote, hand) for remote, hand in product((0, 1), repeat=2)
            if 1 in drive.values(dict(remote=remote, hand=hand, delivered=1))]


def _overlap_obligation(snapshot):
    # For a stopped plant and trusted shared equipment, positive service requires
    # the drive on. The two actual drive relations must then both admit 1.
    formulas = []
    for key in ("remote", "hand"):
        model = build_model(snapshot[key])
        drive = next(a for a in _all_ops(model) if a.name == "drive")
        formulas.append(drive.relation())
    return Obligation("exclusive_command_modes", ("remote", "hand", "delivered", "drive"),
                      f"(drive=1 & {formulas[0]} & {formulas[1]}) -> 0=1", "QE")


def profiles():
    mutations = tuple(_mutation_obligation(i, build_model(spec.snapshot()["hand"]))
                      for i, spec in enumerate(CASES) if i)
    return (_nominal_profile(),
            Profile("attleboro-hand-dependency-mutations-v1", mutations, 8, 3, "3 ticks from readiness"),
            Profile("attleboro-command-domain-overlap-v1", (_overlap_obligation(CASES[0].snapshot()),),
                    1, 0, "constant selector throughout start"))


def _value(value):
    return int(value) if isinstance(value, Fraction) and value.denominator == 1 else str(value)


def _flag(states, predicate, verified):
    if not states:
        return "UNASSESSED"
    if all(predicate(s) for s in states):
        return "PROVED" if verified else "HOLDS_IN_ENUMERATION"
    return "VIOLATED"


def _row(index, spec, positive):
    snapshot = spec.snapshot()
    proc = snapshot["hand"]
    model = build_model(proc)
    executions = model.executions()
    witness = next((s for s in executions if not expr(POST, s)), None)
    reasons = classify(proc)
    if not executions:
        result = "REJECTED" if reasons.result.value == "REJECTED" else "UNKNOWN"
    elif witness is not None:
        result = "REJECTED"
    else:
        result = "PROVED" if positive else "UNKNOWN"
    example = witness or next(iter(executions), None)
    fields = ("ready", "request", "received", "accepted", "delivered", "drive", "run",
              "t", "safe", "q", "pressure", "physical", "observed", "fresh", "trusted", "established")
    return {
        "scenario": f"H{index}", "label": spec.label, "procedure": HAND_PROFILE,
        **baselines(proc), "B4": result,
        "safety": _flag(executions, lambda s: s["safe"], positive),
        "service": _flag(executions, lambda s: s["physical"] and s["t"] <= s["deadline"], positive),
        "observation": _flag(executions, lambda s: s["established"] and s["t"] <= s["deadline"], positive),
        "reason": "All eight Local Hand proof obligations closed" if result == "PROVED" else reasons.basis,
        "failure_reasons": [] if result == "PROVED" else [r.value for r in reasons.reasons],
        "model_sha256": model.sha256, "reachable_terminal_states": len(executions),
        "dependency_states": {key: node.status.value for key, node in proc.required_dependencies.items()},
        "ready_tick": proc.actor_ready_time, "deadline_tick": proc.deadline,
        "initial_state": dict(proc.initial_state),
        "witness": {key: _value(example[key]) for key in fields} if example is not None else None,
    }


def domain_report(profile):
    snapshot = CASES[0].snapshot()
    remote, hand = (build_model(snapshot[key]) for key in ("remote", "hand"))
    r_modes, h_modes = _selector_pairs(remote), _selector_pairs(hand)
    common = set(r_modes) & set(h_modes)
    return {
        "ordered_bits": ["remote_selected", "hand_selected"],
        "fixed_context": "Stopped pump at zero flow, three scans, trusted shared plant, fixed selector and authorized start.",
        "common_conditions": ["actor and command path available", "actor ready by tick 0 for deadline 3",
                              "authorized actor", "motor energized", "trip and pH faults clear",
                              "forward flow unblocked", "fresh credible final observation"],
        "domain_remote": {"necessary_selector_pairs": r_modes,
                          "power_authority": "Utility available, generator idle, MTS on utility, latch clear after scan.",
                          "command_path": sorted(remote.procedure.required_dependencies.keys() - set(remote.procedure.shared_dependencies))},
        "domain_hand": {"necessary_selector_pairs": h_modes,
                        "power_authority": "Utility with MTS on utility, or generator ready with MTS on generator.",
                        "command_path": sorted(hand.procedure.required_dependencies.keys() - set(hand.procedure.shared_dependencies))},
        "shared_dependencies": list(hand.procedure.shared_dependencies),
        "same_shared_objects": all(snapshot["hand"].required_dependencies[k] is snapshot["remote"].required_dependencies[k]
                                   for k in hand.procedure.shared_dependencies),
        "intersection_selector_pairs": sorted(common), "intersection_satisfiable": bool(common),
        "intersection_proof": "PROVED_DISJOINT" if not common and proved(profile) else "UNRESOLVED",
        "cost_comparison": "NOT_COMPARABLE_UNDER_COMMON_CONTEXT" if not common else "REQUIRES_FULL_DOMAIN_CHECK",
        "source_basis": "Loop 0110-1 Hand/Off/Remote selector; pinned simulator applies exclusive panel selection.",
        "source_tree": SOURCE_VERSION,
    }


def reports():
    nominal, mutations, overlap = profiles()
    nominal_ok = proved(nominal)
    rows = [_row(i, spec, nominal_ok and i == 0) for i, spec in enumerate(CASES)]
    return {
        "attleboro_hand_proof_summary": {
            "procedure": HAND_PROFILE, "result": rows[0]["B4"], "record": read_record(nominal),
            "source_tree": SOURCE_VERSION, "mutations_record": read_record(mutations),
            "milestone1_schema_identity": CASES[0].snapshot()["hand"].procedure_id,
            "sampled_plant_states": ["flow", "run delay", "pressure derived from flow"],
            "observed_late_hand_trace_sha256": "1e7dd13efe5d0856dafa080e0c5fb553d0a26f3838761bbce211a0087b6e313e",
            "nominal_witness": rows[0]["witness"],
        },
        "attleboro_hand_mutations": {"rows": rows, "negative_profile_verified": proved(mutations)},
        "attleboro_domain_overlap": domain_report(overlap),
    }
