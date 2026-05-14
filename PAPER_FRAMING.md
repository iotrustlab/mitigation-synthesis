# Paper Framing

Research positioning, terminology, and contribution framing for publication.

---

## 1. Core Project Framing

### One-Paragraph Summary

> We formalize how to synthesize redundant mitigation actions after detecting a compromised control channel. The attacker is modeled at the effect level: it can replace plant-facing commands and, in stealthy cases, spoof controller/operator-facing measurements. The defender has access to an independent redundant intervention path—e.g., backup PLC, external monitor, operator override, or bump-in-the-wire safety device. Control envelopes certify when a given intervention can preserve safety, within timing and intervention-cost bounds, while architecture-level safety metrics such as HFT/PFDavg remain separate constraints.

### Key Design Choices

1. **Effect-level attack model:** We model what commands reach the plant, not how the attacker gained control
2. **Deterministic intervention cost:** `rmetric` is an operational cost budget, not a reliability probability
3. **Architecture constraints separate:** HFT, PFDavg, SFF are constraints, not consumed per action
4. **Domain flexibility:** Water is the running example; power/HARVEY is the motivating pattern

---

## 2. Terminology Comparison

Different communities use different terms for similar concepts. This section maps terminology to avoid confusion.

### Power Systems Community

| Term | Meaning | Our Equivalent |
|------|---------|----------------|
| **Remedial Action Scheme (RAS)** | Automatic system to preserve stability | Control envelope |
| **Special Protection System (SPS)** | Same as RAS (older term) | Control envelope |
| **Corrective action** | Post-contingency response | Mitigation strategy |
| **Contingency** | Fault or disturbance | Attack/failure event |

### ICS Safety Community

| Term | Meaning | Our Equivalent |
|------|---------|----------------|
| **Safety Instrumented System (SIS)** | Dedicated safety controller | Redundant intervention path |
| **Safety Instrumented Function (SIF)** | Specific safety response | Control envelope action |
| **Redundant control** | Multiple controllers for reliability | HFT architecture |
| **Fail-safe** | Default to safe state on failure | Fallback strategy |

### Formal Methods Community

| Term | Meaning | Our Usage |
|------|---------|-----------|
| **Controller synthesis** | Generate controller from spec | Mitigation synthesis |
| **Invariant** | Property preserved by dynamics | Control envelope |
| **Game** | Two-player adversarial interaction | Angel vs. Demon |
| **Strategy** | Player's decision function | Envelope selection |

### Our Contribution: "Redundancy-Aware Mitigation Synthesis"

We introduce this term to bridge communities:
- **Redundancy-aware:** Explicitly models cost of using redundant paths
- **Mitigation:** Response to detected attacks/failures
- **Synthesis:** Formal derivation of provably-safe strategies

---

## 3. Research Gap

### What Standards Require

| Standard | Requirement |
|----------|-------------|
| IEC 61508 | Hardware fault tolerance (HFT), PFDavg targets |
| IEC 62443 | Integrity of control commands |
| NERC PRC-012-2 | Single-fault tolerance, four-part RAS evaluation |
| NIST 800-82 | Defense against "manipulation of control" |

### What Standards DON'T Provide

| Gap | Standard Reference | Impact |
|-----|-------------------|--------|
| Formal attack models | (none specified) | Cannot verify completeness |
| Synthesis algorithms | (none specified) | Manual design required |
| Intervention cost bounds | (qualitative only) | No optimal strategy selection |
| Pre-deployment verification | (post-hoc testing) | Cannot guarantee before deployment |
| Degraded mode formalization | (none specified) | No formal mode transitions |

### Our Contribution

We provide **formal methods to fill these gaps**:

1. **Effect-level attack formalization** via subgame replacement (links to NIST/IEC)
2. **Metric-aware synthesis** with intervention cost bounds (separate from architecture constraints)
3. **Pre-verified envelopes** via KeYmaera X proofs (operationalizes NERC four-part test)
4. **Clear separation** of intervention costs from architecture dependability metrics

---

## 4. Contribution Statement

### Three-Part Contribution

1. **Effect-level attack model for ICS** — Captures NIST "manipulation of control" as plant-facing command replacement with optional sensor/operator-view spoofing. Does NOT model exploit mechanisms (firmware rootkits, etc.).

2. **Metric-aware mitigation model** — Separates deterministic intervention costs (`rmetric`) from architecture-level dependability constraints (HFT, PFDavg, SFF). Does NOT treat PFDavg as a per-action consumable budget.

3. **Control envelopes as verifiable RAS** — Implements NERC PRC-012-2 four-part evaluation as formally-proven loop invariants with explicit cost bounds.

### Claims and Evidence

| Claim | Evidence Required | Status |
|-------|-------------------|--------|
| Effect-level model captures attack patterns | 3+ attack types, SPHERE validation | Pending |
| Intervention cost is practical | Realistic constant calibration | Pending |
| Envelopes certify safety | KeYmaera X proofs | Pending |
| SPHERE grounding | UC1 case study, empirical validation | Pending |

### What We Do NOT Claim

- PFDavg is consumed per backup action (it is an architecture constraint)
- We model exploit mechanisms (we model effects only)
- Original HARVEY targets water treatment (it was power grid)
- Proofs are complete (pending KeYmaera X verification)

---

## 5. Related Work Positioning

### Formal Methods for ICS

| Work | Contribution | Our Difference |
|------|--------------|----------------|
| HyTwin | Attack detection + mitigation horizon | We do response synthesis |
| SafeComp | Safety verification | We add attack modeling |
| KeYmaera X | Hybrid systems prover | We add ICS-specific metrics |

### ICS Security

