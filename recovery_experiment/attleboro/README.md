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
outputs. The proof covers the controller's remote authority gate, including
both SCADA Auto and SCADA Manual because both depend on `remoteEligible`.
It assumes a powered controller executes the scan and samples stable inputs.
It does **not** prove local Hand operation, physical flow, service, protection
hardware, the integrity of an attacker-controlled output path, or a refinement
theorem from Structured Text to differential game logic.

| Formal variable | SPHERE use-case field |
| --- | --- |
| `utility`, `mtsGen`, `genRun` | `ATT_Utility_Available`, `ATT_MTS_Generator`, `ATT_Generator_Running` |
| `resetReq`, `prevResetReq`, `resetPending` | `ATT_Reset_Request`, retained `previous_reset`, `ATT_Reset_Pending` |
| `selectorRemote`, `trip`, `startReq` | `ATT_Selector_Remote`, `ATT_Trip`, `ATT_SCADA_Start_Request` |
| `remoteEligible`, `remoteStart` | `ATT_Remote_Eligible`, `ATT_Remote_Start` |

The source controller is
`sector-water/attleboro-interconnection/implementations/openplc/st/attleboro_controller.st`
in `iotrustlab/sphere-usecases`. Its latch and gate are the correspondence
target. The source tag contract and each bundle's recorded SHA-256 bindings
are checked by `bridge.py`; the bridge does not copy a stale source hash into
this repository.

## Reproduce

From the `mitigation-synthesis` repository root:

```bash
python3 -m recovery_experiment.attleboro.bridge \
  --usecase-dir /path/to/sphere-usecases/sector-water/attleboro-interconnection

python3 -m unittest recovery_experiment.tests.test_attleboro_bridge -v

python3 -m recovery_experiment.attleboro.verify_authority \
  --jar /path/to/keymaerax.jar --z3 /path/to/z3 \
  --output-dir recovery_experiment/attleboro/proof_records
```

The checked-in `proof_records` were produced with KeYmaera X 5.1.1 and Z3.
The runner reports `VERIFIED` only when both archive entries are proved. This
is offline proof evidence, **not** a reviewed Dr.ICS runtime certificate.

`bridge.py` compares every synthetic reference row with the exact one-scan
reset latch and authority equations. OpenPLC captures are sampled less often
than the PLC scans, so it checks only the pointwise authority and start
outputs, plus the implication from bad power to reset pending; it does not
invent the latch state before the first sample or infer missed reset edges.
It counts any mismatch between `ATT_Delivered_Remote_Start` and the PLC's
`ATT_Remote_Start` separately: a compromised fixture may drive the physical
path despite a correctly blocked PLC output.

`MATCHED` means those specific source-bound observations agree. It does not
establish a current-site guarantee or service restoration. New physical or
service properties require a separate model, proof, and review.

The checked-in correspondence receipt binds the clean SPHERE use-case subtree
at commit `202041371e20c8578db44dbe87a17f71d9fbcfd2`. The 20 bundles point
to source-code commit `758e7b27f9ce88a44bf6eab9d9ad3377b7aec7c9` and pass
the current source-hash checks: 13 synthetic bundles and seven OpenPLC
captures, 667 rows in total. Exactly 434 synthetic latch transitions were
checked. Forty-four delivered-output differences across the two adversarial
bundles are reported separately, because they show an enforcement-path bypass
outside the PLC theorem. The seven live bundle metadata records an explicit
post-start reset after utility input before scenario execution; the checker
does not treat that initialization as part of the formal procedure.
