# Procedure stages across the three fixtures

A positive trace records one execution. The result column concerns bounded, credible physical service across all executions in the stated model.

| Procedure | Actor, authority and request | Delivery and physical response | Service evidence and proof scope |
| --- | --- | --- | --- |
| Attleboro Remote | Remote operator at OWS, eligible utility/reset/Remote state, PLC accepts a Start edge | A separate delivered-output stage feeds the VFD. Power and the trip path gate the pump. Three mandatory research scans evolve flow. | Fresh flow and pressure, acceptable protection state and the deadline are explicit in the generated Remote theorem. See the generated positive result for proof status. |
| Attleboro Local Hand | Local operator present and ready at the selected Hand panel | Panel demand reaches the same VFD, pump, motor power, hardwired trip and delivery path | Shares the Remote service contract and observer. Start traces give bounded observations. An end-to-end Hand proof remains open. |
| Attleboro Hold | Withhold a start from the declared stopped state | No positive pump demand | No positive water-service claim. |
| Merwin Local Manual | Local operator checks guide-bearing lube pump and oil level, then requests start | At speed, local sync and a fresh close request precede breaker contact | The evaluator observed initial generation on the representative unit. Formal service remains UNKNOWN. |
| Merwin Local Auto | Same historical local checks and a local start | Automatic roll, synchronization and breaker close | Local Auto trace reached contact at 107.615039 s and sustained generation at 108.127814 s. Formal service remains UNKNOWN. |
| Merwin HCC Remote Auto | HCC operator, Remote Auto, normal auxiliaries and an available research link | Automatic synchronization and close, then physical breaker contact | Representative generation observed. Formal service remains UNKNOWN. |
| Merwin Hold | Retain no-start | Withhold start and close demand | No positive generation claim. Safe hold bounds remain open. |
| CHP controller reset | Engineering access, reset attempt | Siemens-like reset and WAGO-like failed boot are simulated device transitions | Reset leaves logic execution, process readiness, physical output and customer service unestablished. |
| CHP reviewed backup reload | Bootable device, engineering access, available compatible reviewed backup | Simulated load followed by a runtime request | Two increasing counter reads on a disposable OpenPLC runtime establish benign device logic execution. Process readiness, physical output and customer service remain UNKNOWN. |
| CHP isolate/hold | Engineering hold with unknown isolation coverage | Withhold the process restart request | No positive cogeneration claim. Safe ongoing isolation is unresolved. |
| CHP no assured process recovery | Assessment disposition | No actuator request | No candidate establishes safe process or customer service in this model. |

The hydro evaluator requires three consecutive samples with running state, breaker closed and at least 1 MW on the same rows. PacifiCorp's 2004 Exhibit H supplies the historical modes. The threshold, timing and Olmsted-derived plant belong to the fixture. For CHP, CERT Polska reports reset and reload, and describes continued customer supply during interrupted cogeneration. The report leaves the supply mechanism, restart permissives and review method unspecified. The case receipt identifies the source documents, evidence bundles and exact SPHERE tree digests for both domains. [Three-case receipt](../../../PROCEDURE_EXPERIMENT_RECEIPT.md)

## Attleboro cost measurements

The committed projection retains the first three rows of the synthetic nominal Remote bundle, five columns, the 0.1 s research scan period, and the 5 L/s target. Its source commit and the complete upstream CSV and metadata digests are recorded with the projection. No additional checkout is needed to regenerate the report. [Cost sample fixture](../fixtures/nominal_remote_cost_samples.json)

The recorded flows are 0, 4 and 6.4 L/s. Integrating each sampled shortfall over one scan yields 0.0006 m³. The first credited-service sample bears timestamp 12:00:00.200 UTC, 0.2 s after the first recorded sample. Relative to the theorem’s pre-scan state, that row is the endpoint of the third mandatory scan, at 0.3 s. The two elapsed quantities have different clock origins. The trace has one rising drive run-feedback edge and zero seconds of physical service without credited evidence. Active labor and motor energy are unmeasured. The feedback edge count defines the intervention measure for this fixture.

Cost comparison requires two proved procedures with matching initial state, environment, safety and service contracts, deadline, and horizon. Pareto comparison minimizes all six components and returns an incomplete result for missing measurements. Optional weights apply to declared dimensions after division by an explicit reference value in the same unit. No common-context Remote/Hand ranking exists in these fixed, mutually exclusive selector positions.

After generating the Attleboro evaluation, rebuild the case assessments and costs from the repository root with `python3 -m recovery_experiment.procedure_formalism.case_assessment`.
