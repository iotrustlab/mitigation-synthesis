# SPHERE Alignment

Grounding the calculus in the SPHERE CPS Enclave (U of Utah) research infrastructure.

---

## 1. SPHERE Platform Overview

SPHERE (Security and Privacy Heterogeneous Environment for Reproducible Experimentation) is a broader research platform. The artifacts referenced here are from the **CPS Enclave at the University of Utah**, which provides:

- **Tag contracts** for ICS variable inventory
- **Invariant rules** for expected system behavior
- **Attack surface analysis** and threat documentation
- **Simulation profiles** with realistic timing parameters
- **Run bundles** for evidence collection

This document maps SPHERE artifacts to calculus concepts for empirical grounding.

---

## 2. Domain Roles

### Water (Formal Running Example)

- **Role:** Primary formal example
- **Why:** Dynamics are simple and visible; tank/pump/valve model is intuitive
- **Status:** Current dGL model (`valve_model.kyx`, `attack_analysis.kyx`)

### Power/HARVEY (Motivating Attack Pattern)

- **Role:** Motivating original attack
- **Why:** Original HARVEY was a firmware-level PLC rootkit evaluated on a power-grid testbed
- **Status:** Attack pattern abstracted; power-domain model is future work

### SPHERE (Bridge)

- **Role:** Effect-level instantiation across domains
- **Why:** Enables HARVEY-like manipulation in water or power-hydro without reproducing firmware exploit
- **Status:** Integration target

**Summary:**
> The formal example is water because the dynamics are simple and visible. The attack class is motivated by HARVEY, which was originally demonstrated in power systems. SPHERE gives us a way to evaluate the attack effect pattern across domains.

---

## 3. Tag Contract Mapping

### Water Treatment Tags

| SPHERE Tag | Type | dGL Variable | Role |
|------------|------|--------------|------|
| `RW_Tank_Level` | sensor | `x1` | Primary monitored variable |
| `RW_Tank_Level_2` | sensor | `x2` | Secondary tank level |
| `RW_Pump_Speed` | actuator | `P1` | Inflow control |
| `RW_Pump_2_Speed` | actuator | `P2` | Outflow control |
| `RW_Tank_PR_Valve` | actuator | `V1` | Pressure relief valve |
| `RW_Outlet_Valve` | actuator | `V2` | Outlet valve |
| `Alarm_RW_Tank_HH` | sensor | (implicit) | High-high alarm |

### Tag Contract Schema

```yaml
# SPHERE tag contract format
RW_Tank_Level:
  type: sensor
  direction: input
  units: meters
  range: [0, 10]
  update_rate: 1Hz
```

**dGL Translation:**
```
/* Variable declaration with bounds */
Real x1;  /* RW_Tank_Level: 0 <= x1 <= 10 */
```

---

## 4. Invariant Rule Translation

SPHERE defines invariant rules in YAML format. These map directly to dGL postconditions.

### Range Invariant

**SPHERE:**
```yaml
- type: range
  tag: RW_Tank_Level
  min: 0
  max: 10
  severity: critical
```

**dGL:**
```
/* Postcondition */
0 <= x1 & x1 <= 10
```

### Rate-of-Change Invariant

**SPHERE:**
```yaml
- type: rate_of_change
  tag: RW_Tank_Level
  max_rate: 0.5  # meters per second
```

**dGL:**
```
/* Evolution domain constraint */
{ x1' = V1*f1 - V2*P2*f2 & |x1'| <= 0.5 }
```

### Causality Invariant

**SPHERE:**
```yaml
- type: causality
  cause: RW_Pump_Speed
  effect: RW_Tank_Level
  direction: positive
  delay: [0, 30]  # seconds
```

**dGL:**
```
/* Timing bound in evolution */
{ x1' = V1*f1 - ... & t <= 30 }
```

### State Exclusivity

**SPHERE:**
```yaml
- type: state_exclusivity
  tags: [Pump_A_State, Pump_B_State]
  constraint: exactly_one_active
```

**dGL:**
```
/* Guard condition */
? (P1 = 1 -> P2 = 0) & (P2 = 1 -> P1 = 0);
```

---

## 5. Timing Parameters from Profiles

SPHERE simulation profiles provide realistic timing constants.

### realistic.yaml Profile

| Parameter | Value | dGL Usage |
|-----------|-------|-----------|
| Valve response time | τ = 30s | Evolution bound `t <= 30` |
| Pump ramp time | 2s | Transition timing |
| Sensor update rate | 1Hz | Loop period `Tmin` |
| PLC scan cycle | 100ms | Discrete step granularity |

### Application in dGL

```
/* Timing constants from SPHERE profiles */
Real T;      /* Maximum loop duration: 30s */
Real Tmin;   /* Minimum loop duration: 1s */
Real tau;    /* Actuator response time: 30s */

/* Evolution with timing bound */
{ x1' = ..., t' = 1 & t <= T };
? t >= Tmin;
```

---

## 6. HARVEY Pattern as Effect-Level Abstraction

### What Original HARVEY Is

Original HARVEY is a **firmware-level Man-in-the-PLC rootkit**:
- Sits below the PLC control logic (in firmware)
- Intercepts actuator commands before they reach the plant
- Intercepts sensor measurements before they reach control logic or operator view
- Originally evaluated on a **power-grid testbed**

### What SPHERE Provides

SPHERE abstracts the HARVEY pattern as an **effect-level two-way manipulation attack**:
- Plant-facing commands can be maliciously changed
- Controller/operator-visible measurements can show expected behavior

This abstraction can be instantiated in water treatment, water distribution, or power-hydro scenarios.

### Three-Layer Abstraction

