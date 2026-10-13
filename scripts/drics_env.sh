#!/usr/bin/env bash
# Source this file from the repository root (or any directory) before running
# Dr.ICS verification commands.

_drics_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DRICS_ROOT="$(cd "${_drics_script_dir}/.." && pwd)"

if ! type module >/dev/null 2>&1 && [ -r /etc/profile.d/modules.sh ]; then
    # shellcheck source=/dev/null
    source /etc/profile.d/modules.sh
fi

if type module >/dev/null 2>&1; then
    _drics_python_ok=0
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1 && _drics_python_ok=1
    fi
    if [ "${_drics_python_ok}" -ne 1 ]; then
        module load python/3.12.12 >/dev/null 2>&1 || module load python/3.12.4 >/dev/null 2>&1
    fi

    _drics_java_major=""
    if command -v java >/dev/null 2>&1; then
        _drics_java_major="$(java -version 2>&1 | awk -F'[._"]' '/version/ {if ($2 == 1) print $3; else print $2; exit}')"
    fi
    if [ -z "${_drics_java_major}" ] || [ "${_drics_java_major}" -lt 11 ]; then
        module load openjdk/17.0.1 >/dev/null 2>&1 || true
    fi
fi

export DRICS_PYTHON="${DRICS_ROOT}/.venv/bin/python"
export CLEO_PYTHON="${DRICS_ROOT}/.external/cleo/.venv/bin/python"
export CLEO_KEYMAERAX_TIMEOUT_SECONDS="${CLEO_KEYMAERAX_TIMEOUT_SECONDS:-300}"

if [ -d "${DRICS_ROOT}/.external/cleo/.venv/bin" ]; then
    export PATH="${DRICS_ROOT}/.external/cleo/.venv/bin:${PATH}"
elif [ -d "${DRICS_ROOT}/.venv/bin" ]; then
    export PATH="${DRICS_ROOT}/.venv/bin:${PATH}"
fi

unset _drics_script_dir _drics_python_ok _drics_java_major
