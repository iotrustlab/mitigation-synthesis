# Metric Interface

Definition of operational and intervention cost metrics for mitigation cost analysis.

---

## 1. Two Concerns, Two Metric Types

The framework distinguishes two separate concerns:

| Concern | Metric Type | Nature | Example |
|---------|-------------|--------|---------|
| **Operational efficiency** | `ometric` | Continuous cost rate | Water loss, energy waste |
| **Intervention cost** | `rmetric` | Discrete action cost | Override count, actuator wear |

Both metrics start with a positive budget and decrease as costs accumulate. A strategy is viable only if both metrics remain non-negative.

**Important:** These are NOT reliability probabilities. See Section 5 for how IEC 61508 metrics relate.

---

## 2. Operational Metric (ometric)

### Purpose

Tracks costs to the physical process during mitigation:
- Water loss (product waste)
- Energy waste (inefficient pump/valve configurations)
- Production delays

### dGL Representation

```
ometric' = -x2 - c1 * (P1 * (1 - V1)) - c2 * (P2 * (1 - V2))
```

### Components

| Term | Meaning |
|------|---------|
| `-x2` | Water loss rate (proportional to tank 2 level draining) |
| `-c1 * (P1 * (1-V1))` | Cost when pump 1 on but valve 1 closed (wasted energy) |
| `-c2 * (P2 * (1-V2))` | Cost when pump 2 on but valve 2 closed (wasted energy) |

### Interpretation

- `ometric` decreases continuously during operation
- Inefficient configurations (pump on, valve closed) incur additional cost
- Strategy viable only if `ometric >= 0` at termination

---

## 3. Intervention Metric (rmetric)

### Purpose

Tracks costs of invoking the redundant intervention path. This is a **deterministic intervention cost**, not a reliability probability.

### What Intervention Cost May Represent

- Actuator wear from override actions
- Number of backup activations
- Operator burden (if manual override)
- Use of degraded operating mode
- Load shed or production loss
- Maintenance burden
- Any operational cost associated with using the redundant path

### dGL Representation

```
/* Discrete update on control changes */
old_P1 := P1; old_V1 := V1; old_P2 := P2; old_V2 := V2;

/* Redundant intervention path makes decisions */
P1_PLC2: P1 := *;
V1_PLC2: V1 := *;
...

/* Cost for using redundant intervention */
rmetric := rmetric - (|old_P1 - P1| * op1 + |old_V1 - V1| * ov1
                    + |old_P2 - P2| * op2 + |old_V2 - V2| * ov2)
```

### Components

| Term | Meaning |
|------|---------|
| `|old_P1 - P1| * op1` | Cost if backup changes pump 1 |
| `|old_V1 - V1| * ov1` | Cost if backup changes valve 1 |
| `|old_P2 - P2| * op2` | Cost if backup changes pump 2 |
| `|old_V2 - V2| * ov2` | Cost if backup changes valve 2 |

### Interpretation

- `rmetric` decreases discretely when the redundant path overrides the primary
- Cost proportional to number of actuator changes
- Strategy viable only if `rmetric >= 0` at termination

### Better Conceptual Name

While the code uses `rmetric`, conceptually this is better understood as:
- `intervention_budget`
- `override_budget`
- `redundant_action_budget`

---

## 4. Cost Constant Definitions

### Current Status: VALUES TBD

The following constants require semantic grounding with realistic values:

| Constant | Meaning | Units | Proposed Grounding |
|----------|---------|-------|-------------------|
| `c1` | Energy cost coefficient (pump 1) | cost/time | Energy price × pump power |
| `c2` | Energy cost coefficient (pump 2) | cost/time | Energy price × pump power |
| `op1` | Intervention cost for pump 1 change | cost/action | Actuator wear, operator burden |
| `ov1` | Intervention cost for valve 1 change | cost/action | Actuator wear, maintenance |
| `op2` | Intervention cost for pump 2 change | cost/action | Actuator wear, operator burden |
| `ov2` | Intervention cost for valve 2 change | cost/action | Actuator wear, maintenance |

### Grounding Approach (Target)

1. **Energy costs (c1, c2):** Derive from pump power ratings and electricity costs
2. **Intervention costs (op, ov):** Derive from actuator cycle limits, maintenance costs, operator time

---

## 5. Relationship to IEC 61508/61511 Metrics

### Key Distinction

IEC 61508/61511 metrics describe **architecture-level dependability**. They should be modeled as **constraints or parameters**, NOT as per-use consumable budgets.

