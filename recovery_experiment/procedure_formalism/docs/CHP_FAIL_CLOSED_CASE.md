# Polish CHP device, process and service evidence

The historical case assessment describes reset and backup reload attempts and records device-level outcomes. The public incident evidence provides neither a process restart model nor a customer supply mechanism. The pinned SPHERE fixture represents the engineering action, backup checks, device bootability, loading and runtime as a discrete lifecycle. Its two successful benign heartbeats come from a disposable OpenPLC runtime. The recorded lifecycle evaluator labels the broader device recovery simulated even for those runs. [Milestone 1 source audit](../CURRENT_ARTIFACT_AUDIT.md) · [Procedure experiment receipt](../../../PROCEDURE_EXPERIMENT_RECEIPT.md)

The observational experiment reuses the reviewed-backup procedure schema. Its checked-in evidence projection contains the three action decisions, terminal lifecycle fields, source assessment, compile-success flag and scan-counter pair. SHA-256 digests identify the original scenario, event, assessment and runtime files in the pinned case tree. The `capture` function can reproduce the projection from a matching case directory. The replay reads saved evidence offline. [Evidence projection](../milestone2/chp_device_evidence.json) · [Decision rules](../milestone2/chp.py)

`DEVICE_RECOVERY = ESTABLISHED` refers to the fixture lifecycle completing with independent evidence that benign logic executed. It requires an accepted reset, a bootable profile, available compatible reviewed logic, successful load, accepted runtime start, a compile-success marker and two increasing scan-counter observations. `published_device_lifecycle_assessment` preserves the source recording of simulated device recovery. Unknown cyber trust propagates independently of the heartbeat.

| Query | Evidence or blocking condition | End-to-end procedure outcome |
| --- | --- | --- |
| CHP0 | Compatible, reviewed backup and advancing scan counter | UNKNOWN, physical process missing |
| CHP1 | Backup absent | REJECTED at reload |
| CHP2 | Backup incompatible | REJECTED at reload |
| CHP3 | Backup unreviewed | REJECTED at the required review guard |
| CHP4 | Reset leaves controller nonbootable | REJECTED at device preparation |
| CHP5 | Device executing, process permissives unknown | UNKNOWN |
| CHP6 | Device executing, process explicitly unready | REJECTED for this procedure in this state |
| CHP7 | Customer supply mechanism and evidence unresolved | UNKNOWN |
| CHP8 | Persistence unresolved despite device execution | UNKNOWN |

These nine labeled questions draw on six distinct saved bundles. CHP0, CHP5, CHP7 and CHP8 inspect different claim boundaries of the same successful record. CHP8 examines its unresolved trust field. The separate proposed persistent-influence fixture positively injects a hypothetical condition and supplies no evidence of an actual second attack.

B1 checks device bootability. B2 adds access and availability of the backup path. B3 assesses the device/runtime boundary, using empirical heartbeat evidence where present. B4 applies the hard prerequisites and distinguishes physical process readiness, actual CHP production and credible customer-service evidence. When restart is explicitly forbidden, the procedure is rejected. Heat and electricity delivery remain unknown in every row, including where an external supplier could serve customers. The fixture supplies no formal CHP process or service theorem. [Recorded decisions](../results/milestone2/chp_fail_closed_results.json)
