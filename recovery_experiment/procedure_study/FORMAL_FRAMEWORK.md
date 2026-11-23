# Formal lens for the three procedure cases

Recorded 2026-11-20. This is a **research specification** for bounded experiments. The associated case-side calculations are in `iotrustlab/sphere-usecases/experiments/procedure_study`. It does not replace the source assessments, installed
plant procedures, or the proved Attleboro archive.

## 1. What is the object?

For workflow `w`, proposed action `a`, and property `Φ`, use the bounded
workflow slice from the attached NSF proposal:

```text
S_w = (P_w, O_w, R_w, U_w, E*_w, A_w, Φ_w, Y_w)
```

`P` is the process/controller slice; `O` observations and provenance; `R`
human and agent roles; `U` request and action authority; `E*` verification,
handoff, and completion obligations; `A` candidate actions; `Φ` hard safety
and minimum-service properties; `Y` observable outcomes. The proposal's T1
would compile an accepted slice into `Γ_w`; T2 would estimate coordination
state; T3 would decide at a declared adapter. Those are **proposed PRISM
interfaces**, not capabilities established by the three cases. See the
underlying NSF proposal (not redistributed with this experiment),
System and Threat Model, PDF p. 5, and Thrust 1, PDF pp. 5–6.

## 2. Treat actor, interface, controller, and plant as typed nodes