| Layer | Implementation | SPHERE Role |
|-------|---------------|-------------|
| Original HARVEY | Firmware rootkit below PLC control logic | Not implemented |
| SPHERE abstraction | Effect-level experiment harness | ✓ **This is what SPHERE provides** |
| dGL model | Formal effect relation over actuators/sensors | ✓ Formalization target |

### What SPHERE Does NOT Provide

- The actual firmware rootkit implementation
- The specific exploitation chain
- Firmware-rootkit equivalence

### What SPHERE DOES Provide

- Plant-facing actuation manipulation
- Control over what logs/monitors observe
- Reproducible attack scenarios
- Run bundles for evidence collection

### dGL Formalization

```
/* HARVEY-like effect pattern */
{
    ? attackTimer <= AttackTime;
    /* Plant-facing: attacker commands */
    u_actual := u_attack;
    /* Controller/operator-facing: expected values (target extension) */
    /* y_reported := h_nominal(x_nominal); */
}
```

---

## 7. Integration Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTEGRATION PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SPHERE Artifacts          Translation          dGL Models      │
│  ─────────────────         ───────────          ──────────      │
│                                                                 │
│  ┌──────────────┐         ┌─────────┐         ┌────────────┐   │
│  │ Tag Contracts │   →    │ Variable │   →    │ valve_model│   │
│  │ (YAML)       │         │ Decls    │         │ .kyx       │   │
│  └──────────────┘         └─────────┘         └────────────┘   │
│                                                                 │
│  ┌──────────────┐         ┌─────────┐         ┌────────────┐   │
│  │ Invariant    │   →    │ dGL Post-│   →    │ attack_    │   │
│  │ Rules (YAML) │         │ conditions│        │ analysis   │   │
│  └──────────────┘         └─────────┘         │ .kyx       │   │
│                                               └────────────┘   │
│  ┌──────────────┐         ┌─────────┐                          │
│  │ Simulation   │   →    │ Constants │                         │
│  │ Profiles     │         │ (T, tau) │                         │
│  └──────────────┘         └─────────┘                          │
│                                                                 │
│  ┌──────────────┐         ┌─────────┐         ┌────────────┐   │
│  │ Attack       │   →    │ Effect   │   →    │ attack.kyx │   │
│  │ Surface Docs │         │ Patterns │                         │
│  └──────────────┘         └─────────┘         └────────────┘   │
│                                                                 │
│                     VERIFICATION                                │
│                     ────────────                                │
│                                                                 │
│  ┌────────────┐           ┌─────────┐         ┌────────────┐   │
│  │ KeYmaera X │   ←      │ Proof   │   →    │ Verified   │   │
│  │            │           │ Scripts │         │ Envelopes  │   │
│  └────────────┘           └─────────┘         └────────────┘   │
│                                                                 │
│                     VALIDATION                                  │
│                     ──────────                                  │
│                                                                 │
│  ┌────────────┐           ┌─────────┐         ┌────────────┐   │
│  │ SPHERE     │   →      │ Run     │   →    │ Empirical  │   │
│  │ Testbed    │           │ Bundles │         │ Evidence   │   │
│  └────────────┘           └─────────┘         └────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Target Case Study: Water Treatment UC1

### Overview

SPHERE's Water Treatment Use Case 1 (UC1) provides a realistic validation scenario.

### UC1 Parameters

| Parameter | SPHERE Value | Current Model |
|-----------|--------------|---------------|
| Tank capacity | 10,000 L | Normalized to H1=10 |
| Inflow rate | 100 L/min | f1 (to be calibrated) |
| Outflow rate | 120 L/min | f2 (to be calibrated) |
| High alarm | 8,000 L | H1=8 (normalized) |
| Low alarm | 2,000 L | L1=2 (normalized) |

### Alignment Tasks

1. **Parameter calibration:** Map SPHERE physical values to dGL constants
2. **Tag mapping:** Verify variable correspondence
3. **Effect-level attack:** Instantiate overflow attack on UC1
4. **Validation run:** Execute on testbed, compare results

---

## 9. Clarifications and Non-Claims

### What This Mapping Claims

- SPHERE tag contracts can be translated to dGL variable declarations
- SPHERE invariant rules can be translated to dGL postconditions
- SPHERE timing parameters can ground dGL constants
- SPHERE effect-level attacks can validate dGL attack models

### What This Mapping Does NOT Claim

- SPHERE implements the original HARVEY firmware rootkit
- The current dGL model has been validated against SPHERE
- Proofs are complete (pending KeYmaera X verification)

---

## 10. Missing SPHERE Artifacts (Gaps)

Elements not yet available or integrated:

| Artifact | Status | Impact |
|----------|--------|--------|
| Formal verification bridge | Missing | Cannot auto-translate to KeYmaera |
| Standards compliance mapping | Missing | Manual citation required |
| Redundancy architecture patterns | Missing | Using IEC 61508 directly |
| Degraded mode specifications | Missing | Defining in calculus |
| Multi-attack composition | Missing | Single attack only |

---

## Summary

| SPHERE Artifact | Calculus Mapping | Status |
|-----------------|------------------|--------|
| Tag contracts | Variable declarations | Ready |
| Invariant rules | Postconditions | Ready |
| Simulation profiles | Timing constants | Ready |
| Effect-level attacks | Subgame specification | Ready |
| Run bundles | Validation data | Target |
| UC1 parameters | Model calibration | Target |

**Key clarification:** SPHERE enables HARVEY-like effect-level manipulation without implementing the original firmware rootkit. The mapping is effect-level: it reproduces the plant-facing and observer-facing consequences of a firmware-level attack, not the exploit mechanism itself.
