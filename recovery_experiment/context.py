"""Typed, validated recovery contexts for the one supported plant topology."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .model import AttackerAction, PlantParameters, PlantState, TwoTankPlant


class ContextValidationError(ValueError):
    """Raised instead of inventing missing plant, trust, or timing information."""


@dataclass(frozen=True)
class SafetyRequirements:
    variables: tuple[str, str] = ("x1", "x2")
    must_hold_throughout: bool = True


@dataclass(frozen=True)
class ServiceRequirements:
    delivered_flow_variable: str = "q_delivered"
    minimum_flow: float = 1.2
    deadline: float = 1.5


@dataclass(frozen=True)
class RecoveryTiming:
    control_period: float
    backup_startup_delay: float
    isolation_delay: float
    transfer_recovery_deadline: float
    horizon: float


@dataclass(frozen=True)
class RecoveryCostParameters:
    service_loss_weight: float = 10.0
    recovery_time_weight: float = 1.0
    intervention_weight: float = 2.0
    backup_usage_weight: float = 0.5
    conservative_intervention_cost: float = 1.0
    takeover_intervention_cost: float = 2.0


@dataclass(frozen=True)
class TakeoverAssuranceParameters:
    """Trusted runtime facts used by the fixed takeover assurance contract."""

    intervention_budget: float = 2.0
    isolation_cost: float = 1.0
    backup_activation_cost: float = 1.0
    hold_control_cost: float = 1.0

    def validate(self) -> None:
        values = {
            "intervention_budget": self.intervention_budget,
            "isolation_cost": self.isolation_cost,
            "backup_activation_cost": self.backup_activation_cost,
            "hold_control_cost": self.hold_control_cost,
        }
        for name, value in values.items():
            if value < 0:
                raise ContextValidationError(f"{name} must be nonnegative")


@dataclass(frozen=True)
class RecoveryResourceAvailability:
    """Incident-specific operational authority, separate from component existence.

    The fixed synthetic topology contains P1, P2, the primary isolator, and
    both flow gates. These booleans state whether the recovery layer can use a
    trusted, operational control path during this incident. They deliberately
    have no defaults: an omitted fact must be rejected rather than assumed.
    """

    trusted_isolation_available: bool
    trusted_backup_available: bool
    trusted_inflow_control_available: bool
    trusted_demand_control_available: bool

    def validate(self, trusted_actuators: frozenset[str]) -> None:
        values = {
            "trusted_isolation_available": self.trusted_isolation_available,
            "trusted_backup_available": self.trusted_backup_available,
            "trusted_inflow_control_available": self.trusted_inflow_control_available,
            "trusted_demand_control_available": self.trusted_demand_control_available,
        }
        if any(type(value) is not bool for value in values.values()):
            raise ContextValidationError("recovery resource availability must be explicit booleans")
        required_actuators = {
            "trusted_isolation_available": "primary_isolator",
            "trusted_backup_available": "P2_command",
            "trusted_inflow_control_available": "upstream_gate",
            "trusted_demand_control_available": "demand_gate",
        }
        for resource, actuator in required_actuators.items():
            if values[resource] and actuator not in trusted_actuators:
                raise ContextValidationError(
                    f"{resource} requires an explicit trusted actuator binding for {actuator}"
                )


@dataclass(frozen=True)
class RecoveryControlPathAuthority:
    """Separate incident facts used to decide whether a control path is usable.

    Physical component existence belongs to ``RecoveryContext.physical_components``.
    These three explicit sets avoid treating a component's existence as evidence
    that its signal path is operational, trusted, or controllable by recovery.
    ``RecoveryResourceAvailability`` is the final policy-level availability
    decision after these facts and any additional incident evidence are assessed.
    """

    operational: frozenset[str]
    trusted: frozenset[str]
    controllable_by_recovery: frozenset[str]

    def validate(self, known_controls: frozenset[str]) -> None:
        for name, controls in {
            "operational": self.operational,
            "trusted": self.trusted,
            "controllable_by_recovery": self.controllable_by_recovery,
        }.items():
            if not isinstance(controls, frozenset) or not controls <= known_controls:
                raise ContextValidationError(
                    f"{name} recovery-control authority must explicitly reference only known controls"
                )


@dataclass(frozen=True)
class RecoveryContext:
    """Recovery input split between runtime state and trusted plant knowledge.

    This deliberately recognizes only the components of the abstract topology.
    It is not a generic asset inventory and does not claim a connection to SWaT
    or another physical deployment.
    """

    current_state: PlantState
    plant: PlantParameters
    compromised_components: frozenset[str]
    attacker_capabilities: frozenset[AttackerAction]
    trusted_observations: frozenset[str]
    trusted_actuators: frozenset[str]
    physical_components: frozenset[str]
    control_path_authority: RecoveryControlPathAuthority
    available_recovery_resources: Mapping[str, float | bool]
    resource_availability: RecoveryResourceAvailability
    process_dependencies: Mapping[str, tuple[str, ...]]
    safety_requirements: SafetyRequirements
    service_requirements: ServiceRequirements
    recovery_timing: RecoveryTiming
    recovery_cost_parameters: RecoveryCostParameters
    takeover_assurance: TakeoverAssuranceParameters
    plant_model_id: str
    recovery_policy_id: str

    @classmethod
    def from_plant(
        cls,
        plant: TwoTankPlant,
        *,
        cost_parameters: RecoveryCostParameters | None = None,
    ) -> "RecoveryContext":
        p = plant.parameters
        return cls(
            current_state=plant.state.copy(),
            plant=p,
            compromised_components=frozenset({"P1_command_path"}),
            attacker_capabilities=frozenset(
                {AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON}
            ),
            trusted_observations=frozenset({"x1", "x2", "P2_state", "isolation_state"}),
            trusted_actuators=frozenset({"P2_command", "primary_isolator", "upstream_gate", "demand_gate"}),
            physical_components=frozenset(
                {"P1_command_path", "P2_command", "primary_isolator", "upstream_gate", "demand_gate", "T1", "T2", "P1_path", "P2_path"}
            ),
            control_path_authority=RecoveryControlPathAuthority(
                operational=frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}),
                trusted=frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}),
                controllable_by_recovery=frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"}),
            ),
            available_recovery_resources={
                "backup_capacity": p.backup_capacity,
                "primary_isolation": True,
            },
            resource_availability=RecoveryResourceAvailability(
                trusted_isolation_available=True,
                trusted_backup_available=True,
                trusted_inflow_control_available=True,
                trusted_demand_control_available=True,
            ),
            process_dependencies={
                "T1": ("upstream_inflow", "P1_path", "P2_path"),
                "T2": ("P1_path", "P2_path", "downstream_demand"),
                "P2_path": ("T1", "T2"),
            },
            safety_requirements=SafetyRequirements(),
            service_requirements=ServiceRequirements(
                minimum_flow=p.min_service_flow,
                deadline=p.service_deadline,
            ),
            recovery_timing=RecoveryTiming(
                p.control_period,
                p.backup_startup_delay,
                p.isolation_delay,
                p.transfer_recovery_deadline,
                p.horizon,
            ),
            recovery_cost_parameters=cost_parameters or RecoveryCostParameters(),
            takeover_assurance=TakeoverAssuranceParameters(),
            plant_model_id="synthetic-two-tank-v1",
            recovery_policy_id="trusted-backup-takeover-v1",
        )

    def validate(self) -> None:
        self.plant.validate()
        self.takeover_assurance.validate()
        if not self.plant_model_id or not self.recovery_policy_id:
            raise ContextValidationError("plant and recovery-policy identities must be explicit")
        known_components = {
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
        referenced = set(self.compromised_components) | set(self.trusted_actuators)
        if unknown := referenced - known_components:
            raise ContextValidationError(f"unknown component references: {sorted(unknown)}")
        if self.physical_components != frozenset(known_components):
            raise ContextValidationError("this fixed topology requires every modeled physical component to be explicitly recorded")
        if not isinstance(self.control_path_authority, RecoveryControlPathAuthority):
            raise ContextValidationError("control_path_authority must separately record operational, trust, and recovery control facts")
        control_paths = frozenset({"primary_isolator", "P2_command", "upstream_gate", "demand_gate"})
        self.control_path_authority.validate(control_paths)
        if self.compromised_components != frozenset({"P1_command_path"}):
            raise ContextValidationError("this template requires exactly the P1 command path compromise")
        valid_actions = {AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON}
        if not self.attacker_capabilities or not self.attacker_capabilities <= valid_actions:
            raise ContextValidationError("attacker capabilities must be modeled P1 command actions")
        if not isinstance(self.resource_availability, RecoveryResourceAvailability):
            raise ContextValidationError(
                "resource_availability must explicitly bind every trusted recovery resource"
            )
        self.resource_availability.validate(self.trusted_actuators)
        availability_to_control = {
            "trusted_isolation_available": "primary_isolator",
            "trusted_backup_available": "P2_command",
            "trusted_inflow_control_available": "upstream_gate",
            "trusted_demand_control_available": "demand_gate",
        }
        for availability_name, control in availability_to_control.items():
            if getattr(self.resource_availability, availability_name):
                if control not in self.control_path_authority.operational:
                    raise ContextValidationError(f"{availability_name} requires an explicitly operational {control} path")
                if control not in self.control_path_authority.trusted:
                    raise ContextValidationError(f"{availability_name} requires an explicitly trusted {control} path")
                if control not in self.control_path_authority.controllable_by_recovery:
                    raise ContextValidationError(f"{availability_name} requires {control} to be controllable by recovery")
        if self.available_recovery_resources.get("primary_isolation") not in {True, False}:
            raise ContextValidationError("physical primary-isolation existence must be explicitly recorded")
        if (
            self.resource_availability.trusted_isolation_available
            and self.available_recovery_resources.get("primary_isolation") is not True
        ):
            raise ContextValidationError("trusted isolation cannot be available when its physical component is unavailable")
        if self.available_recovery_resources.get("backup_capacity") != self.plant.backup_capacity:
            raise ContextValidationError("backup resource capacity must match the plant configuration")
        if not {"T1", "T2", "P2_path"} <= set(self.process_dependencies):
            raise ContextValidationError("process dependencies do not describe the parallel backup path")
        if self.safety_requirements.variables != ("x1", "x2"):
            raise ContextValidationError("this experiment's safety requirement is defined over x1 and x2")
        if self.service_requirements.delivered_flow_variable != "q_delivered":
            raise ContextValidationError("service must reference modeled q_delivered")
        if self.service_requirements.minimum_flow != self.plant.min_service_flow:
            raise ContextValidationError("service minimum must match the configured plant")
        if self.service_requirements.deadline != self.plant.service_deadline:
            raise ContextValidationError("service deadline must match the configured plant")
        if self.recovery_timing != RecoveryTiming(
            self.plant.control_period,
            self.plant.backup_startup_delay,
            self.plant.isolation_delay,
            self.plant.transfer_recovery_deadline,
            self.plant.horizon,
        ):
            raise ContextValidationError("recovery timing must match the configured plant")
        if not TwoTankPlant(self.plant, self.current_state).within_model_domain():
            raise ContextValidationError("current state is outside configured safety bounds")
        if self.recovery_timing.backup_startup_delay < 0 or self.recovery_timing.isolation_delay < 0:
            raise ContextValidationError("recovery delays must be nonnegative")

    def as_dict(self) -> dict[str, object]:
        return {
            "current_state": asdict(self.current_state),
            "plant": self.plant.as_dict(),
            "compromised_components": sorted(self.compromised_components),
            "attacker_capabilities": sorted(action.value for action in self.attacker_capabilities),
            "trusted_observations": sorted(self.trusted_observations),
            "trusted_actuators": sorted(self.trusted_actuators),
            "physical_components": sorted(self.physical_components),
            "control_path_authority": {
                "operational": sorted(self.control_path_authority.operational),
                "trusted": sorted(self.control_path_authority.trusted),
                "controllable_by_recovery": sorted(self.control_path_authority.controllable_by_recovery),
            },
            "available_recovery_resources": dict(self.available_recovery_resources),
            "resource_availability": asdict(self.resource_availability),
            "process_dependencies": {key: list(value) for key, value in self.process_dependencies.items()},
            "safety_requirements": asdict(self.safety_requirements),
            "service_requirements": asdict(self.service_requirements),
            "recovery_timing": asdict(self.recovery_timing),
            "recovery_cost_parameters": asdict(self.recovery_cost_parameters),
            "takeover_assurance": asdict(self.takeover_assurance),
            "plant_model_id": self.plant_model_id,
            "recovery_policy_id": self.recovery_policy_id,
        }
