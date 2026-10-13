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

SMOKE_DIR="${DRICS_QWEN_SMOKE_DIR:-${REPO_ROOT}/recovery_experiment/results/llm/QWEN_SMOKE_V1}"
"${PYTHON}" - \
    "${SMOKE_DIR}/manifest.json" \
    "${SMOKE_DIR}/completion.json" \
    "${DRICS_LLM_MODEL}" \
    "${DRICS_LLM_REVISION}" <<'PY'
import json
from pathlib import Path
import sys

manifest_path, completion_path, expected_model, expected_revision = sys.argv[1:]
try:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    completion = json.loads(Path(completion_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(
        "A preserved successful smoke result is required before QWEN_BASELINE_V1. "
        f"Set DRICS_QWEN_SMOKE_DIR when it is stored elsewhere: {exc}"
    ) from exc
if manifest.get("model", {}).get("id") != expected_model:
    raise SystemExit("Smoke result model ID does not match the requested baseline model.")
if manifest.get("model", {}).get("revision") != expected_revision:
    raise SystemExit("Smoke result revision does not match the requested baseline revision.")
structured = manifest.get("structured_output", {})
if structured.get("status") != "COMPATIBLE_WITH_CLIENT_VALIDATION":
    raise SystemExit("Smoke result lacks a compatible reviewed serving-schema report.")
if structured.get("canonical_schema_hash") != "7b5237458e64d0aa6b26dbf954a2c4829aae499ba72aeaf33952ec2869fd0e5a":
    raise SystemExit("Smoke result canonical CandidateRecoveryContext hash is unexpected.")
if structured.get("serving_schema_hash") != "3680129007e01223a2b6f2d6eba73d834316434ea04356393c4924535d5bd0e1":
    raise SystemExit("Smoke result serving-schema hash is unexpected.")
removed = structured.get("removed_generation_constraints", [])
if len(removed) != 64 or {item.get("keyword") for item in removed} != {"uniqueItems"}:
    raise SystemExit("Smoke result does not record the 64 reviewed uniqueItems removals.")
if completion.get("status") != "PASS" or not all(
    completion.get("smoke_checks", {}).values()
):
    raise SystemExit("The preserved Qwen smoke result did not pass every required check.")
PY

cd "${REPO_ROOT}"
exec "${PYTHON}" -m recovery_experiment.llm_incident_evaluation baseline "$@"
