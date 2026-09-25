# Trace-Driven Recovery Experiment

This directory is a self-contained, synthetic Dr.ICS recovery experiment. It is
not a SWaT model, a deployed industrial controller, or a claim that the
repository has live testbed access. It preserves the repository's original
`../attack.envelope` and `../water_attack.py` as the Phase-1 regression baseline.

## Plant and assumptions

The topology is `T1 -> {P1, P2} -> T2`: P1 and P2 are parallel paths that move
water from upstream tank T1 to downstream tank T2. P1 is the compromised primary
command path. P2, the isolator, and two flow gates are fixed modeled components,
but their operational, trusted, and recovery-controllable status is an explicit
incident input. A trusted physical isolator blocks the P1 path, rather than
merely overwriting the attacker-controlled P1 command.

All `q` values are **synthetic tank-level-equivalent rates** (level units per
second); tank area has been absorbed into the rates. The dynamics are:

```text
x1' = q_in - q1 - q2
x2' = q1 + q2 - q_out
q1  = (not isolated and P1 command) ? primary_capacity : 0
q2  = (P2 effective) ? backup_capacity : 0
```

`q_demand` is the trusted requested downstream service, while `q_out` is the
physical withdrawal from T2. The simulator sets `q_out=q_demand` and
`q_delivered=q_out`, so stored T2 water can serve consumers during startup even
when instantaneous pump transfer is zero. Historic controlled-hold artifacts
instead deliberately set both inflow and withdrawal to zero during startup.

Default synthetic parameters are `x1=7`, `x2=6`, T1 bounds `[4, 11]`, T2 bounds
`[3, 9]`, normal inflow/demand `1.5`, backup capacity `1.5`, a `1.0 s` backup
startup delay, immediate trusted isolation, a `0.5 s` control period, and a
`1.5 s` service deadline. They are illustrative, not measured values.

Safety requires both tank levels to remain in their bounds throughout the
scenario. The historic controlled-hold service contract permits a startup
interruption, but requires `q_delivered >= q_min` at and after its deadline.
The state-dependent flowing policy requires delivery throughout startup and
uses a separate transfer-path deadline. A successful simulation is only a
trace; it is not a theorem.

## Threat and recovery policies

At every control cycle the scripted attacker may force the P1 command on or off.
The standard trace forces it off for the entire horizon. Attacker action comes
before defender action. The defender then uses one of these scripted policies:

* `conservative_recovery`: closes the trusted upstream and demand gates. Levels
  remain safe in this model, but delivery is zero after the service deadline.
* `trusted_backup_takeover`: commands the trusted isolator and P2, holds upstream
  flow and demand at zero while P2 starts, then resumes balanced flow through P2.
* `trusted_flowing_backup_takeover`: commands the same trusted isolator and P2,
  while keeping configured inflow and T2 withdrawal active during startup. It
  needs the separate state-dependent certificate and sufficient level margins.
* `trusted_controlled_safe_hold`: immediately uses independent P1 isolation and
  trusted upstream/demand gates to hold both tank levels while intentionally
  curtailing delivery for the configured finite horizon. It does not use P2.

The simulator's exact per-interval order is recorded in each JSON trace:
observe, attacker, defender, zero-delay trusted transition, flow calculation,
forward-Euler evolution, monitoring, then delayed-transition clock advance.
Delayed transitions become effective at the next control boundary. This is why
the default `1.0 s` P2 startup is not silently instantaneous.

## Context and costs

`context.py` defines the typed `RecoveryContext`. It separates current runtime
state from plant configuration, names the attack surface and trusted actuators,
and records physical component existence separately from operational, trusted,
and recovery-controllable control paths. Final template availability is explicit
per incident and has no default. Unknown components, inconsistent authority,
capacity inconsistencies, invalid state, and mismatched timing are rejected.

The finite-horizon cost is:

