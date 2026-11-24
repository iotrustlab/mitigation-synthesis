# A valid Remote output can leave the pump stopped

Use mutation M5 of the historical Attleboro design fixture for this figure. Draw the operator, OWS, communication link, PLC, delivered-output boundary, VFD, pump, water path and flow/pressure observer in that order. Place the disturbance between PLC output and delivered actuation. The separate Local Hand input joins at the same VFD. Motor power and the hardwired trip path are common inputs to the drive.

## Figure inputs

| Input | Value in M5 |
| --- | --- |
| Physical state at tick 0 | Pump stopped, no accumulated start scans, actual and previous observed flow 0 L/s, discharge pressure 30 psi. Water path unblocked, pH in range and trip clear. |
| Authority and power | Utility available. Generator idle and unselected, generator readiness 0. Reset latch, current reset request and previous reset request all 0. Remote selected exclusively. |
| Actors and candidates | The authorized Remote operator and local operator are ready at tick 0. The candidates are Remote start, Local Hand and hold/no-start. The selector remains Remote in this scenario. |
| Compromise | The Remote output delivery dependency is COMPROMISED. It may deliver 0 or 1 independently of PLC output, with the selected value held for all three scans. All other modeled dependencies are TRUSTED and the observation is fresh. These states are fixture assumptions. |
| Safety | At each sampled state, flow is in [0,10] L/s, pressure is in [30,90] psi, pH is in range and the trip is clear. |
| Service and evidence | At the deadline, actual flow must reach 5 L/s with pressure at most 90 psi and protections clear. A trusted, fresh observer must report matching values that meet the service bounds. |
| Horizon and deadline | Three mandatory 100 ms scans, from a request at tick 0 to assessment at elapsed tick 3. |

## Figure outputs

Show the Remote execution with delivered bit 0. The operator issues a request, the PLC accepts it and its start output is 1. The drive receives 0. Run feedback remains 0 through all three scans. Their flow samples are 0, 0 and 0 L/s. Discharge pressure stays at 30 psi. The healthy observer faithfully reports zero flow at the deadline. The sampled states satisfy the safety bounds. The execution violates both the physical-service and the service-establishment obligations.

| Candidate | B4 result for positive water service | Reason and figure annotation |
| --- | --- | --- |
| Remote | REJECTED | OUTPUT_STAGE_COMPROMISED. Mark the PLC output 1 and the delivered output 0 on the same execution. A delivered 1 can reach service, but assurance requires every permitted delivery to meet the contract. |
| Local Hand | REJECTED | AUTHORITY_FAILED. A ready local actor cannot establish Hand demand while Remote is selected. Pump safety and water service are unassessed for this excluded procedure. |
| Hold/no-start | REJECTED | SERVICE_NOT_ESTABLISHED. The hold adds no start request. Its desired state is a stopped pump. Physical safety is unassessed. |

Leave the cost vector unavailable for all three candidates. None qualifies for service-compatible cost comparison. Zero in a cost cell would incorrectly suggest a measurement. B1 sees an available component. B2 sees a connected path. B3 reaches an accepted Remote request and PLC output. B4 follows both allowed delivery values through the pump and meter and reports the counterexample.

Use the generated M5 row for the model identity, exact witness and result. The statuses and numbers in this figure concern the frozen research model. Actual site staffing, network and power architecture, drive timing, hydraulics, service thresholds and instrument health remain unknown. [Mutation matrix](../results/attleboro_mutation_matrix.json) · [Theorem and physical units](ATTLEBORO_REMOTE_THEOREM.md) · [Source-to-model correspondence](../../attleboro/source_to_model_map.md)
