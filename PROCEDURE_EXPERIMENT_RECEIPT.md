# Procedure experiment receipt

Recorded 2026-11-17. This receipt binds three **research use cases** to the
`iotrustlab/sphere-usecases` branch tip
`8814de216dda5e9c64ffa9f9a2c0061e6d6b041d`. It records runnable evidence
and its claim boundary. The local files were checked against the clean case
subtrees at that tip. A source document supplies a procedure description;
the Structured Text, fixture timing, thresholds, and plant behavior remain
research implementations unless the case assessment says otherwise.

The source repository's [draft PR #136](https://github.com/iotrustlab/sphere-usecases/pull/136)
has remote head `716e6d2e07ea00e7639f66567e3720fb6d1c2218`. Its Git tree
`7f5bbc06d38be0e06ab31cb6249e146d67ae31e9` matches the local branch tip
`8814de216dda5e9c64ffa9f9a2c0061e6d6b041d` exactly. The code and bundle
commits in the table are local provenance commits; the remote PR head and
case tree IDs identify the published bytes.

| Case | Source code commit | Bundle commit | Case Git tree at bundle commit | Result |
| --- | --- | --- | --- | --- |
| Attleboro interconnection | `f42a177e63dcdbd8187c7922c4daa1765d168f17` | `31cdf15a2029f828ec82993133e901de5543a5af` | `ec3319f9d3ac41352df2a21253f4af3aab7f22ca` | 22/22 source-bound traces matched; two scoped authority theorems proved |
| Merwin hydro | `8814de216dda5e9c64ffa9f9a2c0061e6d6b041d` | `8814de216dda5e9c64ffa9f9a2c0061e6d6b041d` | `e825cc0af6459044a5aef1ac84d6845ac4756b1e` | 12/12 disposable OpenPLC assessments passed |
| Second Polish CHP | `fe91a717220e076b13112e3b8acd953e93c05433` | `f1d9da7c2a5337de068a2605cd2c04dd35051026` | `3bbe96d73b2a450ac238f58504c8a1ff6cf91ee7` | 12/12 independent lifecycle replays passed |

The Git tree IDs pin each complete case directory, including scenarios,
bundles, assessments, and runtime receipts. SHA-256 values below make the
main executable inputs explicit. File paths in the hash table are relative to
the named case directory.

## Bounded abstraction maps and observations

### Attleboro: power transfer and remote authority

