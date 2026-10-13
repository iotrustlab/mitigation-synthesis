#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

readonly MODEL_ID="Qwen/Qwen3.5-9B"
readonly MODEL_REVISION="c202236235762e1c871ad0ccb60c8ee5ba337b9a"
readonly MODEL_SLUG="Qwen--Qwen3.5-9B"
readonly TENSOR_BYTES=19306310880
readonly DOWNLOAD_HEADROOM_BYTES=8589934592
readonly HUGGINGFACE_HUB_VERSION="2.0.0"

if [ "${DRICS_LLM_REVISION:-${MODEL_REVISION}}" != "${MODEL_REVISION}" ]; then
    echo "ERROR: this downloader only accepts the pinned revision ${MODEL_REVISION}." >&2
    exit 1
fi

# Keep model data and the Hugging Face cache out of the Git repository and out
# of a user's small home quota by default. Both locations are configurable.
export DRICS_MODEL_DIR="${DRICS_MODEL_DIR:-${REPO_ROOT}/../drics-llm/models}"
export HF_HOME="${HF_HOME:-${REPO_ROOT}/../drics-llm/cache}"
export HF_HUB_CACHE="${DRICS_HF_HUB_CACHE:-${HF_HOME}/hub}"

DOWNLOAD_VENV="${DRICS_LLM_DOWNLOAD_VENV:-${REPO_ROOT}/.external/llm/download-venv}"
MODEL_SNAPSHOT_DIR="${DRICS_LLM_MODEL_PATH:-${DRICS_MODEL_DIR}/${MODEL_SLUG}/${MODEL_REVISION}}"
MANIFEST_PATH="${MODEL_SNAPSHOT_DIR}/DRICS_MODEL_MANIFEST.json"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

load_python_if_needed() {
    if command -v python3 >/dev/null 2>&1 \
        && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        return
    fi

    if ! type module >/dev/null 2>&1 && [ -r /etc/profile.d/modules.sh ]; then
        # shellcheck source=/dev/null
        source /etc/profile.d/modules.sh
    fi
    if type module >/dev/null 2>&1; then
        module load python/3.12.12 >/dev/null 2>&1 \
            || module load python/3.12.4 >/dev/null 2>&1 \
            || true
    fi

    command -v python3 >/dev/null 2>&1 \
        || fail "Python 3.10+ is required (on CHPC, load python/3.12.12)."
    python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1 \
        || fail "Python 3.10+ is required."
}

available_bytes() {
    df -PB1 "$1" | awk 'NR == 2 {print $4}'
}

directory_bytes() {
    if [ -d "$1" ]; then
        du -sb "$1" | awk '{print $1}'
    else
        echo 0
    fi
}

load_python_if_needed
command -v realpath >/dev/null 2>&1 || fail "The realpath command is required."

resolved_repo_root="$(realpath -m "${REPO_ROOT}")"
resolved_snapshot_path="$(realpath -m "${MODEL_SNAPSHOT_DIR}")"
case "${resolved_snapshot_path}/" in
    "${resolved_repo_root}/"*)
        fail "Model weights must remain outside the Git repository: ${resolved_snapshot_path}"
        ;;
esac

mkdir -p "${DRICS_MODEL_DIR}" "${HF_HOME}" "$(dirname "${DOWNLOAD_VENV}")"

existing_bytes="$(directory_bytes "${MODEL_SNAPSHOT_DIR}")"
remaining_bytes=$((TENSOR_BYTES - existing_bytes))
if [ "${remaining_bytes}" -lt 0 ]; then
    remaining_bytes=0
fi
required_bytes=$((remaining_bytes + DOWNLOAD_HEADROOM_BYTES))
free_bytes="$(available_bytes "${DRICS_MODEL_DIR}")"

if [ -z "${free_bytes}" ] || ! [[ "${free_bytes}" =~ ^[0-9]+$ ]]; then
    fail "Could not determine free space for ${DRICS_MODEL_DIR}."
fi
if [ "${free_bytes}" -lt "${required_bytes}" ]; then
    required_gib=$(( (required_bytes + 1073741823) / 1073741824 ))
    free_gib=$((free_bytes / 1073741824))
    fail "Insufficient free space at ${DRICS_MODEL_DIR}: ${free_gib} GiB available; approximately ${required_gib} GiB required."
fi

if [ ! -x "${DOWNLOAD_VENV}/bin/python" ]; then
    python3 -m venv "${DOWNLOAD_VENV}"
fi

if ! "${DOWNLOAD_VENV}/bin/python" - "${HUGGINGFACE_HUB_VERSION}" <<'PY' >/dev/null 2>&1
import importlib.metadata
import sys

expected = sys.argv[1]
try:
    installed = importlib.metadata.version("huggingface-hub")
except importlib.metadata.PackageNotFoundError:
    raise SystemExit(1)
raise SystemExit(installed != expected)
PY
then
    "${DOWNLOAD_VENV}/bin/python" -m pip install --disable-pip-version-check \
        "huggingface_hub==${HUGGINGFACE_HUB_VERSION}"
fi

echo "Downloading the pinned official model (existing partial files will be reused):"
echo "  repository:    ${MODEL_ID}"
echo "  revision:      ${MODEL_REVISION}"
echo "  snapshot path: ${MODEL_SNAPSHOT_DIR}"
echo "  cache root:    ${HF_HOME}"
echo "  free space:    $((free_bytes / 1073741824)) GiB"
if [ -n "${HF_TOKEN:-}" ]; then
    echo "  authentication: HF_TOKEN is set (value will not be printed)"
