#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${DRICS_PYTHON:-${REPO_ROOT}/.venv/bin/python}"

if [ ! -x "${PYTHON}" ]; then
    PYTHON="$(command -v python3 || true)"
fi
[ -n "${PYTHON}" ] || {
    echo "ERROR: no project Python interpreter was found." >&2
    exit 1
}

export DRICS_LLM_MODEL="${DRICS_LLM_MODEL:-Qwen/Qwen3.5-9B}"
export DRICS_LLM_REVISION="${DRICS_LLM_REVISION:-c202236235762e1c871ad0ccb60c8ee5ba337b9a}"
export DRICS_LLM_BASE_URL="${DRICS_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRICS_MODEL_DIR="${DRICS_MODEL_DIR:-${REPO_ROOT}/../drics-llm/models}"
export DRICS_LLM_MODEL_PATH="${DRICS_LLM_MODEL_PATH:-${DRICS_MODEL_DIR}/Qwen--Qwen3.5-9B/${DRICS_LLM_REVISION}}"
export DRICS_LLM_MODEL_MANIFEST="${DRICS_LLM_MODEL_PATH}/DRICS_MODEL_MANIFEST.json"
export DRICS_LLM_TEMPERATURE="${DRICS_LLM_TEMPERATURE:-0}"
export DRICS_LLM_TOP_P="${DRICS_LLM_TOP_P:-1}"
export DRICS_LLM_MAX_OUTPUT_TOKENS="${DRICS_LLM_MAX_OUTPUT_TOKENS:-4096}"
export DRICS_LLM_SEED="${DRICS_LLM_SEED:-20260926}"
export DRICS_LLM_DISABLE_THINKING="${DRICS_LLM_DISABLE_THINKING:-true}"
export DRICS_LLM_SERVING_BACKEND="${DRICS_LLM_SERVING_BACKEND:-vllm-auto}"

cd "${REPO_ROOT}"
exec "${PYTHON}" -m recovery_experiment.llm_incident_evaluation smoke "$@"
