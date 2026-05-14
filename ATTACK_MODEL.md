# Attack Model

Explanation of the subgame replacement abstraction for modeling ICS attacks.

---

## 1. Motivation

Why model attacks formally?

Traditional ICS security focuses on **detection**: identifying when an attack occurs. However, detection alone is insufficient—we need **response synthesis**: determining what the system should do after detection.

Formal attack modeling enables:
- **Verification** of mitigation strategies before deployment
- **Cost analysis** of different response options
- **Completeness arguments** about coverage of attack classes
- **Standards compliance** with explicit threat model documentation

---

## 2. Abstraction: Attacks as Effect-Level Replacement

The core abstraction: **an attack is modeled by its plant-facing effect**, not by its exploit mechanism.

From the physical process perspective, it doesn't matter *how* an attacker compromised the PLC (firmware rootkit, network MITM, credential theft, etc.)—what matters is that the plant now receives different commands than it would under normal operation.

### Key Design Choice

We model the **effect** of attacks on the physical process, not the **mechanism** by which attacks are carried out.

| Layer | What It Captures | What It Ignores |
|-------|------------------|-----------------|
| Exploit mechanism | How attacker gains control | ✓ Out of scope |
| **Attack effect** | What commands reach the plant | ✓ **Our model** |
| Plant response | How physics evolves | ✓ Continuous dynamics |

### Two-Way Manipulation

Sophisticated attacks (like HARVEY) involve two coordinated effects:

1. **Plant-facing command replacement:** Attacker commands reach actuators instead of legitimate commands
2. **Controller/operator-facing measurement spoofing:** Controller and operator see expected-looking sensor values

```
u_actual := u_attack          /* Plant sees attacker commands */
y_reported := y_nominal       /* Controller/operator sees expected values */
```

This creates a stealthy attack where the physical process is being damaged while the control system and operators see nominal behavior.

---

## 3. dGL Representation

Attacks are expressed using nondeterministic choice (`++`) with time-bounded conditions:

```
{
    ? attackTimer <= AttackTime;
    /* Attack active: plant receives attacker commands */
    P1 := attack_P1;
    V1 := attack_V1;
    P2 := attack_P2;
    V2 := attack_V2;
}
++
{
    ? attackTimer > AttackTime;
    /* Attack over: plant receives legitimate commands */
    P1 := *;
    V1 := *;
    P2 := *;
    V2 := *;
}
```

The `++` operator represents nondeterministic choice: at each step, either the attack branch or the normal branch executes, depending on the timer condition.

### Game-Theoretic Interpretation

In differential game logic:
- **Angel** (defender): controls redundant intervention path, chooses mitigation strategy
- **Demon** (attacker): controls attack timing and values within bounds
- **Goal**: Angel maintains safety despite Demon's worst-case choices

---

## 4. HARVEY as Attack Pattern (Not Direct Implementation)

### What HARVEY Is

Original HARVEY is a **firmware-level Man-in-the-PLC rootkit**. Key characteristics:
- Sits below the PLC control logic (in firmware)
- Intercepts actuator commands before they reach the plant
- Intercepts sensor measurements before they are exposed to control logic or operator view
- Originally evaluated on a **power-grid testbed** (not water treatment)

### Three Layers of Abstraction

| Layer | Description | Our Usage |
|-------|-------------|-----------|
| **Original HARVEY** | Firmware rootkit on PLC | Motivating attack pattern |
| **SPHERE abstraction** | Effect-level testbed manipulation | Empirical validation |
| **dGL model** | Formal effect relation | Verification target |

### What We Do NOT Claim

- We do **not** claim SPHERE implements the original firmware rootkit
- We do **not** claim HARVEY targets water treatment (original was power grid)
- We **do** use HARVEY as a motivating attack **pattern**: two-way manipulation of commands and sensor/operator view

### HARVEY Pattern in dGL

The HARVEY pattern abstracts to:

```
/* Plant-facing: attacker commands reach actuators */
u_actual := u_attack

/* Controller/operator-facing: expected values reported */
y_reported := h_nominal(x_nominal)
```

This lets the physical process evolve under malicious commands while the controller or operator sees a plausible nominal trajectory.

---

## 5. SPHERE Effect-Level Instantiation

In SPHERE, HARVEY-like effects can be reproduced at the experiment harness level:

