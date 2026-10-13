# Dr.ICS Reproducible Environment

## Tested host

- OS: Rocky Linux 8.10, x86_64
- CPU: 2 x Intel Xeon Gold 6130 (32 physical cores, 64 hardware threads)
- RAM: 94 GiB
- GPU: NVIDIA GeForce GT 1030, 2 GiB VRAM
- NVIDIA driver / reported CUDA compatibility: 580.173.02 / CUDA 13.0
- Repository filesystem free space at bootstrap: approximately 10 TiB
- Python: 3.12.12 from the CHPC module system
- Java: OpenJDK 17.0.1 from the CHPC module system

The stock `/usr/bin/python3` on this host is Python 3.6.8 and cannot run this
project. Do not use it. The repository README says Python 3.10+ for the
Dr.ICS code, while the actual CLEO 0.1.0 package metadata
requires Python 3.11+ and its README recommends Python 3.12+. This setup uses
Python 3.12.12 for both environments.

## Environment layout

All machine-local dependencies and runtime state are ignored by Git:

```text
.venv/                         deterministic Dr.ICS Python environment
.external/downloads/          checksum-verified CLEO download cache
.external/cleo/source/        reconstructed CLEO 0.1.0 artifact
.external/cleo/.venv/         CLEO/Z3 Python environment
.run/drics-gpu/               Slurm GPU allocation/server state and logs
```

The deterministic/CLEO bootstrap requires no API key, credential, or model
download. Local Qwen experiments use the separate public artifact and storage
workflow documented in
[`recovery_experiment/LLM_INCIDENT_INTERPRETER.md`](recovery_experiment/LLM_INCIDENT_INTERPRETER.md).

## Bootstrap

From the repository root:

```bash
scripts/bootstrap_drics.sh
source scripts/drics_env.sh
scripts/doctor_drics.sh
```

The bootstrap is safe to rerun. It loads an appropriate Python/OpenJDK module
on CHPC, creates both virtual environments, downloads the exact CLEO artifact,
verifies published checksums, reconstructs the package, installs the pinned
Python dependencies, and installs CLEO editable from that local artifact.
`requirements-drics.lock` pins the project-side JSON Schema validator and its
dependencies; `requirements-cleo.lock` independently pins the proof runtime.

`scripts/drics_env.sh` exports:

```text
DRICS_ROOT
DRICS_PYTHON
CLEO_PYTHON
CLEO_KEYMAERAX_TIMEOUT_SECONDS (default: 300)
```

It also places the CLEO environment on `PATH`, which exposes the matching Z3
binary. Override the proof timeout before sourcing only when needed, for example
`export CLEO_KEYMAERAX_TIMEOUT_SECONDS=600`.

## CLEO and formal backends

- CLEO: 0.1.0, artifact dated 2026-05-19
- Source: `Cleo: Command Line EnvelOpe Verification Tool`
- DOI: <https://doi.org/10.1184/R1/32320254>
- KiltHub/Figshare file: `cleo.zip`, file ID 64722681
- Published MD5: `85ffdf7f92c8b2b870764f3dcf11e6a5`
- Python Z3 / Z3 CLI: 4.16.0
- KeYmaera X: version 5-series JAR bundled inside the CLEO artifact
- Java tested: OpenJDK 17.0.1

The artifact source comments specify a five-minute KeYmaera X timeout but the
released code used 30 seconds. On this host, the legacy Phase-1 ODE proof needs
about 117 seconds and fails at 30 seconds. The bootstrap applies the tracked,
infrastructure-only patch
`scripts/patches/cleo-keymaerax-timeout.patch`, making the timeout configurable
and defaulting it to 300 seconds. The patch changes no envelope, invariant,
tactic, theorem assumption, certificate, or reviewed proof record.

`requirements-cleo.lock` pins the resolved CLEO runtime dependencies. CLEO
itself is installed from the checksum-verified DOI artifact, not from the
unrelated packages with the same name on PyPI or npm.

## Diagnostics

```bash
source scripts/drics_env.sh
scripts/doctor_drics.sh
```

The doctor is read-only. It validates files, interpreters, imports, Z3, Java,
the bundled JAR, and test discovery. It deliberately does not run the expensive
formal regression; `READY` means the infrastructure checks pass, not that a
subsequent theorem run is guaranteed to pass.

## Deterministic tests

```bash
source scripts/drics_env.sh
"$DRICS_PYTHON" -m unittest discover -s recovery_experiment/tests -q
```

Normal-suite result after adding the LLM and GPU automation tests:

```text
Ran 164 tests in 2.699s
OK (skipped=12)
```

## Deterministic incident evaluation

The current `incident_evidence_evaluation` module provides an evaluation API but
does not contain a `__main__` CLI, so `python -m ...` exits silently. Run the
actual current API as follows:

```bash
"$DRICS_PYTHON" - <<'PY'
import json
from recovery_experiment.incident_evidence_evaluation import evaluate_deterministic_pipeline
print(json.dumps(evaluate_deterministic_pipeline().as_dict(), indent=2, sort_keys=True))
PY
```

The tested baseline is 27/27 grounding-status matches: 23 correct acceptances,
4 correct rejections, 0 false acceptances, and 0 false rejections. Template,
formal-model, certificate, service, and recovery-decision accuracy are each
23/23, with 27 `NO_DIVERGENCE` cases.

## CHPC GPU allocation and Qwen execution

The login/development host's 2-GiB GeForce GT 1030 is unsuitable for the local
Qwen baseline. Use the managed Slurm workflow from the repository root:

