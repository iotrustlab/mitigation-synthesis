# Standards to Calculus Mapping

This document maps formal calculus concepts to industrial standards (IEC, NERC, NIST).

---

## Notation and Variable Definitions

### State Variables (Physical Process)

| Symbol | Type | Description | Units |
|--------|------|-------------|-------|
| `x1` | Real | Water level in Tank 1 | meters (normalized) |
| `x2` | Real | Water level in Tank 2 | meters (normalized) |
| `L1`, `H1` | Real | Low/high bounds for Tank 1 | meters |
| `L2`, `H2` | Real | Low/high bounds for Tank 2 | meters |

### Control Variables (Actuators)

| Symbol | Type | Description | Values |
|--------|------|-------------|--------|
| `P1` | Binary | Pump 1 state (inflow) | 0 = off, 1 = on |
| `P2` | Binary | Pump 2 state (outflow) | 0 = off, 1 = on |
| `V1` | Binary | Valve 1 state (inflow) | 0 = closed, 1 = open |
| `V2` | Binary | Valve 2 state (outflow) | 0 = closed, 1 = open |

### Process Parameters

| Symbol | Type | Description | Typical Value |
|--------|------|-------------|---------------|
| `f1` | Real | Inflow rate when pump/valve active | process-specific |
| `f2` | Real | Outflow rate when pump/valve active | process-specific |

### Timing Variables

| Symbol | Type | Description |
|--------|------|-------------|
| `t` | Real | Time within current control loop iteration |
| `T` | Real | Maximum loop duration (upper bound) |
| `Tmin` | Real | Minimum loop duration (lower bound) |
| `attackTimer` | Real | Time since attack started |
| `AttackTime` | Real | Attack duration bound |
| `τ` (tau) | Real | Actuator response time |

### Metric Variables

| Symbol | Type | Description |
|--------|------|-------------|
| `ometric` | Real | Operational cost metric (budget remaining) |
| `rmetric` | Real | Intervention cost metric (budget remaining) |

### Cost Constants

| Symbol | Type | Description |
|--------|------|-------------|
| `c1` | Real | Energy cost coefficient for pump 1 inefficiency |
| `c2` | Real | Energy cost coefficient for pump 2 inefficiency |
| `op1` | Real | Intervention cost for pump 1 override |
| `ov1` | Real | Intervention cost for valve 1 override |
| `op2` | Real | Intervention cost for pump 2 override |
| `ov2` | Real | Intervention cost for valve 2 override |

### Helper Predicates

| Symbol | Definition | Description |
|--------|------------|-------------|
| `safe(x1, x2)` | `(L1 ≤ x1 ≤ H1) ∧ (L2 ≤ x2 ≤ H2)` | Both tanks within safe bounds |
| `isBinary(v)` | `v = 0 ∨ v = 1` | Variable is binary |

---

## Overview

The redundancy-aware mitigation synthesis framework draws from three standards families:

| Standards Family | Contribution | Calculus Mapping |
|-----------------|--------------|------------------|
| NIST SP 800-82, IEC 62443 | Attack model | Subgame replacement |
| IEC 61508, IEC 61511 | Architecture constraints | HFT, PFDavg, SFF (parameters) |
| NERC PRC-012-2 | Response structure | Control envelopes |

**Important distinction:** IEC 61508/61511 metrics describe architecture-level dependability. They are constraints or parameters, not per-action consumable budgets.

---

## 1. Attack Model

### Standard: NIST SP 800-82r3 (Section 2.5)

**Requirement:** "Manipulation of control" - unauthorized changes to instructions, commands, or alarm thresholds affecting the controlled physical process.

**Calculus Mapping:**
- Attacks modeled as **effect-level subgame replacement** via nondeterministic choice (`++`)
- Captures the plant-facing effect, not the exploit mechanism
- dGL representation:

```
{
    ? attackTimer <= AttackTime;
    /* Attack effect: replace plant-facing commands */
    u_actual := u_attack;
}
++
{
    ? attackTimer > AttackTime;
    /* Normal operation: legitimate commands reach plant */
    u_actual := u_nominal;
}
```

For the water tank model, the attack effect is:

```
P1 := 1; V1 := 1;    /* Force inflow */
P2 := 0; V2 := 0;    /* Block outflow */
```

### Standard: IEC 62443-3-3 (FR3)

**Requirement:** Integrity of data transmission - prevents manipulation of measurement values and command parameters.

**Calculus Mapping:**

| Attack Type | Effect | dGL Representation |
|-------------|--------|-------------------|
| Command override | Plant receives attacker commands | `u_actual := u_attack` |
| Sensor spoofing | Controller/operator sees false values | `y_reported := y_nominal` (target) |

### Classification

| Aspect | Standard Citation | Formalization Level |
|--------|------------------|---------------------|
| Attack definition | NIST 800-82 §2.5 | Qualitative |
| Integrity requirements | IEC 62443-3-3 FR3 | Qualitative |
| **Subgame replacement** | **This work** | **Formal (dGL)** |

