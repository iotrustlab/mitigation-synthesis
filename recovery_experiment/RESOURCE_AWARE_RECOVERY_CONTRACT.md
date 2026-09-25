# Resource-Aware Recovery Templates

## Scope

This contract extends the fixed synthetic topology `T1 -> {P1, P2} -> T2` with incident-dependent recovery authority. It is an offline model-construction, verification, certificate, selection, and simulation artifact. It does not claim deployment, live PLC authority, a discovered topology, or general recovery synthesis.

The attacker controls the P1 command surface and can select `P1=0` or `P1=1` at modeled command boundaries. Rewriting that command in memory is not recovery. Every certified template requires an independent physical primary-isolation path.

## Incident Resource Model

`RecoveryContext` records four distinct facts:

| Fact | Representation | Meaning |
| --- | --- | --- |
| Physical component existence | `physical_components` and fixed plant topology | The abstract plant contains P1, P2, an isolator, upstream gate, and demand gate. Existence alone grants no authority. |
| Operational signal path | `control_path_authority.operational` | The relevant path is currently usable. |
| Trusted signal path | `control_path_authority.trusted` | The incident treats the path as outside the P1 compromise boundary. |
| Recovery controllability | `control_path_authority.controllable_by_recovery` | The recovery layer is permitted to actuate the path. |
| Final template availability | `resource_availability` | An explicit incident decision that a trusted operational controllable path is available to a template. |

The final fields have no defaults:

```text
trusted_isolation_available
trusted_backup_available
trusted_inflow_control_available
trusted_demand_control_available
```

If any final `true` value lacks its actuator binding plus operational, trusted, and recovery-controllable evidence, context validation fails. A `false` value does not imply component absence; it represents an incident where the modeled component cannot be relied on by recovery.

## Template Catalogue

Exactly two templates are implemented.

| Template | Required incident resources | Formal family | Service interpretation |
| --- | --- | --- | --- |
| `flowing_backup_takeover` | trusted primary isolation and trusted P2 control | Existing generated bounded `(n,m)` isolation/startup games | Startup flow and positive P2-backed service are established under the matching reviewed theorem. |
| `controlled_safe_hold` | trusted primary isolation, upstream closure, and demand/delivery-curtailment control | New immediate-isolation finite safe-hold game | Safety is established while actual delivery is zero; positive service is deliberately not certified. |

Template applicability is reported before formal construction. It is separate from `FORMAL_PROBLEM_CONSTRUCTED`, `FORMAL_THEOREM_VERIFIED`, `CERTIFICATE_ISSUED`, `CONTEXT_COVERED_BY_CERTIFICATE`, and the selection-time `SERVICE_CONTRACT_SATISFIED` result. No trusted isolation yields `NO_SUPPORTED_RECOVERY_TEMPLATE`, not a global claim that no recovery exists.

## Controlled Safe Hold Mathematics

The safe-hold theorem uses closed initial tank bounds:

```text
L1 <= x1 <= H1,  L2 <= x2 <= H2,  L1,L2 >= 0
qprimary >= 0
externalDemand > 0
qmin >= 0
HoldDuration > 0
interventionBudget >= isolationCost + holdControlCost >= 0
```

`externalDemand`, `qdelivered`, and `qmin` have different roles. Demand remains positive and unchanged. `qdelivered` is actual delivered flow and is zero during the hold. `qmin` is the incident's minimum acceptable service and is represented without being asserted by this safety-only theorem.

The game first universally considers the two attacker P1 choices. It then makes the trusted isolator effective immediately, disables P2, and closes the trusted upstream and delivery paths:

```text
P1 := 0 or P1 := 1;
isolated := 1; P2 := 0;
qin := 0; qout := 0; qdelivered := 0;
interventionBudget := interventionBudget - isolationCost - holdControlCost;
holdClock := 0;
{ x1' = qin - (1-isolated)*P1*qprimary,
  x2' = (1-isolated)*P1*qprimary - qout,
  holdClock' = 1 & holdClock <= HoldDuration };
? holdClock >= HoldDuration;
```

With immediate physical isolation and both gates closed, `x1'=x2'=0`; therefore the closed safety bounds are invariant. The ODE domain does not include safety bounds, and the final clock test forces exactly one positive-duration physical evolution. The theorem does not cover delayed isolation. A delayed hold would need a new theorem with delay-specific tank margins.

## Proof And Certificate Lifecycle

`controlled_safe_hold_formal.py` renders the game; `controlled_safe_hold_proof_profile.py` supplies its one ODE invariant; and `verify_controlled_safe_hold.py` records offline CLEO obligations. The reviewed manifest binds the generated envelope, formal source, profile, verifier, and verification record by SHA-256. `controlled_safe_hold_certificate.py` checks that anchored provenance and the current context but never calls CLEO.

The safe-hold checker requires its own model and policy IDs, immediate physical isolation, positive external demand, a finite horizon, safe current state, budget coverage, and all three trusted hold resources. It does not require P2. The flowing certificates separately reject a context where trusted backup or trusted isolation is unavailable, so certificates cannot cross-authorize the two templates.

## Selection And Cost

Selection order is:

```text
resource/template applicability
-> template-specific formal construction and reviewed certificate coverage
-> incident safety/service/timing requirements
-> deterministic trace-derived cost among only admissible candidates
```

All candidates use the same external demand and configured evaluation horizon. For safe hold, the full-horizon delivery shortfall is measured against unchanged external demand, P2 use is zero, and the intervention cost uses the controlled-hold weight. For takeover, P2 use remains part of the trace-derived cost. Every output labels `formal_cost_bound` as `null`; no formal cost-optimality claim is made.

## Reproduction

Run from the `mitigation_synthesis` repository root. `CLEO_PYTHON` must name the configured Python interpreter with CLEO, Z3, and KeYmaera X support.

```bash
python3 -m recovery_experiment.resource_aware_evaluation \
  --output recovery_experiment/results/resource-aware-recovery-evaluation.json

"$CLEO_PYTHON" -m recovery_experiment.verify_controlled_safe_hold \
  --output-dir recovery_experiment/proof_records/controlled_safe_hold

python3 -m unittest discover -s recovery_experiment/tests -q
RUN_CLEO_REGRESSION=1 "$CLEO_PYTHON" -m unittest discover -s recovery_experiment/tests -q
```

The A--G evaluation covers backup availability, backup loss with hold controls, positive continuous-service rejection, both-template cost comparison, missing isolation, missing hold controls, and a state outside the flowing-takeover margin where safe hold remains certified.

## Limits

Only the two fixed templates and one synthetic topology are modeled. Safe hold is immediate-isolation only, has no restoration policy after the hold horizon, and intentionally certifies safety rather than service. Resource facts are declared incident inputs, not measured live telemetry or independently attested security evidence. No LLM, SPHERE integration, sensor uncertainty, new topology, deployment action, or general strategy synthesis is implemented.
