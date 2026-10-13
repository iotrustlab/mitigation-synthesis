#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

readonly OFFICIAL_MODEL_ID="Qwen/Qwen3.5-9B"
readonly OFFICIAL_REVISION="c202236235762e1c871ad0ccb60c8ee5ba337b9a"
readonly MODEL_SLUG="Qwen--Qwen3.5-9B"
readonly TENSOR_BYTES=19306310880

if [ "${DRICS_LLM_REVISION:-${OFFICIAL_REVISION}}" != "${OFFICIAL_REVISION}" ]; then
    echo "ERROR: this baseline launcher only accepts revision ${OFFICIAL_REVISION}." >&2
    exit 1
fi

export DRICS_MODEL_DIR="${DRICS_MODEL_DIR:-${REPO_ROOT}/../drics-llm/models}"
export HF_HOME="${HF_HOME:-${REPO_ROOT}/../drics-llm/cache}"
export HF_HUB_CACHE="${DRICS_HF_HUB_CACHE:-${HF_HOME}/hub}"

MODEL_PATH="${DRICS_LLM_MODEL_PATH:-${DRICS_MODEL_DIR}/${MODEL_SLUG}/${OFFICIAL_REVISION}}"
export DRICS_LLM_MODEL_PATH="${MODEL_PATH}"
export DRICS_LLM_MODEL_MANIFEST="${MODEL_PATH}/DRICS_MODEL_MANIFEST.json"
SERVED_MODEL="${DRICS_LLM_MODEL:-${OFFICIAL_MODEL_ID}}"
HOST="${DRICS_LLM_HOST:-127.0.0.1}"
PORT="${DRICS_LLM_PORT:-8000}"
TENSOR_PARALLEL_SIZE="${DRICS_LLM_TENSOR_PARALLEL_SIZE:-1}"
MAX_MODEL_LEN="${DRICS_LLM_MAX_MODEL_LEN:-16384}"
GPU_MEMORY_UTILIZATION="${DRICS_LLM_GPU_MEMORY_UTILIZATION:-0.90}"
MIN_GPU_MEMORY_MIB="${DRICS_LLM_MIN_GPU_MEMORY_MIB:-22000}"
ENGINE_SEED="${DRICS_LLM_ENGINE_SEED:-20260926}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

is_positive_integer() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

is_positive_integer "${PORT}" || fail "DRICS_LLM_PORT must be a positive integer."
[ "${PORT}" -le 65535 ] || fail "DRICS_LLM_PORT must be at most 65535."
is_positive_integer "${TENSOR_PARALLEL_SIZE}" \
    || fail "DRICS_LLM_TENSOR_PARALLEL_SIZE must be a positive integer."
is_positive_integer "${MAX_MODEL_LEN}" \
    || fail "DRICS_LLM_MAX_MODEL_LEN must be a positive integer."
is_positive_integer "${MIN_GPU_MEMORY_MIB}" \
    || fail "DRICS_LLM_MIN_GPU_MEMORY_MIB must be a positive integer."
[[ "${ENGINE_SEED}" =~ ^[0-9]+$ ]] || fail "DRICS_LLM_ENGINE_SEED must be a non-negative integer."
awk -v value="${GPU_MEMORY_UTILIZATION}" \
    'BEGIN {exit !(value > 0 && value <= 1)}' \
    || fail "DRICS_LLM_GPU_MEMORY_UTILIZATION must be greater than 0 and at most 1."

command -v realpath >/dev/null 2>&1 || fail "The realpath command is required."
resolved_repo_root="$(realpath -m "${REPO_ROOT}")"
resolved_model_path="$(realpath -m "${MODEL_PATH}")"
case "${resolved_model_path}/" in
    "${resolved_repo_root}/"*)
        fail "Model weights must remain outside the Git repository: ${resolved_model_path}"
        ;;
esac

if [ "${HOST}" != "127.0.0.1" ] && [ "${DRICS_LLM_ALLOW_REMOTE_BIND:-0}" != "1" ]; then
    fail "Refusing non-loopback host ${HOST}. Set DRICS_LLM_ALLOW_REMOTE_BIND=1 only if network exposure is intentional."
fi

if [ -z "${SLURM_JOB_ID:-}" ] && [ "${DRICS_ALLOW_UNALLOCATED_GPU:-0}" != "1" ]; then
    fail "No SLURM allocation detected. Start this server inside an allocated GPU job. For a non-SLURM GPU host, explicitly set DRICS_ALLOW_UNALLOCATED_GPU=1."
