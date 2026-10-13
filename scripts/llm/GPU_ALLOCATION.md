# Dr.ICS CHPC GPU Allocation

This directory provides a noninteractive, ownership-safe Slurm allocation
layer for Dr.ICS LLM experiments. It distinguishes a GPU reported as free from
a GPU verified to satisfy an experiment's memory policy.

## Quick usage

Run these commands from the repository root:

```bash
# Find or reuse one GPU with at least 32 GiB of VRAM.
scripts/llm/allocate_gpu.sh --min-vram 32 --wait

# Confirm that the recorded job still runs and recheck its GPU in the job.
scripts/llm/gpu_allocation_status.sh

# Run any command as a foreground Slurm step in the allocation.
scripts/llm/run_on_gpu.sh nvidia-smi

# Allocate/reuse a GPU, start Qwen, and run exactly one smoke case.
scripts/llm/run_qwen_baseline.sh --smoke-only

# Explicitly request the immutable 27-case baseline, after a fresh smoke pass.
scripts/llm/run_qwen_baseline.sh --baseline

# Release only the recorded managed allocation.
scripts/llm/release_gpu.sh
```

Calling `run_qwen_baseline.sh` with no mode flag is the same as
`--smoke-only`. Allocation by itself never starts Qwen and never runs an
experiment. The full baseline runs only with `--baseline`.

## Verified CHPC candidates

The following ordered partition/account pairs were verified for the current
user on 2026-09-26:

```text
soc-gpu-np:soc-gpu-np
notchpeak-gpu:notchpeak-gpu
```

This preserves the historical preference for `soc-gpu-np`. The allocator does
not submit to other partitions. Override the ordered list without editing the
scripts when another partition has been approved for the user:

```bash
export DRICS_GPU_PARTITIONS='partition-a:account-a,partition-b:account-b'
```

Slurm advertised typed GPU GRES strings on both verified partitions. During
the verification snapshot, `freegpus` listed `a6000` and `a100` on
`soc-gpu-np`, and `v100`, `2080ti`, `p40`, `3090`, and `a100` on
`notchpeak-gpu`. These are observations, not a promise of future availability
or memory size.

`freegpus -p PARTITION` is printed for diagnostics and parsed as an advisory
Stage-A count. In current CHPC behavior, that count can include GPUs on nodes
that are drained, reserved, or unavailable because the node lacks enough free
CPU or RAM for the requested job. Availability can also change before
submission. Therefore, a positive count does not mean a job will start
immediately and does not establish GPU VRAM.

## Allocation and validation

The allocator follows this finite sequence:

```text
ordered partition/account discovery
              |
              v
freegpus and Slurm pre-submit filtering (advisory)
              |
              v
one sbatch attempt at a time
              |
              v
bounded Slurm wait
              |
              v
nvidia-smi inside the RUNNING allocation (authoritative)
              |
        +-----+-----+
        |           |
        v           v
      accept      reject
        |           |
        v           v
 atomic state   cancel only that
 persistence    newly submitted job
```

After Slurm reports `RUNNING`, an overlapping `srun --jobid=...` step queries
the allocation with:

```text
nvidia-smi --query-gpu=index,uuid,name,memory.total \
  --format=csv,noheader,nounits
```

The job is accepted only when the number of CUDA-visible GPUs meets the
requested count and every selected GPU has at least
`MIN_VRAM_GIB * 1024` MiB. This in-allocation measurement is authoritative;
the allocator does not infer memory from a marketing name. An insufficient
new job is cancelled before the next candidate is tried. There are only as
many attempts as configured partition/account pairs, and never more than one
active new attempt at a time.

The default request is:

| Resource | Default | CLI option | Environment variable |
| --- | ---: | --- | --- |
| GPUs | 1 | `--gpus` | `DRICS_GPU_COUNT` |
| Minimum VRAM per GPU | 32 GiB | `--min-vram` | `DRICS_MIN_GPU_MEMORY_GIB` |
| CPUs | 8 | `--cpus` | `DRICS_GPU_CPUS` |
| CPU RAM | 32 GiB | `--mem` | `DRICS_GPU_MEMORY` |
| Walltime | 4 hours | `--walltime` | `DRICS_GPU_WALLTIME` |
| Allocation wait | 60 seconds | `--wait-seconds` | `DRICS_GPU_ALLOCATION_WAIT_SECONDS` |
| Poll interval | 4 seconds | `--poll-seconds` | `DRICS_GPU_ALLOCATION_POLL_SECONDS` |
| Reuse remaining-time floor | 15 minutes | — | `DRICS_GPU_MIN_REMAINING_SECONDS` |
| Job name | `drics-llm` | `--job-name` | `DRICS_GPU_JOB_NAME` |

