# State-Dependent Flowing Takeover Certificate

This separate versioned contract covers only the fixed
`trusted-flowing-backup-takeover-v1` policy for the synthetic
`state-dependent-two-tank-v1` topology. It does not replace the parameterized
controlled-hold theorem.

## Physical And Service Model

Tank levels and `q` values are synthetic **level-equivalent quantities**:
flows use level units per second, with tank area absorbed into their rates.

```text
x1' = qin - q1 - q2
x2' = q1 + q2 - qout
q1  = (1 - isolated) * p1 * qprimary
q2  = p2 * qbackup
```

The attacker controls P1 command `p1` throughout. `isolated` is an independent,
trusted physical isolation state, so later P1 commands cannot restore effective
transfer. P2 command and isolation independence are trusted assumptions, not
software properties proved by this model.

For the exact startup interval, P1 is isolated and P2 is inactive:

```text
q1 = q2 = 0
qin = startupInflow >= 0
demand = qout = startupWithdrawal >= qmin > 0
qdelivered = qout
```

`qout` is actual T2 withdrawal, controlled here to equal trusted demand, and
`qdelivered` is that withdrawal. T2 stored water can thus serve consumers during
startup even though neither pump transfers water. Delivery is not
`min(q1 + q2, demand)`; T2 safety bounds prevent drawing below the safe reserve.

After exactly `StartupDelay`, P2 is active with balanced flow:

```text
qin = demand = qout = q2 = qbackup
q1 = 0
```

Both tank derivatives are zero during the mandatory, exact positive operation
interval `T`. The startup duration is deterministic and exact: its ODE must
reach `startupClock = StartupDelay`, not merely a convenient shorter duration.

## Certified Region

For `S = StartupDelay`:

```text
x1(t) = x1_initial + startupInflow * t
x2(t) = x2_initial - startupWithdrawal * t,  0 <= t <= S
```

Because inflow is nonnegative and withdrawal is positive, the endpoint margins
are sufficient for every intermediate startup state:

```text
L1 <= x1_initial <= H1, L2 <= x2_initial <= H2, L1 >= 0, L2 >= 0
x1_initial + startupInflow * StartupDelay <= H1
x2_initial - startupWithdrawal * StartupDelay >= L2
startupInflow >= 0
startupWithdrawal >= qmin > 0
qprimary >= 0, qbackup >= qmin
0 < StartupDelay <= TransferDeadline, T > 0
qbackup = upstream_nominal = downstream_demand
isolationDelay = 0
interventionBudget >= isolationCost + backupCost >= 0
```

Service is continuous: `qdelivered=qout>=qmin` during startup and operation.
`TransferDeadline` instead bounds restoration of P2's **transfer path**. The
general simulator `service_deadline` is not silently substituted for this
theorem's transfer deadline.

The continuous theorem permits any positive exact startup duration satisfying
its timing bound. The runtime checker additionally requires that duration to be
an integer number of simulator control periods. This conservative trace-model
compatibility condition prevents the discrete simulator from delaying P2 to the
next control boundary beyond the certified continuous-time duration.

With defaults, `(x1,x2)=(7,6)` has T1 margin `11-(7+1*1)=3` and T2 margin
`(6-1.2*1)-3=1.8`. States `(10.5,6)` and `(7,4)` begin safe but fall outside
the certificate because one startup margin is negative.

## Proof And Certificate

`state_dependent_recovery_takeover.envelope`, rendered by
`state_dependent_formal.py`, has startup and operation ODE invariants in
`state_dependent_proof_profile.py`. The symbolic game gives the attacker a fresh
binary P1 choice before isolation and again before P2 activation. Isolation,
rather than missing attacker choices, blocks its physical effect.

The symbolic CLEO proof discharged startup ODE `aq`, operation ODE `bh`, and
top-level arithmetic `a`. All milestones A--E passed. The reviewed offline run
recorded in `state_dependent_certificate_manifest.json` took
`9.85577582300175` seconds; a fresh regression run took about `9.29` seconds.
A separately instantiated concrete proof for `(7,6)` discharged the same three
obligations in about `9.23` seconds. Runtime varies by host and backend startup.

`state_dependent_certificate.py` never runs CLEO. It validates the context,
checks the reviewed manifest and proof-artifact hashes, requires the new
plant/policy identities, and checks all state, flow, timing, authority, service,
and budget assumptions. `COVERED_BY_CERTIFICATE` means exactly this theorem
covers the fixed policy. `NOT_COVERED_BY_CERTIFICATE` does not say the plant is
globally unsafe or unrecoverable. `INVALID_CONTEXT`, `INCOMPATIBLE_CONTEXT`,
`UNTRUSTED_CERTIFICATE`, and `UNVERIFIED` retain their distinct meanings.

The controlled-hold and flowing-startup certificates intentionally reject each
other's policy/model identities.

## Evaluation And Reproduction

Evaluation records initial levels, startup flows/duration, backup capacity,
margins, certificate latency, traces, and existing finite-horizon cost:

```text
J = w_service * accumulated delivery shortfall
  + w_time * recovery establishment time
  + w_action * intervention cost
  + w_backup * integral(q2 dt)
```

Both policies share intervention-cost semantics but are not interchangeable:
controlled hold uses startup `qin=qout=0`; flowing takeover uses `qin=1.0`,
`qout=1.2` and needs the certified margins.

For the default, the `0.5 s` simulator grid records two startup intervals with
`q1=q2=0`, `qin=1.0`, and `qout=qdelivered=1.2`; P2 becomes effective at the
`1.0 s` boundary. That matches the formal event ordering and duration because
the grid divides the delay and isolation is immediate. The simulator is forward
Euler while the theorem is continuous ODE, so this is a consistency check, not
a numerical proof.

```bash
# From mitigation_synthesis with an interpreter that has CLEO, Z3, and KeYmaera X
"$CLEO_PYTHON" -m recovery_experiment.verify_state_dependent_recovery \
  --output-dir recovery_experiment/results/state-dependent-formal

"$CLEO_PYTHON" -m recovery_experiment.verify_state_dependent_context \
  --context safe_recoverable \
  --output-dir recovery_experiment/results/state-dependent-concrete

"$CLEO_PYTHON" -m recovery_experiment.state_dependent_evaluation --verify-concrete
python3 -m unittest discover -s recovery_experiment/tests -v
```

The evaluation includes the covered interior state, both margin failures,
inadequate backup capacity, and startup later than the transfer deadline.

## Limits

This is a finite, constant-flow synthetic two-tank model. It assumes exact
startup delay, immediate independently effective isolation, trusted actuator
authority, exact observations, continuous commanded withdrawal, balanced
post-takeover flow, and one finite operation interval. It does not prove a
hardware trust boundary, model sensing/actuation delay, pump curves/pressure,
source availability, delayed isolation, repeated or indefinite operation,
policy synthesis, or live-testbed integration.
