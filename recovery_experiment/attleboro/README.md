# Attleboro power and authority bridge

This isolated experiment formalizes one control-authority slice of the **2019
Attleboro emergency interconnection control design**. The corresponding
SPHERE use case is an authored research surrogate, not installed Attleboro
logic or a current operating procedure. It sits beside the existing synthetic
parallel-pump Dr.ICS recovery family; its certificates and policy selection do
not apply here.

## Formal boundary

`remote_authority.kyx` contains two one-scan KeYmaera X theorems:

1. If utility is unavailable, MTS is on generator, or the generator is
   running, the controller sets `resetPending=1`, `remoteEligible=0`, and
   `remoteStart=0`.
2. After utility and MTS return to normal, a pending reset remains pending and
   remote outputs stay off until a **new rising** reset request occurs. A
   request held from the generator interval is not a new edge.

The game uses guarded, exhaustive choices for the eligibility and start
outputs. `startDemand` abstracts either a pending momentary Start or a Start
sealed by run feedback; its value is arbitrary in these safety theorems. The
proof covers the controller's remote authority gate, including
both SCADA Auto and SCADA Manual because both depend on `remoteEligible`.
It assumes a powered controller executes the scan and samples stable inputs.
It does **not** prove local Hand operation, physical flow, service, protection
hardware, the integrity of an attacker-controlled output path, or a refinement
theorem from Structured Text to differential game logic.
The source's general motor rule permits a complete automatic-mode demand
exception. This surrogate implements momentary OWS Start and the shared
authority gate, not the full automatic demand path. The authority proof
applies to either SCADA mode position because `startDemand` is arbitrary.

| Formal variable | SPHERE use-case field |
| --- | --- |
| `utility`, `mtsGen`, `genRun` | `ATT_Utility_Available`, `ATT_MTS_Generator`, `ATT_Generator_Running` |
| `resetReq`, `prevResetReq`, `resetPending` | `ATT_Reset_Request`, retained `previous_reset`, `ATT_Reset_Pending` |
| `selectorRemote`, `trip` | `ATT_Selector_Remote`, `ATT_Trip` |
| `startDemand` | Controller `start_pending OR start_sealed`; the OWS `ATT_SCADA_Start_Request` sets the pending state on a rising edge |
| `remoteEligible`, `remoteStart` | `ATT_Remote_Eligible`, `ATT_Remote_Start` |

The source controller is
`sector-water/attleboro-interconnection/implementations/openplc/st/attleboro_controller.st`
in `iotrustlab/sphere-usecases`. Its latch and gate are the correspondence
target. The source tag contract and each bundle's recorded SHA-256 bindings
are checked by `bridge.py`; the bridge does not copy a stale source hash into
this repository.
The [source-to-model map](source_to_model_map.md) records each source step's
ST behavior, tag/Modbus address and owner, simulator behavior, formal
transition, assumption, and source hash.

## Reproduce

From the `mitigation-synthesis` repository root:

```bash
python3 -m recovery_experiment.attleboro.bridge \
  --usecase-dir /path/to/sphere-usecases/sector-water/attleboro-interconnection

python3 -m unittest recovery_experiment.tests.test_attleboro_bridge -v

python3 -m recovery_experiment.attleboro.verify_authority \
  --jar /path/to/keymaerax.jar --z3 /path/to/z3 \
  --output-dir recovery_experiment/attleboro/proof_records

python3 -m recovery_experiment.attleboro.verify_authority \
  --jar /path/to/keymaerax.jar --z3 /path/to/z3 \
  --archive nonvacuity \
  --output-dir recovery_experiment/attleboro/proof_records
```

The checked-in `proof_records` were produced with KeYmaera X 5.1.1 and Z3.
The runner reports `VERIFIED` only when both archive entries are proved. This
is offline proof evidence, **not** a reviewed Dr.ICS runtime certificate.
The separate nonvacuity archive proves two diamond formulas with concrete
antecedent assignments. One starts with unavailable utility and Start demand
on; the other starts with restored utility and a held reset request. Both
have reachable post-scan states with reset pending and remote authority/start
off. These witnesses show the safety theorem antecedents and guarded
branches can execute in the model.

`bridge.py` compares every synthetic reference row with the one-scan reset
latch, authority equations, and pending/sealed momentary Start transition. The
start check accounts for the reference model's one-scan feedback delay and
the 50-scan no-confirmation timeout. OpenPLC captures are sampled less often
than the PLC scans, so it checks pointwise authority and the implication that
remote Start must be off without eligibility, plus the implication from bad
power to reset pending. It cannot reconstruct skipped start/reset pulses or
the retained state before the first sample.
For the `nominal_remote` and `momentary_remote_start` scenarios, it also
requires an `ATT_Actual_Service` tag witness after startup; the momentary case
requires run feedback while Start remains on after the OWS request is released.
Those are observed scenario outcomes, not formal hydraulic-service theorems.
It counts any difference between `ATT_Delivered_Remote_Start` and the PLC's
`ATT_Remote_Start` separately. Only differences in the deliberate adversarial
fixture are classified as a bypass; a sampled live trip transition can also
show a delivery difference while controller and peer images are shuttled.

`MATCHED` means those specific source-bound observations agree. It does not
establish a current-site guarantee or service restoration. New physical or
service properties require a separate model, proof, and review.

The checked-in correspondence receipt binds the clean SPHERE use-case subtree
at commit `31cdf15a2029f828ec82993133e901de5543a5af`. All 22 bundles point
to source-code commit `f42a177e63dcdbd8187c7922c4daa1765d168f17` and pass
the current source-hash checks: 14 synthetic bundles and eight OpenPLC
captures, 727 rows in total. Exactly 464 synthetic latch and 464 synthetic
Start transitions were checked. Forty-five delivered-output differences are
reported separately: 44 in the deliberate adversarial bypass fixtures and
one sampled live trip transition. Physical delivery remains outside the PLC
theorem. The eight live bundle metadata records an explicit
post-start reset after utility input before scenario execution; the checker
does not treat that initialization as part of the formal procedure. The
live driver orders the OWS Start after observed remote eligibility so its
initial pulse is accepted by the PLC.
