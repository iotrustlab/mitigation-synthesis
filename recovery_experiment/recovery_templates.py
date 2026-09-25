"""Typed recovery-template applicability for the fixed synthetic plant family.

This is deliberately a finite catalogue rather than a strategy synthesizer.
It separates fixed topology from incident-specific trusted operational authority
before a formal problem is rendered or a certificate is consulted.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum

from .context import ContextValidationError, RecoveryContext
from .model import AttackerAction, DefenderAction


FLOWING_BACKUP_TAKEOVER_TEMPLATE_ID = "flowing_backup_takeover"
CONTROLLED_SAFE_HOLD_TEMPLATE_ID = "controlled_safe_hold"


class RecoveryTemplateId(str, Enum):
    """The only two recovery templates implemented for this plant family."""

    FLOWING_BACKUP_TAKEOVER = FLOWING_BACKUP_TAKEOVER_TEMPLATE_ID
    CONTROLLED_SAFE_HOLD = CONTROLLED_SAFE_HOLD_TEMPLATE_ID


class TemplateApplicabilityStatus(str, Enum):
    APPLICABLE = "TEMPLATE_APPLICABLE"
    NOT_APPLICABLE = "TEMPLATE_NOT_APPLICABLE"
    INVALID_CONTEXT = "INVALID_INCIDENT_CONTEXT"


@dataclass(frozen=True)
class TemplatePhase:
    """Authority and physical evolution expected for one template phase."""

    name: str
    owner: str
    attacker_commandable: bool
    primary_physically_effective: bool
    duration: str
    mandatory_physical_evolution: bool


@dataclass(frozen=True)
class RecoveryTemplate:
    """A reusable formal-problem family, not a selected runtime policy."""

    template_id: RecoveryTemplateId
    supported_plant_model: str
    required_resources: tuple[str, ...]
    attacker_capabilities: tuple[AttackerAction, ...]
    defender_actions: tuple[DefenderAction, ...]
    phase_structure: tuple[TemplatePhase, ...]
    safety_contract: str
    service_contract: str
    timing_parameters: tuple[str, ...]
    cost_interpretation: str
    proof_template_id: str

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["template_id"] = self.template_id.value
        data["attacker_capabilities"] = [action.value for action in self.attacker_capabilities]
        data["defender_actions"] = [action.value for action in self.defender_actions]
        return data


@dataclass(frozen=True)
class TemplateApplicability:
    template: RecoveryTemplate
    status: TemplateApplicabilityStatus
    reasons: tuple[str, ...]

    @property
    def applicable(self) -> bool:
        return self.status is TemplateApplicabilityStatus.APPLICABLE

    def as_dict(self) -> dict[str, object]:
        return {
            "template": self.template.as_dict(),
            "status": self.status.value,
            "applicable": self.applicable,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class TemplateApplicabilityReport:
    """All template decisions for one incident, including excluded templates."""

    entries: tuple[TemplateApplicability, ...]
    context_error: str | None = None

    @property
    def applicable_templates(self) -> tuple[RecoveryTemplateId, ...]:
        return tuple(entry.template.template_id for entry in self.entries if entry.applicable)

    @property
    def no_supported_template(self) -> bool:
        return not self.applicable_templates

    def for_template(self, template_id: RecoveryTemplateId) -> TemplateApplicability:
        return next(entry for entry in self.entries if entry.template.template_id is template_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "context_error": self.context_error,
            "applicable_templates": [template.value for template in self.applicable_templates],
            "no_supported_template": self.no_supported_template,
            "entries": [entry.as_dict() for entry in self.entries],
        }


FLOWING_BACKUP_TAKEOVER_TEMPLATE = RecoveryTemplate(
    template_id=RecoveryTemplateId.FLOWING_BACKUP_TAKEOVER,
    supported_plant_model="synthetic-two-tank-v1",
    required_resources=("trusted_isolation_available", "trusted_backup_available"),
    attacker_capabilities=(AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON),
    defender_actions=(DefenderAction.START_FLOWING_TAKEOVER,),
    phase_structure=(
        TemplatePhase("attacker_command", "attacker", True, True, "0", False),
        TemplatePhase("isolation_and_backup_start", "trusted_defender", True, True, "0", False),
        TemplatePhase("bounded_pending_evolution", "physical_plant", True, True, "(n,m) control periods", True),
        TemplatePhase("post_takeover_operation", "physical_plant", True, False, "T > 0", True),
    ),
    safety_contract="Tank bounds hold through the generated bounded isolation and P2-startup schedule.",
    service_contract="Continuous startup delivery and positive post-takeover delivery are required by the reviewed takeover certificates.",
    timing_parameters=("control_period", "isolation_periods n", "startup_periods m", "m > n"),
    cost_interpretation="Trace-derived service shortfall plus recovery, isolation, intervention, and backup-usage costs.",
    proof_template_id="bounded-isolation-clock-relative-margins-v1",
)


CONTROLLED_SAFE_HOLD_TEMPLATE = RecoveryTemplate(
    template_id=RecoveryTemplateId.CONTROLLED_SAFE_HOLD,
    supported_plant_model="synthetic-two-tank-v1",
    required_resources=(
        "trusted_isolation_available",
        "trusted_inflow_control_available",
        "trusted_demand_control_available",
    ),
    attacker_capabilities=(AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON),
    defender_actions=(DefenderAction.START_CONTROLLED_SAFE_HOLD,),
    phase_structure=(
        TemplatePhase("attacker_command_before_isolation", "attacker", True, True, "0", False),
        TemplatePhase("immediate_isolation_and_hold_controls", "trusted_defender", True, False, "0", False),
        TemplatePhase("mandatory_safe_hold_evolution", "physical_plant", True, False, "HoldDuration > 0", True),
    ),
    safety_contract="Immediate independent isolation and trusted inflow/demand closure keep both tank levels unchanged for HoldDuration.",
    service_contract="External demand remains positive while actual delivery is zero; the theorem establishes safety, not positive service.",
    timing_parameters=("isolation_delay = 0", "HoldDuration > 0"),
    cost_interpretation="Trace-derived shortfall is measured against unchanged external demand; no backup-use cost is charged.",
    proof_template_id="controlled-safe-hold-immediate-isolation-profile-v1",
)


RECOVERY_TEMPLATES: tuple[RecoveryTemplate, ...] = (
    FLOWING_BACKUP_TAKEOVER_TEMPLATE,
    CONTROLLED_SAFE_HOLD_TEMPLATE,
)


def _availability_reasons(template: RecoveryTemplate, context: RecoveryContext) -> tuple[str, ...]:
    availability = context.resource_availability
    values = {
        "trusted_isolation_available": availability.trusted_isolation_available,
        "trusted_backup_available": availability.trusted_backup_available,
        "trusted_inflow_control_available": availability.trusted_inflow_control_available,
        "trusted_demand_control_available": availability.trusted_demand_control_available,
    }
    reasons = [f"{resource} is not available through a trusted recovery control path" for resource in template.required_resources if not values[resource]]
    if template.template_id is RecoveryTemplateId.CONTROLLED_SAFE_HOLD and not math.isclose(
        context.plant.isolation_delay, 0.0, rel_tol=0.0, abs_tol=1e-12
    ):
        reasons.append(
            "controlled safe hold currently supports immediate physical isolation only; delayed isolation has no hold theorem"
        )
    return tuple(reasons)


def assess_recovery_template_applicability(context: RecoveryContext) -> TemplateApplicabilityReport:
    """Report resource compatibility before rendering a formal model or checking a certificate."""

    try:
        context.validate()
    except (ContextValidationError, ValueError) as exc:
        return TemplateApplicabilityReport(
            tuple(
                TemplateApplicability(template, TemplateApplicabilityStatus.INVALID_CONTEXT, (str(exc),))
                for template in RECOVERY_TEMPLATES
            ),
            str(exc),
        )
    entries = []
    for template in RECOVERY_TEMPLATES:
        reasons = _availability_reasons(template, context)
        entries.append(
            TemplateApplicability(
                template,
                TemplateApplicabilityStatus.NOT_APPLICABLE if reasons else TemplateApplicabilityStatus.APPLICABLE,
                reasons,
            )
        )
    return TemplateApplicabilityReport(tuple(entries))
