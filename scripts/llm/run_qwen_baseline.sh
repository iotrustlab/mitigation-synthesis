#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${DRICS_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
MODE="smoke"
MODE_WAS_SET=0
RELEASE_GPU=0
INSIDE_ALLOCATION=0
READINESS_TIMEOUT="${DRICS_QWEN_READINESS_TIMEOUT_SECONDS:-900}"
PORT="${DRICS_LLM_PORT:-8000}"

usage() {
    cat <<'EOF'
Usage: scripts/llm/run_qwen_baseline.sh [--smoke-only | --baseline]
       [--release-gpu] [--readiness-timeout SECONDS] [--port PORT]

The default is one smoke case.  The 27-case QWEN_BASELINE_V1 runs only with
--baseline.  The server is always stopped; the allocation is retained unless
--release-gpu is explicit.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --smoke-only)
            [ "${MODE_WAS_SET}" -eq 0 ] || { echo "ERROR: choose only one of --smoke-only and --baseline." >&2; exit 2; }
            MODE="smoke"
            MODE_WAS_SET=1
            ;;
        --baseline)
            [ "${MODE_WAS_SET}" -eq 0 ] || { echo "ERROR: choose only one of --smoke-only and --baseline." >&2; exit 2; }
            MODE="baseline"
            MODE_WAS_SET=1
            ;;
        --release-gpu) RELEASE_GPU=1 ;;
        --readiness-timeout)
            shift
            [ "$#" -gt 0 ] || { echo "ERROR: --readiness-timeout needs a value." >&2; exit 2; }
            READINESS_TIMEOUT="$1"
            ;;
        --port)
            shift
            [ "$#" -gt 0 ] || { echo "ERROR: --port needs a value." >&2; exit 2; }
            PORT="$1"
            ;;
        --inside-allocation) INSIDE_ALLOCATION=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

[[ "${READINESS_TIMEOUT}" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: readiness timeout must be a positive integer." >&2
    exit 2
}
[[ "${PORT}" =~ ^[1-9][0-9]*$ ]] && [ "${PORT}" -le 65535 ] || {
    echo "ERROR: port must be an integer from 1 through 65535." >&2
    exit 2
}
if [ ! -x "${PYTHON}" ]; then
    PYTHON="$(command -v python3 || true)"
fi
[ -n "${PYTHON}" ] || { echo "ERROR: no Python interpreter is available." >&2; exit 1; }
"${PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "ERROR: the Dr.ICS Qwen evaluator requires Python 3.10+; bootstrap the project .venv." >&2
    exit 1
}
export DRICS_LLM_SERVING_BACKEND="${DRICS_LLM_SERVING_BACKEND:-vllm-auto}"
case "${DRICS_LLM_SERVING_BACKEND}" in
    vllm|vllm-auto) ;;
    *)
        echo "ERROR: the pinned Qwen runner requires the reviewed vllm-auto serving-schema profile." >&2
        exit 2
        ;;
esac

echo "Running local canonical-to-serving schema compatibility preflight."
(
    cd "${REPO_ROOT}"
    "${PYTHON}" -m recovery_experiment.llm_incident_evaluation \
        preflight --serving-backend "${DRICS_LLM_SERVING_BACKEND}"
)

BASELINE_DIR="${REPO_ROOT}/recovery_experiment/results/llm/QWEN_BASELINE_V1"
if [ "${MODE}" = "baseline" ] && [ -e "${BASELINE_DIR}" ]; then
    echo "ERROR: refusing to overwrite canonical baseline output: ${BASELINE_DIR}" >&2
    exit 1
fi

if [ "${INSIDE_ALLOCATION}" -eq 0 ]; then
    "${SCRIPT_DIR}/allocate_gpu.sh" \
        --min-vram "${DRICS_MIN_GPU_MEMORY_GIB:-32}" \
        --gpus "${DRICS_GPU_COUNT:-1}" \
        --wait

    inner_arguments=(--inside-allocation --readiness-timeout "${READINESS_TIMEOUT}" --port "${PORT}")
    if [ "${MODE}" = "baseline" ]; then
        inner_arguments+=(--baseline)
    else
        inner_arguments+=(--smoke-only)
    fi

    set +e
    "${SCRIPT_DIR}/run_on_gpu.sh" "${SCRIPT_DIR}/run_qwen_baseline.sh" "${inner_arguments[@]}"
    experiment_status=$?
    set -e

    release_status=0
    if [ "${RELEASE_GPU}" -eq 1 ]; then
        set +e
        "${SCRIPT_DIR}/release_gpu.sh"
        release_status=$?
        set -e
    fi
    if [ "${experiment_status}" -ne 0 ]; then
        exit "${experiment_status}"
    fi
    exit "${release_status}"
