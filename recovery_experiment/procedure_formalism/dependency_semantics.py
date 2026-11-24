"""Compile operational dependency status into guarded transition alternatives."""

from .formal_ir import Assignment
from .procedure import DependencyStatus


def transition(node, nominal, alphabet=("0", "1")):
    adverse = tuple((None, value) for value in alphabet)
    if node.status is DependencyStatus.TRUSTED:
        return nominal
    if node.status is DependencyStatus.UNAVAILABLE:
        return Assignment(nominal.name, ())
    if node.status is DependencyStatus.COMPROMISED:
        return Assignment(nominal.name, adverse)
    return Assignment(nominal.name, nominal.alternatives + adverse)