---

## 2. Redundancy Architecture

### Standard: IEC 61508-2 (Table 2)

**Requirement:** Hardware Fault Tolerance (HFT) per Safety Integrity Level (SIL).

| SIL | Type A Elements | Type B Elements |
|-----|-----------------|-----------------|
| 1 | HFT = 0 | HFT = 0 |
| 2 | HFT = 0 | HFT = 1 |
| 3 | HFT = 1 | HFT = 1 |
| 4 | HFT = 1 | HFT = 2 |

**Calculus Mapping:**
- Two-layer architecture: PLC1 (primary) + PLC2 (backup)
- HFT ≥ 1 as architecture constraint (not consumed per action)
- The backup could be: another PLC, an independent monitor, an operator override, or a bump-in-the-wire safety device

```
/* Architecture constraint */
HFT >= required_HFT

/* Control structure */
{
    /* Primary control channel */
    P1_PLC1: P1 := *; V1_PLC1: V1 := *;
};
{
    /* Redundant intervention path */
    P1_PLC2: P1 := *; V1_PLC2: V1 := *;
}
```

### Standard: IEC 61511-1 (Annex B)

**Requirement:** Multi-channel voting architectures.

| Architecture | Description | Formal Constraint |
|--------------|-------------|-------------------|
| 1oo1 | Single channel, no redundancy | HFT = 0 |
| 1oo2 | Two channels, either can trigger | HFT = 1 |
| 2oo2 | Two channels, both must agree | HFT = 0 (different mode) |
| 2oo3 | Three channels, majority vote | HFT = 1 |

**Calculus Mapping:**
- Current model: 1oo2 architecture (backup can override primary)
- Architecture constraint: `HFT >= 1` (system tolerates one compromised channel)

### Classification

| Aspect | Standard Citation | Formalization Level |
|--------|------------------|---------------------|
| HFT requirements | IEC 61508-2 Table 2 | Formally defined |
| Voting architectures | IEC 61511-1 Annex B | Implementation guidance |
| **Architecture as constraint** | **This work** | **Formal (dGL)** |

---

## 3. Architecture Dependability vs. Intervention Cost

**Critical distinction:** IEC 61508/61511 metrics describe architecture-level dependability. They should be modeled as **constraints or parameters**, not as per-use consumable budgets.

### Architecture Constraints (from IEC 61508)

These describe whether the redundant architecture is acceptable:

| Metric | Formula | Description | Role in Calculus |
|--------|---------|-------------|------------------|
| PFDavg | ½ × λ_DU × T_p | Probability of dangerous failure on demand (average) | Architecture constraint |
| PFH | (continuous mode) | Probability of dangerous failure per hour | Architecture constraint |
| SFF | (safe + detected) / total | Safe Failure Fraction | Architecture constraint |
| DC | detected / dangerous | Diagnostic Coverage | Architecture parameter |
| T_p | (proof-test interval) | Time between periodic tests | Architecture parameter |

**Calculus representation (constraints):**

```
/* Architecture adequacy constraints */
HFT >= required_HFT
PFDavg <= PFD_target
proof_test_interval <= Tp_max
```

### Intervention Cost (this work)

`rmetric` (more precisely: `intervention_budget`) is a **deterministic intervention cost**, not a reliability probability:

| Metric | Description | Role |
|--------|-------------|------|
| `rmetric` | Remaining budget for backup interventions | Operational cost |

**What intervention cost may represent:**
- Actuator wear from override actions
- Number of backup activations
- Operator burden
- Use of degraded operating mode
- Load shed or production loss
- Maintenance burden

**Calculus representation (intervention cost):**

```
/* Intervention cost (deterministic) */
rmetric := rmetric - (|old_P1 - P1| * op1 + |old_V1 - V1| * ov1 + ...)
```

### Summary: Two Separate Concerns

| Concern | Metrics | Nature | Calculus Role |
|---------|---------|--------|---------------|
| Architecture adequacy | HFT, PFDavg, SFF, DC | Probabilistic/structural | Constraint |
| Intervention cost | rmetric, op1, ov1, ... | Deterministic cost | Budget |

**The calculus composes both:**

```
safe(x1, x2) ∧ architecture_ok ∧ intervention_budget >= 0
```

### SIL Targets (IEC 61508-1 Table 2)

| SIL | Low Demand (PFDavg) | Continuous (PFH) |
|-----|---------------------|------------------|
| 1 | 10⁻² to 10⁻¹ | 10⁻⁶ to 10⁻⁵ |
| 2 | 10⁻³ to 10⁻² | 10⁻⁷ to 10⁻⁶ |
| 3 | 10⁻⁴ to 10⁻³ | 10⁻⁸ to 10⁻⁷ |
| 4 | 10⁻⁵ to 10⁻⁴ | 10⁻⁹ to 10⁻⁸ |

