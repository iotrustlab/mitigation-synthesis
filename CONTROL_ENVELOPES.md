# Control Envelopes

Explanation of the control envelope concept and its mapping to NERC PRC-012-2.

---

## 1. What is a Control Envelope?

A **control envelope** defines a certified safe region of operation with associated cost bounds. If the system state is within an envelope, there exists a mitigation strategy that:
1. Maintains safety (physical constraints)
2. Stays within budget (metric constraints)

### Formal Structure

```
Envelope = { precondition } [ action ] { postcondition ∧ ¬hazards }
```

| Component | Meaning |
|-----------|---------|
| Precondition | State conditions enabling this strategy |
| Action | dGL program (control actions) |
| Postcondition | Guaranteed outcome if strategy followed |
| ¬hazards | Safety properties maintained |

### Key Property

Envelopes are **disjunctive**: at any state, the system must be in at least one envelope. The union of all envelopes covers all safe operating states.

---

## 2. NERC PRC-012-2 Four-Part Test Mapping

NERC Requirement 5 specifies four parts for evaluating Remedial Action Schemes (RAS). Control envelopes implement this structure formally:

| NERC Part | Requirement | Envelope Component |
|-----------|-------------|-------------------|
| (a) Trigger | Identify conditions that trigger RAS | **Precondition** |
| (b) Respond | Describe RAS response actions | **Action** (dGL program) |
| (c) Effective | Demonstrate response achieves goal | **Postcondition** |
| (d) No adverse | Prove no adverse effects | **Hazard negation** |

### Example Mapping

**NERC RAS:** "When line overload detected, open breaker B1 within 60ms."

**Control Envelope:**
```
{ overload(line) }
[ open(B1); t := 0; { t' = 1 & t <= 60ms } ]
{ ¬overload(line) ∧ safe(grid) }
```

---

## 3. Four Mitigation Strategies

From `attack_analysis.kyx`, four control envelopes define the mitigation space:

### Envelope 1: Wait Out Attack

**Strategy:** Do nothing; attack will end before causing harm.

```
Precondition:
  safe(x1, x2) ∧ attackTimer > AttackTime ∧ ometric >= 0 ∧ rmetric >= 0

Action:
  (none - attack already over)

Postcondition:
  safe(x1, x2) ∧ ometric >= 0 ∧ rmetric >= 0
```

**When applicable:** Attack timer expired, system still safe, budgets available.

**Cost:** Zero additional cost.

---

### Envelope 2: Drain Safely

**Strategy:** Use outflow to reduce tank level, maintaining safety margin.

```
Precondition:
  safe(x1, x2) ∧
  ometric >= (AttackTime-attackTimer)*f2 - (H2-x2-T/(f2-f1))/f2 ∧
  rmetric >= 0 ∧
  f2 >= f1 ∧
  T * (f2-f1) >= f2*(x2 - L1) ∧
  T*f1 <= H1 - (L1 + T * (f2-f1))

Action:
  /* Maintain drainage while attack continues */
  V2 := 1; P2 := 1;  /* Open outflow */

Postcondition:
  safe(x1, x2) ∧ ometric >= 0 ∧ rmetric >= 0
```

**When applicable:** Outflow rate exceeds inflow; sufficient tank margin; operational budget covers drain time.

**Cost:** Operational cost only (water loss during drain).

---

### Envelope 3: Override Valve

**Strategy:** Backup controller closes inflow valve, blocking overflow.

```
Precondition:
  safe(x1, x2) ∧
  ometric >= (AttackTime-attackTimer + T) * c1 ∧
  rmetric >= ov1 * ceil((AttackTime-attackTimer) / Tmin)

Action:
  /* Backup PLC overrides valve */
  V1_PLC2: V1 := 0;
  rmetric := rmetric - ov1;

Postcondition:
  safe(x1, x2) ∧ ometric >= 0 ∧ rmetric >= 0
```

**When applicable:** Sufficient operational budget for energy waste (pump on, valve closed); sufficient intervention budget for multiple overrides.

**Cost:** Both operational (c1 per time unit) and intervention (ov1 per override).

---

### Envelope 4: Override Pump

**Strategy:** Backup controller disables pump, stopping inflow.