```text
J = w_service * accumulated delivery shortfall
  + w_time    * time to recovery establishment
  + w_action  * intervention cost
  + w_backup  * integral(q2 dt)
```

All terms use the same trace horizon. The temporary service shortfall contributes
to cost even before the hard service deadline. Safety and the mandatory service
contract are hard admissibility conditions: costs select only strategies with an
actual `VERIFIED` formal result and qualifying trace outcome.

## Formal model and proof scope

The original `formal.py` and `recovery_takeover.envelope` are preserved as the
historical recovery baseline and its recorded proof evidence. The current,
non-vacuous fixed-policy theorem is versioned separately in
`timed_formal.py`, `timed_proof_profile.py`, and
`timed_recovery_takeover.envelope`. Its exact mathematical contract is in
[`TIMED_CONTRACT.md`](TIMED_CONTRACT.md).

The separately versioned offline theorem is in
`parameterized_formal.py`, `parameterized_proof_profile.py`, and
`parameterized_recovery_takeover.envelope`. It proves the same fixed policy for
all initial tank levels in the closed safe region and for symbolic capacity,
timing, and budget values that satisfy its precondition. Its certificate scope
and trust boundary are documented in
[`PARAMETERIZED_CONTRACT.md`](PARAMETERIZED_CONTRACT.md).

The state-dependent flowing-startup theorem is independently versioned in
`state_dependent_formal.py`, `state_dependent_proof_profile.py`, and
`state_dependent_recovery_takeover.envelope`. It keeps `qin` and `qout` nonzero
during startup, requires runtime T1/T2 margins, and establishes continuous
stored-water delivery while P2 restores the transfer path. Its full contract,
certificate boundary, evaluation, and limitations are in
[`STATE_DEPENDENT_CONTRACT.md`](STATE_DEPENDENT_CONTRACT.md).

`recovery_selection.py` compares only the fixed certificates compatible with one
policy-neutral incident and service contract. Immediate incidents consider the
two immediate-isolation policies; a positive-delay incident is considered only
when a matching delayed-isolation certificate exists. It keeps external demand separate from policy-controlled
withdrawal, admits a policy only when its own certificate establishes the
requested service/timing contract, and compares trace-derived costs only among
admissible candidates. It does not run CLEO, synthesize a strategy, or issue
commands. See
[`RECOVERY_SELECTION_CONTRACT.md`](RECOVERY_SELECTION_CONTRACT.md).
The common finite six-second timing, service, certificate, and cost contract is
documented in [`COMMON_RECOVERY_CONTRACT.md`](COMMON_RECOVERY_CONTRACT.md).

Resource-aware construction is documented in
[`RESOURCE_AWARE_RECOVERY_CONTRACT.md`](RESOURCE_AWARE_RECOVERY_CONTRACT.md).
It has exactly two templates: the existing bounded flowing P2 takeover and a
separate immediate-isolation controlled safe hold. The latter preserves safety
with positive external demand but zero actual delivery, so it can be
certificate-covered and still fail a requested positive-service contract.

The incident-dependent delayed-isolation model is independently versioned in
`delayed_isolation_formal.py`, `delayed_isolation_proof_profile.py`, and
`delayed_isolation_recovery_takeover.envelope`. It gives the attacker two
explicit effective P1 control periods before trusted isolation takes effect,
while P2 starts concurrently. Its safety conditions, simulator correspondence,
construction interface, verified symbolic proof, reviewed local certificate,
evaluation, and trust boundary are in
[`DELAYED_ISOLATION_CONTRACT.md`](DELAYED_ISOLATION_CONTRACT.md). Positive-delay
incidents are authorized only through this matching certificate; they never use
an immediate-isolation certificate.

