# Duration of Attleboro's water-service claim

**Finding.** The nominal Remote (M0) and Local Hand (H0) archives establish sampled safety through the third scan and water service at the deadline. A positive post-recovery dwell over any additional interval requires dynamics, assumptions and observations beyond the last modeled sample.

## What the checked programs cover

Paths are relative to the experiment package. In `formal_model.py:_plant`, the clock starts at the operator's ready tick. For each of three mandatory 100 ms scans the plant chooses a target from the drive and path state, advances flow using gain 2/5, computes pressure, accumulates sampled safety, and advances the clock by one. The initial state and all three endpoints enter the safety flag. The last assignment to physical service uses terminal flow, pressure, trip and pH. The observer samples final flow and pressure once and checks freshness, trust, equality with both physical quantities, and the service thresholds.

| Procedure | Model and evidence | Endpoint |
| --- | --- | --- |
| Remote on utility (M0) | `models/M0.kyx`, `proof_records/M0/end_to_end.kyp`, `proof_records/M0/execution_witness.kyp`, and `proof_records/M0/retained_start.kyp` | From a ready tick of zero, the flow samples are 0, 4 and 6.4 L/s. At tick 3 the pump runs, pressure is 49.2 psi, both readings match, and evidence is fresh. The retained-start result covers the specified three controller outputs. |
| Hand on generator (H0) | `milestone2/evidence/models/attleboro-local-hand-end-to-end-recovery-v1.kyx`, its `end_to_end.kyp` and `execution_witness.kyp` in the corresponding `milestone2/evidence/proof_records` directory, and `results/milestone2/attleboro_hand_mutations.json` | Local acceptance and shared power, drive, pump, pipe and observation yield the same sampled values at the same deadline. H2 starts one tick later and reaches 6.4 L/s at tick 4. That is a different initial premise and an already missed deadline. |

The boundary proofs in `paper_v2/formal_evidence/proof_records/v2_M0/O3_boundary.kyp` and `v2_H0/O3_boundary.kyp` check `t=deadline & t=ready+3` in the respective nominal programs. Each corresponding `O6_correspondence.kyp` checks production of the established flag and its implication to physical service, trust, freshness and both matching readings. Neither program has a fourth scan, a continuous hydraulic evolution between samples, an observation after the deadline, or an invariant governing later demand, power, protection and meter validity. Freezing the final state would not represent hydraulic evolution. Extending the recurrence while keeping all final dependencies fixed would impose new persistence assumptions.

## Separate bounded service intervals

Merwin already checks three electrical polls, at ticks 1285, 1291 and 1296, conditional on its pinned plant reduction (`milestone2/evidence/merwin_plant_reduction.json`). The controlled tank separately proves delivery from 2 s through its 4 s horizon using fixed-duration phases, a constant-rate ODE lemma, and a matching terminal reading (`milestone2/cost.py:rate_integral`, `results/paper_v2/cost_exact_vectors.json`). Each schedule belongs to its own model. The Attleboro results therefore retain the wording “service at the deadline.”