fi

[ -n "${SLURM_JOB_ID:-}" ] || {
    echo "ERROR: internal Qwen runner is not inside Slurm." >&2
    exit 1
}
[[ "${SLURM_STEP_ID:-}" =~ ^[0-9]+$ ]] || {
    echo "ERROR: Qwen runner requires a numeric Slurm step ID; got ${SLURM_STEP_ID:-unset}." >&2
    exit 1
}

RUNTIME_DIR="${DRICS_GPU_STATE_DIR:-${REPO_ROOT}/.run/drics-gpu}"
mkdir -p "${RUNTIME_DIR}/logs"
exec 9>"${RUNTIME_DIR}/qwen-server.lock"
flock -n 9 || {
    echo "ERROR: another managed Qwen server lifecycle is active." >&2
    exit 3
}

readonly MODEL_ID="Qwen/Qwen3.5-9B"
readonly MODEL_REVISION="c202236235762e1c871ad0ccb60c8ee5ba337b9a"
export DRICS_LLM_MODEL="${MODEL_ID}"
export DRICS_LLM_REVISION="${MODEL_REVISION}"
export DRICS_LLM_HOST="127.0.0.1"
export DRICS_LLM_PORT="${PORT}"
export DRICS_LLM_BASE_URL="http://127.0.0.1:${PORT}/v1"
export DRICS_LLM_TEMPERATURE="0"
export DRICS_LLM_TOP_P="1"
export DRICS_LLM_MAX_OUTPUT_TOKENS="4096"
export DRICS_LLM_SEED="20260926"
export DRICS_LLM_DISABLE_THINKING="true"
export DRICS_LLM_MAX_MODEL_LEN="16384"
export DRICS_LLM_TENSOR_PARALLEL_SIZE="1"
export DRICS_LLM_DTYPE="bfloat16"
export DRICS_LLM_QUANTIZATION="none"
minimum_vram_gib="${DRICS_MIN_GPU_MEMORY_GIB:-32}"
[[ "${minimum_vram_gib}" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: DRICS_MIN_GPU_MEMORY_GIB must be a positive integer." >&2
    exit 2
}
export DRICS_LLM_MIN_GPU_MEMORY_MIB="$(( minimum_vram_gib * 1024 ))"
export DRICS_MODEL_DIR="${DRICS_MODEL_DIR:-${REPO_ROOT}/../drics-llm/models}"
export DRICS_LLM_MODEL_PATH="${DRICS_LLM_MODEL_PATH:-${DRICS_MODEL_DIR}/Qwen--Qwen3.5-9B/${MODEL_REVISION}}"
export DRICS_LLM_MODEL_MANIFEST="${DRICS_LLM_MODEL_PATH}/DRICS_MODEL_MANIFEST.json"

node_name="$(hostname -s)"
run_token="$(date -u +%Y%m%dT%H%M%SZ)-job${SLURM_JOB_ID}-step${SLURM_STEP_ID}-$$"
server_log="${RUNTIME_DIR}/logs/qwen-server-${run_token}.log"
server_state="${RUNTIME_DIR}/qwen-server.json"
output_parent="${REPO_ROOT}/recovery_experiment/results/llm/orchestrated/${run_token}"
smoke_dir="${output_parent}/smoke"
mkdir -p "${output_parent}"

mapfile -t allocation_gpu_metadata < <(
    "${PYTHON}" - "${RUNTIME_DIR}/current.json" "${SLURM_JOB_ID}" <<'PY'
import json
from pathlib import Path
import sys

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if int(state.get("job_id", -1)) != int(sys.argv[2]):
    raise SystemExit("current allocation state does not match this Slurm job")
print(state["gpu_name"])
print(state["gpu_count"])
PY
)
[ "${#allocation_gpu_metadata[@]}" -eq 2 ] || {
    echo "ERROR: current allocation GPU metadata is unavailable." >&2
    exit 1
}
export DRICS_LLM_GPU_MODEL="${allocation_gpu_metadata[0]}"
export DRICS_LLM_GPU_COUNT="${allocation_gpu_metadata[1]}"

server_pid=""
cleanup_server() {
    original_status=$?
    trap - EXIT INT TERM HUP
    if [ -n "${server_pid}" ] && kill -0 "${server_pid}" 2>/dev/null; then
        kill -TERM -- "-${server_pid}" 2>/dev/null || true
        for _ in $(seq 1 30); do
            kill -0 "${server_pid}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${server_pid}" 2>/dev/null; then
            kill -KILL -- "-${server_pid}" 2>/dev/null || true
        fi
        wait "${server_pid}" 2>/dev/null || true
    fi
    "${PYTHON}" - "${server_state}" "${run_token}" <<'PY' || true
import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
token = sys.argv[2]
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(0)
if state.get("token") == token:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
PY
    exit "${original_status}"
}
trap cleanup_server EXIT
trap 'exit 130' INT TERM HUP

setsid "${SCRIPT_DIR}/start_qwen35_9b_server.sh" >"${server_log}" 2>&1 &
server_pid=$!
server_pgid="$(ps -o pgid= -p "${server_pid}" | tr -d '[:space:]')"
process_start_ticks="$(awk '{print $22}' "/proc/${server_pid}/stat" 2>/dev/null || true)"
[ "${server_pgid}" = "${server_pid}" ] || {
    echo "ERROR: server did not start in its own process group." >&2
    exit 1
}

"${PYTHON}" - \
    "${server_state}" "${run_token}" "${SLURM_JOB_ID}" "${SLURM_STEP_ID}" \
    "${node_name}" "${server_pid}" "${server_pgid}" "${process_start_ticks}" \
    "${PORT}" "${server_log}" "${DRICS_LLM_MODEL_PATH}" "${REPO_ROOT}" <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

(path_arg, token, job_id, step_id, node, pid, pgid, start_ticks,
 port, log_path, model_path, repo_root) = sys.argv[1:]
path = Path(path_arg)
repo = Path(repo_root).resolve()
marker_repo = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:12]
state = {
    "schema_version": 1,
    "token": token,
    "status": "STARTING",
    "owner": os.environ.get("USER", ""),
    "owner_uid": os.getuid(),
    "managed_marker": "drics-gpu-v1:{}:{}".format(os.getuid(), marker_repo),
    "job_id": int(job_id),
    "step_id": step_id,
    "node": node,
    "pid": int(pid),
    "pgid": int(pgid),
    "process_start_ticks": start_ticks,
    "host": "127.0.0.1",
    "port": int(port),
    "base_url": "http://127.0.0.1:{}/v1".format(port),
    "model": "Qwen/Qwen3.5-9B",
    "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
    "model_path": model_path,
    "log_path": log_path,
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
path.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(prefix=".qwen-server-", suffix=".tmp", dir=str(path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
PY

echo "Waiting up to ${READINESS_TIMEOUT}s for ${MODEL_ID} at ${DRICS_LLM_BASE_URL}"
ready=0
deadline=$((SECONDS + READINESS_TIMEOUT))
while [ "${SECONDS}" -lt "${deadline}" ]; do
    if ! kill -0 "${server_pid}" 2>/dev/null; then
        echo "ERROR: Qwen server exited before readiness. Log: ${server_log}" >&2
        tail -n 80 "${server_log}" >&2 || true
        exit 1
    fi
    if payload="$(curl --fail --silent --show-error --max-time 10 "${DRICS_LLM_BASE_URL}/models" 2>/dev/null)" \
        && printf '%s' "${payload}" | "${PYTHON}" -c \
            'import json,sys; p=json.load(sys.stdin); ids=[x.get("id") for x in p.get("data",[])]; raise SystemExit(0 if "Qwen/Qwen3.5-9B" in ids else 1)' 2>/dev/null; then
        ready=1
        break
    fi
    sleep 5
done
[ "${ready}" -eq 1 ] || {
    echo "ERROR: Qwen readiness timed out. Log: ${server_log}" >&2
    tail -n 80 "${server_log}" >&2 || true
    exit 1
}

"${PYTHON}" - "${server_state}" "${run_token}" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
token = sys.argv[2]
state = json.loads(path.read_text(encoding="utf-8"))
if state.get("token") != token:
    raise SystemExit("server state token changed unexpectedly")
state["status"] = "READY"
fd, temporary = tempfile.mkstemp(prefix=".qwen-server-", suffix=".tmp", dir=str(path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
PY

echo "Qwen server READY; running exactly one smoke case."
"${SCRIPT_DIR}/smoke_qwen35_9b.sh" --output-dir "${smoke_dir}"

if [ "${MODE}" = "baseline" ]; then
    export DRICS_QWEN_SMOKE_DIR="${smoke_dir}"
    echo "Smoke passed; starting explicit 27-case QWEN_BASELINE_V1."
    "${SCRIPT_DIR}/baseline_qwen35_9b.sh"
else
    echo "Smoke passed; full baseline was not requested."
fi

echo "Qwen output: ${output_parent}"
echo "Qwen server log: ${server_log}"
