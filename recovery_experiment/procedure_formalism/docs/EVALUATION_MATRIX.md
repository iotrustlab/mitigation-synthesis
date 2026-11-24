# Attleboro controlled dependency mutations

All rows query the same positive water-service contract. Each mutation explicitly sets the incident state and then constructs every listed candidate in that one snapshot. M10 and M11 use the Local Hand selector on available generator power. M0–M9 and M12–M14 use the Remote selector. Fixed selector position is part of the applicability domain.

| Mode | Decision boundary |
| --- | --- |
| B1 | Checks availability of the named pump component alone. |
| B2 | Checks whether all nodes on the declared path are known available. A compromised node remains reachable. Unknown availability yields UNRESOLVED. |
| B3 | Executes the actor-to-PLC-output prefix of the same discrete model. ACCEPT requires all reachable outputs on and at least one execution. The Remote prefix reads power, latch and trip inputs. Local Hand and hold lack this Remote PLC command. |
| B4 | Checks hard prerequisites, searches exact executions for violations, and admits positive service only with proof of all stage, composed and nonvacuity obligations for the matching formal model. |

ACCEPT is scoped to the individual baseline. The first-stage column identifies where the full procedure first detects the listed failure or unresolved premise. For M13 the first unresolved dependency is the delivered-output boundary. Hold is assessed for the requested positive service and has no matching contract.

| Mutation | Fixture change | Procedure | B1 | B2 | B3 | B4 | First stage | Basis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | Positive Remote | Remote | ACCEPT | ACCEPT | ACCEPT | PROVED | service established | All required obligations closed |
| M1 | MTS on generator | Remote | ACCEPT | ACCEPT | DECLINE | REJECTED | authority | authority failed |
| M2 | Utility restored with held reset | Remote | ACCEPT | ACCEPT | DECLINE | REJECTED | authority | authority failed |
| M3 | Communication unavailable | Remote | ACCEPT | DECLINE | DECLINE | REJECTED | communication | communication unavailable |
| M4 | Controller output compromised | Remote | ACCEPT | ACCEPT | DECLINE | REJECTED | controller | controller compromised |
| M5 | Delivery compromised | Remote | ACCEPT | ACCEPT | ACCEPT | REJECTED | delivery | output stage compromised |
| M5 | Delivery compromised | Hand | ACCEPT | ACCEPT | INAPPLICABLE | REJECTED | authority | authority failed |
| M5 | Delivery compromised | Hold | INAPPLICABLE | INAPPLICABLE | INAPPLICABLE | REJECTED | service contract | service not established |
| M6 | Shared VFD unavailable | Remote | ACCEPT | DECLINE | ACCEPT | REJECTED | actuator | actuator unavailable |
| M6 | Shared VFD unavailable | Hand | ACCEPT | DECLINE | INAPPLICABLE | REJECTED | actuator | actuator unavailable |
| M7 | Flow blocked | Remote | ACCEPT | ACCEPT | ACCEPT | REJECTED | plant | service not established |
| M8 | Final observation stale | Remote | ACCEPT | ACCEPT | ACCEPT | REJECTED | observation | observation stale |
| M9 | Observer compromised | Remote | ACCEPT | ACCEPT | ACCEPT | REJECTED | observation | observer compromised |
| M10 | Local operator absent | Hand | ACCEPT | DECLINE | INAPPLICABLE | REJECTED | actor | actor unavailable |
| M11 | Local operator late | Hand | ACCEPT | ACCEPT | INAPPLICABLE | REJECTED | actor | actor late, deadline missed |
| M12 | Shared trip active | Remote | ACCEPT | ACCEPT | DECLINE | REJECTED | protection | trip active |
| M12 | Shared trip active | Hand | ACCEPT | ACCEPT | INAPPLICABLE | REJECTED | protection | trip active |
| M13 | Delivery integrity unknown | Remote | ACCEPT | UNRESOLVED | ACCEPT | UNKNOWN | dependency evidence | evidence insufficient |
| M14 | No assured positive service | Remote | ACCEPT | DECLINE | DECLINE | REJECTED | communication | communication unavailable |
| M14 | No assured positive service | Hand | ACCEPT | DECLINE | INAPPLICABLE | REJECTED | actor | actor unavailable |
| M14 | No assured positive service | Hold | INAPPLICABLE | INAPPLICABLE | INAPPLICABLE | REJECTED | service contract | service not established |

M5 yields a concrete execution with PLC output 1 and delivered command 0. Run feedback remains off, and final flow is zero. M7 keeps run feedback on with zero flow. In M8 and M9 physical service can hold while credible evidence fails. M13 admits a violating execution under the unresolved delivery state, so its assessment remains UNKNOWN. The catalog of negative witnesses includes a separate existential proof for each of these cases.

M14 has no assured positive-service procedure. Remote lacks its communication path, Hand lacks its local operator, and hold supplies no positive flow contract. In M5 the fixed selector also excludes Hand. No cost ranking is attempted in either incident.

The [baseline comparison](../results/baseline_comparison.json) and [expanded matrix](../results/attleboro_mutation_matrix.json) give exact per-candidate inputs, reasons and outcomes. The [proof summary](../results/proof_summary.json) binds checked archives and proof receipts to each formally evaluated case.
