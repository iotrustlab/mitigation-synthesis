#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=drics_env.sh
source "${SCRIPT_DIR}/drics_env.sh"

ARTIFACT_ROOT="${REPO_ROOT}/.external/cleo"
DOWNLOAD_DIR="${REPO_ROOT}/.external/downloads"
CLEO_SOURCE="${ARTIFACT_ROOT}/source"
CLEO_VENV="${ARTIFACT_ROOT}/.venv"
PROJECT_VENV="${REPO_ROOT}/.venv"

mkdir -p "${DOWNLOAD_DIR}" "${CLEO_SOURCE}"

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "ERROR: Python 3.11+ is required (Python 3.12 recommended)." >&2
    echo "On CHPC, load python/3.12.12 before rerunning this script." >&2
    exit 1
fi
if ! command -v java >/dev/null 2>&1; then
    echo "ERROR: Java is required for the bundled KeYmaera X backend." >&2
    exit 1
fi
for command_name in curl md5sum patch unzip; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        echo "ERROR: required command not found: ${command_name}" >&2
        exit 1
    }
done

download_checked() {
    local url="$1" destination="$2" expected_md5="$3"
    if [ -f "${destination}" ] && printf '%s  %s\n' "${expected_md5}" "${destination}" | md5sum -c --status; then
        return
    fi
    local partial="${destination}.partial"
    curl -L --fail --show-error --retry 3 "${url}" -o "${partial}"
    printf '%s  %s\n' "${expected_md5}" "${partial}" | md5sum -c --status || {
        echo "ERROR: checksum mismatch for ${url}" >&2
        exit 1
    }
    mv "${partial}" "${destination}"
}

# CLEO 0.1.0 artifact: https://doi.org/10.1184/R1/32320254 (2026-05-19).
download_checked \
    "https://ndownloader.figshare.com/files/64722681" \
    "${DOWNLOAD_DIR}/cleo-64722681.zip" \
    "85ffdf7f92c8b2b870764f3dcf11e6a5"
download_checked \
    "https://ndownloader.figshare.com/files/64722864" \
    "${CLEO_SOURCE}/pyproject.toml" \
    "3816b9c41e39c01dd3cdaf4b45aba051"
download_checked \
    "https://ndownloader.figshare.com/files/64722756" \
    "${CLEO_SOURCE}/README.md" \
    "ec55a547ce0d74976d1421ada75e0439"
download_checked \
    "https://ndownloader.figshare.com/files/64722711" \
    "${CLEO_SOURCE}/LICENSE.txt" \
    "b787c682b72f740e269c48e137b9cfec"

if [ ! -f "${CLEO_SOURCE}/cleo/keymaerax.jar" ]; then
    unzip -q -o "${DOWNLOAD_DIR}/cleo-64722681.zip" -d "${CLEO_SOURCE}"
fi

TIMEOUT_PATCH="${REPO_ROOT}/scripts/patches/cleo-keymaerax-timeout.patch"
if ! grep -q 'CLEO_KEYMAERAX_TIMEOUT_SECONDS' "${CLEO_SOURCE}/cleo/keymaerax_utils.py"; then
    patch -d "${CLEO_SOURCE}" -p1 < "${TIMEOUT_PATCH}"
fi
if [ ! -f "${CLEO_SOURCE}/cleo/keymaerax.jar" ]; then
    echo "ERROR: bundled KeYmaera X JAR was not reconstructed from the CLEO artifact." >&2
    exit 1
fi

if [ ! -x "${PROJECT_VENV}/bin/python" ]; then
    python3 -m venv "${PROJECT_VENV}"
fi
"${PROJECT_VENV}/bin/python" -m pip install --upgrade pip
if [ -f "${REPO_ROOT}/requirements-drics.lock" ]; then
    "${PROJECT_VENV}/bin/python" -m pip install -r "${REPO_ROOT}/requirements-drics.lock"
fi

if [ ! -x "${CLEO_VENV}/bin/python" ]; then
    python3 -m venv "${CLEO_VENV}"
fi
"${CLEO_VENV}/bin/python" -m pip install --upgrade pip
if [ -f "${REPO_ROOT}/requirements-cleo.lock" ]; then
    "${CLEO_VENV}/bin/python" -m pip install -r "${REPO_ROOT}/requirements-cleo.lock"
    "${CLEO_VENV}/bin/python" -m pip install --no-deps -e "${CLEO_SOURCE}"
else
    "${CLEO_VENV}/bin/python" -m pip install "z3-solver==4.16.0.0"
    "${CLEO_VENV}/bin/python" -m pip install -e "${CLEO_SOURCE}"
fi

echo "Bootstrap complete."
echo "Project Python: ${PROJECT_VENV}/bin/python"
echo "CLEO Python:    ${CLEO_VENV}/bin/python"
echo "Next: ${SCRIPT_DIR}/doctor_drics.sh"
