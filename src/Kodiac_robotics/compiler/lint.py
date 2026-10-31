"""Compile-time linter and diagnostic engine for .green specifications.

Enforces compile-time diagnostics per ARCHITECTURE.md §6.3, RULING.md (ADR-0012, ADR-0013):
- Errors:
  - E001: Object not found
  - E002: Ambiguous object
  - E003: Type error / invalid role / invalid predicate
  - E004: Comparator against parameter direction
  - E005: Demo fails own test / exceeds physical sanity cap
- Warnings:
  - W101: Non-visual tactile keyword -> MANUAL(...)
  - W102: Step without provenance
  - W103: Demo margin < 2σ
  - W104: Depth-critical check under Tier C
  - W105: 'or' disjunction used
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    RunResult,
    Verdict,
)

# Non-visual tactile keyword ontology (Rule W101)
TACTILE_KEYWORDS = {
    "gently",
    "firmly",
    "force",
    "torque",
    "weight",
    "slam",
    "temperature",
    "sound",
    "current",
}

# Physical sanity caps per ADR-0013
PHYSICAL_SANITY_CAPS: dict[str, float] = {
    "align_xy_cm": 4.0,
    "gap_cm": 2.0,
    "min_cm": 8.0,
    "max_speed_cm_s": 2.5,
}

# Normative predicate parameter directions per ARCHITECTURE.md §6.2
PREDICATE_PARAM_DIRECTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "on": {
        "align_xy_cm": ("<=", "="),
        "gap_cm": ("<=", "="),
        "depth_tol": ("<=", "="),
    },
    "inside": {
        "rim_margin_cm": (">=", "="),
        "depth_tol": ("<=", "="),
    },
    "near": {
        "max_cm": ("<=", "="),
    },
    "lifted": {
        "min_cm": (">=", "="),
    },
    "moves_with": {
        "slip_cm": ("<=", "="),
        "window_s": ("=",),
    },
    "dwell": {
        "for_s": (">=", "="),
        "max_speed_cm_s": ("<=", "="),
    },
}

# Normative predicate object arity per ARCHITECTURE.md §6.2
PREDICATE_ARITY: dict[str, tuple[int, int]] = {
    "on": (2, 2),
    "inside": (2, 2),
    "near": (2, 2),
    "lifted": (1, 1),
    "moves_with": (2, 2),
    "dwell": (1, 2),
}

# Valid roles per predicate argument position
# Role types: "effector" | "rigid" | "container" | "articulated" | "surface"
PREDICATE_ROLE_CONSTRAINTS: dict[str, list[set[str]]] = {
    "on": [
        {"rigid", "articulated"},
        {"rigid", "surface", "container", "articulated"},
    ],
    "inside": [
        {"rigid", "articulated"},
        {"container"},
    ],
    "near": [
        {"effector", "rigid", "container", "articulated", "surface"},
        {"effector", "rigid", "container", "articulated", "surface"},
    ],
    "lifted": [
        {"rigid", "articulated"},
    ],
    "moves_with": [
        {"effector", "rigid"},
        {"rigid", "articulated"},
    ],
    "dwell": [
        {"rigid", "articulated"},
        {"effector", "rigid", "container", "articulated", "surface"},
    ],
}


class Diagnostic(BaseModel):
    """Structured compile-time diagnostic message."""

    code: str  # E001-E005, W101-W105
    message: str
    severity: Literal["error", "warning"] = "error"
    step_index: int | None = None
    line: int | None = None
    col: int | None = None

    def __str__(self) -> str:
        loc = f"step {self.step_index + 1}: " if self.step_index is not None else ""
        return f"[{self.severity.upper()} {self.code}] {loc}{self.message}"


def _find_atoms(expr: Expr) -> list[Atom]:
    """Recursively collect all atoms in an Expr tree."""
    atoms: list[Atom] = []
    if expr.op == "atom" and expr.atom is not None:
        atoms.append(expr.atom)
    for child in expr.children:
        atoms.extend(_find_atoms(child))
    return atoms


def _has_or_op(expr: Expr) -> bool:
    """Check if Expr tree contains any 'or' operations."""
    if expr.op == "or":
        return True
    return any(_has_or_op(child) for child in expr.children)


def lint_green(
    test: GreenTest,
    context: dict[str, Any] | RunResult | None = None,
) -> list[Diagnostic]:
    """Validates GreenTest AST against normative diagnostic rules:

    - Errors:
      E001: object not found in objects list
      E002: ambiguous or duplicate object declarations
      E003: type error (invalid predicate, arity mismatch, role violation)
      E004: comparator contradicts parameter direction
      E005: demonstration fails its own test or exceeds physical sanity caps
    - Warnings:
      W101: non-visual tactile keyword -> recommend MANUAL(...)
      W102: step lacks provenance quote and timestamp grounding
      W103: demonstration margin < 2σ
      W104: depth-critical check evaluated under Tier C geometry
      W105: 'or' disjunction used in step expression
    """
    diagnostics: list[Diagnostic] = []

    # Unpack context
    demo_run: RunResult | None = None
    context_dict: dict[str, Any] = {}
    if isinstance(context, RunResult):
        demo_run = context
    elif isinstance(context, dict):
        context_dict = context
        run_obj = context.get("demo_run") or context.get("demo_result")
        if isinstance(run_obj, RunResult):
            demo_run = run_obj

    # --------------------------------------------------------------------------
    # 1. Object Declaration Checks (E002)
    # --------------------------------------------------------------------------
    declared_names: dict[str, ObjectDecl] = {}
    seen_prompts: dict[str, str] = {}

    for obj in test.objects:
        # Check duplicate names
        if obj.name in declared_names:
            diagnostics.append(
                Diagnostic(
                    code="E002",
                    message=f"Duplicate object name '{obj.name}' declared in objects",
                    severity="error",
                )
            )
        declared_names[obj.name] = obj

        # Check ambiguous prompts without distinguishing attributes
        if obj.prompt:
            prompt_key = obj.prompt.strip().lower()
            if prompt_key in seen_prompts:
                other_name = seen_prompts[prompt_key]
                other_obj = declared_names.get(other_name)
                # Check if distinguished by size_cm or role
                if (
                    other_obj
                    and obj.size_cm == other_obj.size_cm
                    and obj.role == other_obj.role
                ):
                    diagnostics.append(
                        Diagnostic(
                            code="E002",
                            message=(
                                f"Ambiguous objects '{obj.name}' and '{other_name}' "
                                f"share identical prompt '{obj.prompt}' without distinct attributes"
                            ),
                            severity="error",
                        )
                    )
            else:
                seen_prompts[prompt_key] = obj.name

    # Helper to check if an identifier is declared
    def is_declared(name: str) -> bool:
        if name in declared_names:
            return True
        for obj in test.objects:
            if name in obj.aliases:
                return True
        return False

    def get_role(name: str) -> str | None:
        if name in declared_names:
            return declared_names[name].role
        for obj in test.objects:
            if name in obj.aliases:
                return obj.role
        return None

    # --------------------------------------------------------------------------
    # 2. Step, Expression, & Atom Checks (E001, E003, E004, E005, W101, W102, W104, W105)
    # --------------------------------------------------------------------------
    geometry_tier = context_dict.get("geometry_tier")
    if demo_run:
        for badge in demo_run.badges:
            if "TIER C" in badge:
                geometry_tier = "C"

    tactile_pattern = re.compile(
        r"\b(" + "|".join(TACTILE_KEYWORDS) + r")\b", re.IGNORECASE
    )

    # Check header comment for tactile keywords
    if test.header_comment:
        m = tactile_pattern.search(test.header_comment)
        if m:
            diagnostics.append(
                Diagnostic(
                    code="W101",
                    message=(
                        f"Non-visual tactile keyword '{m.group(1)}' detected in header; "
                        f"recommend MANUAL(\"{m.group(1)} requirement\") instead of unmeasured oracle"
                    ),
                    severity="warning",
                )
            )

    for step in test.steps:
        # Check W102 (Step without provenance)
        if step.provenance.quote is None and step.provenance.t_start is None:
            diagnostics.append(
                Diagnostic(
                    code="W102",
                    message=(
                        f"Step {step.index + 1} ('{step.name}') lacks provenance quote and timestamp grounding"
                    ),
                    severity="warning",
                    step_index=step.index,
                )
            )

        # Check W101 (Non-visual tactile keywords in quote or extra provenance)
        quote_text = step.provenance.quote or ""
        extra_text = " ".join(ep.quote or "" for ep in step.extra_provenance)
        full_prov_text = f"{quote_text} {extra_text}".strip()
        if full_prov_text:
            m = tactile_pattern.search(full_prov_text)
            if m:
                diagnostics.append(
                    Diagnostic(
                        code="W101",
                        message=(
                            f"Non-visual tactile keyword '{m.group(1)}' detected in step {step.index + 1}; "
                            f"recommend MANUAL(\"{m.group(1)} requirement\") instead of unmeasured oracle"
                        ),
                        severity="warning",
                        step_index=step.index,
                    )
                )

        # Check W105 ('or' disjunction used)
        if _has_or_op(step.expr):
            diagnostics.append(
                Diagnostic(
                    code="W105",
                    message=(
                        f"Step {step.index + 1} ('{step.name}') contains non-canonical 'or' branching logic"
                    ),
                    severity="warning",
                    step_index=step.index,
                )
            )

        # Check atoms within the step
        atoms = _find_atoms(step.expr)
        for atom in atoms:
            if atom.kind == "looks":
                # Check object exists
                if atom.args:
                    obj_name = atom.args[0]
                    if not is_declared(obj_name):
                        diagnostics.append(
                            Diagnostic(
                                code="E001",
                                message=f"Object '{obj_name}' referenced in looks() is not declared",
                                severity="error",
                                step_index=step.index,
                            )
                        )
                continue

            if atom.kind == "manual":
                # Valid manual specification
                continue

            if atom.kind == "pred":
                pred_name = atom.name or ""

                # Check valid predicate name
                if pred_name not in PREDICATE_ARITY:
                    diagnostics.append(
                        Diagnostic(
                            code="E003",
                            message=f"Unsupported manipulation action/predicate '{pred_name}'",
                            severity="error",
                            step_index=step.index,
                        )
                    )
                    continue

                # Check object arity
                min_args, max_args = PREDICATE_ARITY[pred_name]
                if not (min_args <= len(atom.args) <= max_args):
                    diagnostics.append(
                        Diagnostic(
                            code="E003",
                            message=(
                                f"Predicate '{pred_name}' expects {min_args}"
                                f"{f' to {max_args}' if min_args != max_args else ''} "
                                f"object arguments, got {len(atom.args)}"
                            ),
                            severity="error",
                            step_index=step.index,
                        )
                    )

                # Check E001 (Object existence) & E003 (Role compatibility)
                role_constraints = PREDICATE_ROLE_CONSTRAINTS.get(pred_name, [])
                for arg_idx, arg_name in enumerate(atom.args):
                    if not is_declared(arg_name):
                        diagnostics.append(
                            Diagnostic(
                                code="E001",
                                message=(
                                    f"Object '{arg_name}' in predicate '{pred_name}' is not declared in objects"
                                ),
                                severity="error",
                                step_index=step.index,
                            )
                        )
                    else:
                        role = get_role(arg_name)
                        if arg_idx < len(role_constraints):
                            valid_roles = role_constraints[arg_idx]
                            if role and role not in valid_roles:
                                diagnostics.append(
                                    Diagnostic(
                                        code="E003",
                                        message=(
                                            f"Object '{arg_name}' with role '{role}' is invalid for "
                                            f"position {arg_idx + 1} of predicate '{pred_name}' "
                                            f"(expected one of: {sorted(valid_roles)})"
                                        ),
                                        severity="error",
                                        step_index=step.index,
                                    )
                                )

                # Check parameters: known names, directions (E004), and sanity caps (E005)
                valid_directions = PREDICATE_PARAM_DIRECTIONS.get(pred_name, {})
                for p in atom.params:
                    # Known parameter
                    if p.name not in valid_directions:
                        diagnostics.append(
                            Diagnostic(
                                code="E003",
                                message=f"Parameter '{p.name}' is invalid for predicate '{pred_name}'",
                                severity="error",
                                step_index=step.index,
                            )
                        )
                        continue

                    # Direction check (E004)
                    allowed_ops = valid_directions[p.name]
                    if p.op not in allowed_ops:
                        expected_op = allowed_ops[0]
                        diagnostics.append(
                            Diagnostic(
                                code="E004",
                                message=(
                                    f"Parameter '{p.name}' comparator '{p.op}' contradicts expected "
                                    f"direction '{expected_op}'"
                                ),
                                severity="error",
                                step_index=step.index,
                            )
                        )

                    # Physical sanity caps (E005)
                    if p.name in PHYSICAL_SANITY_CAPS:
                        cap = PHYSICAL_SANITY_CAPS[p.name]
                        if p.value > cap:
                            diagnostics.append(
                                Diagnostic(
                                    code="E005",
                                    message=(
                                        f"Parameter '{p.name}={p.value}' exceeds physical sanity cap "
                                        f"({cap}); demonstration is too sloppy to produce an oracle"
                                    ),
                                    severity="error",
                                    step_index=step.index,
                                )
                            )

                # Check W104 (Depth-critical under Tier C)
                if geometry_tier == "C":
                    is_depth_critical = False
                    if pred_name == "inside":
                        is_depth_critical = True
                    elif pred_name == "on":
                        if any(p.name == "depth_tol" for p in atom.params):
                            is_depth_critical = True
                    if is_depth_critical:
                        diagnostics.append(
                            Diagnostic(
                                code="W104",
                                message=(
                                    f"Depth-critical predicate '{pred_name}' evaluated under uncalibrated "
                                    f"Tier C geometry; depth measurements may fall to CAN'T TELL"
                                ),
                                severity="warning",
                                step_index=step.index,
                            )
                        )

    # --------------------------------------------------------------------------
    # 3. Demonstration Self-Test Run Evaluation (E005, W103)
    # --------------------------------------------------------------------------
    if demo_run:
        if demo_run.verdict == Verdict.FAIL:
            diagnostics.append(
                Diagnostic(
                    code="E005",
                    message="Demonstration fails its own test (verdict=FAIL)",
                    severity="error",
                )
            )
        elif demo_run.verdict == Verdict.CANT_TELL:
            reason_str = ", ".join(r.value for r in demo_run.reasons)
            diagnostics.append(
                Diagnostic(
                    code="E005",
                    message=f"Demonstration self-test inconclusive (verdict=CANT_TELL: {reason_str})",
                    severity="error",
                )
            )

        # Check W103 (Demo margin < 2σ)
        for s_res in demo_run.steps:
            for comp in s_res.decisive:
                if comp.sigma > 0 and comp.margin < 2.0 * comp.sigma:
                    diagnostics.append(
                        Diagnostic(
                            code="W103",
                            message=(
                                f"Demonstration margin for '{comp.name}' ({comp.margin:.2f}) "
                                f"is less than 2σ threshold ({2.0 * comp.sigma:.2f})"
                            ),
                            severity="warning",
                            step_index=s_res.index,
                        )
                    )

    return diagnostics