```bash
scripts/llm/allocate_gpu.sh --min-vram 32 --wait
scripts/llm/gpu_allocation_status.sh
scripts/llm/run_on_gpu.sh nvidia-smi

# The default high-level run is one smoke case, not the 27-case baseline.
scripts/llm/run_qwen_baseline.sh --smoke-only

# Release the retained allocation when it is no longer needed.
scripts/llm/release_gpu.sh
```

The verified candidate order is
`soc-gpu-np:soc-gpu-np,notchpeak-gpu:notchpeak-gpu`. `freegpus` and Slurm GRES
metadata provide only a pre-submit advisory filter; the former can include
drained, reserved, or CPU/RAM-blocked nodes. A job becomes usable only after
`nvidia-smi` inside the running allocation confirms the configured count and
at least 32 GiB per GPU by default.

The other defaults are one GPU, eight CPUs, 32 GiB of CPU RAM, a four-hour
walltime, a 60-second finite allocation wait, and one active submission attempt
at a time. They are configurable through the allocator CLI or
`DRICS_GPU_COUNT`, `DRICS_MIN_GPU_MEMORY_GIB`, `DRICS_GPU_CPUS`,
`DRICS_GPU_MEMORY`, `DRICS_GPU_WALLTIME`, and
`DRICS_GPU_ALLOCATION_WAIT_SECONDS`. Use `DRICS_GPU_PARTITIONS` for an approved
ordered `PARTITION:ACCOUNT` override and `DRICS_GPU_GRES` only with an exact
type currently advertised by Slurm.

Accepted state is written atomically to `.run/drics-gpu/current.json` and
`current.env`; per-job records, a repository-specific Slurm marker, and an
allocator lock prevent duplicate or unrelated-job cleanup. `release_gpu.sh`
can cancel only an exactly recorded, currently owned managed job.

`run_qwen_baseline.sh` starts vLLM and the evaluator in one foreground `srun`
step and communicates only through `127.0.0.1`. It always stops the server on
exit and retains the GPU allocation unless `--release-gpu` is explicit. The
27-case immutable run requires the explicit `--baseline` flag and is preceded
by a successful fresh smoke case. See
[`scripts/llm/GPU_ALLOCATION.md`](scripts/llm/GPU_ALLOCATION.md) for state,
output, dry-run, lifecycle, and cleanup details.

Live validation on 2026-09-26 obtained job `15842018` on `notch501` in
`soc-gpu-np`; its RTX A6000 reported 46,068 MiB. Allocation status and
`run_on_gpu.sh nvidia-smi` passed, safe reuse was confirmed, and the job was
released afterward without touching the existing `vscode-gpu` job. The pinned
Qwen server reached READY with vLLM 0.27.0. Its smoke request then failed before
generation because xgrammar and its Guidance fallback do not support the
canonical schema's `uniqueItems` keyword. The schema was not weakened and the
27-case baseline was not run; see `LLM_INCIDENT_INTERPRETER.md` for the
preserved compatibility result.

A subsequent reviewed serving-schema adapter removed only those 64
generation-time `uniqueItems` occurrences while retaining the unchanged local
canonical validator. Live job `15844987` on `notch368` used another RTX A6000
with 46,068 MiB; vLLM 0.27.0 generated valid JSON and canonical validation
passed. The response then failed closed at provenance validation because it
invented `incident_metadata:plant_identity` and misbound source strings.
Grounding/formal work did not run, the job was released, and no 27-case
baseline was started.

## CLEO-enabled regression

```bash
source scripts/drics_env.sh
RUN_CLEO_REGRESSION=1 "$CLEO_PYTHON" \
  -m unittest discover -s recovery_experiment/tests -q
```

These tests are intentionally much slower because they launch KeYmaera X for
the gated proof obligations.

Baseline on this host with the configurable 300-second backend timeout:

```text
Ran 130 tests in 640.465s
OK
wall time: 641.13s
```

## Representative direct proof

Always use a new output directory rather than a reviewed proof-record directory:

```bash
source scripts/drics_env.sh
proof_dir="$(mktemp -d /tmp/drics-delayed-proof.XXXXXX)"
"$CLEO_PYTHON" -m recovery_experiment.verify_delayed_isolation_recovery \
  --output-dir "$proof_dir"
```

On this host, the delayed-isolation verifier returned `VERIFIED` in 74.01
seconds. Four ODE obligations (`be`, `bn`, `bu`, and `ch`) and one arithmetic
obligation passed; all five reported recovery milestones passed.

## Troubleshooting

- **Python syntax/import errors:** the stock Python is too old. Source
  `scripts/drics_env.sh` and use `$DRICS_PYTHON` or `$CLEO_PYTHON` explicitly.
- **`cleo` resolves to a different project:** use `$CLEO_PYTHON`; this repository
  requires the formal-verification artifact identified by the DOI above.
- **`z3` missing:** source `scripts/drics_env.sh`; Z3 is installed in the CLEO
  environment and that environment is prepended to `PATH`.
- **KeYmaera X timeout:** preserve the formal artifacts and increase only
  `CLEO_KEYMAERAX_TIMEOUT_SECONDS` if the host is slower.
- **Java missing/too old:** on CHPC, `module load openjdk/17.0.1`. A different
  machine should provide a supported modern OpenJDK in `PATH`.
- **Downloaded artifact is corrupt:** rerun the bootstrap. It rejects a file
  whose MD5 differs from the published artifact checksum.
- **Old paths:** never reuse historical absolute paths such as
  `/home/jainta-paul/Desktop/CPS-Verification`. All scripts resolve the current
  repository root relative to themselves.
