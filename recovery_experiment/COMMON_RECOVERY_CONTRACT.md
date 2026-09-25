# Common Six-Second Recovery Contract

This contract compares the two fixed **immediate-isolation** recovery policies.
It is an offline synthetic-model assurance artifact, not a claim about a
deployed process or a generic recovery synthesizer. The separately certified
delayed-isolation policy has different physical authority and timing
assumptions; its contract is [`DELAYED_ISOLATION_CONTRACT.md`](DELAYED_ISOLATION_CONTRACT.md)
and it is never cost-compared against an immediate-isolation incident.

## Physical Model And Authority

The common topology is `T1 -> {P1, P2} -> T2`. All flows are synthetic
level-equivalent rates, so the same equations are used in the simulator and the
formal games:

```text
x1' = qin - q1 - q2
x2' = q1 + q2 - qout
q1  = (1 - isolated) * p1 * qprimary
q2  = p2 * qbackup
qdelivered = qout
```

The default initial state is `(x1, x2) = (7, 6)`. Safety must hold throughout:
`4 <= x1 <= 11` and `3 <= x2 <= 9`. Default normal inflow, downstream
external demand, P1 capacity, and P2 capacity are each `1.5`; the minimum
acceptable delivered flow is `1.2`.

The attacker retains both `FORCE_PRIMARY_OFF` and `FORCE_PRIMARY_ON` actions on
the compromised `P1_command_path` for the full six-second trace. The recovery
model assumes independently trusted, immediately effective primary isolation,
the P2 command path, and the upstream and demand gates. Isolation is the reason
later P1 commands have no physical transfer effect; an in-memory rejection of
future attacker commands would not meet this contract.

The available trusted resource is `backup_capacity = 1.5`. The intervention
budget is `2.0`, which covers isolation cost `1.0` plus P2 activation cost
`1.0`. These are model-level resource assumptions, not hardware measurements.

## One Timing And Service Contract

The default shared evaluation interval is six seconds from recovery response
start. P2's exact startup delay is one second, the recovery deadline is 1.5
seconds, and the simulator control period is 0.5 seconds. The default request
therefore requires five seconds of post-takeover operation:

```text
startup duration S                 = 1.0 s
post-takeover operation T          = 6.0 - S = 5.0 s
total evaluation and formal horizon = S + T = 6.0 s
```

`IncidentServiceContract` binds the following facts for both policies:

```text
external_demand                 = 1.5
required_delivered_flow         = 1.2 by default
require_continuous_delivery     = policy-request dependent
permitted_interruption_duration = 0.0 s for continuous requests, 1.0 s otherwise
recovery_deadline               = 1.5 s
assured_operation_duration      = 5.0 s
evaluation_horizon              = 6.0 s
```

The terms intentionally differ:

* **External demand** is the downstream request, fixed at `1.5`; a policy never
  changes it by curtailing withdrawal.
* **Actual delivery** is modeled `qdelivered = qout`.
* **Minimum acceptable delivery** is the incident's `required_delivered_flow`.
* **Service shortfall** is `integral(max(0, external_demand - qdelivered) dt)`
  over the complete six-second horizon.

Thus satisfying the `1.2` minimum does not mean satisfying the full `1.5`
external demand. A requested post-takeover duration longer than `T` is rejected
as incompatible with this finite evaluation contract.

## Formal Horizon

The canonical symbolic envelopes are unchanged. Each has two sequential ODEs:
an exact startup phase and one mandatory operation phase with symbolic `T > 0`.
The installed CLEO implementation represents repetition with `*`; it permits a
zero iteration for an angelic loop. Neither recovery theorem contains `*`.
`^@` in these games dualizes an attacker choice or ODE; it is not a repetition
operator. The ordinary timing tests after each ODE force the selected phase to
reach its bound, so `S` and `T` are not optional zero-duration phases.

For this contract, the existing symbolic theorem is instantiated with `T = 5`.
The resulting assurance is finite and exactly six seconds, not indefinite
operation. `common_horizon.py` performs that binding, and
`verify_common_horizon.py` reuses the unchanged canonical games and proof
profiles to check the baseline concrete instantiations.

| Policy | Formal startup | Formal post-takeover operation | Formal total horizon |
| --- | ---: | ---: | ---: |
| Controlled hold | 1.0 s | 5.0 s | 6.0 s |
| Flowing takeover | 1.0 s | 5.0 s | 6.0 s |

The common-horizon verifier is an additional offline regression check. Runtime
selection still uses each policy's own reviewed manifest plus numeric coverage
conditions; it never invokes CLEO. An altered or untrusted manifest remains
non-authorizing.

## Policy Service Properties

**Controlled hold.** The trusted isolator blocks P1, and both `qin` and `qout`
are zero for exactly the one-second P2 startup interval. Hence actual delivery
is zero and the delivery interruption is exactly one second. After P2 activates,
the theorem establishes `qdelivered = q2 = qbackup >= qmin` for five seconds.
It is admissible only when the incident permits at least that one-second
interruption. It cannot satisfy an uninterrupted positive-delivery request.
With the defaults, its six-second external-demand shortfall is `1.5 * 1 = 1.5`.

**Flowing takeover.** During startup, `qin = 1.0`, `qout = qdelivered = 1.2`,
and `q1 = q2 = 0`; T2 storage supplies the actual delivery. The state-dependent
startup margins establish safety for that exact interval. After activation,
`qin = qout = qdelivered = q2 = 1.5` for five seconds. Therefore it meets a
continuous minimum-flow request up to `1.2`, but not continuous full external
demand of `1.5` during startup. Its default shortfall is `(1.5 - 1.2) * 1 =
0.3`. It applies only when the T1 overflow and T2 depletion margins are within
the state-dependent certificate region.

No result with neither candidate admitted says that recovery is impossible; it
says only that these two fixed policies do not establish the requested contract.

## Cost And Evaluation Meaning

The selector uses one context, one six-second horizon, one external demand, and
one `RecoveryCostParameters` value for both candidates:

```text
J = w_service * service_loss
  + w_time * recovery_duration
  + w_intervention * intervention_cost
  + w_resource * backup_usage
```

For the default weights `(10, 1, 2, 0.5)`, both candidates have one-second
recovery duration, intervention cost `2`, and five-second backup use `7.5`.
The deterministic simulated values are `J = 23.75` for controlled hold and
`J = 11.75` for flowing takeover. The latter wins only among the two certified,
service-admissible candidates.

`cost_interpretation.estimated_before_selection` is the candidate's
counterfactual cost estimate used for comparison. It is computed from the same
completed deterministic simulator trace exposed as
`observed_from_completed_simulation`. Neither is a physical observation nor a
formally proved cost bound. The selector does not claim global optimality.

## Reproduction

Run from `mitigation_synthesis`:

```bash
# Offline formal check; CLEO, Z3, and KeYmaera X are required.
"$CLEO_PYTHON" -m recovery_experiment.verify_common_horizon \
  --output-dir recovery_experiment/results/common-horizon-formal

# Offline deterministic selection and trace-derived cost comparison.
python3 -m recovery_experiment.recovery_selection_evaluation \
  --output recovery_experiment/results/recovery-selection-evaluation.json

python3 -m unittest discover -s recovery_experiment/tests -v
```

The selection evaluation includes: both candidates with permitted interruption,
an uninterrupted `1.2` request, an uninterrupted full-demand `1.5` request, a
state-margin case where flowing takeover is outside its certificate, and cases
where neither candidate is authorized. It reports certificate status, requested
contract, candidate theorem horizon, trace data, cost interpretation, and the
reason for every rejection.
