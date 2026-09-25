"""Scripted attacker and defender policies for reproducible, not synthesized, runs."""

from __future__ import annotations

from dataclasses import dataclass

from .model import AttackerAction, DefenderAction, PlantState


@dataclass(frozen=True)
class PersistentPrimaryAttacker:
    """Keeps attacking the compromised P1 command surface for its full interval."""

    action: AttackerAction = AttackerAction.FORCE_PRIMARY_OFF
    active_until: float = float("inf")

    def select(self, state: PlantState) -> AttackerAction:
        return self.action if state.time < self.active_until else AttackerAction.NOOP


@dataclass(frozen=True)
class NoRecoveryPolicy:
    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.NORMAL


@dataclass(frozen=True)
class ConservativeRecoveryPolicy:
    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.CONSERVATIVE_HOLD


@dataclass(frozen=True)
class TrustedControlledSafeHoldPolicy:
    """Immediately isolate P1 and close trusted inflow and demand controls."""

    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.START_CONTROLLED_SAFE_HOLD


@dataclass(frozen=True)
class TrustedBackupTakeoverPolicy:
    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.START_TAKEOVER


@dataclass(frozen=True)
class TrustedFlowingBackupTakeoverPolicy:
    """Keeps source inflow and downstream withdrawal active during P2 startup."""

    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.START_FLOWING_TAKEOVER


@dataclass(frozen=True)
class TrustedDelayedIsolationFlowingBackupTakeoverPolicy:
    """Starts isolation and P2 together while P1 remains effective until the delay expires."""

    def select(self, state: PlantState) -> DefenderAction:
        return DefenderAction.START_DELAYED_ISOLATION_FLOWING_TAKEOVER


@dataclass(frozen=True)
class ScheduledPrimaryAttacker:
    """One explicit P1 command per simulator control cycle.

    The schedule is intentionally finite and deterministic. Once exhausted, its
    final action remains active, matching a persistent attacker rather than an
    implicit attack reset.
    """

    actions: tuple[AttackerAction, ...]

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("scheduled attacker requires at least one P1 action")
        if any(action not in {AttackerAction.FORCE_PRIMARY_OFF, AttackerAction.FORCE_PRIMARY_ON} for action in self.actions):
            raise ValueError("scheduled attacker supports only explicit P1 on/off actions")

    def select(self, state: PlantState) -> AttackerAction:
        return self.actions[min(state.control_cycle, len(self.actions) - 1)]