`recovery_model_builder.py` is the small typed incident-to-formal-problem
builder for this same two-tank, parallel-pump family. It reconstructs the
canonical immediate and two-control-period delayed games only when the rendered
structure exactly matches their reviewed artifacts. It also constructs bounded
integer schedules `IsolationDelay=n*ControlPeriod` and
`StartupDelay=m*ControlPeriod`, with `n >= 0` and `m > n`. The generated
one-period `1T/3T` theorem now has a separate reviewed local provenance manifest
and certificate checker. Other generated schedules remain unauthorized even
after a successful offline CLEO run until their own review occurs. The lifecycle,
margin derivation, and exact timing rules are in
[`BOUNDED_SCHEDULE_CONTRACT.md`](BOUNDED_SCHEDULE_CONTRACT.md).

The timed game gives the attacker a fresh binary `p1` command before isolation
and again before backup activation. It gives the defender an ordinary,
Angel-controlled startup ODE of exactly `StartupDelay`, followed by one ordinary
Angel-controlled ODE of exactly `T > 0`. The timing tests are outside a dual:
in this CLEO version an ordinary test is a strict conjunction with its successor,
whereas a dualized test is translated as `test OR successor`. This avoids relying
on a dualized test as a timing guard. There is no `*` loop, so zero post-takeover
iterations cannot satisfy the timed theorem.

For the concrete baseline, the defender immediately establishes independent
trusted isolation, holds `qin=qd=0` for exactly one second while P2 starts, then
sets `qin=qd=qbackup`, activates P2, and runs the plant for exactly `T=0.5 s`.
The postcondition requires actual modeled delivery
`qdelivered=q2=qd >= qmin`, recovery no later than `RecoveryDeadline`, safe tank
levels, and a nonnegative intervention budget. Service is permitted to be zero
during startup only. This is a fixed finite `1.5 s` recovery horizon, not a claim
of indefinite operation, optimal synthesis, a parameterized proof, delayed
isolation assurance, or a deployment guarantee.

The timed template supports immediate effective trusted isolation, a deterministic
exact startup duration, nonnegative tank lower bounds, balanced nominal inflow
and demand, and backup capacity equal to that nominal flow. The simulator can
explore other configurations, but they are reported as `UNSUPPORTED_TEMPLATE`,
`REJECTED_CAPACITY`, or `REJECTED_DEADLINE` as appropriate, never as a global
claim that no safe recovery exists. Conservative hold remains explicitly
`REJECTED_SERVICE` for this takeover experiment when `q_min` is positive.

## Run it

Run all commands from the repository root (`mitigation_synthesis`). Python 3.10+
and the standard library are enough for simulation and tests.

```bash
python3 -m recovery_experiment.run_experiment --seed 7 --suite
python3 -m unittest discover -s recovery_experiment/tests -v
```

The first command writes JSON (metadata plus records) and CSV traces, plus a
comparison report, below `recovery_experiment/results/`. Outputs include the
fixed seed, parameters, full validated context, event ordering, and numerical
method. Re-running with the same seed and configuration produces the same data.

Formal verification needs a Python interpreter with the existing CLEO package,
which in turn uses Z3 for arithmetic obligations and KeYmaera X for hybrid-system
obligations. Set `CLEO_PYTHON` to that interpreter; this avoids embedding a
machine-specific installation path:

