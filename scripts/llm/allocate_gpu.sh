#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${DRICS_PYTHON:-${REPO_ROOT}/.venv/bin/python}"

if [ ! -x "${PYTHON}" ]; then
    PYTHON="$(command -v python3 || true)"
fi
[ -n "${PYTHON}" ] || {
    echo "ERROR: no Python interpreter is available." >&2
    exit 1
}
"${PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' || {
    echo "ERROR: GPU allocation tooling requires Python 3.8+; bootstrap the project .venv." >&2
    exit 1
}

exec "${PYTHON}" "${SCRIPT_DIR}/gpu_allocation.py" allocate "$@"