| Work | Contribution | Our Difference |
|------|--------------|----------------|
| XPhysICS | Attack taxonomy | We formalize as dGL |
| SPHERE | Testbed + artifacts | We add verification layer |
| HARVEY | Firmware rootkit attack | We abstract to effect level |

### Standards Compliance

| Work | Contribution | Our Difference |
|------|--------------|----------------|
| NERC CIP papers | Compliance auditing | We provide formal evidence |
| IEC 61508 guides | Implementation guidance | We separate constraints from costs |

### Our Position

We **bridge** these areas:
- Take attack **effects** from ICS security (HARVEY pattern, XPhysICS taxonomy)
- Apply formal verification (KeYmaera X)
- Ground in industrial standards (IEC, NERC)
- Validate on research testbed (SPHERE effect-level instantiation)

---

## 6. Domain Roles in Paper

### Water (Running Example)

- **Why:** Dynamics are simple; tank/pump/valve model is intuitive
- **Role:** Primary formal example throughout paper
- **Advantage:** Accessible to reviewers without power-systems background

### Power/HARVEY (Motivating Attack)

- **Why:** Original HARVEY was firmware-level rootkit on power grid
- **Role:** Motivating attack pattern; shows real-world relevance
- **Caution:** Do not claim HARVEY targets water treatment

### SPHERE (Empirical Bridge)

- **Why:** Enables effect-level attack instantiation without firmware exploit
- **Role:** Validation infrastructure; grounds formal model
- **Caution:** SPHERE provides effect-level abstraction, not firmware rootkit

**Paper framing:**
> The formal example is water because the dynamics are simple and visible. The attack class is motivated by HARVEY, which was originally demonstrated in power systems. SPHERE gives us a way to evaluate the attack effect pattern across domains.

---

## 7. Target Venues

### Primary Targets

| Venue | Focus | Fit |
|-------|-------|-----|
| **DSN** (Dependable Systems and Networks) | Safety, security, formal methods | Strong fit: verification + ICS |
| **NFM** (NASA Formal Methods) | Formal verification of critical systems | Strong fit: KeYmaera X proofs |
| **FM** (Formal Methods) | Core formal methods | Good fit: dGL contributions |

### Secondary Targets

| Venue | Focus | Fit |
|-------|-------|-----|
| CAV | Computer-aided verification | Possible: tool/technique |
| S&P | Security | Possible: ICS security angle |
| CCS | Security | Possible: attack modeling |

### Venue-Specific Framing

**For DSN:**
- Emphasize dependability, intervention cost bounds
- Standards compliance as motivation
- Case study focus

**For NFM:**
- Emphasize KeYmaera X proofs, dGL
- Hybrid systems aspect
- Formal guarantees focus

**For FM:**
- Emphasize calculus contributions
- Game-theoretic aspects
- Theoretical foundations

---

## 8. Paper Structure (Proposed)

### Standard Structure

1. **Introduction** (~1 page)
   - Problem: detection ≠ response
   - Gap: standards require but don't formalize
   - Contribution: redundancy-aware mitigation synthesis

2. **Background** (~1 page)
   - dGL and KeYmaera X
   - ICS architecture and threats
   - Standards overview

3. **Framework** (~3 pages) **← CRITICAL PATH**
   - 3.1 System Model (water tank, PLCs)
   - 3.2 Attack Model (effect-level subgame replacement)
   - 3.3 Metrics (ometric for operational, rmetric for intervention; NOT PFDavg budget)
   - 3.4 Control Envelopes (4 strategies, NERC mapping)
   - 3.5 Verification (KeYmaera X approach)

4. **Case Study** (~2 pages)
   - SPHERE water treatment UC1
   - Effect-level attack instantiation
   - Proof results

5. **Evaluation** (~1 page)
   - Proof complexity
   - Metric calibration
   - Standards coverage

6. **Related Work** (~0.5 page)
   - Position vs. HyTwin, XPhysICS, HARVEY, standards

7. **Conclusion** (~0.5 page)
   - Summary
   - Future work

---

## 9. Writing Guidelines

### Terminology Consistency

Use these terms throughout:
- "Control envelope" (not RAS, SIF, invariant)
- "Effect-level subgame replacement" (not attack injection)
- "Redundant intervention path" (not backup PLC specifically—could be operator, monitor, etc.)
- "Intervention cost" or `rmetric` (not "redundancy cost" or "PFD budget")
- "Architecture constraint" for HFT, PFDavg (not "consumed per action")

### Standards Citations

Always cite specific sections:
- "IEC 61508-2 Table 2" (not just "IEC 61508")
- "NERC PRC-012-2 Requirement 5(a-d)" (not just "NERC")
- "NIST SP 800-82r3 Section 2.5" (not just "NIST")

### Claim Qualification

Until proofs complete, use:
- "We propose that..." (not "We prove that...")
- "The control envelope is intended to..." (not "guarantees...")
- "Pending formal verification..." (explicit status)

### HARVEY/SPHERE Precision

- "Original HARVEY was evaluated on a power-grid testbed"
- "SPHERE abstracts the HARVEY pattern as effect-level manipulation"
- "We use HARVEY as a motivating attack pattern, not a direct implementation"

---

## Summary

| Aspect | Approach |
|--------|----------|
| Core term | "Redundancy-Aware Mitigation Synthesis" |
| Gap | Standards require, don't formalize |
| Contribution | Effect-level attack model + intervention cost + pre-verified envelopes |
| NOT | PFDavg-as-budget, exploit mechanisms, HARVEY targets water |
| Evidence | KeYmaera X proofs + SPHERE validation |
| Venues | DSN, NFM, FM |
| Status | Framework defined, verification pending |