```bash
export CLEO_PYTHON=/path/to/cleo-python
"$CLEO_PYTHON" -m recovery_experiment.verify_recovery \
  --context baseline_feasible \
  --output-dir recovery_experiment/results/formal

"$CLEO_PYTHON" -m recovery_experiment.verify_timed_recovery \
  --context baseline_feasible \
  --output-dir recovery_experiment/results/timed-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_parameterized_recovery \
  --output-dir recovery_experiment/results/parameterized-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_state_dependent_recovery \
  --output-dir recovery_experiment/results/state-dependent-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_state_dependent_context \
  --context safe_recoverable \
  --output-dir recovery_experiment/results/state-dependent-concrete

"$CLEO_PYTHON" -m recovery_experiment.verify_delayed_isolation_recovery \
  --output-dir recovery_experiment/results/delayed-isolation-formal

python3 -m recovery_experiment.delayed_isolation_evaluation \
  --output recovery_experiment/results/delayed-isolation-evaluation.json

python3 -m recovery_experiment.recovery_model_builder_evaluation \
  --output recovery_experiment/results/recovery-model-builder-evaluation.json

"$CLEO_PYTHON" -m recovery_experiment.verify_intermediate_delay_recovery \
  --output-dir recovery_experiment/results/intermediate-delay-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_bounded_delay_recovery \
  --isolation-periods 3 --startup-periods 4 \
  --output-dir recovery_experiment/results/bounded-3t4-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_bounded_delay_recovery \
  --isolation-periods 3 --startup-periods 5 \
  --output-dir recovery_experiment/results/bounded-3t5-formal

python3 -m recovery_experiment.bounded_schedule_evaluation \
  --output recovery_experiment/results/bounded-schedule-evaluation.json

python3 -m recovery_experiment.certificate_evaluation --verify-concrete
"$CLEO_PYTHON" -m recovery_experiment.state_dependent_evaluation --verify-concrete

python3 -m recovery_experiment.recovery_selection_evaluation

"$CLEO_PYTHON" -m recovery_experiment.verify_controlled_safe_hold \
  --output-dir recovery_experiment/proof_records/controlled_safe_hold

python3 -m recovery_experiment.resource_aware_evaluation \
  --output recovery_experiment/results/resource-aware-recovery-evaluation.json

"$CLEO_PYTHON" -m recovery_experiment.run_experiment \
  --seed 7 --suite --verify
```

Each standalone verification runner parses its generated envelope, creates an
`EnvelopeSession`, discovers required annotations, attaches the matching proof
profile, runs CLEO, and writes obligations, status, and elapsed time. Statuses
are strict: `VERIFIED` only after all obligations pass; `UNVERIFIED` for parser,
backend, timeout, or unresolved obligations; `INVALID_CONTEXT` for malformed
input; `UNSUPPORTED_TEMPLATE` for an unmodeled configuration; and
`REJECTED_CAPACITY`, `REJECTED_DEADLINE`, or `REJECTED_SERVICE` only for the
corresponding deterministic gate. `NO_VERIFIED_SERVICE_CANDIDATE` means only
that none of the policies actually evaluated qualified for execution.

## Assurance workflows

Two distinct workflows are implemented. Concrete verification validates and
instantiates an observed `RecoveryContext`, then invokes CLEO. Offline-prepared
assurance instead uses the separately `VERIFIED` parameterized theorem and a
runtime certificate check. The check validates the context, confirms reviewed
manifest and proof-artifact digests, checks plant/policy identity, then checks
the theorem's state, timing, flow, capacity, trust, and budget assumptions. It
does not invoke CLEO or issue physical commands.

`COVERED_BY_CERTIFICATE` authorizes only the fixed synthetic takeover policy
under the proved theorem. `NOT_COVERED_BY_CERTIFICATE` is not a safety violation
or a global infeasibility claim. `INVALID_CONTEXT`, `INCOMPATIBLE_CONTEXT`, and
`UNTRUSTED_CERTIFICATE` identify malformed context, model/policy mismatch, and
manifest/artifact trust failures respectively; `UNVERIFIED` denotes a trusted
manifest that does not record a verified theorem. The manifest digest is a reviewed
trust anchor; runtime checking detects drift but does not independently reprove
the KeYmaera X result.

## Controlled contexts and limits

`scenarios.py` provides five deterministic contexts: a feasible baseline,
insufficient P2 capacity, startup later than the service deadline, conservative
safe-but-service-losing behavior, and a case where neither current candidate is
verified. Results always keep simulation and formal outcome fields separate.

Next work should formalize repeated operating horizons and additional delayed
timing families, expand the certified assumptions beyond balanced flow, add additional
attack and plant classes, and then connect a separately validated incident
interpreter. No LLM, SPHERE connector, testbed reset, or live actuation is
implemented here.
