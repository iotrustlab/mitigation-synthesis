"""Measure transition and proof reuse across five checked recovery procedures."""

import ast
from collections import Counter
import re
from pathlib import Path

from .. import verify
from ..attleboro import attleboro
from ..evaluation import MUTATIONS
from ..formal_model import build_model
from . import cost, hand, merwin
from .proofs import proved


PACKAGE = Path(__file__).resolve().parents[1]
CORE = ("procedure.py", "formal_ir.py", "dependency_semantics.py")
FAMILY_SOURCES = {
    "Attleboro": ("attleboro.py", "formal_model.py", "milestone2/hand.py"),
    "controlled water": ("milestone2/cost.py",),
    "Merwin": ("domain_cases.py", "milestone2/merwin.py", "milestone2/merwin_reduction.py"),
}
SHARED_OPERATIONS = (
    "RecoveryProcedure binds an identified candidate to its typed dependencies and provenance.",
    "dependency_semantics.transition substitutes nominal, finite disturbed, empty or union relations.",
    "Assignment and Stage encode finite guarded updates; executions enumerates exact rational endpoint states.",
    "hybrid_program emits the same assignment relations as fresh slots and a joint dL test.",
    "Stage-prefix boxes and the composed box reuse the finite substitution/arithmetic proof pattern. A separate diamond checks progress.",
    "verify._solve replays the generated dL through KeYmaera X, binds the archive to named proof objects and records obligation timings.",
)


def _count(filename, names=()):
    """Physical nonblank non-comment source lines; model strings and docstrings count."""
    source = (PACKAGE / filename).read_text()
    lines = source.splitlines()
    if names:
        blocks = [item for item in ast.parse(source).body if getattr(item, "name", None) in names]
        if {b.name for b in blocks} != set(names):
            raise ValueError(f"Unknown measured function in {filename}")
        lines = [line for b in blocks for line in lines[b.lineno - 1:b.end_lineno]]
    return sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in lines)


def _relations(stages):
    return {s.name: {a.name: a.relation() for a in s.assignments} for s in stages}


def _mutation_delta(before, after):
    lhs, rhs = _relations(before), _relations(after)
    return {s: [k for k in a if a[k] != rhs[s].get(k)] for s, a in lhs.items() if a != rhs[s]}


def _pair(label, left, right):
    a, b = _relations(left), _relations(right)
    same_boundary = [s for s in a if s in b]
    return {
        "pair": label, "identical_stage_names": same_boundary, "identical_stage_name_count": len(same_boundary),
        "identical_full_stage_relations": [s for s in same_boundary if list(a[s].items()) == list(b[s].items())],
        "matching_assignment_relations_at_same_named_stage": {
            s: sum(b[s].get(k) == v for k, v in a[s].items()) for s in same_boundary
        },
    }


def _row(pid, model_hash, stages, profile, valid, family, guards, plant, invariants, contracts,
         specificity, mutation, changed_stages, remote_entries=None):
    if remote_entries is not None:
        tactics = [re.search(r'Tactic "[^"]+"\s+(.*?)\s+End\.', entry, re.S)[1].strip()
                   for entry in remote_entries.values()]
        obligations = list(remote_entries)
    else:
        tactics = [o.tactic for o in profile.obligations]
        obligations = [o.name for o in profile.obligations]
    return {
        "procedure": pid, "formal_model_sha256": model_hash, "formal_result_bound": valid,
        "source_family": family, "ir": "formal_ir.Assignment and Stage",
        "renderer": "formal_ir.hybrid_program", "dependencies": "dependency_semantics.transition",
        "prover": "verify._solve", "proof_archive_adapter": "formal_model.FormalModel" if remote_entries else "milestone2.proofs.Profile",
        "stages": [s.name for s in stages], "assignments": sum(len(s.assignments) for s in stages),
        "generic_stage_contract_reuse": contracts, "case_specific_guards": guards,
        "plant_definition": plant, "case_specific_invariant_or_bound": invariants,
        "case_specific_tactics": specificity, "tactic_counts_in_nominal_archive": dict(Counter(tactics)),
        "nominal_obligations": obligations, "mutation_probe": mutation,
        "changed_transition_slots_in_probe": changed_stages,
    }


