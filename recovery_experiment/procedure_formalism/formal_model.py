"""Bounded water procedure. The executor and proof archive consume the same IR."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json

from .attleboro import HAND_ID, PLANT_MODEL, REMOTE_ID, SOURCE_VERSION
from .dependency_semantics import transition
from .formal_ir import Assignment as A, Stage, executions, expr, hybrid_program
from .procedure import DependencyStatus, RecoveryProcedure


GENERATOR = "finite-procedure-dl-v1"
THREAT = "persistent-boolean-stage-and-finite-meter-v1"
SCANS = 3
# Initial slots are separate from all generated post-state variables.
INPUTS = {
    "utility": "utility", "genMode": "mts_generator", "genRun": "generator_running",
    "genReady": "generator_ready", "resetPending": "reset_pending",
    "resetReq": "reset_request", "prevReset": "previous_reset",
    "remote": "remote_selected", "hand": "hand_selected", "tripInput": "trip",
    "ph": "ph_out_of_range", "blockedInput": "flow_blocked",
    "healthy": "observation_fresh", "authorized": "authorized", "qInit": "initial_flow",
}
POST = ("safe==1 and t<=deadline and t==ready+3 and run==1 and physical==1 "
        "and established==1 and q>=5 and pressure<=90 and trusted==1 and fresh==1 "
        "and observed==q and observedPressure==pressure")
STAGE_PROPERTIES = {
    "actor": "request==1 and received==1 and ready<=deadline",
    "controller": "accepted==1 and output==1",
    "delivery": "output==1 and delivered==1",
    "plant": "run==1 and t==ready+3 and safe==1 and physical==1 and q>=5",
    "observer": "trusted==1 and fresh==1 and observed==q and observedPressure==pressure and established==1",
}


def _hash(data):
    return sha256(data.encode()).hexdigest()


def _safe(q, pressure):
    return f"{q}>=0 and {q}<=10 and {pressure}>=30 and {pressure}<=90 and trip==0 and ph==0"


def _plant():
    """Exactly three samples, including the first powered scan without run feedback."""
    ops = [A.indicator("effective", "drive==1 and pumpOK==1 and power==1 and trip==0"),
           A.nominal("pInit", "30+3*qInit"), A.indicator("safeInit", _safe("qInit", "pInit"))]
    previous, earlier_safe, prior_clock = "qInit", "safeInit", "ready"
    for scan in range(1, SCANS + 1):
        # A persistent command/power sample and initially stopped pump specialize
        # the saturating two-scan counter exactly to 0, effective, effective.
        run = f"run{scan}"
        raw, flow, pressure = f"raw{scan}", f"flow{scan}", f"p{scan}"
        safe, target, clock = f"safe{scan}", f"target{scan}", f"tick{scan}"
        ops.extend((
            A.nominal(run, "0" if scan == 1 else "effective"),
            A.conditional(target, f"{run}==1 and blocked==0", "10", "0"),
            A.nominal(raw, f"{previous}+(2/5)*({target}-{previous})"),
            A.conditional(flow, f"{raw}<1/100", "0", raw),
            A.nominal(pressure, f"30+3*{flow}"),
            A.indicator(safe, f"{earlier_safe}==1 and " + _safe(flow, pressure)),
            A.nominal(clock, f"{prior_clock}+1"),
        ))
        previous, earlier_safe, prior_clock = flow, safe, clock
    ops.extend((A.nominal("q", previous), A.nominal("pressure", pressure),
                A.nominal("run", run), A.nominal("safe", earlier_safe), A.nominal("t", clock),
                A.indicator("physical", "q>=5 and pressure<=90 and trip==0 and ph==0")))
    return ops


def retained_start():
    """Three surrogate PLC scans, including a released pulse and feedback lag."""
    ops = [A("eligible", ((None, "0"), (None, "1"))),
           A("secondFeedback", ((None, "0"), (None, "1")))]
    pending, sealed, wait = "0", "0", "0"
    for i, (edge, fb) in enumerate((("1", "0"), ("0", "0"), ("0", "secondFeedback")), 1):
        # Rising Start initializes retained demand before processing feedback.
        pre, seal_pre, age = f"pre{i}", f"sealPre{i}", f"age{i}"
        new_pending, new_seal, new_wait = f"pend{i}", f"seal{i}", f"wait{i}"
        ops.extend((
            A.conditional(pre, f"{edge}==1", "1", pending),
            A.conditional(seal_pre, f"{edge}==1", "0", sealed),
            A.conditional(age, f"{edge}==1", "0", wait),
            A.conditional(new_wait, f"eligible==1 and {fb}==0 and {seal_pre}==0 and {pre}==1",
                          f"{age}+1", "0"),
            A.indicator(new_pending, f"eligible==1 and {fb}==0 and {pre}==1 and {new_wait}<50"),
            A.indicator(new_seal, f"eligible==1 and {fb}==1 and ({pre}==1 or {seal_pre}==1)"),
            A.indicator(f"out{i}", f"eligible==1 and ({new_pending}==1 or {new_seal}==1)"),
        ))
        pending, sealed, wait = new_pending, new_seal, new_wait
    return ops


@dataclass(frozen=True)
class FormalModel:
    procedure: RecoveryProcedure
    initial: dict
    stages: tuple[Stage, ...]

    def executions(self):
        return executions(self.stages, self.initial)

    @property
    def sha256(self):
        return _hash(self.archive())

    def title(self, name):
        binding = json.dumps(self.procedure.as_dict(), sort_keys=True, separators=(",", ":"))
        return f"{self.procedure.procedure_id}_{_hash(binding)[:16]}_{name}"

    def archive(self, *, violation=False):
        p = self.procedure
        binding = json.dumps(p.as_dict(), sort_keys=True, separators=(",", ":"))
        header = (f"/* Procedure {p.procedure_id} | dependency model {_hash(binding)}\n"
                  f"   Plant {PLANT_MODEL} | threat {THREAT}\n"
                  f"   Source tree {SOURCE_VERSION} | generator {GENERATOR} */\n\n")
        return header + "\n".join(self.entries(violation).values())

    def entries(self, violation=False):
        initial = self.initial
        gamma = " & ".join(f"{key}={value}" for key, value in initial.items())
        all_ops = []
        entries = {}

        def entry(name, formula, slots, tactic):
            declared = " ".join(f"Real {key};" for key in sorted(set(slots)))
            return (f'ArchiveEntry "{self.title(name)}"\nProgramVariables\n  {declared}\nEnd.\n'
                    f'Problem\n  {formula}\nEnd.\nTactic "Finite stage proof"\n  {tactic}\nEnd.\nEnd.\n')

        def modal(name, ops, post, diamond=False):
            op, cl = ("<", ">") if diamond else ("[", "]")
            program = hybrid_program(ops)
            formula = f"({gamma}) -> {op}\n    {program}\n  {cl} ({post})"
            slots = [*initial, *(a.name for a in ops)]
            entries[name] = entry(name, formula, slots, "implyR(1); chase(1); QE")

        for stage in self.stages:
            all_ops.extend(stage.assignments)
            if not violation:
                modal(f"stage_{stage.name}", list(all_ops), expr(STAGE_PROPERTIES[stage.name]))
        if violation:
            modal("violation", all_ops, "!" + expr(POST), True)
        else:
            modal("end_to_end", all_ops, expr(POST))
            modal("execution_witness", all_ops, expr(POST), True)
            if self.procedure.procedure_id == REMOTE_ID:
                ops = retained_start()
                relation = hybrid_program(ops)
                conclusion = expr("out1==eligible and out2==eligible and out3==eligible")
                entries["retained_start"] = entry("retained_start", f"[{relation}] ({conclusion})",
                                                  (op.name for op in ops), "chase(1); QE")
            # An unconditional witness supplies a valuation of every assumption.
            setup = " ".join(f"{name}:={value};" for name, value in initial.items())
            entries["precondition_witness"] = entry(
                "precondition_witness", f"<{setup}>({gamma})", initial, "chase(1); QE")
        return entries


def _number(value):
    return Fraction(int(value)) if isinstance(value, bool) else Fraction(str(value))


def build_model(proc):
    if proc.procedure_id not in (REMOTE_ID, HAND_ID):
        raise ValueError("bounded water proof requires a Remote or Hand procedure")
    if proc.plant_model != PLANT_MODEL:
        raise ValueError("unsupported water plant model")
    deps = proc.required_dependencies
    initial = {key: _number(proc.initial_state[field]) for key, field in INPUTS.items()}
    initial.update(ready=Fraction(str(proc.actor_ready_time)), deadline=Fraction(str(proc.deadline)))
    remote = proc.procedure_id == REMOTE_ID

    def output(node, name, value):
        return transition(deps[node], A.nominal(name, value))

    actor = [output(proc.actor, "request", "authorized")]
    if remote:
        actor.extend([output("ows", "displayRequest", "request"),
                      output("communication", "received", "displayRequest")])
    else:
        actor.append(output("hand_panel", "received", "request"))
    ctrl = [transition(deps["trip_path"], A.indicator("trip", "tripInput==1 or ph==1"))]
    if remote:
        ctrl.extend((
            A.indicator("badPower", "utility==0 or genMode==1 or genRun==1"),
            A.indicator("pending", "badPower==1 or (resetPending==1 and (resetReq==0 or prevReset==1))"),
            A.indicator("accepted", "received==1 and badPower==0 and pending==0 and remote==1 and trip==0"),
            output("plc", "output", "accepted"),
        ))
        delivery = [output("delivery", "delivered", "output")]
    else:
        ctrl.extend((A.indicator("accepted", "received==1 and hand==1 and remote==0"),
                     A.nominal("output", "accepted")))
        delivery = [A.nominal("delivered", "output")]

    panel = "remote==1 and hand==0" if remote else "hand==1 and remote==0"
    plant = [
        transition(deps["motor_power"], A.indicator("power", "(genMode==1 and genReady==1) or (genMode==0 and utility==1)")),
        transition(deps["vfd"], A.indicator("drive", f"delivered==1 and {panel}")),
        output("pump", "pumpOK", "1"), output("water_path", "blocked", "blockedInput"),
        *_plant(),
    ]
    obs = deps["observer"]
    # A single trust choice governs both readings. Unknown chooses either the
    # complete nominal relation or the complete adversarial relation.
    trusted = transition(obs, A.nominal("trusted", "1"), ("0",))
    observer = [trusted, A.nominal("fresh", "healthy")]
    for name, actual, alphabet in (("observed", "q", ("0", "10")),
                                   ("observedPressure", "pressure", ("30", "90"))):
        # At the final sample a stale flow channel retains its initially zero
        # reading. The research pressure channel remains sampled independently.
        nominal = "q" if name == "observed" else actual
        operator = A.conditional(name, "fresh==1", nominal, "0") if name == "observed" else A.nominal(name, nominal)
        if obs.status is DependencyStatus.TRUSTED:
            observer.append(operator)
        else:
            branches = []
            for guard, value in operator.alternatives:
                condition = "trusted==1"
                if guard:
                    condition += " and " + ("fresh==0" if guard.startswith("!") else guard)
                branches.append((condition, value))
            branches.extend(("trusted==0", value) for value in alphabet)
            observer.append(A(name, tuple(branches)))
    observer.append(A.indicator("established", "trusted==1 and fresh==1 and physical==1 and observed==q and observedPressure==pressure and observed>=5 and observedPressure<=90"))
    return FormalModel(proc, initial, tuple(Stage(name, tuple(ops)) for name, ops in
                       zip(STAGE_PROPERTIES, (actor, ctrl, delivery, plant, observer))))
