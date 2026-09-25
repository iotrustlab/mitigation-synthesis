"""Controlled context-to-CLEO-envelope instantiation for trusted backup takeover."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .context import RecoveryContext


class FormalStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_RUN = "NOT_RUN"
    INVALID_CONTEXT = "INVALID_CONTEXT"
    UNSUPPORTED_TEMPLATE = "UNSUPPORTED_TEMPLATE"
    REJECTED_CAPACITY = "REJECTED_CAPACITY"
    REJECTED_DEADLINE = "REJECTED_DEADLINE"
    REJECTED_SERVICE = "REJECTED_SERVICE"
    NO_VERIFIED_SERVICE_CANDIDATE = "NO_VERIFIED_SERVICE_CANDIDATE"


@dataclass(frozen=True)
class FormalReadiness:
    status: FormalStatus
    reason: str


@dataclass(frozen=True)
class FormalInstance:
    context: RecoveryContext
    envelope_text: str
    mapping: dict[str, str]


def _num(value: float) -> str:
    """Render finite synthetic constants in CLEO's ordinary decimal syntax."""

    if int(value) == value:
        return str(int(value))
    return format(value, ".12g")


def assess_takeover_readiness(context: RecoveryContext) -> FormalReadiness:
    """Reject configurations outside the *proved* model before calling a prover.

    This is a model-domain decision, not a proof failure or a counterexample.
    The current proof template represents immediate trusted isolation and a
    bounded backup-startup hold.  The simulator can explore delayed isolation,
    but that behavior has not been formalized yet.
    """

    context.validate()
    plant = context.plant
    if plant.backup_capacity < plant.min_service_flow:
        return FormalReadiness(
            FormalStatus.REJECTED_CAPACITY,
            "backup capacity is below the mandatory post-deadline service flow",
        )
    if plant.backup_startup_delay > plant.service_deadline:
        return FormalReadiness(
            FormalStatus.REJECTED_DEADLINE,
            "backup startup completes after the mandatory service deadline",
        )
    if plant.isolation_delay != 0:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the first formal template supports only immediate trusted isolation; delayed isolation is not proved",
        )
    if plant.upstream_nominal != plant.downstream_demand:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the first proof profile requires balanced nominal inflow and demand after takeover",
        )
    if plant.backup_capacity != plant.upstream_nominal:
        return FormalReadiness(
            FormalStatus.UNSUPPORTED_TEMPLATE,
            "the first proof profile requires backup capacity to balance nominal flow",
        )
    return FormalReadiness(FormalStatus.NOT_RUN, "eligible for concrete CLEO verification")


def _precondition(context: RecoveryContext) -> str:
    p, s = context.plant, context.current_state
    return f"""
L1 = {_num(p.low_t1)} & H1 = {_num(p.high_t1)}
& L2 = {_num(p.low_t2)} & H2 = {_num(p.high_t2)}
& x1 = {_num(s.x1)} & x2 = {_num(s.x2)}
& qprimary = {_num(p.primary_capacity)} & qbackup = {_num(p.backup_capacity)}
& qmin = {_num(p.min_service_flow)}
& StartupDelay = {_num(p.backup_startup_delay)} & IsolationDelay = {_num(p.isolation_delay)}
& T = {_num(p.control_period)} & Tmin = {_num(p.control_period)}
& isolationCost = 1 & backupCost = 1 & interventionBudget = 2
& L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
& qprimary >= 0 & qbackup >= qmin & qmin > 0
& T > 0 & Tmin > 0 & Tmin <= T
& IsolationDelay = 0
& p1 = {1 if s.p1_command else 0} & p2 = {1 if s.p2_command else 0}
& isolated = {1 if s.primary_path_isolated else 0}
""".strip()


def _envelope_section(text: str) -> str:
    """Indent all lines because CLEO's envelope format is indentation-sensitive."""

    return "\n".join(f"    {line}" for line in text.splitlines())


def render_recovery_envelope(context: RecoveryContext) -> FormalInstance:
    """Instantiate one checked template; no arbitrary caller-provided fragments exist."""

    readiness = assess_takeover_readiness(context)
    if readiness.status is not FormalStatus.NOT_RUN:
        raise ValueError(f"cannot instantiate unsupported recovery context: {readiness.reason}")

    text = f'''envelope "Trusted backup takeover recovery"

Guideline
    Prove bounded startup recovery and repeated safe operation after trusted primary-path isolation.
    P1 remains attacker-controlled. P2 and isolated are defender-controlled trusted resources.

Definitions
    Definitions
        Bool safe(Real x1, Real x2) <-> (L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2);
        Bool binary(Real v) <-> (v = 0) | (v = 1);
    End.

    ProgramVariables
        Real x1; Real x2;
        Real L1; Real H1; Real L2; Real H2;
        Real p1; Real p2; Real isolated;
        Real qin; Real qd; Real qprimary; Real qbackup; Real qmin;
        Real startupClock; Real operationClock; Real StartupDelay; Real IsolationDelay;
        Real T; Real Tmin;
        Real interventionBudget; Real isolationCost; Real backupCost;
    End.

precondition
{_envelope_section(_precondition(context))}

postcondition
    L1 <= x1 & x1 <= H1 & L2 <= x2 & x2 <= H2
    & isolated = 1 & p2 = 1
    & qin = qbackup & qd = qbackup
    & p2 * qbackup >= qmin
    & interventionBudget >= 0

game
    {{
        {{
            {{ p1 := 0; }}
            ++
            {{ p1 := 1; }}
        }}^@;
        isolated := 1;
        p2 := 0;
        qin := 0;
        qd := 0;
        startupClock := 0;
        {{
            startup_ode: {{
                x1' = qin - (1-isolated) * p1 * qprimary - p2 * qbackup,
                x2' = (1-isolated) * p1 * qprimary + p2 * qbackup - qd,
                startupClock' = 1
                & x1 >= 0 & x2 >= 0 & startupClock <= StartupDelay
            }};
            ? startupClock >= StartupDelay;
        }}^@;
        {{
            {{ p1 := 0; }}
            ++
            {{ p1 := 1; }}
        }}^@;
        p2 := 1;
        qin := qbackup;
        qd := qbackup;
        interventionBudget := interventionBudget - (isolationCost + backupCost);
        operation_loop: {{
            {{
                {{ p1 := 0; }}
                ++
                {{ p1 := 1; }}
            }}^@;
            isolated := 1;
            p2 := 1;
            qin := qbackup;
            qd := qbackup;
            operationClock := 0;
            {{
                operation_ode: {{
                    x1' = qin - (1-isolated) * p1 * qprimary - p2 * qbackup,
                    x2' = (1-isolated) * p1 * qprimary + p2 * qbackup - qd,
                    operationClock' = 1
                    & x1 >= 0 & x2 >= 0 & operationClock <= T
                }};
                ? operationClock >= Tmin;
            }}^@;
        }}*
    }}
'''
    return FormalInstance(
        context=context,
        envelope_text=text,
        mapping={
            "simulator.x1": "x1",
            "simulator.x2": "x2",
            "simulator.P1_command": "p1",
            "simulator.P2_command": "p2",
            "simulator.primary_path_isolated": "isolated",
            "simulator.q_in": "qin",
            "simulator.q_demand": "qd",
            "simulator.q1": "(1-isolated) * p1 * qprimary",
            "simulator.q2": "p2 * qbackup",
        },
    )
