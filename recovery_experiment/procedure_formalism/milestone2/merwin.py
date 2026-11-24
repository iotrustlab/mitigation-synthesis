"""HCC Remote Auto on the pinned, trace-conditioned representative hydro case."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json

from ..dependency_semantics import transition
from ..domain_cases import REMOTE_AUTO, merwin_procedures
from ..formal_ir import Assignment as A, Stage, executions, expr, hybrid_program
from ..procedure import DependencyStatus as D, EvidenceStatus as E
from .merwin_reduction import FIXTURE, RECORD, S, checked_reduction, trajectory
from .proofs import Obligation, Profile, digest, proved, read_record, object_hash

ID = "merwin-hcc-remote-auto-end-to-end-recovery-v1"
POST = "safe==1 and service==1 and credible==1 and clock==deadline"
DEFAULTS = {
    "remoteMode": 1,
    "plantReady": 1,
    "auxNormal": 1,
    "syncAvailable": 1,
    "contactOperable": 1,
    "generationCoupled": 1,
    "meterFresh": 1,
}


@dataclass(frozen=True)
class Scenario:
    description: str
    statuses: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)


CASES = (
    Scenario("Nominal historical HCC branch on the representative research plant"),
    Scenario("Required HCC actor absent", {"hcc_operator": D.UNAVAILABLE}),
    Scenario("Remote communication unavailable", {"hcc_link": D.UNAVAILABLE}),
    Scenario("Local guide-bearing lubrication indication unavailable", {"lube": D.UNAVAILABLE}),
    Scenario("Remote auxiliaries abnormal", inputs={"auxNormal": 0}),
    Scenario("Synchronization window unavailable", inputs={"syncAvailable": 0}),
    Scenario("Close demand issued, contact fails to close", inputs={"contactOperable": 0}),
    Scenario("Breaker contact closes, electrical generation coupling lost", inputs={"generationCoupled": 0}),
    Scenario("Final power sample stale", inputs={"meterFresh": 0}),
    Scenario("Shared hydro unit unavailable", {"hydro_unit": D.UNAVAILABLE}),
    Scenario("Unknown breaker integrity", {"breaker": D.UNKNOWN}),
)


def candidates(scenario):
    """Share the prior four typed schemas and attach one scenario-wide resource state."""
    schemas = merwin_procedures()
    old = next(p for p in schemas if p.procedure_id == REMOTE_AUTO)
    nodes = {}
    for p in schemas:
        for key, node in p.required_dependencies.items():
            users = tuple(ID if user == REMOTE_AUTO else user for user in node.required_by)
            status = scenario.statuses.get(key, D.TRUSTED if key in old.required_dependencies else D.UNKNOWN)
            nodes[key] = replace(
                node,
                required_by=users,
                status=status,
                source_status=E.RESEARCH_AUTHORED,
                threat_effect="Finite Boolean stage signal or inhibited branch.",
            )
    result = []
    facts = trajectory()[1]
    for p in schemas:
        required = {key: nodes[key] for key in p.required_dependencies}
        common = dict(
            required_dependencies=required,
            initial_state={"active_mode": "hcc_remote_auto", **DEFAULTS, **scenario.inputs},
        )
        if p.procedure_id == REMOTE_AUTO:
            evidence = dict(p.evidence_status_by_field)
            for key in (
                "actor_ready_time",
                "safety_definition",
                "freshness_requirement",
                "attacker_effects",
                "horizon",
                "deadline",
                "plant_model",
                "initial_state",
            ):
                evidence[key] = E.RESEARCH_AUTHORED
            p = replace(
                p,
                **common,
                procedure_id=ID,
                actor_ready_time=facts["start_tick"],
                horizon=facts["horizon_ticks"],
                deadline=facts["horizon_ticks"],
                plant_model="merwin-trace-conditioned-gate-rotor-generator-v1",
                safety_definition="Per-scan gate in [0,100]%, speed in [0,110]%, relay-permitted contact.",
                service_definition="Three consecutive recorded-clock samples with running state, closed contact and at least 1 MW.",
                observation_relation="The trusted power channel samples actual generation on the same three polls.",
                freshness_requirement="All three service samples are fresh.",
                evidence_status_by_field=evidence,
            )
        else:
            p = replace(p, **common)
        result.append(p)
    return tuple(result)


def _stages(proc):
    f = trajectory()[1]
    nodes = proc.required_dependencies

    def signal(key, name, predicate):
        return transition(nodes[key], A.indicator(name, predicate))

    actor = (
        signal("hcc_operator", "request", "remoteMode==1"),
        signal("scada", "issued", "request==1"),
        signal("hcc_link", "received", "issued==1"),
    )
    controller = (
        signal("auxiliaries", "auxOK", "auxNormal==1"),
        signal("sequencer", "accepted", "received==1 and remoteMode==1 and auxOK==1 and plantReady==1"),
    )
    roll = (
        signal("hydro_unit", "drive", "accepted==1"),
        A.conditional("peakGate", "drive==1", str(f["max_gate"]), "0"),
        A.conditional("peakSpeed", "drive==1", str(f["max_open_speed"]), "0"),
        A.conditional("rollSpeed", "drive==1", str(f["speed_at_sync"]), "0"),
        A.conditional("settleClock", "drive==1", str(f["settled_tick"]), "0"),
        A.indicator("atSpeed", "drive==1 and settleClock>requestClock and settleClock<syncClock"),
    )
    phase = f["phase_milli_deg"]
    sync = (
        A.nominal("slipScaled", f"(rollSpeed-100*{S})*3"),
        A.nominal("phase", f"0-{abs(phase)}" if phase < 0 else str(phase)),
        A.nominal("predicted", "5000*phase+126*slipScaled"),
        A.indicator(
            "window",
            "atSpeed==1 and syncAvailable==1 and voltage>=1000 and voltage<=1050 "
            "and slipScaled>0-300000 and slipScaled<300000 and predicted>0-15000000 and predicted<15000000",
        ),
        signal(
            "synchronization",
            "relay",
            "syncAvailable==1 and voltage>=1000 and voltage<=1050 and "
            "phase>=0-10000 and phase<=10000 and slipScaled>0-335000 and slipScaled<335000",
        ),
        signal("breaker_command", "closeCmd", "window==1"),
    )
    delivery = (
        A.nominal("contactClock", "syncClock+1"),
        A.conditional("timerMs", "closeCmd==1 and relay==1", "100", "0"),
        signal("breaker", "contact", "timerMs>=50 and contactOperable==1"),
        A.conditional("terminalSpeed", "contact==1", "100000000", "peakSpeed"),
        A.indicator("running", "contact==1 and closeCmd==1"),
    )
    plant = [
        A.indicator(
            "safe",
            "peakGate>=0 and peakGate<=100000000 and peakSpeed>=0 and peakSpeed<=110000000 "
            "and terminalSpeed>=0 and terminalSpeed<=110000000 and (contact==0 or (relay==1 and closeCmd==1))",
        )
    ]
    observe = [signal("power_meter", "trusted", "1==1")]
    for i, (tick, mechanical) in enumerate(zip(f["service_ticks"], f["mechanical_micro_mw"]), 1):
        plant.extend(
            (
                A.nominal(f"tick{i}", str(tick)),
                A.conditional(f"torque{i}", "drive==1", str(mechanical), "0"),
                A.conditional(
                    f"rawMW{i}", "contact==1 and generationCoupled==1", f"torque{i}*97/100000000", "0"
                ),
                A.conditional(f"mw{i}", f"rawMW{i}>80", "80", f"rawMW{i}"),
                A.indicator(f"physical{i}", f"contact==1 and running==1 and mw{i}>=1"),
            )
        )
        fresh = "meterFresh" if i == 3 else "1"
        observe.extend(
            (
                A.nominal(f"fresh{i}", fresh),
                A.conditional(
                    f"observed{i}",
                    f"trusted==1 and fresh{i}==1",
                    f"mw{i}",
                    f"observed{i-1}" if i > 1 else "0",
                ),
                A.indicator(
                    f"credit{i}",
                    f"trusted==1 and fresh{i}==1 and observed{i}==mw{i} "
                    f"and observed{i}>=1 and physical{i}==1",
                ),
            )
        )
    plant.extend(
        (
            A.nominal("clock", "tick3"),
            A.indicator(
                "service",
                "physical1==1 and physical2==1 and physical3==1 "
                "and contactClock<=tick1 and tick1<tick2 and tick2<tick3",
            ),
        )
    )
    observe.append(A.indicator("credible", "credit1==1 and credit2==1 and credit3==1"))
    return tuple(
        Stage(name, tuple(ops))
        for name, ops in (
            ("actor", actor),
            ("controller", controller),
            ("roll", roll),
            ("synchronization", sync),
            ("delivery", delivery),
            ("plant", plant),
            ("observer", observe),
        )
    )


def model(index):
    proc = next(p for p in candidates(CASES[index]) if p.procedure_id == ID)
    f = trajectory()[1]
    initial = {
        **DEFAULTS,
        **CASES[index].inputs,
        "requestClock": f["start_tick"],
        "syncClock": f["sync_tick"],
        "voltage": f["voltage_milli_pu"],
        "deadline": f["horizon_ticks"],
    }
    return proc, initial, _stages(proc)


def _obligation(name, stages, initial, post, diamond=False):
    ops = [a for stage in stages for a in stage.assignments]
    gamma = " & ".join(f"{k}={v}" for k, v in initial.items())
    pm = ("<", ">") if diamond else ("[", "]")
    formula = f"({gamma}) -> {pm[0]} {hybrid_program(ops)} {pm[1]} ({post})"
    return Obligation(name, tuple(initial) + tuple(a.name for a in ops), formula)


def profile(index):
    proc, initial, stages = model(index)
    if index in (0, 3):
        contracts = (
            ("actor_controller", 2, "request==1 and received==1 and accepted==1"),
            ("roll_sync", 4, "atSpeed==1 and closeCmd==1 and relay==1"),
            ("delivery", 5, "closeCmd==1 and contact==1 and running==1"),
            ("plant", 6, "safe==1 and service==1"),
            ("observation", 7, "credible==1"),
            ("end_to_end", 7, POST),
        )
        obligations = [_obligation(name, stages[:n], initial, expr(post)) for name, n, post in contracts]
        obligations.append(_obligation("execution_witness", stages, initial, expr(POST), True))
        name = ID
    else:
        obligations = [_obligation("violation", stages, initial, "!" + expr(POST), True)]
        name = f"merwin-mer{index}-violation"
    return Profile(
        name, tuple(obligations), len(proc.required_dependencies), 4, "1296 mandatory 100 ms scans (129.6 s)"
    )


DEEP = (0, 6, 7, 8, 10)


def profiles():
    return tuple(profile(i) for i in DEEP)


def _all(states, key):
    return bool(states) and all(s[key] == 1 for s in states)


def _report(index, reduction_ok):
    proc, initial, stages = model(index)
    states = executions(stages, initial)
    # The PLC sees a speed indication. B3 conditions its close sequence on
    # that indication and never executes the physical roll or breaker stages.
    feedback = Stage("controller_inputs", (
        A.nominal("rollSpeed", str(trajectory()[1]["speed_at_sync"])),
        A.nominal("atSpeed", "accepted"),
    ))
    controller_states = executions((*stages[:2], feedback, stages[3]), initial)
    statuses = {n.node_id: n.status for n in proc.required_dependencies.values()}
    unavailable = [k for k, s in statuses.items() if s is D.UNAVAILABLE]
    uncertain = [k for k, s in statuses.items() if s is D.UNKNOWN]
    end = next((s for s in states if not expr(POST, s)), None)
    exemplar = end if end is not None else states[0] if states else {}
    witness = {
        k: str(exemplar[k])
        for k in (
            "request",
            "accepted",
            "atSpeed",
            "relay",
            "closeCmd",
            "contact",
            "running",
            "mw1",
            "mw2",
            "mw3",
            "service",
            "credible",
            "clock",
        )
        if k in exemplar
    }
    if unavailable:
        outcome, reason = "REJECTED", "Required dependency unavailable: " + ", ".join(unavailable)
    elif not reduction_ok:
        outcome, reason = "UNKNOWN", "Missing or stale scan-reduction evidence"
    elif end is not None and uncertain:
        outcome, reason = "UNKNOWN", "A counterexample depends on unresolved " + ", ".join(uncertain)
    elif end is not None:
        outcome, reason = "REJECTED", "Concrete model execution violates " + ", ".join(
            k for k in ("accepted", "atSpeed", "closeCmd", "contact", "service", "credible") if not end[k]
        )
    elif index in (0, 3) and states and proved(profile(index)):
        outcome, reason = "PROVED", "All bound stage, universal, progress and scan-reduction checks passed"
    else:
        outcome, reason = "UNKNOWN", "No matching end-to-end proof and nonvacuity witness"

    def property_status(key):
        if not states or not reduction_ok:
            return "UNASSESSED"
        if outcome == "PROVED":
            return "PROVED"
        if _all(states, key):
            return "HOLDS_IN_ENUMERATION"
        return "POSSIBLE_VIOLATION" if uncertain else "VIOLATED"

    record = profile(index) if index in (*DEEP, 3) else None
    archive_status = "PROVED" if record and proved(record) else "UNASSESSED"
    return dict(
        scenario=f"MER{index}",
        procedure=ID,
        description=CASES[index].description,
        B1="DECLINE" if statuses["hydro_unit"] is D.UNAVAILABLE else "ACCEPT",
        B2="DECLINE" if unavailable else "UNRESOLVED" if uncertain else "ACCEPT",
        B3="ACCEPT" if _all(controller_states, "closeCmd") else "DECLINE",
        B4=outcome,
        safety=property_status("safe"),
        service=property_status("service"),
        observation=property_status("credible"),
        reason=reason,
        execution=witness,
        formal_model_hash=(
            record.sha256
            if record
            else object_hash([initial, [a.relation() for s in stages for a in s.assignments]])
        ),
        archive_status=archive_status,
        proof_profile=record.name if record else None,
        dependency_states={k: v.value for k, v in statuses.items()},
    )


def reports():
    f = trajectory()[1]
    ok = checked_reduction()
    rows = [_report(i, ok) for i in range(len(CASES))]
    positives = profile(0)
    return {
        "merwin_proof_summary": {
            "selected_mode": "HCC Remote Auto",
            "procedure_id": ID,
            "profile": positives.name,
            "formal_model_hash": positives.sha256,
            "proof_profile_hash": positives.profile_hash,
            "result": rows[0]["B4"],
            "trace_conditioned_reduction": f,
            "reduction_verified": ok,
            "reduction_input_sha256": digest(FIXTURE.read_bytes()),
            "numerical_certificate": json.loads(RECORD.read_text()) if RECORD.is_file() else None,
            "proof": read_record(positives),
            "modes": [p.procedure_id for p in candidates(CASES[0])],
            "boundary": "The fixed hydraulic pressure, gate-command and synchronization-telemetry trajectory, zero-order hold and integer precision are research assumptions. No as-built or unconditioned startup guarantee.",
        },
        "merwin_mutations": {"rows": rows},
        "merwin_reuse": {
            "schema": "RecoveryProcedure and the four historical procedure schemas with one incident-scoped node registry",
            "shared_unchanged": [
                "DependencyNode",
                "dependency_semantics.transition",
                "formal_ir.Assignment",
                "formal_ir.Stage",
                "formal_ir.executions",
                "formal_ir.hybrid_program",
                "verify._solve",
            ],
            "common_functional_boundaries": ["actor", "controller", "delivery", "plant", "observer"],
            "common_boundary_count": 5,
            "hydro_specific_boundaries": ["off-grid rolling and settlement", "synchronization"],
            "case_specific": [
                "HCC auxiliary/mode guard",
                "synchronizer and relay comparisons",
                "contact",
                "gated rotor, torque and three-sample MW conversion",
            ],
            "numerical_reduction": "Trace-conditioned fixed-point specializer with independent Z3 ground arithmetic checks",
            "tactic": "Same finite dL prefix/composition and reachability tactic as Attleboro",
            "mutations": "Regenerate typed node relations or initial values. The contract and proof tactic are unchanged for the violation queries.",
            "procedures": [p.as_dict() for p in candidates(CASES[0])],
        },
    }
