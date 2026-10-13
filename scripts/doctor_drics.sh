#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=drics_env.sh
source "${SCRIPT_DIR}/drics_env.sh"

failures=0
ok() { printf '%-31s %s\n' "$1" "OK${2:+ ($2)}"; }
fail() { printf '%-31s %s\n' "$1" "FAIL${2:+ ($2)}"; failures=$((failures + 1)); }

echo "Dr.ICS environment doctor"
echo
printf '%-31s %s\n' "Repository root:" "${REPO_ROOT}"
printf '%-31s %s\n' "OS:" "$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
printf '%-31s %s\n' "Architecture:" "$(uname -m)"

required_files=(
    recovery_experiment/context.py
    recovery_experiment/model.py
    recovery_experiment/policies.py
    recovery_experiment/recovery_model_builder.py
    recovery_experiment/formal_problem.py
    recovery_experiment/incident_evidence.py
    recovery_experiment/incident_interpreter.py
    recovery_experiment/context_grounding.py
    recovery_experiment/incident_pipeline.py
    recovery_experiment/tests/test_incident_evidence_pipeline.py
)
missing_files=0
for relative_path in "${required_files[@]}"; do
    [ -f "${REPO_ROOT}/${relative_path}" ] || missing_files=$((missing_files + 1))
done
if [ "${missing_files}" -eq 0 ]; then ok "Recovery experiment files:"; else fail "Recovery experiment files:" "${missing_files} missing"; fi

if [ -x "${DRICS_PYTHON}" ]; then
    ok "Project Python:" "$(${DRICS_PYTHON} --version 2>&1)"
else
    fail "Project Python:" "run scripts/bootstrap_drics.sh"
fi

if [ -x "${CLEO_PYTHON}" ]; then
    ok "CLEO Python:" "$(${CLEO_PYTHON} --version 2>&1)"
    cleo_version="$(${CLEO_PYTHON} -c 'import importlib.metadata; print(importlib.metadata.version("cleo"))' 2>/dev/null)"
    if [ -n "${cleo_version}" ]; then ok "CLEO import:" "${cleo_version}"; else fail "CLEO import:"; fi
    z3_version="$(${CLEO_PYTHON} -c 'import z3; print(z3.get_version_string())' 2>/dev/null)"
    if [ -n "${z3_version}" ]; then ok "Python Z3:" "${z3_version}"; else fail "Python Z3:"; fi
else
    fail "CLEO Python:" "run scripts/bootstrap_drics.sh"
fi

if command -v z3 >/dev/null 2>&1; then ok "Z3 command:" "$(z3 --version 2>&1)"; else fail "Z3 command:" "source scripts/drics_env.sh"; fi
if command -v java >/dev/null 2>&1; then ok "Java:" "$(java -version 2>&1 | head -1)"; else fail "Java:"; fi

kyx_jar="${REPO_ROOT}/.external/cleo/source/cleo/keymaerax.jar"
if [ -s "${kyx_jar}" ]; then ok "KeYmaera X backend:" "bundled JAR"; else fail "KeYmaera X backend:" "${kyx_jar}"; fi

if [ -x "${DRICS_PYTHON}" ] && (cd "${REPO_ROOT}" && "${DRICS_PYTHON}" -c 'import recovery_experiment; import unittest; s=unittest.defaultTestLoader.discover("recovery_experiment/tests"); assert s.countTestCases() > 0') >/dev/null 2>&1; then
    ok "Unit-test import check:"
else
    fail "Unit-test import check:"
fi

echo
if [ "${failures}" -eq 0 ]; then
    echo "Overall: READY"
    exit 0
else
    echo "Overall: NOT READY (${failures} problem(s))"
    exit 1
fi

