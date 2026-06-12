# Redundancy-Aware Mitigation Synthesis for ICS

A formal verification framework for synthesizing safe redundant controller responses in Industrial Control Systems (ICS) under attack or failure conditions.

## Problem Statement

Building on HyTwin's attack detection and mitigation horizon capabilities, this project addresses the **response synthesis problem**: given that an attack has been detected and a mitigation window identified, how do we formally synthesize and verify safe redundant control responses?

The attacker is modeled at the **effect level**: it can replace plant-facing commands and, in stealthy cases, spoof controller/operator-facing measurements. The defender has access to an independent **redundant intervention path**—e.g., backup PLC, external monitor, operator override, or bump-in-the-wire safety device.

## Approach Overview

The framework uses **differential game logic (dGL)** to model:

1. **Effect-Level Attack Model** — Attacker actions as plant-facing command replacement (subgame replacement)
2. **Intervention Cost Metrics** — Operational costs (`ometric`) + intervention costs (`rmetric`)
3. **Control Envelopes** — Certified safe regions with cost bounds, providing mitigation certificates

Verification is performed using **KeYmaera X**, with standards alignment to IEC 61508, IEC 62443, and NERC PRC-012-2.

**Important distinctions:**
- We model attack **effects** on the plant, not exploit mechanisms
- `rmetric` is a deterministic intervention cost, NOT a PFDavg budget
- HFT, PFDavg, SFF are architecture constraints, not consumed per action

## Repository Structure

| File | Description | Status |
|------|-------------|--------|
| `valve_model.kyx` | Basic water tank dGL model | Complete |
| `valve_model_basic.kyx` | Model with metrics instrumentation | Complete |
| `attack.kyx` | Overflow attack shorthand / note artifact | Supporting |
| `attack_analysis.kyx` | Main composed model with attack, metrics, and proposed mitigation strategies | Model complete, proofs pending |
| `attack.envelope` | CLEO-style envelope draft for general override mitigation | Draft |
| `attackvalve.envelope` | CLEO-style envelope draft for valve-focused mitigation | Draft |
| `water_attack.py` | Local parser / development runner for the envelope drafts | Active |
| `requirements.md` | Detailed runtime and verification setup instructions | Current |

## Quick Start

Detailed setup and version guidance live in [requirements.md](requirements.md).

### Direct `.kyx` workflow

```bash
keymaerax valve_model.kyx
keymaerax attack_analysis.kyx
```

### `.envelope` workflow

After installing CLEO in a Python 3.12 environment:

```bash
python water_attack.py
python water_attack.py attackvalve.envelope
```

Current state:
- both envelope files parse successfully
- the attack envelopes are still draft proof artifacts
- full verification of `attack.envelope` is not complete yet because annotations for `a` and `aw` are still missing

### Model Variables

| Variable | Description | Type |
|----------|-------------|------|
| `x1, x2` | Water levels in tanks | Continuous state |
| `P1, P2` | Pump controls | Binary (0/1) |
| `V1, V2` | Valve controls | Binary (0/1) |
| `f1, f2` | Flow rates | Parameters |
| `ometric` | Operational cost (budget remaining) | Metric |
| `rmetric` | Intervention cost (budget remaining) | Metric |

### Safety Property

```
safe(x1, x2) <-> (L1 <= x1 <= H1) & (L2 <= x2 <= H2)
```

## Domain Roles

- **Water:** Formal running example (simple dynamics, intuitive model)
- **Power/HARVEY:** Motivating attack pattern (original HARVEY was power-grid firmware rootkit)
- **SPHERE:** Effect-level attack instantiation across domains (U of Utah CPS Enclave)

## Related Work

- **HyTwin**: Hybrid digital twin for attack detection and mitigation horizon
- **SPHERE/CPS Enclave**: Security and Privacy Heterogeneous Environment for Reproducible Experimentation (U of Utah)
- **XPhysICS**: Taxonomy of physical-domain ICS attacks
- **HARVEY**: Firmware-level PLC rootkit (power-grid origin; we use as attack pattern)
- **dGL**: Differential game logic for hybrid systems verification

## Target Venues

- DSN (Dependable Systems and Networks)
- NFM (NASA Formal Methods)
- FM (Formal Methods)

## Contributing

When contributing:
- keep the formal artifacts small and readable
- state whether you tested the `.kyx` workflow, the `.envelope` workflow, or both
- update `requirements.md` if toolchain expectations change

## License

TBD

## References

See `mitigation_synthesis_paper/refs.bib` for complete bibliography (97 entries).