def report():
    remote = build_model(attleboro()["remote"])
    m5 = MUTATIONS[5]
    changed_remote = build_model(attleboro(m5.dependencies, m5.states)["remote"])
    local = build_model(hand.CASES[0].snapshot()["hand"])
    changed_local = build_model(hand.CASES[4].snapshot()["hand"])
    hand_profile = hand.profiles()[0]
    mer_proc, _, hydro_stages = merwin.model(0)
    hydro_profile = merwin.profile(0)
    _, _, changed_hydro = merwin.model(10)
    a, b = cost.plans(cost.SCENARIOS["C0"])
    water_bounds = "Three mandatory scans at 100 ms, two-tick run delay, snapped sampled flow, pressure and protection bounds."
    water_contracts = "Both command modes invoke FormalModel.entries with identical STAGE_PROPERTIES and composed POST."
    rows = [
        _row(remote.procedure.procedure_id, remote.sha256, remote.stages, None, verify.verified(remote),
             "Attleboro", "Powered PLC, utility selector, reset latch, Remote mode, trip and Start edge.",
             water_bounds, "0 to 10 L/s, pressure in bounds, service at 5 L/s by tick 3.",
             water_contracts, "Finite-stage tactic plus separate retained-Start proof.",
             "M5 output delivery compromised", _mutation_delta(remote.stages, changed_remote.stages), remote.entries()),
        _row(hand.HAND_PROFILE, hand_profile.sha256, local.stages, hand_profile, proved(hand_profile),
             "Attleboro", "Local actor arrival, Hand panel/selector, shared motor power and trip.",
             water_bounds, "0 to 10 L/s, pressure in bounds, service at 5 L/s by tick 3.",
             water_contracts, "Original finite-stage tactics imported directly from the generated Hand archive.",
             "H4 shared VFD unavailable", _mutation_delta(local.stages, changed_local.stages)),
        _row(mer_proc.procedure_id, hydro_profile.sha256, hydro_stages, hydro_profile,
             proved(hydro_profile) and merwin.checked_reduction(), "Merwin",
             "Remote mode, HCC link, normal auxiliaries, synchronization window, permissive relay and contact.",
             "Trace-conditioned fixed-point gate slew, flow, torque, off-grid speed and contact-dependent electric generation.",
             "Gate and speed bounds on every reconstructed scan; three same-row running, contact and >=1 MW samples.",
             "Five stage boundary roles match the Attleboro names. Hydro-specific prefix predicates are emitted by the shared dL renderer.",
             "Generic finite-stage dL tactic; separate Z3 ground-integer recurrence and bound check.",
             "MER10 unresolved breaker integrity", _mutation_delta(hydro_stages, changed_hydro)),
    ]
    for path in (a, b):
        auto = path.procedure.procedure_id == cost.A_ID
        prof = cost.proof_profile(path)
        changed = cost.plans(cost.SCENARIOS["C1" if auto else "C2"])[0 if auto else 1]
        rows.append(_row(
            path.procedure.procedure_id, prof.sha256, path.stages, prof, proved(prof),
            "controlled water", "Automatic actor, network and controller B." if auto else "Local actor and direct panel C.",
            "Two analytic constant-rate tank phases with exact in-model cost accumulation.",
            "Continuous volume between bounded endpoints; minimum sustained flow from the same deadline through the horizon.",
            "Both candidates share controller and plant prefix predicates, a hard service/evidence formula, and the same cost theorem template.",
            "Generic finite-stage dL tactic plus solve and QE for the frozen-rate ODE.",
            "C1 controller B compromised" if auto else "C2 local actor unavailable",
            _mutation_delta(path.stages, changed.stages),
        ))
    # Compare common stage names literally; no semantic equivalence by variable renaming is inferred.
    comparisons = [_pair("Remote / Hand", remote.stages, local.stages),
                   _pair("Remote / HCC Remote Auto", remote.stages, hydro_stages),
                   _pair("automatic P2 / local P3", a.stages, b.stages)]
    return {
        "rows": rows, "actual_unchanged_operations": SHARED_OPERATIONS, "stage_comparisons": comparisons,
        "stage_comparison_method": "Exact serialized assignment relations by variable name within matching named stages. Identical relation templates can have different case inputs.",
        "mutation_change": {
            "policy": "Replace the affected status or input and regenerate the stage relation/model. Recheck hash bindings for each changed proof.",
            "goal": "A changed transition changes the instantiated theorem formula. The original safety/service predicate is retained. A negative query switches from a universal guarantee to a violation diamond or an empty-branch box.",
            "tactics_and_bounds": "The listed one-dependency mutations use the same case bounds and finite-stage tactic; the cost ODE and hydro arithmetic reduction remain case-specific.",
            "unchanged_projection": "A cost candidate can reuse its exact proof when only the other path changes and its projected model is byte-identical.",
        },
        "loc": {
            "unit": "Nonblank physical lines excluding comment-only lines. Docstrings and embedded model text count. File counts include validation and reporting. Shared files are counted once per inventory.",
            "generic_core": {f: _count(f) for f in CORE},
            "shared_milestone2_proof_adapter": {"milestone2/proofs.py": _count("milestone2/proofs.py")},
            "original_proof_runner_selected_functions": {"verify.py#_solve,_version,_digest": _count("verify.py", ("_solve","_version","_digest"))},
            "case_sources": {family: {f: _count(f) for f in sources} for family, sources in FAMILY_SOURCES.items()},
            "scope": "domain_cases.py also houses CHP schemas; only its Merwin-specific function count is isolated below. The Attleboro model includes the original water archive assembly. LOC is a source footprint, not saved effort.",
            "merwin_schema_builder_only": _count("domain_cases.py", ("merwin_procedures",)),
        },
    }
