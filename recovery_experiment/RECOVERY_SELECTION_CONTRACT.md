# Certificate-Based Recovery Selection

This module selects only among pre-existing, offline-verified policies compatible
with one synthetic two-tank incident. It is not a strategy synthesizer, does not
run CLEO at selection time, and does not actuate a plant.

## Common Incident And Service Model

`RecoveryIncident` contains one policy-neutral `RecoveryContext` and one common
`IncidentServiceContract`. The common context includes the runtime tank state,
plant bounds and capacities, attacker P1-command capabilities, explicit
incident resource authority, timing, intervention budget, cost weights, and
evaluation horizon. Component existence, operational state, trust, recovery
controllability, and final template availability are distinct context facts.

The service contract is common to every candidate considered for one incident:

```text
external_demand
required_delivered_flow
require_continuous_delivery
permitted_interruption_duration
recovery_deadline
assured_operation_duration
evaluation_horizon
```

`external_demand` must equal the plant's configured downstream demand. It remains
at `1.5` in the default incident even when controlled hold sets its physical
`qout=0`. Thus curtailment is represented as unmet external demand, rather than
removing demand from the comparison.

Requested service and physical withdrawal are distinct:

```text
external demand: demand imposed by the incident
qout:             actual T2 withdrawal commanded by the selected policy
qdelivered:       modeled delivered amount, equal to qout
```

Diagnostic traces report both continuous service and service after the incident's
own deadline/required flow. The legacy simulator deadline monitor is retained
only as a separate trace field and does not decide selector admissibility.

The common contract requires an explicit maximum service interruption and an
assurance duration covered by the selected finite theorem. Takeover theorems
bind a positive operation duration as `T = horizon - startupDelay > 0`; the
default immediate instance has `T=5 s` and the default delayed instance has
`T=4.5 s`. Controlled safe hold instead proves one mandatory full-horizon
`HoldDuration > 0` ODE with no positive-service claim. Each is a finite formal
horizon, not an indefinite guarantee. See
[`COMMON_RECOVERY_CONTRACT.md`](COMMON_RECOVERY_CONTRACT.md) and
[`DELAYED_ISOLATION_CONTRACT.md`](DELAYED_ISOLATION_CONTRACT.md) for the exact
timing, service, safety, and cost semantics.

## Existing Policy Contracts

| Policy | Startup action | Formal service guarantee | Certificate region |
| --- | --- | --- | --- |
| Controlled safe hold | Immediately isolate P1, disable P2, and set `qin=qout=qdelivered=0` using trusted hold gates | Safety throughout a mandatory finite hold while positive external demand remains explicit; no positive delivery is established | Any initially safe state with immediate independent isolation, trusted upstream/demand gates, finite horizon, and hold budget; P2 is not required |
| Flowing takeover | Isolate P1, keep `qin=startupInflow` and `qout=startupWithdrawal` while P2 starts | Safety and `qdelivered=qout>=qmin` throughout startup and the bound five-second operation interval | The controlled assumptions plus T1 overflow and T2 depletion startup margins, and simulator-grid compatible startup timing |
| One-period delayed flowing takeover | Command trusted isolation and P2 together, while P1 remains attacker-commandable for exactly one control period | Safety and `qdelivered=qout>=qmin` through one pre-isolation P1 choice, remaining P2 startup, and a positive post-takeover interval | Separate reviewed generated theorem only: `IsolationDelay=ControlPeriod`, `StartupDelay=3*ControlPeriod`, four delay/startup margins, independent trusted isolation, and budget assumptions |
| Delayed flowing takeover | Command trusted isolation and P2 together, while P1 remains attacker-commandable for exactly two control periods | Safety and `qdelivered=qout>=qmin` through two pre-isolation P1 choices, remaining P2 startup, and a positive post-takeover interval | Separate delayed theorem only: `IsolationDelay=2*ControlPeriod`, `StartupDelay=3*ControlPeriod`, four delay/startup margins, independent trusted isolation, and budget assumptions |

Controlled safe hold is certificate-covered at the default state but cannot
satisfy a positive-service request because its formal game deliberately sets
delivery to zero for the full hold horizon. Flowing takeover only satisfies
continuous service up to its proved `startupWithdrawal` value, `1.2` by default;
it does not prove continuous full external demand of `1.5` during startup.

The selector first determines resource-compatible templates. Immediate trusted
isolation plus P2 permits flowing takeover; immediate trusted isolation plus
both hold gates permits controlled safe hold. For reviewed one-control-period
and two-control-period delays it considers only their own delay-specific flowing
certificate. Other bounded generated schedules present no candidate even if a
local proof record is `VERIFIED`, until that exact schedule receives independently
reviewed provenance. It then projects unchanged incident facts into the matching
explicit plant and policy identity and invokes only that policy's checker. It
never uses one policy's certificate to authorize another.