Define a typed graph `G=(V,E,kind,provenance)`. In the local
[actor/interface model](https://github.com/iotrustlab/sphere-usecases/blob/codex/procedure-usecases/experiments/procedure_study/network_cost/ACTOR_INTERFACE_README.md), nodes include
human, agent, interface, controller, actuator, plant, and observer. Edges are
not interchangeable:

| Relation | Question | Attleboro example |
| --- | --- | --- |
| `Access(r,i,x)` | Can actor `r` reach interface `i` in this state and time? | Local human at VFD keypad; an offsite software agent cannot press it. |
| `Authority(r,a,x)` | May this role request or perform action `a` in the selected mode? | Remote operator's SCADA authority ends on generator; physical Hand belongs to a local actor. |
| `PathUp(i,a,x)` | Is a candidate command route available? | OWS→PLC or keypad→VFD; no cable-level redundancy is asserted. |
| `Accept_C(a,x)` | Did the controller accept the request? | `ATT_Remote_Eligible` and `ATT_Remote_Start` after one scan. |
| `Deliver(a,x)` | Did the output reach an actuator? | This can differ from PLC output in a compromised-downstream fixture. |
| `Respond_P(a,x)` | Did the plant produce flow or power? | `ATT_Actual_Flow` is separate from motor `Run_FB`. |
| `Establish_O(x)` | Can a fresh observer establish the effect? | Stale flow observation cannot establish water service. |

The bounded candidate request is

```text
Candidate(r,i,a,x,D) = Access(r,i,x) ∧ Authority(r,a,x)
                     ∧ PathUp(i,a,x) ∧ EarliestEffect(r,i,a,x) ≤ D.
```

`Candidate` is not `Deliver`, `Respond_P`, or `Establish_O`. For a local Hand
path, PLC acceptance may be inapplicable; the local actor model leaves all
downstream outcomes unresolved. An agent may request a timed human handoff
through a **proposed** queue, while direct VFD access stays false. The
interface's access/location labels are analytic, not surveyed floor
coordinates.

## 3. Give the hybrid transition its owners and assumptions

Use state `x=(mode, latch, role/location, path status, plant variables,
evidence, clocks)`. A conceptual round is:

```text
environment disturbance/fault → eligible human or controller choice
→ discrete PLC/actuator transition → plant flow x' = f_mode(x,u,d)
→ sampled, provenance-bearing observation → next decision state.
```

The environment can choose only disturbances declared in a case. An
operator/agent can choose only actions assigned to its authority; an agent
cannot acquire physical access by graph reachability. Source-backed
protections remain hard constraints. The response budget follows the
proposal's T3 form:

```text
T_verify + T_validate/decide + T_actuate + T_physical + T_reserve ≤ T_Φ.
```

The current Attleboro KeYmaera X theorem covers a **discrete PLC scan** under
an intact enforcement boundary. The separate [CLEO flow envelope](cleo/attleboro_sampled_flow.envelope)
covers one authored finite flow phase. No theorem composes the complete
actor/controller/plant/observer round. Merwin has a representative
Olmsted-derived hydro simulator but no comparable proved archive. CHP has a
discrete device lifecycle plus a separate [generic ODE surrogate](https://github.com/iotrustlab/sphere-usecases/blob/codex/procedure-usecases/experiments/procedure_study/chp_surrogate/README.md),
not a Polish-plant model.

## 4. State the claim before running a prover

The source-bounded Attleboro authority property is, schematically,

```text
(bad power ∨ restored utility with reset still pending and no new reset edge)
→ [one modeled PLC scan] (remoteEligible=0 ∧ remoteStart=0).
```

The [canonical proof archive](../attleboro/remote_authority.kyx)
has two KeYmaera X safety proofs and two separate reachable witness proofs.
The [source-to-model map](../attleboro/source_to_model_map.md)
and 22 checked bundles support bounded correspondence; HyPLC did not
translate the full bound ST. A generated ModelPlex controller formula matched
25/25 applicable scans in two traces and rejected three mutated PLC outputs,
yet [one compromised trace](modelplex/TRACE_MONITOR_RECEIPT.md)
still had 22 downstream delivery differences. Thus a proof of the controller
gate is not a proof of physical service or a deployed plant monitor.

For Merwin, a useful future property would include mode-specific authority,
ordered speed/sync/close/contact feedback, and safe plant constraints over
time. The current 12/12 replay result is **trace acceptance**, not a
universal theorem. For CHP, logic execution, process readiness, CHP output,
customer supply, and cyber trust are distinct propositions; the public report
does not provide enough site data for a safe process-restart theorem.

## 5. Cost is compared only inside the feasible set

`Φ` and local protections are hard predicates. A cost function cannot pay to
violate them. The current [path/cost package](https://github.com/iotrustlab/sphere-usecases/blob/codex/procedure-usecases/experiments/procedure_study/network_cost/README.md) computes
case-specific vectors from pinned run bundles:

```text
C_ATT = (demo-threshold flow deficit [m³], evidence-gap [s],
         local presence [person·h], remote-ineligible time [s], starts [count])
C_MER = (representative setpoint gap [MWh], startup latency [s],
         actor presence [person·h], unknown cycle/water effects)
C_CHP = (reset count, ordinal log loss, unknown real outage/effort)
```

The generic CHP toy additionally integrates electrical and thermal demand
gaps in `MWh` and `MWhth`; those are not incident losses. Comparing candidate
procedures requires matched starting state, disturbance assumptions, and
horizon. Ranking vectors then requires declared weights or a Pareto rule.
No cost-optimal synthesis is claimed. The [CLEO choice envelope](cleo/attleboro_documented_choice.envelope)
verifies a **proposed eligible Remote-or-Hand branch** under a precondition
that one branch is already enabled; it does not infer an optimal policy.

## 6. A state-pair test makes the human variable consequential

The proposal defines decision sufficiency over a declared scenario class:

```text
α_w(x₁)=α_w(x₂) ⇒ D_Φ(x₁,a)=D_Φ(x₂,a).
```

The [local actor/interface test](https://github.com/iotrustlab/sphere-usecases/blob/codex/procedure-usecases/experiments/procedure_study/network_cost/examples/actor_interface.json)
exhibits a bounded counterexample for a projection that keeps Attleboro
generator/mode/trip state but omits local presence. At tick 8, otherwise
identical research states differ only in `local_actor_present`. A Hand
candidate can reach the modeled effect at research deadline tick 15 when
present, but is infeasible when absent. Arrival at tick 22 yields modeled
effect tick 29 and misses the deadline. This establishes a **toy decision
distinction**, not actual staffing, local action, or water delivery.

## 7. What is grounded, and what could be novel?

Existing primary foundations already supply important pieces:

* [SPHERE](https://www.isi.edu/proxy-sphere/resources/) supplies reproducible
  controller/process experimentation.
* [HyTwin](https://facweb.cdm.depaul.edu/smitsch/pdf/nfm25-hytwin.pdf) reasons
  about hybrid-process security intervention and a physical mitigation
  horizon.
* [Hybrid Game Control Envelope Synthesis](https://publikationen.bibliothek.kit.edu/1000199221/196556129)
  studies verified/synthesized nondeterministic winning policies. CLEO is a
  checker for proposed envelopes; the local Attleboro envelope does not
  establish maximality or cost optimality.

The **proposed PRISM contribution** is the tested combination: derive a
decision-sufficient process/workflow slice with provenance and human/agent
access; estimate coordination completion beyond factual request tracking;
then choose a timely, authorized, least-disruptive response at a declared
adapter. The proposal itself calls for state-pair search, request-tracking
baselines, component ablations, human/agent observation provenance, and
adapter-coverage tests. A human graph node, floor picture, or network path
alone is not novel. The bounded state pair and Attleboro proof are early
components, not a validation of the complete PRISM claim.

The separate, unpublished public-exposure-paper BYU surrogate
shows a useful **evidence-tagging practice** (`stated`, `seen`, `measured`,
`inferred`, `drawn`). It describes a different gas-turbine/hot-water plant and
does not contain a Polish CHP process ODE or a transferable control program.
No BYU rating, topology, or network connection is transplanted into the
generic CHP toy.