```
Precondition:
  safe(x1, x2) ∧
  ometric >= 0 ∧
  rmetric >= ov2 * ceil((AttackTime-attackTimer) / Tmin)

Action:
  /* Backup PLC overrides pump */
  P1_PLC2: P1 := 0;
  rmetric := rmetric - op1;

Postcondition:
  safe(x1, x2) ∧ ometric >= 0 ∧ rmetric >= 0
```

**When applicable:** Sufficient intervention budget for pump overrides.

**Cost:** Intervention cost only (no energy waste since pump off).

---

## 4. Worked Example

**Scenario:**
- Attack starts at t=0, duration AttackTime=100s
- Current state: x1=5 (tank 1), x2=3 (tank 2)
- Safety bounds: L1=0, H1=10, L2=0, H2=8
- Budgets: ometric=50, rmetric=10
- Costs: c1=0.5, ov1=2, op1=2
- Timing: Tmin=10s, T=15s

**Step 1: Check Envelope 1 (Wait Out)**
```
attackTimer > AttackTime?  → 0 > 100?  → FALSE
```
Not applicable (attack still active).

**Step 2: Check Envelope 4 (Override Pump)**
```
safe(x1, x2)?  → (0 <= 5 <= 10) ∧ (0 <= 3 <= 8)?  → TRUE
ometric >= 0?  → 50 >= 0?  → TRUE
rmetric >= op1 * ceil(AttackTime/Tmin)?
  → 10 >= 2 * ceil(100/10)?
  → 10 >= 2 * 10?
  → 10 >= 20?  → FALSE
```
Not applicable (insufficient redundancy budget).

**Step 3: Check Envelope 3 (Override Valve)**
```
ometric >= (AttackTime + T) * c1?
  → 50 >= (100 + 15) * 0.5?
  → 50 >= 57.5?  → FALSE
```
Not applicable (insufficient operational budget).

**Step 4: Check Envelope 2 (Drain Safely)**
```
Requires: f2 >= f1, specific margin calculations...
```
(Depends on flow rate parameters)

**Result:** With given budgets, may need to increase ometric or rmetric, or wait for attack to partially elapse before envelope becomes applicable.

---

## 5. Verification Status

**IMPORTANT: All envelopes are PROPOSED but not yet PROVEN.**

| Envelope | dGL Expression | KeYmaera X Proof |
|----------|---------------|------------------|
| 1 (Wait out) | Defined in attack_analysis.kyx | **PENDING** |
| 2 (Drain) | Defined in attack_analysis.kyx | **PENDING** |
| 3 (Override valve) | Defined in attack_analysis.kyx | **PENDING** |
| 4 (Override pump) | Defined in attack_analysis.kyx | **PENDING** |
| Combined invariant | Disjunction of all four | **PENDING** |

### What "Proven" Means

Once proven in KeYmaera X:
- Envelope is a valid loop invariant
- If precondition holds, postcondition guaranteed
- Safety maintained through all transitions
- Cost bounds formally verified

### Current Status

The control envelopes are mathematically specified in the dGL code. They represent the **intended** invariant structure. Formal verification in KeYmaera X is required to confirm they are actually invariants of the system dynamics.

---

## 6. Design Principles

### Completeness

The disjunction of all envelopes should cover all reachable safe states:
```
∀σ. safe(σ) → (envelope_1(σ) ∨ envelope_2(σ) ∨ envelope_3(σ) ∨ envelope_4(σ))
```

### Non-interference

Each envelope can be executed independently; no envelope's action violates another's precondition.

### Monotonicity

Cost budgets only decrease; once an envelope becomes inapplicable due to budget, it stays inapplicable.

### Composability

Envelopes can be sequenced: use envelope_3 until budget exhausted, then switch to envelope_4.

---

## Summary

| Envelope | Strategy | Operational Cost | Intervention Cost |
|----------|----------|-----------------|-------------------|
| 1 | Wait out | 0 | 0 |
| 2 | Drain | Water loss | 0 |
| 3 | Override valve | Energy waste (c1) | ov1 per override |
| 4 | Override pump | 0 | op1 per override |

**Note:** `rmetric` is intervention cost (deterministic), NOT PFDavg budget. Architecture constraints (HFT, PFDavg, SFF) are separate and not consumed per action.

**Verification Status:** All envelopes PROPOSED (pending KeYmaera X proof)
