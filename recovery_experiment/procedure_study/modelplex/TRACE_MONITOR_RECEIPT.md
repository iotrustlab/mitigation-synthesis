# Attleboro ModelPlex trace check

[evaluate_trace_monitor.py](evaluate_trace_monitor.py) reads the committed `attleboro_bad_power_ctrl.kym` formula. It accepts only the Boolean grammar present in that artifact and rejects unknown symbols or syntax. This is an offline evaluator for saved research traces, not a deployed monitor.

## Scan alignment and field mapping

Each synthetic CSV row records inputs sampled for a controller scan and outputs after that scan. Rows outside the bad-power antecedent (`utility=0`, `mtsGen=1`, or `genRun=1`) are skipped.

| Generated symbol | Saved trace column | Role |
| --- | --- | --- |
| `utility` | `ATT_Utility_Available` | sampled input |
| `mtsGen` | `ATT_MTS_Generator` | sampled input |
| `genRun` | `ATT_Generator_Running` | sampled input |
| `selectorRemote` | `ATT_Selector_Remote` | sampled input |
| `trip` | `ATT_Trip` | sampled input |
| `resetReq` | `ATT_Reset_Request` | sampled input |
| `resetPendingpost` | `ATT_Reset_Pending` | after-scan PLC output |
| `remoteEligiblepost` | `ATT_Remote_Eligible` | after-scan PLC output |
| `remoteStartpost` | `ATT_Remote_Start` | after-scan PLC output |

`startDemand` abstracts pending or run-feedback-sealed Start state, not just the CSV's OWS Start request. The evaluator requires the monitor to pass for both Boolean `startDemand` values. `prevResetReqpost` is unobserved internal after-scan memory; the evaluator existentially projects it over `{0,1}`. This can assess visible outputs only.

## Saved results and rerun

From the mitigation repository root, set `SPHERE_DIR` to a checkout of the SPHERE procedure-usecases branch:

```bash
SPHERE_DIR=/path/to/sphere-usecases
python3 recovery_experiment/procedure_study/modelplex/evaluate_trace_monitor.py \
  --trace "$SPHERE_DIR/sector-water/attleboro-interconnection/runs/local-reference/generator_absent/tags.csv" \
  --output /tmp/attleboro_monitor_result.json
python3 recovery_experiment/procedure_study/modelplex/evaluate_trace_monitor.py \
  --trace "$SPHERE_DIR/sector-water/attleboro-interconnection/runs/local-reference/adversarial_scada_compromised/tags.csv" \
  --output /tmp/attleboro_monitor_compromised_result.json
```

The committed monitor SHA-256 is `48a2ca454ee13a15b2bcb8f84ca1af40a3b857dad544604d6bfd014e9a5f37a3`. The saved JSON results are [trace_monitor_result.json](trace_monitor_result.json) and [trace_monitor_compromised_result.json](trace_monitor_compromised_result.json).

| Saved trace | Trace SHA-256 | Bad-power rows checked | Visible controller result | PLC/delivered-output differences |
| --- | --- | ---: | --- | ---: |
| `generator_absent/tags.csv` | `0d9e689b08b3b86d831dad38ab35113a5449b89bcfcac0d826a9e2acaee090b6` | 25 of 30 | 25 match, 0 mismatch | 0 |
| `adversarial_scada_compromised/tags.csv` | `218fdd32f74bf3cf3bcfe8392c86e00b61645136c5bf20e7217284c830821618` | 25 of 30 | 25 match, 0 mismatch | 22 |

At tick 8, the evaluator flips each of `ATT_Remote_Eligible`, `ATT_Remote_Start`, and `ATT_Reset_Pending` in memory. The formula rejects all three mutated rows for both `startDemand` values. No saved trace changes. The compromised trace passes because its PLC outputs remain inhibited; `ATT_Delivered_Remote_Start` is downstream and is not a monitor input.

The bundled KeYmaera X 5.0 CLI's direct `-codegen` attempt on the bare `.kym` failed with `Error parsing archiveStart`. No C code generation or proof of the Python evaluator is claimed.
