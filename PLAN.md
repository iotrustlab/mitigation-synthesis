# Mitigation Synthesis Research Plan

## Purpose

This document captures the revised research plan after completing the canonical Phase 1 artifact. The goal is to move from one verified example to a paper-ready research contribution suitable for a top formal methods venue and competitive for a CPS-IoT Week style venue.

The plan is organized around a clear evaluation matrix:

- 2 systems
- 2 attack families
- one common formal workflow for mitigation certification

## Current Baseline

The repository currently contains one end-to-end verified canonical example:

- system: two-tank water process
- attack family: actuator command forcing
- mitigation: redundant control path overrides `P1 := 0`
- artifact: `attack.envelope`
- proof runner: `water_attack.py`

What is already complete:

- one CLEO-checkable envelope
- one proof harness that fills in the needed invariant and ODE tactic
- end-to-end verification of the narrowed final-step scenario
- cleaned repository focused on the canonical artifact

What is not yet complete:

- full remaining attack horizon
- multiple attack families
- multiple systems
- automated synthesis beyond hand-written proof annotations

## Paper-Level Goal

The target contribution is not just "we proved one toy example." The target contribution is:

1. a formal problem statement for redundancy-aware mitigation synthesis,
2. a reusable proof workflow for attack-aware mitigation certificates,
3. evidence that the workflow applies across more than one CPS and more than one attack family,
4. some level of automation in generating or checking mitigation candidates.

## Core Research Claim

The paper should aim to support a claim like this:

"Given a CPS model, an attack-effect model, a redundant intervention path, and cost/safety objectives, we can synthesize or certify mitigation envelopes that preserve safety while accounting for intervention and operational cost."

## Evaluation Matrix

The core evaluation should cover four combinations:

| System | Attack Family A | Attack Family B |
|--------|------------------|-----------------|
| System 1 | required | required |
| System 2 | required | required |

Minimum expected evidence:

- one verified artifact per matrix cell
- one mitigation story per matrix cell
- one summary table comparing proof status, mitigation choice, and cost bounds

## Recommended System Choices

### System 1: Two-Tank Water System

Keep the current water-tank model as System 1.

Why:

- already modeled
- already verified in a canonical case
- intuitive safety story
- clean actuator semantics

### System 2: Recommended Choice

Recommended default choice:

- a simple thermal or HVAC control system with low-dimensional continuous dynamics and discrete actuation

Why:

- different physics from the water-tank example
- still manageable in differential game logic
- easy to explain to reviewers
- lets us show that the method is not tied to flow systems

Acceptable fallback:

- a richer water or pipeline variant if thermal modeling becomes too costly

This fallback is less impressive for generality, but may reduce implementation risk.

## Recommended Attack Family Choices

The exact labels can change later, but the plan should assume two attack-effect families.

### Attack Family A: Forced Unsafe Actuator Command

Definition:

- the attacker overwrites the primary control path with a harmful actuator command

Current baseline instance:

- force `P1 := 1`, keep `V1 := 1`, keep the secondary path inactive

Why this should stay:

- it matches the current verified example
- it is simple and physically meaningful
- it cleanly motivates a redundant override

### Attack Family B: Stuck or Frozen Command

Definition:

- the attacker causes a command or actuator state to remain fixed instead of updating normally

Why this is the best next family:

- it is different from pure forced-command replacement
- it still fits the same formal machinery reasonably well
- it is easier to model and verify than jumping immediately to sensor spoofing

Stretch-family candidate for later:

- sensor spoofing or measurement falsification

This is important long term, but it should not be the first expansion because it changes the modeling problem more sharply.

## Revised Phase Plan

### Phase 1: Canonical Verified Baseline

Status:

- complete

Objective:

- establish one trustworthy end-to-end verified artifact

Deliverables:

- `attack.envelope`
- `water_attack.py`
- repository documentation

Exit criteria:

- end-to-end proof passes through CLEO plus KeYmaera X
- safety and metric nonnegativity are certified for the narrowed final-step case

Main limitation left behind by this phase:

- the proof only covers the case where less than one control period remains before the attack ends

### Phase 2: Full-Horizon Result for System 1, Attack Family A

Objective:

- remove the final-step-only assumption while keeping the same attack family and the same system

Key technical change:

- prove safety for an arbitrary remaining attack horizon, not just the last attacked iteration

Required modeling work:

- remove the assumption `AttackTime < attackTimer + Tmin`
- introduce cost-to-go reasoning for multiple future interventions
- decide whether to use a ghost counter, a closed-form bound, or both

Required proof work:

- strengthen the loop invariant to track remaining intervention budget across multiple attacked cycles
- recheck the continuous proof obligations under the stronger invariant

Recommended implementation choice:

- use a ghost variable for "remaining attacked control steps" first

Why:

- it is easier to reason about than a direct `ceil(...)` term
- it gives a cleaner invariant for proof development

Deliverables:

- updated envelope for System 1, Attack A
- updated proof runner
- design note explaining the strengthened invariant

Exit criteria:

- the same attack can remain active for multiple future loops
- repeated redundant overrides are formally shown sufficient
- `rmetric` stays nonnegative under the cost-to-go argument

