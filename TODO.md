# Task List

Prioritized tasks for the Redundancy-Aware Mitigation Synthesis project.

---

## Priority 1: Foundation (Critical Path)

### Task 1.1: First KeYmaera X Proof
- **Status:** Pending
- **Owner:** TBD
- **Description:** Complete proof of simplest control envelope (wait-out attack strategy)
- **Acceptance Criteria:**
  - [ ] `envelope_1` proven as loop invariant in KeYmaera X
  - [ ] Proof script committed to repository
  - [ ] Proof statistics documented (steps, time, lemmas)
  - [ ] Tactic explanations added as comments

### Task 1.2: Effect-Level Attack Model Documentation
- **Status:** Pending
- **Owner:** TBD
- **Description:** Document attack model with explicit effect-level framing
- **Acceptance Criteria:**
  - [ ] NIST SP 800-82 "manipulation of control" linked to effect-level replacement
  - [ ] Three-layer abstraction clear (HARVEY → SPHERE → dGL)
  - [ ] HARVEY correctly characterized as power-grid firmware rootkit (not water treatment)
  - [ ] SPHERE role as effect-level instantiation documented
  - [ ] 3 concrete attack effect examples (overflow, drain, sensor spoof)

### Task 1.3: Intervention Cost Grounding
- **Status:** Pending
- **Owner:** TBD
- **Description:** Define semantic grounding for intervention cost constants
- **Acceptance Criteria:**
  - [ ] Constants c1, c2 defined in terms of energy cost
  - [ ] Constants op1, ov1, op2, ov2 defined as intervention costs (NOT PFD impact)
  - [ ] Clear separation from architecture constraints (HFT, PFDavg, SFF)
  - [ ] Example calculations with realistic values
  - [ ] Document what intervention cost may represent (actuator wear, operator burden, etc.)

---

## Priority 2: Control Envelopes

### Task 2.1: Control Envelope Explanation
- **Status:** Pending
- **Owner:** TBD
- **Description:** Document control envelope concept with NERC mapping
- **Acceptance Criteria:**
  - [ ] NERC PRC-012-2 four-part test mapped to envelope structure
  - [ ] All 4 mitigation strategies explained with worked examples
  - [ ] Cost calculations demonstrated step-by-step
  - [ ] Verification status clearly marked as PROPOSED (pending proof)

### Task 2.2: Prove Remaining Envelopes
- **Status:** Pending
- **Owner:** TBD
- **Depends On:** Task 1.1
- **Description:** Complete KeYmaera X proofs for all mitigation strategies
- **Acceptance Criteria:**
  - [ ] Envelope 2 (drain safely) proven
  - [ ] Envelope 3 (override valve) proven
  - [ ] Envelope 4 (override pump) proven
  - [ ] Combined disjunction proven as invariant

---

## Priority 3: SPHERE Grounding

### Task 3.1: SPHERE Effect-Level Integration
- **Status:** Pending
- **Owner:** TBD
- **Description:** Ground model in SPHERE water treatment parameters with correct framing
- **Acceptance Criteria:**
  - [ ] Variables mapped to SPHERE tags (x1→RW_Tank_Level, P1→RW_Pump)
  - [ ] Timing constants from SPHERE profiles used (valve tau=30s)
  - [ ] Effect-level attack pattern instantiated (NOT firmware rootkit)
  - [ ] SPHERE role clearly documented as effect-level abstraction
  - [ ] Integration pipeline documented

---

## Priority 4: Paper Writing

### Task 4.1: Paper Section 3 (Framework)
- **Status:** Pending
- **Owner:** TBD
- **Depends On:** Tasks 1.1-1.3, 2.1
- **Description:** Write core framework section of paper
- **Acceptance Criteria:**
  - [ ] 3.1 System Model subsection complete
  - [ ] 3.2 Attack Model subsection complete (effect-level, not exploit mechanism)
  - [ ] 3.3 Metrics subsection complete (intervention cost separate from architecture constraints)
  - [ ] 3.4 Control Envelopes subsection complete
  - [ ] 3.5 Verification subsection complete
  - [ ] At least one theorem stated
  - [ ] Running water tank example throughout
  - [ ] HARVEY correctly framed as motivating pattern (power-grid origin)

### Task 4.2: Architecture Figure
- **Status:** Pending
- **Owner:** TBD
- **Description:** Create architecture diagram for README and paper
- **Acceptance Criteria:**
  - [ ] Physical Process → Primary PLC → Redundant Intervention Path layers shown
  - [ ] Attack effect vector indicated (not exploit mechanism)
  - [ ] Metrics layer shown (ometric, rmetric)
  - [ ] Architecture constraints shown separately (HFT, PFDavg)
  - [ ] Envelope certification indicated
  - [ ] SPHERE evidence loop shown

---

## Completed Tasks

_(None yet)_

---

## Notes

- All tasks have "Owner: TBD" until assigned
- Dependencies must be completed before dependent tasks start
- Acceptance criteria must be fully met before marking complete
- Update this file as tasks progress

### Key Terminology Reminders

- `rmetric` = intervention cost (NOT PFDavg budget)
- HFT, PFDavg, SFF = architecture constraints (NOT consumed per action)
- HARVEY = power-grid firmware rootkit (NOT water treatment)
- SPHERE = effect-level abstraction (NOT firmware rootkit implementation)
- We model attack **effects**, not exploit mechanisms

---

## Current State

**Last Updated:** TBD

**Summary:**
- Foundation tasks pending
- No KeYmaera X proofs completed
- Paper at ~10% readiness

**Blockers:**
- None currently blocking start of Task 1.1
