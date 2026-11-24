# Bounded procedure semantics

A procedure fixes a service contract, initial state, deadline, horizon and named resources. Its stages carry typed dependency references, source identities and separate evidence classifications. The water fixture measures time in 100 ms ticks. Merwin and CHP retain unresolved fields at their observed level of evidence.

A single incident snapshot creates one object per component. Mutating the VFD once therefore changes a required dependency of both pump procedures. A change to the Remote delivery boundary leaves the local panel relation independent. Procedure instances share physical resources without silently switching the physical selector or changing the starting state to make another procedure eligible.

## Stage relations

Let a stage assign a fresh value y from a relation R(x,y) over its preceding state x. The stage's status determines the relation.

| Status | Allowed behavior |
| --- | --- |
| TRUSTED | The nominal value or guarded transition. |
| COMPROMISED | Any value in that component's declared finite disturbance alphabet. For the delivery boundary the bit can vary independently of PLC output. |
| UNAVAILABLE | The empty relation. A positive-service procedure needing this component is ineligible even though a box on the empty program can be vacuously true. |
| UNKNOWN | Union of nominal and disturbed stage relations. A proof valid across the entire union can establish the guarantee. A possible violation confined to a hypothetical unresolved state leaves the real status unknown. |

A single disturbance choice holds for the bounded interval in the water study. The sampled flow and pressure readings have their own finite domains. The schema records whether the basis of a field is a historical source, authored model, trace, formal proof or unknown. A trusted node in a research scenario still has research-authored status for the trust assumption.

The executable IR evaluates the guarded assignments with exact rational arithmetic. Its dL renderer assigns fresh variables nondeterministically and then tests their joint defining relation. Every right-hand side depends only on initial or earlier variables, so moving these tests to a conjunction preserves the sequential relation. The model archive binds procedure, resource state, plant, threat model, source and generator identity. Changing an input changes its hash and invalidates reuse of an unmatched proof.

## Decisions

The end-to-end box covers every allowed execution. A separate diamond establishes a successful execution under the same precondition. Each stage event has its own predicate. Pump run confirmation precedes flow, and physical service can hold with a stale or untrusted sample. The checked obligations and the bounded pump law appear in the [Remote theorem](ATTLEBORO_REMOTE_THEOREM.md).

The evaluator admits a procedure only after validating its matching proof records, nonvacuity and postcondition. A known failed hard requirement or a concrete admitted violation excludes a procedure. Unresolved source assumptions, an unsupported plant or a missing proof yield UNKNOWN. The portfolio reports NO_ASSURED_RECOVERY when every candidate lacks a positive-service guarantee. Hold has a separate no-start contract and supplies no positive-service candidate.

## Cost and scope

Only procedures admitted for a common initial state, environment, horizon, deadline and service/safety contract can be ranked. Pareto comparison preserves each component's units. Explicit reference scales and weights permit a declared comparison on selected dimensions. Missing observations remain missing. The study does not infer staffing, energy use or customer outcomes from a start bit.

The result's event vector describes one identified execution. SERVICE_OBSERVED means a fresh reading crosses the declared flow and pressure thresholds. SERVICE_ESTABLISHED additionally requires credibility and the physical predicate. A reported value on a compromised observation channel can therefore cross the threshold while establishment fails.