---

## 4. Control Envelopes

### Standard: NERC PRC-012-2 (Requirement 5)

**Requirement:** Four-part evaluation for Remedial Action Schemes (RAS):

| Part | NERC Requirement | Calculus Mapping |
|------|-----------------|------------------|
| (a) Trigger | Identify conditions that trigger RAS | **Precondition** |
| (b) Respond | Describe RAS response actions | **Action** (dGL program) |
| (c) Effective | Demonstrate response achieves goal | **Postcondition** |
| (d) No adverse | Prove no adverse effects | **Hazard negation** |

**Calculus Mapping:**
- Control envelope = `{precondition} [action] {postcondition ∧ ¬hazards}`
- Four mitigation strategies as disjunction:

```
/* Envelope 1: Wait out attack */
(safe(x1, x2) ∧ attackTimer > AttackTime ∧ ometric >= 0 ∧ rmetric >= 0)

/* Envelope 2: Drain safely */
∨ (safe(x1, x2) ∧ ometric >= drain_cost ∧ rmetric >= 0)

/* Envelope 3: Override valve */
∨ (safe(x1, x2) ∧ ometric >= energy_cost ∧ rmetric >= valve_override_cost)

/* Envelope 4: Override pump */
∨ (safe(x1, x2) ∧ ometric >= 0 ∧ rmetric >= pump_override_cost)
```

### Standard: NERC PRC-012-2 (Requirement 1)

**Requirement:** Single-fault tolerance - RAS must operate correctly with any single component failure.

**Calculus Mapping:**
- HFT ≥ 1 constraint ensures single-fault tolerance
- Redundant intervention path available when primary channel is compromised

### Standard: NERC PRC-012-2 (Requirement 6)

**Requirement:** Corrective Action Plan timeline for identified deficiencies.

**Calculus Mapping:**
- Response time bound: `t_action - t_trigger ≤ τ`
- IEEE C37.013 reference: breaker trip 50-60ms

### Classification

| Aspect | Standard Citation | Formalization Level |
|--------|------------------|---------------------|
| Four-part RAS test | NERC PRC-012-2 R5 | Qualitative |
| Single-fault tolerance | NERC PRC-012-2 R1 | Qualitative |
| **Control envelopes** | **This work** | **Formal (dGL)** |

---

## 5. Standards Gaps (Our Contribution)

The following aspects are required by standards but **not formally specified**:

| Gap | Standard Reference | Our Contribution |
|-----|-------------------|------------------|
| Attack effect formalization | NIST 800-82 "manipulation" | Subgame replacement (effect-level) |
| Synthesis algorithm | (none specified) | Control envelope derivation |
| Response time formalization | "timely" undefined | Bounded response in dGL (`τ`) |
| Intervention cost bounds | Qualitative guidance | Deterministic intervention metric |
| Adverse response prevention | Post-hoc evaluation | Pre-verified envelopes |
| Degraded mode specification | (none specified) | Formal mode transitions |

**What we do NOT claim:**
- We do not claim PFDavg is consumed per backup action
- We do not claim to model exploit mechanisms (firmware rootkits, etc.)
- We do not claim proofs are complete (pending KeYmaera X verification)

---

## 6. Citation Guide

### IEC Standards
- **IEC 61508** (all parts): Functional safety of E/E/PE safety-related systems
- **IEC 61511** (all parts): Functional safety - Safety instrumented systems for process industry
- **IEC 62443-3-3**: Security for industrial automation - System security requirements

### NERC Standards
- **NERC PRC-012-2**: Remedial Action Schemes

### NIST Publications
- **NIST SP 800-82r3**: Guide to Operational Technology Security

### IEEE Standards
- **IEEE C37.013**: Standard for AC High-Voltage Generator Circuit Breakers

---

## Summary Table

| Calculus Concept | Primary Standard | Section/Table | Our Formalization |
|-----------------|------------------|---------------|-------------------|
| Subgame replacement | NIST SP 800-82r3 | Section 2.5 | Effect-level attack relation |
| Integrity attacks | IEC 62443-3-3 | FR3 | Command/sensor perturbation |
| HFT architecture | IEC 61508-2 | Table 2 | Architecture constraint |
| Voting logic | IEC 61511-1 | Annex B | Guard conditions |
| PFDavg, SFF, DC | IEC 61508-6 | Annex B | Architecture constraints (not consumed) |
| SIL targets | IEC 61508-1 | Table 2 | Constraint parameters |
| Four-part RAS test | NERC PRC-012-2 | Requirement 5 | Control envelope structure |
| Single-fault tolerance | NERC PRC-012-2 | Requirement 1 | HFT ≥ 1 constraint |
| Response time | IEEE C37.013 | (breaker timing) | Timing bound `τ` |
| Intervention cost | **This work** | — | `rmetric` budget |