fi

command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi is unavailable; no usable NVIDIA GPU was detected."

mapfile -t all_gpu_rows < <(
    nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv,noheader,nounits 2>/dev/null
)
[ "${#all_gpu_rows[@]}" -gt 0 ] || fail "No NVIDIA GPU is visible in this job."

declare -a selected_gpu_rows=()
visible_devices="${CUDA_VISIBLE_DEVICES:-${NVIDIA_VISIBLE_DEVICES:-}}"
if [ -n "${visible_devices}" ] && [ "${visible_devices}" != "all" ]; then
    IFS=',' read -r -a visible_tokens <<< "${visible_devices}"
    for token in "${visible_tokens[@]}"; do
        token="${token//[[:space:]]/}"
        [ -n "${token}" ] || continue
        matched=""
        for row in "${all_gpu_rows[@]}"; do
            IFS=',' read -r gpu_index gpu_uuid gpu_name gpu_memory <<< "${row}"
            gpu_index="${gpu_index//[[:space:]]/}"
            gpu_uuid="${gpu_uuid//[[:space:]]/}"
            if [ "${token}" = "${gpu_index}" ] \
                || [ "${token}" = "${gpu_uuid}" ] \
                || [[ "${gpu_uuid}" == "${token}"* ]]; then
                matched="${row}"
                break
            fi
        done
        [ -n "${matched}" ] \
            || fail "CUDA_VISIBLE_DEVICES entry ${token} could not be matched to an allocated GPU. MIG instances require a full-GPU allocation for this BF16 baseline."
        selected_gpu_rows+=("${matched}")
    done
else
    selected_gpu_rows=("${all_gpu_rows[@]}")
fi

if [ "${#selected_gpu_rows[@]}" -lt "${TENSOR_PARALLEL_SIZE}" ]; then
    fail "Tensor parallel size ${TENSOR_PARALLEL_SIZE} exceeds the ${#selected_gpu_rows[@]} visible GPU(s)."
fi

declare -a gpu_descriptions=()
for ((gpu_number = 0; gpu_number < TENSOR_PARALLEL_SIZE; gpu_number++)); do
    row="${selected_gpu_rows[${gpu_number}]}"
    IFS=',' read -r gpu_index gpu_uuid gpu_name gpu_memory <<< "${row}"
    gpu_index="${gpu_index//[[:space:]]/}"
    gpu_name="${gpu_name#${gpu_name%%[![:space:]]*}}"
    gpu_name="${gpu_name%${gpu_name##*[![:space:]]}}"
    gpu_memory="${gpu_memory//[[:space:]]/}"
    [[ "${gpu_memory}" =~ ^[0-9]+$ ]] || fail "Could not parse GPU memory from: ${row}"
    if [[ "${gpu_name,,}" == *"gt 1030"* ]]; then
        fail "${gpu_name} is explicitly unsupported for Qwen3.5-9B BF16 inference."
    fi
    if [ "${gpu_memory}" -lt "${MIN_GPU_MEMORY_MIB}" ]; then
        fail "GPU ${gpu_index} (${gpu_name}) has ${gpu_memory} MiB; at least ${MIN_GPU_MEMORY_MIB} MiB per selected GPU is required."
    fi
    gpu_descriptions+=("GPU ${gpu_index}: ${gpu_name} (${gpu_memory} MiB)")
done

[ -d "${MODEL_PATH}" ] || fail "Pinned model snapshot not found at ${MODEL_PATH}. Run scripts/llm/download_qwen35_9b.sh first."
[ -r "${MODEL_PATH}/config.json" ] || fail "Model snapshot is incomplete: ${MODEL_PATH}/config.json is missing."

manifest_path="${DRICS_LLM_MODEL_MANIFEST}"
[ -r "${manifest_path}" ] || fail "Pinned snapshot manifest is missing: ${manifest_path}"
command -v python3 >/dev/null 2>&1 || fail "python3 is required to validate the model manifest."
python3 - "${MODEL_PATH}" "${manifest_path}" "${OFFICIAL_MODEL_ID}" "${OFFICIAL_REVISION}" "${TENSOR_BYTES}" <<'PY' \
    || fail "The local snapshot failed pinned-manifest identity or SHA-256 validation."
import hashlib
import json
from pathlib import Path
import sys

model_path_arg, manifest_arg, expected_model, expected_revision, expected_tensor_bytes = sys.argv[1:]
model_path = Path(model_path_arg).resolve()
manifest_path = Path(manifest_arg).resolve()
with manifest_path.open("r", encoding="utf-8") as handle:
    manifest = json.load(handle)