| HARVEY Mechanism | SPHERE Abstraction |
|------------------|-------------------|
| Firmware command interception | Plant-facing variable manipulation |
| Firmware sensor injection | Expected network/operator view simulation |
| Stealthy operation | Coordinated timing of both |

**SPHERE does NOT implement:**
- The actual firmware rootkit
- The specific exploitation chain
- The power-grid-specific payload

**SPHERE DOES provide:**
- Effect-level manipulation of plant-facing actuation
- Control over what logs/monitors observe
- Reproducible attack scenarios across domains (water, power-hydro)

---

## 6. Attack Taxonomy Alignment

### XPhysICS EffectFamily Mapping

| XPhysICS Category | Effect Description | dGL Pattern |
|-------------------|-------------------|-------------|
| OVERFLOW_ACCUMULATION | Force inflow, block outflow | `P1:=1, V1:=1, P2:=0, V2:=0` |
| UNDERFLOW_DEPLETION | Block inflow, force outflow | `P1:=0, V1:=0, P2:=1, V2:=1` |
| COMMAND_OVERRIDE | Coerce actuator commands | `u := u_attack` |
| SENSOR_SPOOF | Falsify sensor readings | `y_reported := y_fake` |
| ALARM_SUPPRESSION | Hide trigger conditions | Guard manipulation |
| ENERGY_EXCURSION | Speed/pressure limits | Rate constraint violation |

### Current Implementation

The current model implements **overflow attack**:

```
/* From attack.kyx */
Attack: Overflow

P1_PLC1 -> 1    /* Force pump on */
V1_PLC1 -> 1    /* Force inflow valve open */
P2_PLC1 -> 0    /* Disable outflow pump */
V2_PLC1 -> 0    /* Close outflow valve */

for time AttackTime
```

This causes water to accumulate in Tank 1, potentially causing overflow.

---

## 7. Target Attacks (Pending Implementation)

### 7.1 Drain Attack

**Effect:** Deplete water reserves
**Pattern:** Maximize outflow, minimize inflow

```
P1 := 0; V1 := 0;    /* No inflow */
P2 := 1; V2 := 1;    /* Maximum outflow */
```

### 7.2 Sensor Spoof Attack (Target)

**Effect:** Hide unsafe condition from operators/controllers
**Pattern:** Report false sensor values

```
x1_reported := x1 - bias;    /* Report lower level than actual */
```

### 7.3 Alarm Suppression Attack (Target)

**Effect:** Prevent safety system activation
**Pattern:** Suppress high-level alarms

```
alarm_HH := 0;    /* Force alarm off despite high level */
```

---

## 8. Standards Justification

### NIST SP 800-82r3 (Section 2.5)

> "Manipulation of control" includes unauthorized changes to instructions, commands, or alarm thresholds that affect the controlled physical process.

Our effect-level model directly captures this: the attacker changes what commands reach the actuators.

### IEC 62443-3-3 (FR3)

> Framework Requirement 3 (FR3) addresses integrity, including "prevention of unauthorized manipulation of measurement values and command parameters."

Our attack model captures both:
- Command manipulation: `u_actual := u_attack`
- Measurement manipulation: `y_reported := y_fake` (target extension)

---

## 9. Domain Roles

### Water (Current Running Example)

- **Role:** Formal running example
- **Why:** Dynamics are simple and visible; tank/pump/valve model is intuitive
- **Status:** Current dGL model

### Power (HARVEY Origin)

- **Role:** Motivating original attack
- **Why:** Original HARVEY was power-grid firmware rootkit
- **Status:** Future case study, not current model

### SPHERE (Bridge)

- **Role:** Effect-level instantiation across domains
- **Why:** Enables HARVEY-like manipulation in water or power-hydro without firmware exploit
- **Status:** Integration target

---

## Summary

| Aspect | Approach |
|--------|----------|
| Abstraction level | Effect-level (plant-facing commands) |
| Formalism | dGL nondeterministic choice |
| Time bounds | `attackTimer <= AttackTime` |
| Current attacks | Overflow |
| Target attacks | Drain, sensor spoof, alarm suppression |
| Standards alignment | NIST 800-82, IEC 62443 |
| HARVEY role | Motivating pattern (power-grid origin) |
| SPHERE role | Effect-level validation infrastructure |
| What we model | Attack **effects** on plant |
| What we ignore | Exploit **mechanisms** |
