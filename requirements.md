# Runtime and Verification Requirements

This document explains how to run the canonical Phase 1 artifact without using machine-specific paths.

## Scope

The repository now centers on one CLEO envelope workflow:

- `attack.envelope` is the formal artifact
- `water_attack.py` is the local runner

There is no separate bundled `.kyx` workflow in this cleaned Phase 1 snapshot.

## Recommended Toolchain

| Component | Recommended Version | Why |
|-----------|---------------------|-----|
| Git | 2.34+ | Standard repository operations |
| Python | 3.12.x | Matches the CLEO artifact requirements |
| pip | 24+ | Modern editable-install support |
| Java | 21 LTS | Stable runtime for KeYmaera X |
| Z3 CLI | 4.16.0 | Recommended backend for KeYmaera X and CLEO |
| Python `z3-solver` | 4.16.0.0 | Matches the tested CLEO install |
| KeYmaera X | 5.x | Required by CLEO for proof discharge |
| CLEO | 0.1.0 artifact dated 2026-05-19 | Provides `EnvelopeSession`, parsing, and verification |

## External Dependencies

You need:

1. a local CLEO checkout or artifact unpack
2. Java available on `PATH`
3. Z3 available on `PATH` as `z3`, or configured in KeYmaera X
4. KeYmaera X available to CLEO

## Get CLEO

Use the CLEO artifact associated with:

- DOI `10.1184/R1/32320254`
- Title: `Cleo: Command Line EnvelOpe Verification Tool`

After unpacking, the CLEO directory should contain at least:

- `pyproject.toml`
- `cleo/`
- `examples/`
- `tests/`

## Create the CLEO Virtual Environment

From the CLEO root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Configure Z3 for KeYmaera X

Recommended:

- install Z3 CLI 4.16.0
- make sure `z3` is available on `PATH`

If you prefer explicit KeYmaera X configuration, add or update `~/.keymaerax/keymaerax.conf` with:

```text
QE_TOOL = z3
Z3_PATH = <path-to-your-z3-binary>
```

Replace `<path-to-your-z3-binary>` with your own local Z3 path.

## Run the Canonical Phase 1 Verification

Activate the CLEO virtual environment first, then run from the repository root:

```bash
python mitigation_synthesis/water_attack.py
```

Expected output includes:

- the envelope parses correctly
- `PASS loop_inductive`
- `PASS loop_post`
- `PASS ode`
- `PASS arithmetic`

## Parser-Only Mode

If you only want a syntax and parsing smoke test:

```bash
python mitigation_synthesis/water_attack.py --parse-only
```

## Current Verification Status

The current Phase 1 artifact is fully configured for the canonical proof profile in `attack.envelope`.

This means:

- the loop invariant is supplied automatically by `water_attack.py`
- the ODE annotation is supplied automatically by `water_attack.py`
- CLEO verification succeeds end to end for this canonical case

## CLEO Smoke Tests

Once CLEO is installed, these checks are useful from the CLEO root:

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

- parser and envelope-format tests pass
- `examples/lotka.envelope` verifies successfully

## Repo-Specific Notes

- The repository does not bundle a standalone KeYmaera X installation.
- The verification path depends on an external CLEO installation.
- `water_attack.py` must run in an environment where `cleo` is importable.
- Docker is optional, not required.