if manifest.get("model_id") != expected_model:
    raise SystemExit(1)
if manifest.get("requested_revision") != expected_revision:
    raise SystemExit(1)
if manifest.get("resolved_commit") != expected_revision:
    raise SystemExit(1)
if manifest.get("tensor_bytes") != int(expected_tensor_bytes):
    raise SystemExit(1)

recorded_files = manifest.get("files")
if not isinstance(recorded_files, list) or not recorded_files:
    raise SystemExit(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


recorded_names = set()
for item in recorded_files:
    if not isinstance(item, dict):
        raise SystemExit(1)
    name = item.get("path")
    if not isinstance(name, str):
        raise SystemExit(1)
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or name in recorded_names:
        raise SystemExit(1)
    recorded_names.add(name)
    path = model_path / relative
    if not path.is_file() or path.stat().st_size != item.get("size_bytes"):
        raise SystemExit(1)
    if sha256_file(path) != item.get("sha256"):
        raise SystemExit(1)

actual_names = {
    path.relative_to(model_path).as_posix()
    for path in model_path.rglob("*")
    if path.is_file()
    and path != manifest_path
    and not (
        path.relative_to(model_path).parts
        and path.relative_to(model_path).parts[0] == ".cache"
    )
}
if actual_names != recorded_names:
    raise SystemExit(1)
PY

if ! type module >/dev/null 2>&1 && [ -r /etc/profile.d/modules.sh ]; then
    # shellcheck source=/dev/null
    source /etc/profile.d/modules.sh
fi

if ! type vllm_serve >/dev/null 2>&1 && ! command -v vllm >/dev/null 2>&1; then
    if type module >/dev/null 2>&1; then
        module load vllm/current >/dev/null 2>&1 \
            || fail "Could not load the CHPC vllm/current module."
    fi
fi

if type vllm_serve >/dev/null 2>&1; then
    server_kind="CHPC vllm/current Apptainer launcher"
    server_is_function=1
    # The current CHPC module defines `vllm_serve` with an unquoted `$@` and
    # its container runscript evaluates arguments once more. Preserve the JSON
    # quotes through that site wrapper. A direct vLLM executable must receive
    # ordinary JSON instead.
    chat_template_kwargs='{\"enable_thinking\":false}'
elif command -v vllm >/dev/null 2>&1; then
    server_kind="vllm executable: $(command -v vllm)"
    server_is_function=0
    server_command=(vllm serve)
    chat_template_kwargs='{"enable_thinking":false}'
else
    fail "No compatible vLLM server was found. On CHPC, module load vllm/current."
fi

server_arguments=(
    "${MODEL_PATH}"
    --served-model-name "${SERVED_MODEL}"
    --host "${HOST}"
    --port "${PORT}"
    --dtype bfloat16
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}"
    --max-model-len "${MAX_MODEL_LEN}"
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
    --seed "${ENGINE_SEED}"
    --language-model-only
    --reasoning-parser qwen3
    --default-chat-template-kwargs "${chat_template_kwargs}"
    --generation-config vllm
    --no-enable-log-requests
    --log-error-stack
    --trust-remote-code
)

echo "Starting the local Dr.ICS Qwen server:"
echo "  hostname:        $(hostname)"
echo "  server:          ${server_kind}"
echo "  artifact:        ${OFFICIAL_MODEL_ID}@${OFFICIAL_REVISION}"
echo "  model path:      ${MODEL_PATH}"
echo "  manifest:        ${DRICS_LLM_MODEL_MANIFEST} (all recorded SHA-256 hashes verified)"
echo "  served model:    ${SERVED_MODEL}"
echo "  endpoint:        http://${HOST}:${PORT}/v1"
echo "  precision:       BF16 (no quantization)"
echo "  text-only mode:  enabled"
echo "  thinking:        disabled"
echo "  max model len:   ${MAX_MODEL_LEN}"
echo "  tensor parallel: ${TENSOR_PARALLEL_SIZE}"
echo "  engine seed:     ${ENGINE_SEED}"
for description in "${gpu_descriptions[@]}"; do
    echo "  ${description}"
done

if [ "${server_is_function}" -eq 1 ]; then
    # Bash's exec builtin cannot directly resolve a shell function. The CHPC
    # wrapper remains attached to the Apptainer payload for the lifetime of
    # the server.
    vllm_serve "${server_arguments[@]}"
else
    exec "${server_command[@]}" "${server_arguments[@]}"
fi
