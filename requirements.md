# Runtime and Verification Requirements

This document explains how to run the repository without relying on machine-specific paths.

## Scope

This repository contains two kinds of formal artifacts:

1. `.kyx` files for direct KeYmaera X use
2. `.envelope` files plus `water_attack.py` for the CLEO-based envelope workflow

These workflows have different requirements.

## Recommended Toolchain

| Component | Recommended Version | Why |
|-----------|---------------------|-----|
| Git | 2.34+ | Standard repository operations |
| Python | 3.12.x | Matches the CLEO artifact requirements |
| pip | 24+ | Modern editable-install support |
| Java | 21 LTS | Stable runtime for KeYmaera X; Java 11+ is generally acceptable |
| Z3 CLI | 4.16.0 | Recommended for the CLEO workflow |
| Python `z3-solver` | 4.16.0.0 | Matches the tested CLEO install |
| KeYmaera X | 5.x | Needed for proving dGL obligations |
| CLEO | 0.1.0 artifact dated 2026-05-19 | Provides `EnvelopeSession`, `parse_envelope`, and proof checking |

## What Is In This Repo

| File type | Purpose |
|-----------|---------|
| `*.kyx` | Differential game logic models for KeYmaera X |
| `*.envelope` | CLEO envelope drafts |
| `water_attack.py` | Local runner for parsing or developing the attack envelopes |

## Workflow A: Run the `.kyx` Models Directly

Use this if you want to inspect or prove the KeYmaera X models directly.

### Requirements

- KeYmaera X 5.x installed separately
- Java installed and available on `PATH`

### Commands

From the repository root:

```bash
cd mitigation_synthesis
keymaerax valve_model.kyx
keymaerax attack_analysis.kyx
```

If your KeYmaera X installation is not exposed as `keymaerax`, use the launch method provided by your own installation.

## Workflow B: Run the `.envelope` Files with CLEO

Use this if you want to parse or verify the envelope drafts.

### Requirements

- Python 3.12.x
- Java on `PATH`
- Z3 installed either:
  - on `PATH` as `z3`, or
  - through KeYmaera X configuration
- A local checkout or unpacked copy of the CLEO artifact

### Get CLEO

Use the CLEO artifact associated with:

- DOI `10.1184/R1/32320254`
- Title: `Cleo: Command Line EnvelOpe Verification Tool`

After unpacking, the CLEO directory should contain:

- `pyproject.toml`
- `cleo/`
- `examples/`
- `questions/`
- `tests/`

### Create the CLEO Virtual Environment

From the CLEO root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### Configure Z3 for KeYmaera X

Recommended:

- install Z3 CLI 4.16.0
- make sure `z3` is available on `PATH`

If you prefer explicit KeYmaera X configuration, add or update `~/.keymaerax/keymaerax.conf` with:

```text
QE_TOOL = z3
Z3_PATH = <path-to-your-z3-binary>
```

Use your own local Z3 path in place of `<path-to-your-z3-binary>`.

### Run the Repo's Envelope Runner

Activate the CLEO virtual environment first, then run from this repository root:

```bash
cd mitigation_synthesis
python water_attack.py
python water_attack.py attackvalve.envelope
```

These commands perform parser smoke tests for:

- `attack.envelope`
- `attackvalve.envelope`

### Current Verification Status

The current repository state is:

- `attack.envelope` parses successfully
- `attackvalve.envelope` parses successfully
- the repo's attack envelopes are not yet fully verified

Known proof gap in `attack.envelope`:

- missing loop invariant for game id `a`
- missing ODE annotation / tactic for game id `aw`

So the current `water_attack.py` path is a parser/development harness, not a completed proof script.

## CLEO Smoke Tests

Once CLEO is installed, these are useful checks from the CLEO root:

```bash
source .venv/bin/activate
python -m pytest tests/test_parser.py tests/test_envelope_format.py -q
python - <<'PY'
from cleo.envelope_file import check_envelope_file
result = check_envelope_file("examples/lotka.envelope")
print(result.all_passed)
PY
```

Expected behavior:

- the parser/unit tests should pass
- `examples/lotka.envelope` should verify successfully

## Repo-Specific Notes

- This repository does not bundle its own standalone KeYmaera X installation for opening `.kyx` files directly.
- The envelope workflow depends on an external CLEO installation.
- `water_attack.py` imports `cleo`, so it must be run from an environment where CLEO has already been installed.
- Docker is optional, not required.

## Minimum Practical Setup

If you only want to inspect the formal models:

- install KeYmaera X
- open `attack_analysis.kyx`

If you want to work on the envelope path:

- install CLEO in a Python 3.12 virtual environment
- install or configure Z3
- run `python water_attack.py`

