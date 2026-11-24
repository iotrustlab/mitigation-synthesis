"""Two independent paths on one controlled water benchmark with certified cost."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
import json

from ..dependency_semantics import transition
from ..formal_ir import Assignment as A, Stage, executions, expr, hybrid_program
from ..procedure import DependencyKind as K, DependencyNode, DependencyStatus as D
from ..procedure import EvidenceStatus as E, RecoveryProcedure, field_evidence
from .proofs import Obligation, Profile, proved, read_record

A_ID = "controlled-water-automatic-P2-v1"
B_ID = "controlled-water-manual-P3-v1"
SHARED = ("power_feed", "delivery_pipe", "meter")
PATHS = {
    A_ID: ("auto_actor", "network_B", "controller_B", "actuator_B", "power_B"),
    B_ID: ("local_actor", "interface_C", "actuator_C", "power_C"),
}
KINDS = {
    "auto_actor": K.SOFTWARE_ACTOR, "network_B": K.COMMUNICATION_PATH, "controller_B": K.CONTROLLER,
    "actuator_B": K.ACTUATOR, "power_B": K.POWER_SOURCE,
    "local_actor": K.HUMAN_ACTOR, "interface_C": K.INTERFACE, "actuator_C": K.ACTUATOR,
    "power_C": K.POWER_SOURCE, "power_feed": K.POWER_SOURCE, "delivery_pipe": K.PHYSICAL_PROCESS,
    "meter": K.OBSERVER,
}
WEIGHTS = ("wService", "wTime", "wIntervention", "wResource")
COSTS = ("cService", "cTime", "cIntervention", "cResource")
UNITS = ("L", "s", "manual action", "J")
POLICIES = {"COST-W1": (8, 3, 1, 1), "COST-W2": (1, 1, 3, 4), "COST-W3": (1, 1, 1, 1)}
RESEARCH = "CONTROLLED RESEARCH BENCHMARK"
SCOPE = "Constant-rate balance benchmark with isolated P1, persistent binary dependency effects and a final fresh meter."
HARD = "safe==1 and physical==1 and credible==1 and elapsed==horizon"


@dataclass(frozen=True)
class Context:
    """Common physical contract and both available path specifications, in SI-derived units."""

    initial_volume: int = 12
    primary_flow: int = 0
    inflow: int = 1
    demand: int = 3
    minimum: int = 2
    horizon: int = 4
    deadline: int = 2
    lower: int = 4
    upper: int = 17
    auto_delay: int = 1
    manual_delay: int = 2
    auto_capacity: int = 3
    manual_capacity: int = 3
    auto_watts: int = 4
    manual_watts: int = 1
    faults: tuple = ()

    def __post_init__(self):
        if not (0 < self.minimum <= self.demand and 0 < self.deadline <= self.horizon
                and 0 <= self.lower <= self.initial_volume <= self.upper and self.primary_flow == 0):
            raise ValueError("invalid controlled physical contract")
        if not all(0 <= d <= self.horizon for d in (self.auto_delay, self.manual_delay)):
            raise ValueError("startup must lie in the measurement horizon")
        if not all(0 <= q <= self.demand for q in (self.auto_capacity, self.manual_capacity)):
            raise ValueError("rated supply must lie within benchmark demand")
        if min(self.auto_watts, self.manual_watts, self.inflow) < 0:
            raise ValueError("rates must be nonnegative")
        if len(dict(self.faults)) != len(self.faults) or any(k not in KINDS or not isinstance(s, D)
                                                              for k, s in self.faults):
            raise ValueError("invalid resource state")
        object.__setattr__(self, "faults", tuple(sorted(self.faults)))

    @property
    def fingerprint(self):
        return sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


SCENARIOS = {
    "C0": Context(),
    "C1": Context(faults=(("controller_B", D.COMPROMISED),)),
    "C2": Context(faults=(("local_actor", D.UNAVAILABLE),)),
    "C3": Context(faults=(("power_feed", D.UNAVAILABLE),)),
    "C4": Context(faults=(("meter", D.COMPROMISED),)),
    "C5": Context(auto_capacity=2),
    "C6": Context(manual_delay=3),
    "C7": Context(faults=(("delivery_pipe", D.UNAVAILABLE),)),
}


def procedures(ctx):
    faults = dict(ctx.faults)
    nodes = {}
    for key, kind in KINDS.items():
        required = tuple(p for p, path in PATHS.items() if key in path or key in SHARED)
        nodes[key] = DependencyNode(
            key, kind, faults.get(key, D.TRUSTED), "controlled benchmark", required, E.RESEARCH_AUTHORED,
            RESEARCH, "Persistent binary choice, with a compromised meter reporting a low or full-scale reading.",
            "P1 is isolated. Candidate paths share the feed, pipe and meter.",
        )
    out = []
    for pid, path in PATHS.items():
        auto = pid == A_ID
        resources = {key: nodes[key] for key in (*path, *SHARED)}
        out.append(RecoveryProcedure(
            procedure_id=pid, case_id="controlled-water-cost", version="1", actor=path[0],
            role="automatic backup" if auto else "local backup operator", actor_ready_time=0,
            interface=None if auto else "interface_C", communication_path="network_B" if auto else None,
            authority_requirements=("authorized backup request",), controller="controller_B" if auto else None,
            controller_guard="Accept a delivered request on the active path.",
            controller_transition="Set output from accepted request.",
            output_stage=path[-2], delivered_actuation_relation="Powered actuator follows selected output.",
            actuator=path[-2], plant_model="two-phase-water-balance-v1", observer="meter",
            observation_relation="Healthy terminal sample equals delivered flow.",
            freshness_requirement="Meter samples final constant-flow phase at the horizon.",
            service_definition=f"Deliver at least {ctx.minimum} L/s continuously from {ctx.deadline} s through {ctx.horizon} s.",
            safety_definition=f"Water volume lies within [{ctx.lower},{ctx.upper}] L throughout.",
            initial_state={"volume_L": ctx.initial_volume, "primary_flow_L_s": ctx.primary_flow,
                           "inflow_L_s": ctx.inflow, "demand_L_s": ctx.demand, "initial_cost": 0},
            deadline=ctx.deadline, horizon=ctx.horizon, required_dependencies=resources,
            shared_dependencies=SHARED, attacker_effects={k: n.threat_effect for k, n in resources.items()},
            cost_vector_definition=COSTS, source_references=(RESEARCH, "recovery_experiment/cost.py"),
            evidence_status_by_field=field_evidence(E.RESEARCH_AUTHORED),
        ))
    return tuple(out)


@dataclass(frozen=True)
class WaterPlan:
    context: Context
    procedure: RecoveryProcedure
    initial: dict
    stages: tuple

    def terminal(self):
        return executions(self.stages, {**self.initial, **dict.fromkeys(WEIGHTS, 1)})

    def cost_coefficients(self):
        """Independent closed-form cost for a nominal powered path, checked in dL."""
        p = self.initial
        wait, active = p["start"], p["horizon"] - p["start"]
        return (wait*p["demand"] + active*(p["demand"]-p["capacity"]),
                wait, p["manual"], active*p["watts"])


def plans(ctx):
    out = []
    for proc in procedures(ctx):
        auto = proc.procedure_id == A_ID
        nodes = proc.required_dependencies

        def link(node, slot, rhs):
            return transition(nodes[node], A.nominal(slot, rhs))

        prefix = [link(proc.actor, "request", "1")]
        prefix.append(link("network_B" if auto else "interface_C", "accepted", "request"))
        output = link("controller_B", "output", "accepted") if auto else A.nominal("output", "accepted")
        stages = [Stage("authority", tuple(prefix)), Stage("controller", (output,))]
        stages.append(Stage("delivery", (
            link("power_feed", "feed", "1"), link("power_B" if auto else "power_C", "power", "feed"),
            link(proc.actuator, "actuated", "output"), A.nominal("drive", "actuated*power"),
            link("delivery_pipe", "passage", "1"), A.nominal("q", "drive*passage*capacity"),
        )))
        # Exact integrals of constant rates. Active and waiting intervals partition the horizon.
        stages.append(Stage("plant", (
            A.nominal("active", "horizon-start"), A.nominal("elapsed", "start+active"),
            A.nominal("atStart", "initialVolume+inlet*start"),
            A.nominal("atEnd", "atStart+(inlet-q)*active"),
            A.indicator("safe", "lower<=initialVolume and initialVolume<=upper and lower<=atStart and atStart<=upper and lower<=atEnd and atEnd<=upper"),
            A.indicator("physical", "start<=deadline and q>=minimum and elapsed==horizon"),
        )))
        trusted = transition(nodes["meter"], A.nominal("trusted", "1"), ("0",))
        observer = (trusted, A.nominal("fresh", "1"),
                    A("reading", (("trusted==1", "q"), ("trusted==0", "0"), ("trusted==0", "demand"))),
                    A.indicator("credible", "trusted==1 and fresh==1 and reading==q and reading>=minimum"))
        stages.append(Stage("observation", observer))
        stages.append(Stage("cost", (
            A.nominal("deficitAtStart", "start*demand"), A.nominal("cService", "deficitAtStart+active*(demand-q)"),
            A.conditional("cTime", "q>=minimum", "start", "horizon"),
            A.nominal("cIntervention", "manual*accepted"), A.nominal("cResource", "drive*watts*active"),
            A.nominal("J", "+".join(f"{w}*{c}" for w, c in zip(WEIGHTS, COSTS))),
        )))
        initial = dict(initialVolume=ctx.initial_volume, inlet=ctx.inflow, demand=ctx.demand,
                       minimum=ctx.minimum, horizon=ctx.horizon, deadline=ctx.deadline,
                       lower=ctx.lower, upper=ctx.upper, start=ctx.auto_delay if auto else ctx.manual_delay,
                       capacity=ctx.auto_capacity if auto else ctx.manual_capacity, manual=int(not auto),
                       watts=ctx.auto_watts if auto else ctx.manual_watts)
        out.append(WaterPlan(ctx, proc, initial, tuple(stages)))
    return tuple(out)


def rate_integral():
    # All variables except the five evolved quantities are frozen phase parameters.
    variables = ("v", "d", "r", "l", "tau", "vInit", "dInit", "rInit", "lInit",
                 "vRate", "dRate", "rRate", "lRate", "span", "lower", "upper")
    gamma = "tau=0 & span>=0 & v=vInit & d=dInit & r=rInit & l=lInit"
    ode = "{v'=vRate,d'=dRate,r'=rRate,l'=lRate,tau'=1 & tau<=span}"
    post = ("v=vInit+vRate*tau & d=dInit+dRate*tau & r=rInit+rRate*tau & l=lInit+lRate*tau"
            " & ((lower<=vInit & vInit<=upper & lower<=vInit+span*vRate & vInit+span*vRate<=upper)"
            " -> (lower<=v & v<=upper))")
    return Obligation("rate_integral", variables, f"({gamma}) -> [{ode}] ({post})",
                      "implyR(1); solve(1); QE")


def proof_profile(plan):
    ends = plan.terminal()
    if not ends:
        return None
    gamma = " & ".join([*(f"{k}={v}" for k, v in plan.initial.items()), *(f"{w}>=0" for w in WEIGHTS)])
    fingerprint = [plan.procedure.procedure_id, plan.initial,
                   {key: node.status.value for key, node in plan.procedure.required_dependencies.items()}]
    suffix = sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:10]
    auto = plan.procedure.procedure_id == A_ID
    name = f"cost_{'P2' if auto else 'P3'}_{suffix}"

    def obligation(label, stage_count, post, diamond=False):
        operations = [a for s in plan.stages[:stage_count] for a in s.assignments]
        variables = tuple(plan.initial) + WEIGHTS + tuple(a.name for a in operations)
        opening, closing = ("<", ">") if diamond else ("[", "]")
        formula = f"({gamma}) -> {opening}{hybrid_program(operations)}{closing} ({post})"
        return Obligation(label, variables, formula)

    if all(expr(HARD, state) for state in ends):
        coeffs = plan.cost_coefficients()
        cost_expr = "+".join(f"{w}*{n}" for w, n in zip(WEIGHTS, coeffs))
        post = " and ".join((HARD, *(f"{c}=={n}" for c, n in zip(COSTS, coeffs)), f"J=={cost_expr}"))
        obligations = (rate_integral(), obligation("controller", 2, "output=1"),
                       obligation("plant", 4, "safe=1 & physical=1"),
                       obligation("composition", 6, expr(post)), obligation("nonvacuity", 6, expr(post), True))
    else:
        obligations = (obligation("violation", 6, "!" + expr(HARD), True),)
    return Profile(name, obligations, len(plan.procedure.required_dependencies), 1,
                   f"{plan.context.horizon} s, service from {plan.context.deadline} s")


def profiles():
    unique = {}
    for ctx in SCENARIOS.values():
        for plan in plans(ctx):
            profile = proof_profile(plan)
            if profile:
                unique[profile.name] = profile
    return tuple(unique.values())


def _availability(nodes):
    states = {node.status for node in nodes}
    if D.UNAVAILABLE in states:
        return "DECLINE"
    if D.UNKNOWN in states:
        return "UNRESOLVED"
    return "ACCEPT"


def assessment(plan):
    proc = plan.procedure
    nodes = proc.required_dependencies
    states = plan.terminal()
    control_states = executions(plan.stages[:2], plan.initial)
    control = ("ACCEPT" if control_states and all(s["output"] == 1 for s in control_states) else "DECLINE")
    profile = proof_profile(plan)
    certified = profile is not None and proved(profile)
    individual = {}
    for field, slot in (("safety", "safe"), ("service", "physical"), ("observation", "credible")):
        if not states:
            individual[field] = "UNASSESSED"
        elif any(s[slot] == 0 for s in states):
            individual[field] = "VIOLATED"
        else:
            individual[field] = "HOLDS_IN_ENUMERATION"

    unavailable = [node.node_id for node in nodes.values() if node.status == D.UNAVAILABLE]
    violation = next((s for s in states if not expr(HARD, s)), None)
    witness = None
    if unavailable:
        classification, reason = "REJECTED", "Required dependency unavailable: " + ", ".join(unavailable)
    elif violation is not None:
        witness = {k: int(violation[k]) for k in ("output", "drive", "q", "start", "deadline", "safe",
                                                  "physical", "trusted", "reading", "credible")}
        unresolved = any(n.status == D.UNKNOWN for n in nodes.values())
        classification = "UNKNOWN" if unresolved else "REJECTED"
        if not violation["physical"]:
            reason = ("Opening misses the service deadline." if violation["start"] > violation["deadline"]
                      else "Delivered flow falls below the minimum.")
        elif not violation["credible"]:
            reason = "The final service observation lacks integrity."
        else:
            reason = "Tank safety bounds are violated."
    elif states and certified:
        classification, reason = "PROVED", "Validated universal safety/service/cost and progress obligations."
        individual = dict.fromkeys(individual, "PROVED")
    else:
        classification, reason = "UNKNOWN", "Matching formal evidence is unresolved."

    return {
        "procedure": proc.procedure_id, "context_sha256": plan.context.fingerprint,
        "B1": _availability([nodes[proc.actuator]]), "B2": _availability(nodes.values()),
        "B3": control if proc.controller else "INAPPLICABLE", "B4": classification, **individual,
        "reason": reason, "witness": witness, "profile": profile.name if profile else None,
        "formal_model_sha256": profile.sha256 if profile else None,
        "proof_profile_sha256": profile.profile_hash if profile else None,
        "dependency_states": {k: n.status.value for k, n in nodes.items()},
        "proof_for_queried_profile": certified, "proof_kind": ("violation" if violation else "recovery") if profile else None,
    }


def certified_selection(candidates, weights):
    candidates = tuple(candidates)
    if not candidates:
        raise ValueError("comparison requires a candidate set")
    ctx = candidates[0].context
    if any(p.context != ctx for p in candidates):
        raise ValueError("comparison requires the same complete context and hard contract")
    if len(set(p.procedure.procedure_id for p in candidates)) != len(candidates):
        raise ValueError("duplicate cost candidate")
    if len(weights) != len(WEIGHTS):
        raise ValueError("declare all four policy weights")
    w = tuple(Fraction(v) for v in weights)
    if any(v < 0 for v in w):
        raise ValueError("policy weights must be nonnegative")
    costs, vectors = {}, {}
    # Only plans reconstructed from this complete incident may inherit its formula.
    for candidate in candidates:
        canonical = next((p for p in plans(ctx) if p.procedure == candidate.procedure), None)
        if canonical != candidate:
            raise ValueError("candidate differs from its common-context model")
        if assessment(candidate)["B4"] == "PROVED":
            coeffs = candidate.cost_coefficients()
            pid = candidate.procedure.procedure_id
            vectors[pid] = coeffs
            costs[pid] = sum(wn * cn for wn, cn in zip(w, coeffs))
    best = min(costs.values()) if costs else None
    winners = sorted(k for k, v in costs.items() if v == best)
    frontier = [k for k, a in vectors.items() if not any(
        all(v <= x for v, x in zip(b, a)) and any(v < x for v, x in zip(b, a)) for b in vectors.values()
    )]
    return {"cost_by_admissible_procedure": {k: str(v) for k, v in costs.items()},
            "weights": [str(v) for v in w], "winners": winners, "pareto_frontier": sorted(frontier),
            "result": "NO_ASSURED_RECOVERY" if not winners else "TIE" if len(winners) > 1 else "SELECTED"}


def reports():
    rows, selections = [], []
    for scenario, ctx in SCENARIOS.items():
        candidates = plans(ctx)
        rows.extend({"scenario": scenario, **assessment(p)} for p in candidates)
        selections.extend({"scenario": scenario, "policy": policy, "context_sha256": ctx.fingerprint,
                           **certified_selection(candidates, weights)} for policy, weights in POLICIES.items())
    verified_profiles = []
    for profile in profiles():
        record = read_record(profile)
        verified_profiles.append({"profile": profile.name, "formal_model_sha256": profile.sha256,
                                  "proof_profile_sha256": profile.profile_hash,
                                  "record": record, "validated": proved(profile)})
    expressions = {}
    for p in plans(SCENARIOS["C0"]):
        coeffs = p.cost_coefficients()
        expressions[p.procedure.procedure_id] = {"components": dict(zip(COSTS, coeffs)),
                                                 "units": dict(zip(COSTS, UNITS)),
                                                 "formal_expression": " + ".join(
                                                     f"{n}*{w}" for n, w in zip(coeffs, WEIGHTS)),
                                                 "profile": proof_profile(p).name, "scope": "C0"}
    return {
        "common_context_cost_proofs": {"label": RESEARCH, "scope": SCOPE, "profiles": verified_profiles,
                                       "nominal_expressions": expressions},
        "common_context_cost_mutations": {"label": RESEARCH, "rows": rows},
        "common_context_cost_selection": {"label": RESEARCH, "weight_order": WEIGHTS, "units": UNITS,
                                          "nominal_expressions": expressions, "rows": selections,
                                          "contexts": {k: asdict(c) for k, c in SCENARIOS.items()}},
    }