CPU RAM and GPU VRAM are separate requirements. The 32-GiB VRAM value is an
initial Qwen 3.5-9B allocation policy, not a claim that the model requires
exactly 32 GiB. For example:

```bash
scripts/llm/allocate_gpu.sh \
  --min-vram 48 --gpus 1 --walltime 02:00:00 --cpus 12 --mem 64G
```

The default wait is finite. On timeout, an allocator-created pending job is
cancelled safely before another configured candidate is considered. With
`--no-wait`, one submitted job may remain pending and its job ID is reported;
a later allocator invocation recognizes that same managed job instead of
creating duplicates.

### Optional typed GPU request

Generic `--gres=gpu:COUNT` plus post-allocation validation is the default.
When a type has been verified in current `sinfo` output, target it with either:

```bash
scripts/llm/allocate_gpu.sh --gpu-type a100
export DRICS_GPU_GRES='gpu:a100:1'
```

The embedded count in `DRICS_GPU_GRES` must match `--gpus`. Do not invent or
normalize type strings: use the exact GRES type advertised by Slurm. Typed
requests are still validated with `nvidia-smi` after allocation.

### Dry run

```bash
scripts/llm/allocate_gpu.sh --dry-run
```

Dry-run mode performs read-only partition, GRES, and `freegpus` discovery and
prints every candidate `sbatch` command. It prints `DRICS_GPU_READY=0` with
reason `DRY_RUN`, returns success, and never calls `sbatch`.

## Safe reuse and duplicate prevention

Each submitted job has all of the following identities:

- the requested job name, `drics-llm` by default;
- the current Unix UID;
- a Slurm comment marker derived from the UID and this repository's resolved
  path;
- a per-job record below `.run/drics-gpu/jobs/`.

The allocator holds `.run/drics-gpu/allocator.lock`, so concurrent invocations
cannot both submit. It reuses only a running job whose owner, name, and exact
managed marker all match. Before reuse it checks that the job is still running,
has at least the requested CPUs, CPU RAM, and original time limit, has at least
the configured remaining-time floor, and repeats the in-allocation GPU-count
and VRAM validation. It refuses ambiguous managed duplicates and owned
same-name jobs without the repository marker. It does not reuse an
insufficient job and does not cancel that pre-existing job.

An existing `vscode-gpu`, interactive, or other user job is unrelated even if
it happens to be on a suitable node. It is neither reused nor cancelled.

## Runtime state and automation output

Runtime data is stored under the ignored directory `.run/drics-gpu/` by
default:

```text
.run/drics-gpu/
    allocator.lock
    current.env
    current.json
    jobs/JOB_ID.json
    logs/
    qwen-server.lock
    qwen-server.json       present only during a managed server step
```

Set `DRICS_GPU_STATE_DIR` to move this state directory. State is written
atomically with user-only file permissions and contains no credentials.
`current.json` contains the complete machine-readable record;
`current.env` provides shell-safe values including the job, node, partition,
account, GPU count/name/memory, walltime, creation time, and managed marker.

At the end of a successful allocation, stdout contains a stable block like:

```text
DRICS_GPU_READY=1
DRICS_GPU_JOB_ID=12345678
DRICS_GPU_NODE=notchXYZ
DRICS_GPU_PARTITION=soc-gpu-np
DRICS_GPU_NAME=NVIDIA_RTX_A6000
DRICS_GPU_MEMORY_MIB=49140
DRICS_GPU_STATE_FILE=/path/to/mitigation-synthesis/.run/drics-gpu/current.env
```

An unavailable allocation instead ends with `DRICS_GPU_READY=0` and a
`DRICS_GPU_REASON=...` value such as `NO_SUITABLE_GPU_AVAILABLE` or
`ALLOCATION_PENDING`. Exit status 0 means accepted (or a completed dry run), 2
means no allocation is ready, 3 means a safety/tooling error, and 130 means an
interrupted wait.