## Selection Algorithm

`select_recovery_policy` performs the following deterministic steps:

1. Validate the common incident and supported topology.
2. Determine resource-compatible templates, then construct their distinct formal
   problem identities before projecting facts into certificate identities.
3. Verify each certificate's canonical manifest provenance and bound artifacts.
4. Check its exact certified region.
5. Compare its established timing, finite assurance duration, startup delivery,
   and post-takeover delivery with the incident service contract.
6. Simulate candidates only for diagnostics and trace-derived cost estimation.
7. Select the lowest `J` only among certificate-covered candidates that satisfy
   the requested contract.

Candidate status is explicit:

* `COVERED_AND_REQUIREMENTS_SATISFIED`: eligible for cost comparison.
* `COVERED_BUT_REQUESTED_SERVICE_NOT_ESTABLISHED`: valid certificate, but its
  theorem does not establish the incident's service or timing request.
* `NOT_COVERED_BY_CERTIFICATE`, `INVALID_OR_INCOMPATIBLE_CONTEXT`,
  `UNTRUSTED_OR_UNAVAILABLE_CERTIFICATE`, or
  `FORMAL_GUARANTEE_UNAVAILABLE_OR_UNRESOLVED`: not authorized.

No authorized candidate means only that no implemented policy compatible with
the incident meets the request. It is not a global unrecoverability claim.

## Common-Demand Cost

`calculate_cost` retains its prior default behavior for existing evaluations.
The selector passes `service_target=external_demand`, using:

```text
service_loss = sum(max(0, external_demand - qdelivered) * interval)
J = w_service * service_loss
  + w_time * recovery_duration
  + w_action * intervention_cost
  + w_backup * integral(q2 dt)
```

The immediate policies use the same incident state, horizon, external demand,
and cost weights. Default trace results for a request allowing interruption are:

| Policy | Startup delivery | Service loss | J | Eligible |
| --- | ---: | ---: | ---: | --- |
| Controlled safe hold | 0.0 | 9.0 | 92.0 | Yes, only when zero delivery and a full-horizon interruption are permitted |
| Flowing takeover | 1.2 | 0.3 | 11.75 | Yes |

These are simulated trace costs, not formal costs or proof of global optimality.
The output labels the pre-selection estimate, completed-simulation value, and
absent formal cost bound separately.

## Evaluation Cases

`recovery_selection_evaluation.py` retains deterministic immediate and delayed
legacy cases. `resource_aware_evaluation.py` reports the resource-dependent A--G
cases and is the authoritative evaluation for the two-template construction:

* Flowing takeover is selected for continuous `1.2` service at `(7,6)`; hold is
  covered but service-inadequate.
* At `(10.5,6)`, flowing takeover is outside its T1-margin certificate while
  controlled safe hold remains covered and is selected only because full-horizon
  interruption is allowed.
* With interruption allowed at `(7,6)`, both are covered and flowing takeover
  wins the common-demand trace-cost comparison.
* A continuous `1.5` request leaves no authorized candidate: hold interrupts,
  while flowing's startup certificate guarantees only `1.2`.
* A delayed `I=1.0`, `S=1.5` incident considers only the delayed flowing policy;
  its matching certificate covers the two permitted P1 command periods.
* Missing trusted isolation, an untrusted manifest, and an incompatible topology
  are each distinguished rather than authorized.

The evaluation records per-candidate certificate latency, selection/admissibility
latency, simulation/cost latency, and total local latency. On the local
synthetic run, total selection was sub-millisecond per normal scenario. This is
not a physical real-time guarantee. Offline CLEO proof time remains separate:
about `4.15 s` for controlled safe hold in the current CLEO run, `9.86 s` for
immediate flowing takeover, and `19.20 s` for delayed flowing takeover in the
reviewed revalidation.

## Run

```bash
# From mitigation_synthesis
python3 -m recovery_experiment.recovery_selection_evaluation
python3 -m recovery_experiment.resource_aware_evaluation

python3 -m unittest discover -s recovery_experiment/tests -v
```

## Limits And Next Formal Step

The selector is a finite candidate comparison. It does not synthesize a hybrid
controller, establish physical trust, prove a cost optimum, or turn a successful
trace into a formal service/cost theorem. The next needed formal capability is a
shared recovery contract that proves longer-horizon delivery and explicitly
models external demand while comparing multiple actions under the same temporal
service objective.
