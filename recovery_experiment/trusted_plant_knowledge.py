"""Manually supplied trusted facts that evidence interpretation may not invent."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .context import TakeoverAssuranceParameters
from .model import AttackerAction, PlantParameters


class TrustedKnowledgeValidationError(ValueError):
    """Raised for malformed trusted configuration, not for incident evidence."""


@dataclass(frozen=True)
class ComponentKnowledge:
    component_id: str
    role: str
    context_component: str | None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class BackupRelationship:
    primary_component: str
    backup_component: str
    backup_control: str
    independently_trusted_by_design: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TrustedPlantKnowledge:
    """Static synthetic topology, signal mappings, and formal-model boundaries."""

    knowledge_id: str
    plant_identity: str
    plant_parameters: PlantParameters
    formal_plant_model_id: str
    default_recovery_policy_id: str
    components: tuple[ComponentKnowledge, ...]
    process_dependencies: tuple[tuple[str, tuple[str, ...]], ...]
    backup_relationships: tuple[BackupRelationship, ...]
    physical_isolator_control: str
    hold_inflow_control: str
    hold_demand_control: str
    observation_signal_map: tuple[tuple[str, str], ...]
    trusted_observation_sources: frozenset[str]
    attack_capability_map: tuple[tuple[str, tuple[AttackerAction, ...]], ...]
    supported_template_ids: tuple[str, ...]

    def component_ids(self) -> frozenset[str]:
        return frozenset(component.component_id for component in self.components)

    def context_components(self) -> frozenset[str]:
        return frozenset(
            component.context_component for component in self.components if component.context_component is not None
        )

    def process_dependency_mapping(self) -> dict[str, tuple[str, ...]]:
        return dict(self.process_dependencies)

    def observation_target(self, signal: str) -> str | None:
        return dict(self.observation_signal_map).get(signal)

    def attack_actions(self, capability: str) -> tuple[AttackerAction, ...] | None:
        return dict(self.attack_capability_map).get(capability)

    def is_backup_for(self, primary: str, backup: str) -> bool:
        return any(
            relationship.primary_component == primary and relationship.backup_component == backup
            for relationship in self.backup_relationships
        )

    def validate(self) -> None:
        self.plant_parameters.validate()
        if not self.knowledge_id or not self.plant_identity:
            raise TrustedKnowledgeValidationError("knowledge and plant identities must be explicit")
        component_ids = self.component_ids()
        if len(component_ids) != len(self.components):
            raise TrustedKnowledgeValidationError("trusted component identifiers must be unique")
        required = {"T1", "T2", "P1", "P2", "isolator", "upstream_gate", "demand_gate"}
        if not required <= component_ids:
            raise TrustedKnowledgeValidationError("trusted knowledge must describe the fixed synthetic plant components")
        expected_context = {
            "P1_command_path",
            "P2_command",
            "primary_isolator",
            "upstream_gate",
            "demand_gate",
            "T1",
            "T2",
            "P1_path",
            "P2_path",
        }
        if self.context_components() != expected_context:
            raise TrustedKnowledgeValidationError("trusted component mapping does not match the fixed formal topology")
        if not self.is_backup_for("P1", "P2"):
            raise TrustedKnowledgeValidationError("trusted knowledge must explicitly declare P2 as P1 backup")
        if self.physical_isolator_control != "primary_isolator":
            raise TrustedKnowledgeValidationError("the current formal plant supports only primary_isolator")
        if {self.hold_inflow_control, self.hold_demand_control} != {"upstream_gate", "demand_gate"}:
            raise TrustedKnowledgeValidationError("the current safe-hold model requires upstream and demand gates")
        if not self.trusted_observation_sources:
            raise TrustedKnowledgeValidationError("trusted observation sources must be explicit")
        if self.attack_actions("modify_primary_pump_command") != (
            AttackerAction.FORCE_PRIMARY_OFF,
            AttackerAction.FORCE_PRIMARY_ON,
        ):
            raise TrustedKnowledgeValidationError("the formal attack mapping must explicitly cover P1 off/on commands")

    def as_dict(self) -> dict[str, object]:
        return {
            "knowledge_id": self.knowledge_id,
            "plant_identity": self.plant_identity,
            "plant_parameters": self.plant_parameters.as_dict(),
            "formal_plant_model_id": self.formal_plant_model_id,
            "default_recovery_policy_id": self.default_recovery_policy_id,
            "components": [component.as_dict() for component in self.components],
            "process_dependencies": {key: list(value) for key, value in self.process_dependencies},
            "backup_relationships": [relationship.as_dict() for relationship in self.backup_relationships],
            "physical_isolator_control": self.physical_isolator_control,
            "hold_inflow_control": self.hold_inflow_control,
            "hold_demand_control": self.hold_demand_control,
            "observation_signal_map": dict(self.observation_signal_map),
            "trusted_observation_sources": sorted(self.trusted_observation_sources),
            "attack_capability_map": {
                capability: [action.value for action in actions]
                for capability, actions in self.attack_capability_map
            },
            "supported_template_ids": list(self.supported_template_ids),
        }


@dataclass(frozen=True)
class RecoveryConfiguration:
    """Explicit incident-independent recovery authority and timing configuration."""

    configuration_id: str
    control_period: float | None
    isolation_delay: float | None
    backup_startup_delay: float | None
    transfer_recovery_deadline: float | None
    horizon: float | None
    trusted_controls: frozenset[str]
    controllable_controls: frozenset[str]
    assurance: TakeoverAssuranceParameters
    required_delivered_flow: float
    require_continuous_delivery: bool
    permitted_interruption_duration: float

    def validate(self) -> None:
        if not self.configuration_id:
            raise TrustedKnowledgeValidationError("recovery configuration identity must be explicit")
        for name, value in {
            "control_period": self.control_period,
            "isolation_delay": self.isolation_delay,
            "backup_startup_delay": self.backup_startup_delay,
            "transfer_recovery_deadline": self.transfer_recovery_deadline,
            "horizon": self.horizon,
        }.items():
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0
            ):
                raise TrustedKnowledgeValidationError(f"{name} must be finite and nonnegative when configured")
        if self.control_period is not None and self.control_period <= 0:
            raise TrustedKnowledgeValidationError("control_period must be positive when configured")
        if self.horizon is not None and self.horizon <= 0:
            raise TrustedKnowledgeValidationError("horizon must be positive when configured")
        controls = {"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}
        if not self.trusted_controls <= controls or not self.controllable_controls <= controls:
            raise TrustedKnowledgeValidationError("recovery authority names an unsupported control")
        self.assurance.validate()
        if self.required_delivered_flow < 0 or self.permitted_interruption_duration < 0:
            raise TrustedKnowledgeValidationError("service values must be nonnegative")
        if type(self.require_continuous_delivery) is not bool:
            raise TrustedKnowledgeValidationError("continuous-delivery requirement must be explicit")

    def as_dict(self) -> dict[str, object]:
        return {
            "configuration_id": self.configuration_id,
            "control_period": self.control_period,
            "isolation_delay": self.isolation_delay,
            "backup_startup_delay": self.backup_startup_delay,
            "transfer_recovery_deadline": self.transfer_recovery_deadline,
            "horizon": self.horizon,
            "trusted_controls": sorted(self.trusted_controls),
            "controllable_controls": sorted(self.controllable_controls),
            "assurance": asdict(self.assurance),
            "required_delivered_flow": self.required_delivered_flow,
            "require_continuous_delivery": self.require_continuous_delivery,
            "permitted_interruption_duration": self.permitted_interruption_duration,
        }


def synthetic_two_tank_knowledge(parameters: PlantParameters | None = None) -> TrustedPlantKnowledge:
    """Return the manually maintained knowledge base for the one supported plant."""

    knowledge = TrustedPlantKnowledge(
        knowledge_id="synthetic-two-tank-trusted-knowledge-v1",
        plant_identity="synthetic-two-tank-parallel-pump-v1",
        plant_parameters=parameters or PlantParameters(),
        formal_plant_model_id="synthetic-two-tank-v1",
        default_recovery_policy_id="trusted-backup-takeover-v1",
        components=(
            ComponentKnowledge("T1", "upstream_tank", "T1"),
            ComponentKnowledge("T2", "downstream_tank", "T2"),
            ComponentKnowledge("P1", "primary_transfer_path", "P1_path"),
            ComponentKnowledge("P2", "backup_transfer_path", "P2_path"),
            ComponentKnowledge("isolator", "primary_path_isolation", "primary_isolator"),
            ComponentKnowledge("upstream_gate", "trusted_inflow_control", "upstream_gate"),
            ComponentKnowledge("demand_gate", "trusted_service_control", "demand_gate"),
            # The command surfaces are explicitly represented by these existing formal components.
            ComponentKnowledge("P1_command", "compromised_command_surface", "P1_command_path"),
            ComponentKnowledge("P2_command", "backup_command_surface", "P2_command"),
        ),
        process_dependencies=(
            ("T1", ("upstream_inflow", "P1_path", "P2_path")),
            ("T2", ("P1_path", "P2_path", "downstream_demand")),
            ("P2_path", ("T1", "T2")),
        ),
        backup_relationships=(BackupRelationship("P1", "P2", "P2_command", True),),
        physical_isolator_control="primary_isolator",
        hold_inflow_control="upstream_gate",
        hold_demand_control="demand_gate",
        observation_signal_map=(
            ("x1", "x1"),
            ("x2", "x2"),
            ("P1_command", "P1_command_path"),
            ("P1_actual", "P1_path"),
            ("control_period", "timing"),
            ("isolation_delay", "timing"),
            ("backup_startup_delay", "timing"),
        ),
        trusted_observation_sources=frozenset({"synthetic_telemetry", "synthetic_ids"}),
        attack_capability_map=(
            ("modify_primary_pump_command", (AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON)),
        ),
        supported_template_ids=("flowing_backup_takeover", "controlled_safe_hold"),
    )
    knowledge.validate()
    return knowledge


def synthetic_recovery_configuration(
    parameters: PlantParameters | None = None,
) -> RecoveryConfiguration:
    """Return explicit timing, authority, and service values for synthetic recovery."""

    p = parameters or PlantParameters()
    configuration = RecoveryConfiguration(
        configuration_id="synthetic-recovery-configuration-v1",
        control_period=p.control_period,
        isolation_delay=p.isolation_delay,
        backup_startup_delay=p.backup_startup_delay,
        transfer_recovery_deadline=p.transfer_recovery_deadline,
        horizon=p.horizon,
        trusted_controls=frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}),
        controllable_controls=frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}),
        assurance=TakeoverAssuranceParameters(),
        required_delivered_flow=p.min_service_flow,
        require_continuous_delivery=True,
        permitted_interruption_duration=0.0,
    )
    configuration.validate()
    return configuration
