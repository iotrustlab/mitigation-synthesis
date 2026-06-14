# Redundancy-Aware Mitigation Synthesis for ICS

This repository now contains the canonical Phase 1 artifact for the project: one CLEO-checkable mitigation envelope for a water-tank attack scenario.

## Phase 1 Goal

The Phase 1 objective is to show one end-to-end formally verified example of:

1. an attacker changing plant-facing commands,
2. a redundant mitigation path overriding the attack, and
3. a proof that safety and cost bounds are preserved.

This is intentionally narrower than the full research vision. It gives us one trustworthy baseline before expanding to richer models or automated synthesis.

## What Is In Scope

| File | Purpose |
|------|---------|
| `attack.envelope` | Canonical Phase 1 mitigation envelope |
| `water_attack.py` | Local parser and verification runner for the canonical envelope |
| `requirements.md` | Toolchain and run instructions |

## Scenario Summary

The model is a two-tank water system with binary pumps and valves.

- `x1`, `x2`: tank levels
- `P1`, `P2`: pump commands
- `V1`, `V2`: valve commands
- `ometric`: remaining operational budget
- `rmetric`: remaining mitigation budget

The attacker is modeled at the effect level. During the active attack window, it forces the primary controller toward an unsafe inflow pattern. The defender has a redundant path that can still force `P1 := 0`.

The Phase 1 envelope proves a final-step case:

- less than one control period remains before the attack ends,
- the system starts in a safe shutdown configuration,
- the secondary tank is already empty (`x2 = 0`),
- the redundant controller can spend one mitigation action to keep the system safe.

## Quick Start

Detailed setup is in [requirements.md](requirements.md).

From the repository root, after activating an environment where CLEO is installed and KeYmaera X plus Z3 are available:

```bash
python mitigation_synthesis/water_attack.py
```

Expected result:

- `attack.envelope` parses correctly
- `loop_inductive` passes
- `loop_post` passes
- `ode` passes
- `arithmetic` passes

To do only a parser smoke test:

```bash
python mitigation_synthesis/water_attack.py --parse-only
```

## Current Research Position

What Phase 1 proves:

- a redundant override exists for this canonical final-step case
- the override preserves safety
- the override keeps both metrics nonnegative

What Phase 1 does not yet prove:

- the full multi-step attack horizon
- synthesis of the mitigation automatically
- broader actuator choices or richer cost models
- a general architecture search over redundant paths

## Contributing

When changing the Phase 1 artifact:

- keep the formal model small and readable
- rerun `water_attack.py`
- update `requirements.md` if toolchain expectations change

## License

TBD