else
    echo "  authentication: standard Hugging Face credential resolution (anonymous is valid for this public artifact)"
fi

mkdir -p "${MODEL_SNAPSHOT_DIR}"

"${DOWNLOAD_VENV}/bin/python" - \
    "${MODEL_ID}" \
    "${MODEL_REVISION}" \
    "${MODEL_SNAPSHOT_DIR}" \
    "${MANIFEST_PATH}" \
    "${HUGGINGFACE_HUB_VERSION}" \
    "${TENSOR_BYTES}" <<'PY'
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import struct
import sys

from huggingface_hub import HfApi, snapshot_download

(
    model_id,
    revision,
    snapshot_arg,
    manifest_arg,
    hub_version,
    expected_tensor_bytes_arg,
) = sys.argv[1:]
snapshot_path = Path(snapshot_arg).resolve()
manifest_path = Path(manifest_arg).resolve()
token = os.environ.get("HF_TOKEN") or None
expected_tensor_bytes = int(expected_tensor_bytes_arg)

info = HfApi(token=token).model_info(model_id, revision=revision)
if info.sha != revision:
    raise SystemExit(
        f"Resolved revision {info.sha!r} does not match required commit {revision!r}."
    )

snapshot_download(
    repo_id=model_id,
    revision=revision,
    local_dir=str(snapshot_path),
    token=token,
)

required_files = (
    "config.json",
    "tokenizer_config.json",
    "model.safetensors.index.json",
)
missing = [name for name in required_files if not (snapshot_path / name).is_file()]
if missing:
    raise SystemExit(f"Downloaded snapshot is incomplete; missing: {', '.join(missing)}")


def load_json(name: str) -> dict:
    with (snapshot_path / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


files = []
for path in sorted(snapshot_path.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(snapshot_path)
    if relative.parts and relative.parts[0] == ".cache":
        continue
    if path == manifest_path or path.name == f".{manifest_path.name}.tmp":
        continue
    files.append(
        {
            "path": relative.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    )

config = load_json("config.json")
tokenizer_config = load_json("tokenizer_config.json")
weight_index = load_json("model.safetensors.index.json")
tensor_shards = sorted(set(weight_index.get("weight_map", {}).values()))
if not tensor_shards:
    raise SystemExit("The safetensors index does not name any tensor shards.")
missing_shards = [name for name in tensor_shards if not (snapshot_path / name).is_file()]
if missing_shards:
    raise SystemExit(f"Downloaded tensor shards are missing: {', '.join(missing_shards)}")
actual_tensor_bytes = sum((snapshot_path / name).stat().st_size for name in tensor_shards)
if actual_tensor_bytes != expected_tensor_bytes:
    raise SystemExit(
        "Pinned tensor byte count mismatch: "
        f"expected {expected_tensor_bytes}, found {actual_tensor_bytes}."
    )

parameter_count = 0
parameter_count_by_dtype: dict[str, int] = {}
for name in tensor_shards:
    with (snapshot_path / name).open("rb") as handle:
        header_size = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_size))
    for tensor_name, metadata in header.items():
        if tensor_name == "__metadata__":
            continue
        count = math.prod(metadata["shape"])
        parameter_count += count
        dtype = metadata["dtype"]
        parameter_count_by_dtype[dtype] = parameter_count_by_dtype.get(dtype, 0) + count
manifest = {
    "manifest_schema": "drics-local-model-manifest-v1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "model_id": model_id,
    "requested_revision": revision,
    "resolved_commit": info.sha,
    "artifact_source": f"https://huggingface.co/{model_id}/tree/{revision}",
    "public": not bool(info.private),
    "gated": bool(info.gated),
    "license": next(
        (
            tag.removeprefix("license:")
            for tag in (info.tags or [])
            if tag.startswith("license:")
        ),
        None,
    ),
    "library_name": info.library_name,
    "pipeline_tag": info.pipeline_tag,
    "huggingface_hub_version": hub_version,
    "snapshot_path": str(snapshot_path),
    "model_type": config.get("model_type"),
    "architectures": config.get("architectures"),
    "torch_dtype": config.get("torch_dtype")
    or config.get("dtype")
    or config.get("text_config", {}).get("torch_dtype")
    or config.get("text_config", {}).get("dtype"),
    "max_position_embeddings": config.get("max_position_embeddings")
    or config.get("text_config", {}).get("max_position_embeddings"),
    "tokenizer_class": tokenizer_config.get("tokenizer_class"),
    "model_config": config,
    "tokenizer_config": tokenizer_config,
    "parameter_count": parameter_count,
    "parameter_count_by_dtype": parameter_count_by_dtype,
    "tensor_shards": tensor_shards,
    "tensor_bytes": actual_tensor_bytes,
    "files": files,
    "total_file_bytes": sum(item["size_bytes"] for item in files),
}

temporary_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
with temporary_path.open("w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(temporary_path, manifest_path)

print(f"Pinned snapshot ready: {snapshot_path}")
print(f"Resolved commit: {info.sha}")
print(f"Manifest: {manifest_path}")
print(f"Recorded artifact bytes: {manifest['total_file_bytes']}")
PY

echo "Download and integrity manifest generation complete."