Research value:

- turns the artifact from a one-step certificate into a horizon-level mitigation result

### Phase 3: Add Attack Family B on System 1

Objective:

- show the method is not tied to one attack-effect class

Required modeling work:

- define the stuck or frozen command family precisely
- model how the attack affects the primary control path
- identify the corresponding redundant mitigation action

Required proof work:

- derive a new mitigation envelope
- prove safety and metric bounds under Attack Family B

Deliverables:

- second verified envelope on System 1
- comparison note between Attack A and Attack B

Exit criteria:

- System 1 supports two distinct verified attack families
- each family has a justified mitigation and cost story

Research value:

- strengthens the claim that the framework captures attack-effect categories, not a single hand-crafted exploit story

### Phase 4: Port Both Attack Families to System 2

Objective:

- show the workflow is reusable across systems with different physics

Required modeling work:

- formalize System 2 plant dynamics
- define safety conditions and actuator semantics
- instantiate both attack families on System 2

Required proof work:

- adapt or redesign mitigation envelopes for the second system
- prove both attack families with cost-aware reasoning

Deliverables:

- System 2 model and proof harness
- two verified artifacts for System 2

Exit criteria:

- the full 2 by 2 matrix is populated
- each cell has at least one verified mitigation story

Research value:

- this is the minimum evaluation shape that starts to look publishable instead of anecdotal

### Phase 5: Mitigation Synthesis Automation

Objective:

- move beyond hand-written proof annotations and toward a genuine synthesis workflow

Important scoping choice:

- start with template-based automation, not LLM-first automation

Why:

- easier to evaluate rigorously
- easier to make soundness claims about
- more likely to satisfy FM reviewers

Recommended automation target:

- search over mitigation templates
- search over invariant templates
- replay verification automatically

Possible inputs:

- attack family
- system parameters
- allowed redundant actions
- cost coefficients

Possible outputs:

- candidate envelope
- candidate invariant
- chosen tactic profile
- verification result

Deliverables:

- synthesis driver or search prototype
- benchmark scripts
- summary table over the 2 by 2 matrix

Exit criteria:

- at least part of the currently manual annotation process is generated automatically
- automation succeeds on more than one matrix cell

Research value:

- this is where "mitigation synthesis" becomes a direct technical contribution rather than a long-term aspiration

### Phase 6: Paper Package and Evaluation

Objective:

- turn the artifacts into a paper-ready story with evidence and claims aligned to venue expectations

Required evaluation dimensions:

- proof success or failure by matrix cell
- synthesis time or user effort
- mitigation cost comparison
- operational cost comparison
- modeling effort and proof annotation effort

Required writing assets:

- one motivating running example
- one formal problem statement
- one algorithm or workflow section
- one soundness statement or theorem
- one evaluation section over the matrix

Exit criteria:

- complete draft figures and tables
- reproducible scripts
- a narrative that clearly distinguishes baseline assumptions, limitations, and contributions

## Venue-Aware Emphasis

### Formal Methods Emphasis

The paper should emphasize:

- formal problem definition
- soundness of the workflow
- proof-carrying mitigation certificates
- reusable synthesis or verification templates

Likely reviewer questions:

- what is the precise formal novelty
- how much is automated
- how reusable is the method across examples

### CPS-IoT Week Emphasis

The paper should emphasize:

- attack-response workflow
- operational meaning of redundancy
- mitigation choices under cost bounds
- cross-system relevance

Likely reviewer questions:

- is this more than a toy
- are the attacks meaningful
- does the method help with real CPS design tradeoffs

## Suggested Immediate Next Actions

1. Lock System 1 as the current two-tank water example.
2. Decide whether System 2 will be thermal or a richer flow system.
3. Keep Attack Family A as forced unsafe actuator command.
4. Tentatively lock Attack Family B as stuck or frozen actuator command.
5. Start Phase 2 on System 1 before touching automation.

## Suggested Order of Implementation

1. Phase 2
2. Phase 3
3. Phase 4
4. Phase 5
5. Phase 6

Why this order:

- it expands depth before breadth
- it reuses the current proof structure as long as possible
- it avoids premature investment in automation before the target search space is stable

## Risks and Scope Traps

Primary risks:

- moving to sensor spoofing too early
- choosing a System 2 model that is formally too expensive
- trying to build an LLM agent before the formal templates are stable

Scope traps to avoid:

- polishing the current Phase 1 artifact indefinitely
- adding many attack stories without finishing the 2 by 2 matrix
- overcommitting to realism before the method is generalized

## Minimum Publishable Target

For a strong first submission, the minimum credible target should be:

- 2 systems
- 2 attack families
- 4 verified mitigation cases
- at least partially automated mitigation or annotation generation
- one clear soundness story

If that target proves too large, the acceptable fallback is:

- 2 systems
- 2 attack families
- 4 verified cases
- manual but systematic proof workflow
- automation presented as ongoing work rather than the main contribution

The fallback may still support an FM-style submission if the formal contribution is sharp enough, but automation would strengthen the story considerably.
