# Timed Fixed-Takeover Contract

This is the versioned contract for `timed_recovery_takeover.envelope`. It does
not replace the original `recovery_takeover.envelope` baseline.

## Plant and authority

The synthetic plant is `T1 -> {P1, P2} -> T2`. The level-equivalent flow rates
have units of tank-level per second:

```text
x1' = qin - q1 - q2
x2' = q1 + q2 - qd
q1  = (1 - isolated) * p1 * qprimary
q2  = p2 * qbackup
```

The attacker chooses the binary primary command `p1`. The defender has a fixed
policy, not a choice among policies: immediately establish trusted isolation,
hold `qin=qd=0` while the backup starts, then enable P2 and set
`qin=qd=qbackup`. The isolation mechanism is an independent trusted actuator;
once `isolated=1`, the primary effective flow is zero even if the attacker sets
`p1=1`. The envelope assigns the resulting post-isolation value `q1:=0`; it does
not ask CLEO to re-expand that product expression in an arithmetic assignment.
The postcondition and both ODE profiles nevertheless state the corresponding
effective-flow equality `q1=(1-isolated)*p1*qprimary` (and `q2=p2*qbackup`).

## Concrete timed theorem

For the supplied baseline state and parameters:

```text
x1=7, x2=6, [L1,H1]=[4,11], [L2,H2]=[3,9]
qprimary=qbackup=qin_nominal=qd_nominal=1.5
qmin=1.2, StartupDelay=1.0 s, RecoveryDeadline=1.5 s
OperationDuration=T=0.5 s, isolation delay=0, budget=2
```

The startup ODE is Angel-duration-controlled because the fixed defender policy
waits exactly the configured startup interval. Its domain requires
`startupClock <= StartupDelay`; the ordinary Angel test
`startupClock >= StartupDelay` makes the selected duration exactly one second.
`recoveryClock` advances with the startup clock and must be no later than the
recovery deadline before P2 activation.

During startup, `q1=q2=qdelivered=0`; the service requirement is intentionally
not required. After startup, the policy reasserts isolation, activates P2, and
sets `q1=0`, `q2=qdelivered=qd=qbackup`. Thus the formal service predicate is
actual modeled delivery `qdelivered >= qmin`, not merely nominal capacity.

The policy must then execute one Angel-duration-controlled operating ODE with
`operationClock=T=0.5 s`. Its test requires `operationClock >= T`, so a zero
iteration or zero-time post-takeover execution cannot establish the postcondition.
The theorem is a fixed finite horizon of `StartupDelay + T = 1.5 s`; it makes no
claim about indefinite operation or all future cycles.

## Assumptions and scope

The theorem assumes immediate effective isolation, deterministic exact startup
duration, balanced steady flows, and no sensor/actuator failures outside the P1
command compromise. It covers only contexts admitted by the timed template.
The tank lower safety bounds must be nonnegative because both ODE domains
explicitly require nonnegative tank levels throughout the timed intervals.
Delayed isolation, variable startup availability, unbalanced flow, and a longer
recovery horizon are not declared unsafe; they are unsupported by this theorem.

## Simulator correspondence

The simulator applies the attacker command before the defender command, makes a
zero-delay isolator effective immediately, computes flows, integrates one
control interval, and only then advances delayed-transition clocks. With the
baseline `0.5 s` control period and `1.0 s` backup delay, it therefore produces
two zero-flow startup intervals `[0,0.5]` and `[0.5,1.0]`, followed by a balanced
backup-flow interval `[1.0,1.5]`. This is the same finite sequence represented
by the formal startup ODE followed by the mandatory operation ODE.

The explicit `qin=qd=0` startup mode is a modelled planned service interruption:
T1 and T2 are held constant because no water enters or leaves either tank. It is
not evidence that a physical process can tolerate zero external inflow or
demand. The simulator permits delayed isolation, unbalanced flow, other timing,
and longer horizons; the timed theorem does not cover those configurations.

## Verification record

Run the following with the CLEO-enabled interpreter:

```bash
"$CLEO_PYTHON" -m recovery_experiment.verify_timed_recovery \
  --context baseline_feasible \
  --output-dir recovery_experiment/results/timed-formal
```

The recorded baseline run completed in about `9.04 s` with status `VERIFIED`.
The emitted JSON records three discharged obligations: startup ODE `al`,
operation ODE `bb`, and top-level arithmetic obligation `a`.

* Milestone A: the exact `StartupDelay` zero-flow startup ODE preserves tank
  safety (`al`: passed).
* Milestone B: the postcondition requires `qdelivered >= qmin` and
  `recoveryClock <= RecoveryDeadline` (`a`: passed).
* Milestone C: the exact positive `T` backup-operation ODE preserves safety and
  delivery (`bb`: passed).
* Milestone D: all obligations of the complete finite game passed.

Each run writes the instantiated envelope and `timed_verification.json` to the
requested output directory. Those generated run artifacts are intentionally
ignored; the versioned source contract and proof profile are the reproducible
evidence in this directory.