The source is CDM Smith's 2019 interconnection control-design addendum,
especially Loop 0110-1 and the transfer/power-fail loops cited by the
[SPHERE source assessment](https://github.com/iotrustlab/sphere-usecases/blob/716e6d2e07ea00e7639f66567e3720fb6d1c2218/sector-water/attleboro-interconnection/docs/source_assessment.md).
It is procurement/design evidence, not an installed controller or current
site procedure. The authored controller and simulator separate OWS requests,
PLC authority, generator/MTS state, physical Hand, hardwired trip, and flow.

| Source-bounded relation | Executable representation | Checked evidence |
| --- | --- | --- |
| Utility loss, MTS generator position, or generator running removes SCADA authority | `ATT_Utility_Available`, `ATT_MTS_Generator`, `ATT_Generator_Running` set retained `ATT_Reset_Pending`; `ATT_Remote_Eligible` and `ATT_Remote_Start` are false | KeYmaera X one-scan theorem and 22 trace bundles |
| Normal power return does not itself restore SCADA authority | A **new rising** `ATT_Reset_Request` after restoration clears the pending latch | Second KeYmaera X one-scan theorem; synthetic latch transitions |
| OWS Start is momentary and run feedback seals its output | `ATT_SCADA_Start_Request` edge starts `start_pending`; `ATT_Run_FB` seals `ATT_Remote_Start`; unconfirmed start expires after 50 controller scans | 464 synthetic Start transitions, momentary synthetic and OpenPLC traces |
| Generator Hand is a local physical path | Selector, local operator, Hand request, motor power, and trip reside in the simulator | Trace scenarios only; outside the authority proof |

The [granular source-to-model map](recovery_experiment/attleboro/source_to_model_map.md)
pins each source step to its ST line/behavior, tag, Modbus address and owner,
simulator behavior, formal transition, assumption, and source artifact hashes.

The proof archive is
[`recovery_experiment/attleboro/remote_authority.kyx`](recovery_experiment/attleboro/remote_authority.kyx)
with the checked-in [verification record](recovery_experiment/attleboro/proof_records/remote_authority_verification.json).
KeYmaera X 5.1.1 with Z3 returned `PROVED` for both entries; the record hashes
the model and nonempty proof artifacts. `startDemand` in those theorems is
arbitrary pending or sealed demand, so the proof remains valid after the
momentary-start implementation. It does not prove the five-second timer,
physical service, the Hand path, hardwired enforcement against a forged
output, ST refinement, or current Attleboro behavior.
The source's general motor rule allows a complete automatic-mode demand
exception. This bounded surrogate implements the momentary OWS Start path and
the shared SCADA authority gate; it does not implement the full automatic
demand path. The authority theorems hold for either SCADA mode position
because demand is arbitrary but eligibility is required in both.

The separate [nonvacuity archive](recovery_experiment/attleboro/remote_authority_nonvacuity.kyx)
has two proved diamond formulas. Their concrete antecedents satisfy the
guards and admit the post-scan states below; these model executions prevent
the box theorems from resting on empty antecedents or dead guarded paths.

| Witness | Concrete pre-scan assignment | Reachable post-scan assignment |
| --- | --- | --- |
| Bad utility | `utility=0, mtsGen=0, genRun=0, selectorRemote=1, trip=0, startDemand=1, resetPending=0, resetReq=0, prevResetReq=0` | `resetPending=1, remoteEligible=0, remoteStart=0` |
| Held reset after restoration | `utility=1, mtsGen=0, genRun=0, selectorRemote=1, trip=0, startDemand=1, resetPending=1, resetReq=1, prevResetReq=1` | `resetPending=1, remoteEligible=0, remoteStart=0` |

Both entries returned `PROVED` with KeYmaera X 5.1.1 and Z3. The
[authority verification record](recovery_experiment/attleboro/proof_records/remote_authority_verification.json)
and [nonvacuity verification record](recovery_experiment/attleboro/proof_records/remote_authority_nonvacuity_verification.json)
contain the model and nonempty `.kyp` artifact SHA-256 values. The authority
artifact digests are `7951d25cb075407e5b51a5d31153b71a3b67ff6e3e7b13fc3fd53df899312458`
and `fe48994af3051a5c9020c3601257de93ad1fbb2eb13dab67d891cf82e2f5debf`;
the nonvacuity artifact digests are
`555afc8490ad056757946a6f38fa8f413b96f6676eba850bfeab61ddc8c13686`
and `9df4a8fc593064b2d6665f9ac72b9e49274a031343a0dcc046e694379c99b1e9`.

The [correspondence receipt](recovery_experiment/attleboro/proof_records/correspondence_receipt.json)
binds 14 synthetic bundles and eight OpenPLC captures: 22/22 `MATCHED`, 727
observed rows, 464 one-scan reset-latch transitions, and 464 one-scan Start
transitions. Nominal and momentary Start bundles include an actual-service
tag witness after startup. Forty-five `ATT_Delivered_Remote_Start` differences
are reported separately: 44 in deliberate adversarial bypass fixtures and
one sampled live trip transition. Physical delivery is outside the PLC theorem.
Live polls can skip PLC scans and reset pulses, so the bridge
checks only pointwise authority and the nominal/momentary scenario witnesses
there. The eight live captures include a separate post-start reset after
utility input, and their driver waits for observed remote eligibility before
issuing OWS Start.

### Merwin: historical startup modes on a representative hydro plant

PacifiCorp Exhibit H §H.6.1 (2004) distinguishes Local Manual, Local Auto,
and HCC Remote Auto starts; the [SPHERE source assessment](https://github.com/iotrustlab/sphere-usecases/blob/716e6d2e07ea00e7639f66567e3720fb6d1c2218/sector-energy/merwin-hydro/source_assessment.md)
records the exact locators and limits. The executable case adapts the existing
Olmsted-derived hydro backend. It is not a Merwin as-built model or a current
operating order.

| Source-bounded step | Executable representation | Acceptance observation |
| --- | --- | --- |
| Local Manual: local operator, lube pump and oil level, then manual sync and close | `MER_Local_Operator_Present`, lube/oil guards, `MER_Local_Start_Cmd`, followed by fresh local sync and close requests | At speed, synchronizing state, breaker command/contact, and generation in order |
| Local Auto: local start with lube/oil checks, automatic sync and close | Local request with auto selector; backend automatic sequence | Same physical feedback, without manual sync/close commands |
| HCC Remote Auto: remote selector and normal auxiliaries, HCC start | `MER_Mode_Remote_Auto`, auxiliary/HCC/link guards, `MER_HCC_Start_Cmd` | Same ordered feedback; wrong actor and lost link are denied |

All 12 recorded OpenPLC scenarios have `PASS` assessments. I independently
reran the evaluator in a temporary copy and reproduced every checked-in
assessment. It requires ordered speed, sync, close request, and contact
milestones, followed by **three consecutive samples** with running state,
closed-breaker feedback, and at least 1 MW **on the same rows**. The 1 MW
threshold, timing, remote-link fault, and representative plant dynamics are
research choices. The seven focused tests pass, including rejection of
disjoint breaker/power samples and out-of-order closure. No KeYmaera X or
current-site proof is claimed.

### Second Polish CHP: device recovery, not process restart

The [SPHERE source assessment](https://github.com/iotrustlab/sphere-usecases/blob/716e6d2e07ea00e7639f66567e3720fb6d1c2218/sector-energy/poland-2025-chp-recovery/source_assessment.md)
maps CERT Polska's follow-up report to reported Siemens reset/backup reload,
WAGO failed recovery, and device-log loss. It does not supply the CHP control
program, backup review method, process permissives, or customer-service
mechanism. The fixture therefore models device lifecycle only.

| Source-bounded milestone | Executable representation | Claim limit |
| --- | --- | --- |
| Factory reset attempted | `reset` transition requires engineering access; Siemens-like fixture can boot, WAGO-like fixture remains unbootable | Reset is simulated, including in OpenPLC bundles |
| Available logic backup reloaded | `load_backup` requires bootability plus available, compatible, reviewed research backup | Backup provenance and compatibility are explicit research guards |
| Recovered controller executes | `start_runtime` is simulated in fixture runs; successful OpenPLC compile and two increasing native `%MD0` scan-counter reads establish benign runtime execution | A heartbeat does not establish cyber trust, turbine/process readiness, or customer service |

Eight fixture and four OpenPLC bundles replayed independently: 12/12
`REPLAY_PASS`. Two OpenPLC bundles recorded `EXECUTED` benign heartbeat;
three fixture bundles recorded `SIMULATED` runtime; seven bundles did not
establish runtime. Every assessment leaves process restart and customer
service `NOT_ESTABLISHED` and cyber trust `UNKNOWN`. The labeled
persistent-influence case is a counterfactual, not a reported second attack.
Seven lifecycle tests pass, including negative claim and fabricated-state
checks. No formal proof or actual CHP restart is claimed.

### Positive and negative trace witnesses

| Case and pinned bundle | Precise observed outcome | Interpretation |
| --- | --- | --- |
| Attleboro `runs/local-reference/nominal_remote` | `ATT_Actual_Service=1` in 28 of 30 scans; `ATT_Remote_Start=1` in all 30; zero reset-pending scans | Positive research service witness for available utility and Remote selection |
| Attleboro `runs/local-reference/generator_absent` | After MTS changes to Generator (scans 8–29), `ATT_Reset_Pending=1` in all 22 scans, `ATT_Remote_Start=0` in all 22, and `ATT_Actual_Service=0` in all 22 | Negative service witness when generator power is unavailable; three earlier service scans and one residual-flow scan at utility loss are not counted as restored service |
| Merwin `runs/local_auto` | Assessment `PASS`; breaker contact at 107.615039 s, sustained same-row generation at 108.127814 s | Positive startup to representative initial generation |
| Merwin `runs/missing_lube` | Assessment `PASS` for expected denial; `start_denied=true`, breaker contact false, generation false, maximum power 0 MW | Negative guard witness, not a successful start |
| CHP `runs/siemens_compatible_openplc` | Benign heartbeat execution `EXECUTED`; device recovery `SIMULATED`; process and customer service `NOT_ESTABLISHED`; cyber trust `UNKNOWN` | Positive device-runtime witness with process outcome deliberately undetermined |
| CHP `runs/wago_nonbootable_openplc` | Benign runtime and device recovery `NOT_ESTABLISHED`; process and customer service `NOT_ESTABLISHED` | Negative bootability/recovery witness |

## Source artifact SHA-256

| Case and file | SHA-256 |
| --- | --- |
| Attleboro `tag_contract.yaml` | `c01a555556f0af3b0538c1240187ff794302a27ba66c5fb293c74870db8da7d0` |
| Attleboro `implementations/openplc/configs/openplc_map.yaml` | `71fbbd1adf0a7717e37a15433ffdd9a9026d71ab7ad989d6d7ab2e9a185f5ca3` |
| Attleboro `implementations/openplc/st/attleboro_controller.st` | `e0fb9a37b81bc43820e5b525666f1b998615cfbfc438bdd46305db28f17119cc` |
| Attleboro `implementations/openplc/st/attleboro_simulator.st` | `51b8380cc7a68e05725f1427438541c596b44eb7f9eb2e153f61c8012c89a1e1` |
| Attleboro `scenarios/cases.yaml` | `9cfb4f842282d474947628b4047f9eb626306f320e98430dd69afea0e25b333b` |
| Attleboro `model/core.py` | `484cee751d2b9568d399c9217b0bf33df2d59baee4f43a0dede37b2c6609fcf2` |
| Attleboro `model/run.py` | `0d600acdbebf2d8d28bb9b3dcf1c49382d0117b24dd644a0b59bd79dc459f2df` |
| Attleboro `model/live.py` | `19f3a596b276affc9067cc0ebaf9f382755a3b7eaa33eba2cdb13d16a2acfd6a` |
| Merwin `tag_contract.yaml` | `b242a9afdb56e47e6406259580e9017ca4c36e90d2d2b5a84a72229534735d86` |
| Merwin `implementations/openplc/configs/openplc_map.yaml` | `3e41e4b2d03a69436348f5693fbfb33d8c583d6da2afdebb88679614f746eca6` |
| Merwin `implementations/openplc/st/merwin_controller.st` | `c8b74bd88e640ea2b2caf5f7eb4e94612c5d460c02f6bebfe0cfc9adecfcdaba` |
| Merwin `implementations/openplc/st/merwin_simulator.st` | `cde204ba7a533f63b1b09df7f047cc3579822218ec7180b5b6f3c37f3d3b75ec` |
| Merwin `run_scenario.py` | `5c8c3d7fa0eaf967c6b41dd01d803ffd57e41270dd7e7c87e83229f4714a4aa4` |
| Merwin `evaluate.py` | `80cc068e9019061a9cdad0546ed574e841d22c8acbd5ac2318b1d9b959c9ecf5` |
| CHP `tag_contract.yaml` | `407327f971f8034f3b7f76ee4c1989502f31a866105b2197572fa9c647618f4e` |
| CHP `implementations/openplc/configs/openplc_map.yaml` | `3222eebe504ccd84de8a9bf1dba0de475b1c498337ed4ba62c49537c0a712e8b` |
| CHP `implementations/openplc/st/chp_heartbeat.st` | `74b0abb8b82c112f5aa688b53caaad52823731053a88fd18d9ee4715e801d7a9` |
| CHP `lifecycle.py` | `d8e659bab45b241b0377917d0d22f3502b29937098f75294fb4c3bd10eb63f7c` |
| CHP `replay.py` | `22b9e622445488d00aa4730671031fc6e7b8e8c3295e3e7d3b7795030e4cff47` |

The Attleboro model SHA-256 is
`0a8d8e93051eca6668caa4995d1828851b2c225ee575f987620a582095540c18`;
the nonvacuity model SHA-256 is
`07e3dbe4aa62cc02dd0ccc98292006f6a75158a45628791c075d4981304d36e0`;
the bridge SHA-256 is
`652ba4a2cd22bf7e6af47113086e7518504bbadba31b6b5e7779920444acd6f2`;
the source-to-model map SHA-256 is
`99d2b735803b989c1c765fe1acfa26e584f63cf56b6e2463d65271c0ff0fc33d`.
Merwin's 12 runtime receipts pin the disposable OpenPLC image
`sha256:159e1c4fe84db6cd05ea630d6f1e71bbd75f0d29cc75e091b5ceb6ff4ccbf529`;
the two CHP OpenPLC heartbeat confirmations use the same image. A Git tree
pin and file hash establish source identity, not hardware attestation.

## Rerun commands

Use the pinned commits above and the dependencies listed in each SPHERE case
README. From the `mitigation-synthesis` root:

```bash
python3 -m recovery_experiment.attleboro.bridge \
  --usecase-dir /path/to/sphere-usecases/sector-water/attleboro-interconnection
python3 -m unittest recovery_experiment.tests.test_attleboro_bridge -v
python3 -m recovery_experiment.attleboro.verify_authority \
  --jar /path/to/keymaerax.jar --z3 /path/to/z3 \
  --output-dir recovery_experiment/attleboro/proof_records
```

From `sphere-usecases/sector-energy/merwin-hydro`, preferably in a disposable
copy because evaluation rewrites `assessment.json`:

```bash
python3 evaluate.py scenarios/local_auto.yaml runs/local_auto
python3 -m unittest discover -s tests -v
```

From `sphere-usecases/sector-energy/poland-2025-chp-recovery`:

```bash
python3 replay.py runs/siemens_compatible_openplc
python3 -m unittest discover -s tests -v
```

### Commands actually executed for this receipt

The following commands use the real local paths and exited 0. Merwin was
evaluated in a copy to avoid changing pinned bundle files; the CHP test copy
was initialized as a temporary Git repository because its fixture driver
records `git rev-parse HEAD`.

```bash
# Working directory: /Users/lag/Development/mitigation-synthesis
python3.12 -m recovery_experiment.attleboro.bridge \
  --usecase-dir /Users/lag/Development/sphere-usecases/sector-water/attleboro-interconnection \
  --output recovery_experiment/attleboro/proof_records/correspondence_receipt.json
python3.12 -m recovery_experiment.attleboro.verify_authority \
  --jar /Users/lag/Downloads/keymaerax.jar --z3 /opt/homebrew/bin/z3 \
  --output-dir recovery_experiment/attleboro/proof_records --archive authority
python3.12 -m recovery_experiment.attleboro.verify_authority \
  --jar /Users/lag/Downloads/keymaerax.jar --z3 /opt/homebrew/bin/z3 \
  --output-dir recovery_experiment/attleboro/proof_records --archive nonvacuity
python3.12 -m unittest recovery_experiment.tests.test_attleboro_bridge -v
python3 -m unittest discover -s recovery_experiment/tests -v

# Working directory: /private/tmp/merwin-receipt-validation
for spec in scenarios/*.yaml; do case_id=${spec#scenarios/}; python3.12 evaluate.py "$spec" "runs/${case_id%.yaml}" >/dev/null || exit 1; done

# Working directory: /private/tmp/sector-energy/merwin-hydro
python3.12 -m unittest discover -s tests -v

# Working directory: /Users/lag/Development/sphere-usecases/sector-energy/poland-2025-chp-recovery
for bundle in runs/*; do python3.12 replay.py "$bundle" >/dev/null || exit 1; done

# Working directory: /private/tmp/chp-receipt-validation, after temporary git init/commit
python3.12 -m unittest discover -s tests -v
```

The results were: Attleboro bridge 22/22 `MATCHED`, four KeYmaera X entries
`PROVED` across the safety and nonvacuity archives, and nine bridge tests
passed. The canonical deterministic suite ran 173 tests with 12 optional
CLEO integration skips and otherwise passed. Merwin 12/12 assessments
reproduced with seven tests passed; CHP
12/12 `REPLAY_PASS` with seven tests passed. The authority and witness
verification records and proof hashes are linked above.

### Translation and CLEO availability

No `hyplc` or `cleo` executable and no importable `cleo` package were found
in the active Python 3.12 environment; the canonical checkout's
`.external/cleo` is absent. Its bootstrap script expects the checksum-verified
CLEO 0.1.0 artifact, so CLEO was not run. KeYmaera X 5.1.1 and Z3 were
available and produced the four proofs recorded above.

HyPLC translator source exists locally at
`/Users/lag/Development/hyplc-st-to-hp`, but the installed translator command
below exited 1 with `Could not deserialize ATN with version 3 (expected 4)`:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/lag/Development/hyplc-st-to-hp/hyplc-st-to-hp/antlr_env/bin/python \
  /Users/lag/Development/hyplc-st-to-hp/hyplc-st-to-hp/hyplc-st-to-hp.py \
  --STFile /Users/lag/Development/sphere-usecases/sector-water/attleboro-interconnection/implementations/openplc/st/attleboro_controller.st
```

A separate parser-regeneration trial in `/private/tmp` then rejected the
same bound ST at line 8: `mismatched input 'AT' expecting {',', ':'}` and
produced no hybrid program. The grammar also lacks declaration `:=`
initialization used for retained reset/Start bits and the timeout counter.
The KeYmaera X JAR contains no HyPLC CLI classes. Thus the current ST is
outside the available translator subset, and no ST-to-dGL refinement or
CLEO synthesis result is claimed.

The independent check for this receipt evaluated all 12 Merwin scenarios in
a disposable copy and compared the resulting assessments for JSON equality
with the recorded assessments. It replayed all 12 CHP bundles from their
recorded requests and scenario inputs, and ran both cases' seven focused
tests. The Attleboro bridge checked all 22 final bundles and its nine
focused tests; the two authority theorems were re-proved with KeYmaera X
5.1.1 and Z3. In the source repository, scoped regressions also passed 31
existing pytest tests plus the Olmsted and Rovisys provenance/translation
checks. Native host `iec2c` was skipped because the available binary is a
Linux ELF; the recorded OpenPLC runtime compilations ran in Docker. These are
bounded executable observations and one scoped
formal authority proof, not an assurance statement for any live facility.

## Remote CI status

The [SPHERE PR #136 provenance run #177](https://github.com/iotrustlab/sphere-usecases/actions/runs/44171932137)
reported failure before its `provenance`, `unit-tests`, and
`te-downs-vogel-model` jobs started. GitHub displayed an account payment or
spending-limit block; no remote test result is claimed. The local full gate
rerun passed 131 unit tests with one skip; the HTTP loopback case passed when
loopback access was allowed. Downs–Vogel passed 26 tests with 14 skips, and
the local provenance, translation, binding, and render checks passed. The
remote CI billing block remains outside these local validation results.