### Architecture Constraints (NOT Consumed Per Action)

| Metric | Formula | Description | Role |
|--------|---------|-------------|------|
| PFDavg | ½ × λ_DU × T_p | Probability of dangerous failure on demand | Architecture constraint |
| PFH | (continuous) | Probability of dangerous failure per hour | Architecture constraint |
| HFT | (hardware fault tolerance) | Number of faults tolerated | Architecture constraint |
| SFF | (safe + detected) / total | Safe Failure Fraction | Architecture parameter |
| DC | detected / dangerous | Diagnostic Coverage | Architecture parameter |
| T_p | (proof-test interval) | Time between tests revealing hidden faults | Architecture parameter |

### Correct Usage in Calculus

```
/* Architecture adequacy (constraints, not consumed) */
HFT >= required_HFT
PFDavg <= PFD_target
proof_test_interval <= Tp_max

/* Intervention cost (deterministic, consumed per action) */
rmetric := rmetric - override_cost(action)
```

### What PFDavg Actually Is

PFDavg is the **probability that a safety function is unavailable when demanded**, usually computed from:
- Dangerous undetected failure rate (λ_DU)
- Proof-test interval (T_p)

It is NOT a per-activation budget that gets "used up" each time the backup acts. A safety function with PFDavg = 10⁻³ has a 0.1% chance of being unavailable when needed—this probability doesn't change based on how many times you've used it.

### Correct Interpretation

| Concept | Nature | How It Works |
|---------|--------|--------------|
| PFDavg | Probability | Architecture parameter; doesn't change per action |
| HFT | Count | Architecture constraint; doesn't change per action |
| `rmetric` | Budget | Operational cost; decreases with each intervention |

---

## 6. Cost Bounds in Postconditions

The control envelopes specify minimum metric budgets for each strategy:

### Envelope 1: Wait Out Attack
```
attackTimer > AttackTime & ometric >= 0 & rmetric >= 0
```
No additional cost if attack ends before safety violated.

### Envelope 2: Drain Safely
```
ometric >= (AttackTime-attackTimer)*f2 - ... & rmetric >= 0
```
Requires operational budget to cover drain duration. No intervention cost (primary still operating).

### Envelope 3: Override Valve
```
ometric >= (AttackTime-attackTimer + T) * c1 & rmetric >= ov1 * ceil((AttackTime-attackTimer) / Tmin)
```
Requires both operational (energy waste from pump running against closed valve) and intervention (override) budgets.

### Envelope 4: Override Pump
```
ometric >= 0 & rmetric >= op1 * ceil((AttackTime-attackTimer) / Tmin)
```
Requires intervention budget for pump overrides. No energy waste since pump is off.

---

## 7. Design Rationale

### Why Two Metrics?

Single-metric systems conflate different concerns:
- Operational costs (process efficiency, production)
- Intervention costs (redundant path usage, maintenance)

Separating them enables:
- Pareto-optimal strategy selection
- Explicit safety/efficiency tradeoffs
- Clear separation from architecture constraints

### Why Deterministic Budgets?

- Enables formal verification without probabilistic reasoning
- Simple non-negativity postconditions
- Clear "strategy viable" semantics
- Composes cleanly across time intervals

### Why Separate from PFDavg?

PFDavg is a **dependability property of the architecture**, computed from failure rates and test intervals. It doesn't make sense to "spend" PFDavg each time you use a backup—the backup either works or it doesn't, with probability governed by its failure modes.

`rmetric` captures something different: the **operational cost** of using the redundant path, regardless of whether that path happens to fail.

---

## Summary

| Aspect | Operational (ometric) | Intervention (rmetric) |
|--------|----------------------|------------------------|
| Tracks | Process efficiency | Redundant path usage |
| Updates | Continuous (differential) | Discrete (on override) |
| Costs | Water loss, energy waste | Actuator changes |
| Nature | Deterministic cost | Deterministic cost |
| NOT | Reliability probability | PFDavg budget |
| Viability | `ometric >= 0` | `rmetric >= 0` |
| Constants | c1, c2 | op1, ov1, op2, ov2 |
| Status | **VALUES TBD** | **VALUES TBD** |

### Architecture Constraints (Separate)

| Constraint | Nature | Not Consumed |
|------------|--------|--------------|
| `HFT >= 1` | Architecture requirement | ✓ |
| `PFDavg <= target` | Dependability requirement | ✓ |
| `proof_test <= Tp_max` | Testing requirement | ✓ |
