# Controlled research benchmark for formal cost choice

The benchmark compares two water-delivery procedures at one tank. All quantities are authored research parameters. Every candidate starts with primary path P1 isolated, 12 L in the tank, inflow 1 L/s and demand 3 L/s. Both face the same persistent binary disturbance model, common feed, downstream pipe, flow meter, four-second horizon and two-second service deadline. The volume must remain within [4,17] L throughout. Physical flow must be at least 2 L/s continuously from 2 s through 4 s, and the final fresh meter reading must agree with physical flow.

| Property | Automatic backup P2 | Manually enabled alternate P3 |
| --- | --- | --- |
| Command dependencies | Software actor, network B, controller B | Local operator and interface C |
| Delivery dependencies | Actuator B and power B | Actuator C and power C |
| Shared physical objects | Upstream power feed, delivery pipe, meter | Same feed, pipe and meter |
| Mandatory startup duration | 1 s | 2 s |
| Nominal active supply | 3 L/s | 3 L/s |
| Enabled drive consumption | 4 W | 1 W |
| Manual interventions | 0 | 1 |

Candidate-specific startup time, capacity and wattage are attributes of the two paths present together in the *same* incident. A mutation changes this incident for both candidates. One context fingerprint covers initial conditions, rates, horizon, service, tank bounds and all resource states. Selection reconstructs each typed candidate from that context and checks its matching proof. Changing an unused dependency can preserve a candidate's proof because the stage relation projects onto resources used by that candidate. The whole incident must still agree across a comparison.

## Tank and formal cost state

Let the startup phase last s seconds and the active phase last H − s seconds. Initially all costs are zero. During startup delivered flow q is zero. During the active phase q comes from accepted output, powered actuation, pipe passage and rated capacity. In each phase the constant rates are

```text
V'             = inflow − q                         L/s
cService'      = demand − q                         L/s
cTime'         = 1 if q is below minimum, else 0     s/s
cResource'     = drive * watts                      J/s
```

The discrete local acceptance adds one manual intervention. A universal KeYmaera X ODE obligation proves the exact integrals of arbitrary frozen rates from the initial values. It also proves that a constant-rate volume stays within bounds whenever both interval endpoints are within bounds. The stage model composes the exact two endpoint maps with fixed durations summing to H, checks all three tank endpoints, and distinguishes physical service from a credible observation. This is the finite-stage counterpart of the repository's constant-rate tank balances.

Each admissible profile contains a controller prefix, a plant prefix, the constant-rate ODE, a universal composed theorem and an execution diamond for the same postcondition. The composed theorem proves hard safety, service, credible observation, the four component totals and the exact weighted total for **all nonnegative policy weights**. The weights convert L, s, manual actions and J to policy points.

| Nominal procedure | Proved components in order (L, s, actions, J) | Certified weighted total |
| --- | --- | --- |
| P2 | (3,1,0,12) | 3wService + wTime + 12wResource |
| P3 | (6,2,1,2) | 6wService + 2wTime + wIntervention + 2wResource |

The P2 and P3 terminal volumes are 7 L and 10 L respectively. Both nominal choices lie on the Pareto frontier. All-zero weights preserve a tie.

| Policy | Weights (service, time, intervention, resource) | P2 points | P3 points | Selected |
| --- | --- | --- | --- | --- |
| COST-W1, service-heavy | (8,3,1,1) | 39 | 57 | P2 |
| COST-W2, intervention/resource-heavy | (1,1,3,4) | 52 | 19 | P3 |
| COST-W3, equal points per declared unit | (1,1,1,1) | 16 | 11 | P3 |

## Controlled dependency experiments

| Scenario | Change | Assured alternatives |
| --- | --- | --- |
| C0 | Nominal | P2 and P3 |
| C1 | Compromised B controller can suppress output | P3 |
| C2 | Local actor unavailable | P2 |
| C3 | Common upstream feed unavailable | None |
| C4 | Shared meter compromised | None. Physical flow can meet the target while trustworthy evidence fails. |
| C5 | P2 capacity drops to 2 L/s | P2 and P3. P2's proved deficit rises to 6 L; the minimum still holds. |
| C6 | P3 opens at 3 s | P2. P3 achieves terminal flow but misses the start of sustained service. |
| C7 | Common delivery pipe unavailable | None |

The formal experiment uses three positive profiles and four reachable-violation profiles. A known unavailable required dependency disables the branch. The selection code considers only procedures with validated positive profiles, records ties, and returns NO_ASSURED_RECOVERY when the admissible set is empty. B3 reads the automatic controller prefix. The local direct panel has no controller-only result. Costs support this finite comparison under the stated policy. The controlled fixture makes no claim about an installed water system, operator response times or utility tariffs.
