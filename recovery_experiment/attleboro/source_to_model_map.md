# Attleboro source-to-model map

This map binds one bounded 2019 control-design slice to the authored SPHERE
surrogate and the separate KeYmaera X authority abstraction. It does not
assert installed Attleboro logic or a current operating procedure. The source
is CDM Smith's 20 March 2019 Addendum No. 1, Section 13305; locators below
are the printed/PDF pages recorded in the [source assessment](https://github.com/iotrustlab/sphere-usecases/blob/716e6d2e07ea00e7639f66567e3720fb6d1c2218/sector-water/attleboro-interconnection/docs/source_assessment.md).

The SPHERE [draft PR #136](https://github.com/iotrustlab/sphere-usecases/pull/136)
has remote head `716e6d2e07ea00e7639f66567e3720fb6d1c2218`, root tree
`7f5bbc06d38be0e06ab31cb6249e146d67ae31e9`. The Attleboro case tree
is `ec3319f9d3ac41352df2a21253f4af3aab7f22ca` (local bundle commit
`31cdf15a2029f828ec82993133e901de5543a5af`). The files used for this
map have SHA-256:

| SPHERE file, relative to `sector-water/attleboro-interconnection` | SHA-256 |
| --- | --- |
| `docs/source_assessment.md` | `367128c8697963bb126b4e68bb55ee963eb4427b66b731eb316395bba077de44` |
| `provenance/control_logic.yaml` | `c100c199900ef89556f42d082f3a4e9bb5c084d1e7dae38c2a6e385d028cc620` |
| `tag_contract.yaml` | `c01a555556f0af3b0538c1240187ff794302a27ba66c5fb293c74870db8da7d0` |
| `implementations/openplc/configs/openplc_map.yaml` | `71fbbd1adf0a7717e37a15433ffdd9a9026d71ab7ad989d6d7ab2e9a185f5ca3` |
| `implementations/openplc/st/attleboro_controller.st` | `e0fb9a37b81bc43820e5b525666f1b998615cfbfc438bdd46305db28f17119cc` |
| `implementations/openplc/st/attleboro_simulator.st` | `51b8380cc7a68e05725f1427438541c596b44eb7f9eb2e153f61c8012c89a1e1` |

The address and owner labels below come from that exact OpenPLC map. Both
programs declare the same located address; the map's owner identifies which
image writes the value. OWS requests are fixture writes to controller-owned
coils. `ATT_Delivered_Remote_Start` is an extra trace observation of the
simulator peer coil, not a contract/map tag. The bridge's live shuttles can
show a transient peer/controller difference across scans.

## 1. Momentary OWS Start and run seal

- **Source step:** General motor rule, PDF p. 16: momentary OWS Start is
  sealed by run confirmation; no confirmation within five seconds drops the
  start output. The source also permits a complete automatic-mode demand
  exception, which this surrogate does not implement.
- **Controller ST:** `attleboro_controller.st` lines 69–97 in behavior
  `att_power_authority` detect a rising Start, retain `start_pending`, seal
  on `in_ATT_Run_FB`, and expire after 50 scans at the declared 100 ms period.
  Line 97 gates either pending or sealed demand by `ATT_Remote_Eligible`.
- **Tag/address/owner:** `ATT_SCADA_Start_Request` coil 0 `%QX0.0`, controller;
  `ATT_Run_FB` coil 178 `%QX22.2`, simulator; `ATT_Remote_Start` coil 3
  `%QX0.3`, controller. `ATT_SCADA_Auto_Mode` coil 1 `%QX0.1`, controller,
  is recorded but the full automatic demand branch is not implemented.
- **Simulator:** `attleboro_simulator.st` lines 58–84 treat the delivered
  remote coil as a physical request only in Remote selection, require motor
  power and no trip, set run feedback after two simulator scans, and then
  advance illustrative flow.
- **Formal transition:** `remote_authority.kyx` abstracts the pending or
  sealed state as arbitrary `startDemand`; `remoteStart` may be 1 only if
  `remoteEligible=1` and `startDemand=1`. The 50-scan timer is checked in
  synthetic trace correspondence, not proved in the dGL safety theorems.
- **Assumption:** The 100 ms scan is a research fixture. The momentary input
  is delivered after observed remote eligibility in live captures; the
  controller is powered and can observe a stable input snapshot per scan.

## 2. Power failure and generator remove SCADA authority

- **Source step:** Loop 0110-1, printed pp. 8–9 / PDF pp. 21–22, removes
  the SCADA start bit on power failure. Loop 0128-1, printed p. 12 / PDF p. 25,
  removes SCADA Auto and Manual while MTS is on generator.
- **Controller ST:** lines 54–68 in `att_power_authority` set the retained
  reset latch when utility is unavailable, MTS is on generator, or generator
  run is indicated; they compute `ATT_Remote_Eligible` from power, latch,
  Remote selector and trip. Lines 71–74 clear pending/sealed Start when
  ineligible; line 97 keeps the output off.
- **Tag/address/owner:** `ATT_Utility_Available` coil 160 `%QX20.0`,
  `ATT_Generator_Running` coil 162 `%QX20.2`, `ATT_MTS_Generator` coil 163
  `%QX20.3`, and `ATT_Selector_Remote` coil 166 `%QX20.6` are simulator-owned.
  `ATT_Reset_Pending` coil 5 `%QX0.5`, `ATT_Remote_Eligible` coil 4 `%QX0.4`,
  and `ATT_Remote_Start` coil 3 `%QX0.3` are controller-owned.
- **Simulator:** lines 51–62 compute usable motor power separately from
  utility/MTS/generator readiness and keep the panel request separate from
  PLC authority. Generator readiness coil 161 `%QX20.1` is a simulator
  fixture input, not equivalent to generator running coil 162.
- **Formal transition:** The first archive entry checks the bad-power guard,
  assigns `resetPending:=1`, computes `remoteEligible:=0`, then
  `remoteStart:=0` regardless of `startDemand`. A separate diamond witness
  starts with `utility=0`, `mtsGen=0`, `genRun=0`, `startDemand=1` and reaches
  that poststate.
- **Assumption:** A powered PLC executes the modeled scan during the transfer;
  the source does not provide generator-transfer timing, controller power
  architecture, or a physical enforcement guarantee against output forgery.

## 3. Utility restoration requires later Power Fail Reset

- **Source step:** Loop 0128-1, printed p. 12 / PDF p. 25, requires both
  return to utility position and operator Power Fail Reset before SCADA use.
- **Controller ST:** lines 56–63 give bad power precedence over reset and
  clear `reset_pending` only on `out_ATT_Reset_Request AND NOT previous_reset`
  after power conditions return. A reset held throughout transfer is not a
  new edge. Lines 64–68 keep remote eligibility false while pending.
- **Tag/address/owner:** `ATT_Reset_Request` coil 2 `%QX0.2`, controller;
  `ATT_Reset_Pending` coil 5 `%QX0.5`, controller; utility coil 160 and MTS
  coil 163, simulator; remote eligibility coil 4, controller.
- **Simulator:** lines 52–54 resume motor power on utility when MTS is back;
  physical power restoration does not write the PLC reset request.
- **Formal transition:** The second archive entry assumes utility=1,
  MTS=0, generator-run=0, pending=1, and no new reset edge, and proves
  pending=1, eligible=0, start=0 after one scan. Its diamond witness uses
  `resetReq=prevResetReq=1` and reaches the same state.
- **Assumption:** A rising edge is the surrogate's implementation of a
  distinct later operator action; the source does not specify PLC edge
  detection. The eight live bundle initializations record a separate reset
  after the bridge has delivered utility input.

## 4. Local Hand and hardwired trips

- **Source step:** Loop 0110-1, printed pp. 6–9 / PDF pp. 19–22, separates
  Hand/Off/Remote and hardwired e-stop, winding-temperature,
  discharge-pressure, pH, and station-flood paths. Loop 0128-1 permits
  generator operation in Hand.
- **Controller ST:** lines 64–68 use `ATT_Selector_Remote` and `ATT_Trip`
  in the authority guard. The controller has no command over Hand selection
  or the independent hardwired drive cutout.
- **Tag/address/owner:** `ATT_Selector_Hand` coil 165 `%QX20.5`,
  `ATT_Selector_Remote` coil 166 `%QX20.6`, `ATT_Local_Operator_Present` coil
  167 `%QX20.7`, `ATT_Hand_Request` coil 168 `%QX21.0`; protection coils
  `ATT_EStop` 169, `ATT_High_Temp` 170, `ATT_High_Pressure_Switch` 171,
  `ATT_pH_Out_Of_Range` 172, `ATT_Flooded` 173, combined `ATT_Trip` 174
  `%QX21.6`; all are simulator-owned.
- **Simulator:** lines 55–75 combine the hardwired trip and choose exactly
  one panel path; physical run feedback drops without motor power or on trip,
  independently of a later PLC scan.
- **Formal transition:** The authority guard includes `selectorRemote` and
  `trip`; the model does not prove Hand operation, hardwired independence, or
  physical output enforcement.
- **Assumption:** Local actor presence, generator readiness, panel exclusivity,
  drive behavior and timing are research fixture choices, not verified
  Attleboro wiring.

## 5. Forward flow and no-flow observation

- **Source step:** Loop 0120-1, printed p. 11 / PDF p. 24, has forward-flow
  metering and a no-flow alarm with run confirmation. Loops 0125-1 and
  0150-2 add pressure/pH observations and interlocks.
- **Controller ST:** lines 100–109 in `att_service_evidence` distinguish
  run-with-no-flow alarm from service credited by fresh observed flow,
  pressure and protection bits.
- **Tag/address/owner:** `ATT_Run_FB` coil 178, `ATT_Actual_Service` coil 179
  `%QX22.3`, `ATT_Flow_Observation_Fresh` coil 177 `%QX22.1`, all simulator;
  `ATT_Actual_Flow` holding registers 2048–2049 `%MD0`,
  `ATT_Observed_Flow` 2050–2051 `%MD1`, and
  `ATT_Discharge_Pressure` 2052–2053 `%MD2`, all simulator; controller
  `ATT_Service_Established` coil 6 `%QX0.6` and `ATT_No_Flow_Alarm` coil 7
  `%QX0.7`.
- **Simulator:** lines 77–92 use a two-scan run delay, first-order flow,
  stale meter behavior, illustrative 5 L/s service and 90 psi pressure
  checks. These numbers are not site parameters.
- **Formal transition:** Flow, alarm and service are outside
  `remote_authority.kyx`. The bridge only requires a later
  `ATT_Actual_Service` witness in nominal and momentary scenarios; it does
  not prove hydraulic recovery.
- **Assumption:** Pump curve, flow/pressure thresholds, meter health and
  response timing are SPHERE research values. The physical flow, observed
  flow, and credited service tags are distinct by design.

## Verification boundary

The source-to-model map is a reviewed correspondence argument, not an
automated ST-to-dGL refinement theorem. The 22 source-hash-bound bundles
agree with the scoped bridge; synthetic rows check exact scan transitions,
while sampled OpenPLC rows check pointwise authority and scenario witnesses.
Two authority theorems and two nonvacuity diamonds have KeYmaera X proof
artifacts. The separate `ATT_Delivered_Remote_Start` observation shows 44
deliberate adversarial delivery bypass rows and one live trip transition
difference. No conclusion about today's plant, customer service, or full
automatic-mode demand follows from this map.
