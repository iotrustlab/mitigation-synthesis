# Evidence at the implementation base

The published procedure bridge at `bc8fd363750cfd4d244a604bebf42d06ffc4d026` contains the historical models. The original checkout on `main` ends three commits earlier. All 174 tracked inputs were hashed before implementation. [The digest inventory](historical_inputs.sha256) records individual SHA-256 values for 76 protected artifacts, including the certificates, theorem families, manifests, archives, correspondence records, and historical proof output.

| Evidence | Established scope |
| --- | --- |
| [Authority archive](../attleboro/remote_authority.kyx) and [reachability archive](../attleboro/remote_authority_nonvacuity.kyx) | Given bad utility/generator conditions, or restored utility with a pending latch and no new reset edge, a powered controller scan inhibits Remote output for arbitrary start demand. Both input classes have reachable poststates. |
| [CLEO choice and flow archives](../procedure_study/cleo) | Choice assumes an eligible Remote or Hand branch and proves the selected command location is eligible. The flow theorem freezes the initial sample in the slope for one exact 0.1 s phase. For a target of 0 or 10 L/s it proves the pre-clamp endpoint lies in [0,10] L/s. Neither theorem establishes delivery or positive flow at a recovery deadline. |
| [Trace bridge](../attleboro/bridge.py), [source map](../attleboro/source_to_model_map.md) and [receipts](../attleboro/proof_records) | The source-hash checks and correspondence rerun matched all 22 synthetic and OpenPLC bundles, covering 727 rows and 464 one-scan synthetic start and reset transitions each. Nominal service is observed in traces. Of 45 controller/delivery discrepancies, 44 belong to deliberate fixture mutations and one to a sampled trip transition. |
| [ModelPlex receipts](../procedure_study/modelplex) | On the saved bad-power samples the controller monitor accepts visible inhibited outputs, including when downstream delivery differs. The sampled monitor covers discrete controller behavior only. |
| [Existing builder](../recovery_model_builder.py), [formal assessment](../formal_problem.py), [selection](../recovery_selection.py), [context](../context.py) and [cost](../cost.py) | These bind schedules, existing certificate identities and older tank models to context, service and cost. A proof or score for one of these configurations cannot be transferred to the new pump procedure. Their APIs and regression tests are preserved. |

## Boundaries of the water fixture

The historical 2019 design evidence supports the Remote/Hand distinction, loss of SCADA authority on power transfer, separate reset after restoration, a momentary start sealed by confirmation, and forward-flow metering and trip paths. The [source-to-model map](../attleboro/source_to_model_map.md) supplies the loop and page locators.

The authored controller implements rising edges and retained state. The historical design's five-second start-confirmation interval becomes 50 scans in the research implementation. The simulator takes two enabled scans to confirm running, chooses a target of 10 or 0 L/s, advances flow by two fifths of the gap, and snaps values below 0.01 L/s to zero. The simulator computes pressure in psi as 30 + 3 times flow in L/s. Its service checks use 5 L/s, 90 psi and protection bits. Meter health controls whether a sample refreshes. Scan timing, exact equations, input stability, credibility assumptions and thresholds are research choices.

The pinned SPHERE case tree is `ec3319f9d3ac41352df2a21253f4af3aab7f22ca`. The reviewed reference simulator is `model/core.py`, SHA-256 `484cee751d2b9568d399c9217b0bf33df2d59baee4f43a0dede37b2c6609fcf2`. The pinned ST controller and simulator are identified in the source map. Hand and Remote use distinct command locations and converge on the same VFD, pump, motor supply, trip protection, delivery path and measurement. The procedure-specific independence and Boolean failure effects describe the study fixture.

Current wiring, power architecture, staffing, network redundancy, instrument integrity and calibration, water demand, pressure requirements and as-built hydraulics remain unknown. The source and correspondence evidence do not establish translation/refinement of an installed controller, continuous-time safety between samples, customer supply or indefinite service. The package uses an offline, historical research scenario.

## Other cases

The [procedure experiment receipt](../../PROCEDURE_EXPERIMENT_RECEIPT.md) pins the Merwin and CHP case trees and records 12 assessed bundles apiece. The Merwin research traces check an ordered startup sequence and joint breaker-contact/power samples. CHP records include two benign OpenPLC heartbeat executions. The traces supply neither a general Merwin service proof nor evidence of physical CHP restart or customer service.