`gpu_allocation_status.sh` returns success only when the recorded, owned job is
still `RUNNING` and its GPU remains suitable. Its default check runs
`nvidia-smi` again inside the allocation. `--no-recheck` is available only for
a cheaper Slurm-state check.

`run_on_gpu.sh` performs the same ownership and suitability checks, preserves
the command's argument boundaries, streams its output, and returns its exit
status. It never releases the allocation:

```bash
scripts/llm/run_on_gpu.sh bash -lc 'hostname -s; nvidia-smi -L'
```

## Qwen server and evaluation lifecycle

The high-level interface keeps the server and client in one foreground Slurm
step on the allocated node:

```text
run_qwen_baseline.sh
    -> allocate or safely reuse
    -> run_on_gpu.sh (one foreground srun step)
         -> start Qwen/vLLM in its own process group
         -> wait for http://127.0.0.1:PORT/v1/models
         -> run exactly one smoke case
         -> optionally run the 27-case baseline with --baseline
         -> stop the server process group on every exit path
```

The endpoint is bound to loopback and both server and evaluator use
`localhost`, avoiding a public compute-node listener and SSH-forwarding
dependency. The readiness timeout defaults to 900 seconds and can be changed
with `--readiness-timeout` or `DRICS_QWEN_READINESS_TIMEOUT_SECONDS`; `--port`
or `DRICS_LLM_PORT` selects the loopback port.

The server is always stopped when the experiment step exits, whether the run
succeeds, fails, or is interrupted. The GPU allocation remains available for
later commands by default. Pass `--release-gpu` to release it after the
experiment:

```bash
scripts/llm/run_qwen_baseline.sh --smoke-only --release-gpu
```

During an active managed run, `stop_qwen_server.sh` can signal only the exact
recorded numeric Slurm step. It does not cancel the allocation. Normal wrapper
cleanup removes the transient server record automatically.

Experiment output is preserved under
`recovery_experiment/results/llm/orchestrated/RUN_TOKEN/`. The smoke output is
kept there even when `--baseline` proceeds to the canonical immutable
`QWEN_BASELINE_V1`. An existing canonical baseline is never overwritten.

### Observed Qwen compatibility result

The 2026-09-26 live test allocated job `15842018` in `soc-gpu-np` on
`notch501`. The allocated NVIDIA RTX A6000 reported 46,068 MiB, status/reuse
and `run_on_gpu.sh nvidia-smi` succeeded, and vLLM 0.27.0 loaded the pinned
BF16 model and reached READY. The single smoke request was rejected before
generation because xgrammar and its Guidance fallback do not implement the
unchanged response schema's `uniqueItems` keyword. The diagnostic result is
preserved below `recovery_experiment/results/llm/orchestrated/`; no 27-case
baseline ran. The server and managed allocation were then stopped/released,
while the unrelated `vscode-gpu` job remained running.

## Cleanup guarantees

Release the current allocation, or name one explicit recorded job:

```bash
scripts/llm/release_gpu.sh
scripts/llm/release_gpu.sh --job-id 12345678
```

Cancellation requires a valid per-job ledger, matching current UID, matching
repository-specific marker in both the ledger and Slurm, and the exact job ID.
The script never uses broad cancellation by user or job-name pattern. Stale
state for an already finished recorded job is removed without touching any
other job. Releasing an allocation naturally terminates all of its Slurm
steps.

## Troubleshooting

- `NO_SUITABLE_GPU_AVAILABLE` means no configured candidate produced a GPU
  that passed the policy within the finite attempt window. Do not lower the
  threshold merely to force a test; retry later or request an approved typed
  GPU.
- `ALLOCATION_PENDING` with `--no-wait` means the single managed attempt was
  left queued intentionally. Re-run the allocator or status command later.
- `ALLOCATOR_BUSY` means another allocator invocation holds the repository
  lock. Wait for it to finish rather than submitting manually.
- `EXISTING_ALLOCATION_INSUFFICIENT` means a matching managed job exists but
  does not meet the current request. It is left untouched for deliberate
  cleanup with `release_gpu.sh --job-id JOB_ID`.
- A positive `freegpus` count alongside a pending job is not contradictory;
  drained, reserved, CPU/RAM-constrained, or concurrently claimed nodes can
  make the advisory count unusable for this request.
- The login/development host's GeForce GT 1030 has only 2 GiB of VRAM and is
  unsuitable. Suitability is established only inside a Slurm allocation.
