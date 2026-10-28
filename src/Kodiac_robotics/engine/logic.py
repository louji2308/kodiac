"""Kleene 3-valued logic engine for boolean evaluation under uncertainty."""

from __future__ import annotations

from Kodiac_robotics.contracts.core import Expr, Tri
from Kodiac_robotics.predicates.base import get_atom_key


def kleene_not(val: Tri) -> Tri:
    """Kleene 3-valued NOT operation.

    not T -> F
    not F -> T
    not U -> U
    """
    if val == Tri.T:
        return Tri.F
    elif val == Tri.F:
        return Tri.T
    return Tri.U


def kleene_and(a: Tri, b: Tri) -> Tri:
    """Kleene 3-valued AND operation.

    T and T -> T
    F and X -> F, X and F -> F (False dominates)
    T and U -> U, U and T -> U
    U and U -> U
    """
    if a == Tri.F or b == Tri.F:
        return Tri.F
    if a == Tri.T and b == Tri.T:
        return Tri.T
    return Tri.U


def kleene_or(a: Tri, b: Tri) -> Tri:
    """Kleene 3-valued OR operation.

    T or X -> T, X or T -> T (True dominates)
    F or F -> F
    F or U -> U, U or F -> U
    U or U -> U
    """
    if a == Tri.T or b == Tri.T:
        return Tri.T
    if a == Tri.F and b == Tri.F:
        return Tri.F
    return Tri.U


def evaluate_conjunction(literals: list[tuple[bool, Tri]]) -> Tri:
    """Evaluates a conjunction of possibly negated Tri-state literals.

    Args:
        literals: List of tuples `(is_positive, val)`. If `is_positive` is False,
                  `val` is negated with `kleene_not(val)`.

    Returns:
        Evaluated Tri state for the conjunction. Empty list evaluates to Tri.T.
    """
    if not literals:
        return Tri.T

    acc = Tri.T
    for is_positive, val in literals:
        lit_val = val if is_positive else kleene_not(val)
        acc = kleene_and(acc, lit_val)
        if acc == Tri.F:
            return Tri.F  # Short-circuit on False

    return acc


def evaluate_expr_tree(expr: Expr, atom_values: dict[str, Tri]) -> Tri:
    """Recursively evaluates an AST Expr tree using Kleene 3-valued logic.

    Args:
        expr: AST Expr node (atom, not, and, or).
        atom_values: Mapping of atom key strings to Tri states.

    Returns:
        Evaluated Tri value for the expression tree.
    """
    if expr.op == "atom":
        if expr.atom is None:
            return Tri.U
        key = get_atom_key(expr.atom)
        return atom_values.get(key, Tri.U)

    if expr.op == "not":
        if not expr.children:
            return Tri.U
        return kleene_not(evaluate_expr_tree(expr.children[0], atom_values))

    if expr.op == "and":
        acc = Tri.T
        for child in expr.children:
            acc = kleene_and(acc, evaluate_expr_tree(child, atom_values))
            if acc == Tri.F:
                return Tri.F
        return acc

    if expr.op == "or":
        acc = Tri.F
        for child in expr.children:
            acc = kleene_or(acc, evaluate_expr_tree(child, atom_values))
            if acc == Tri.T:
                return Tri.T
        return acc

    return Tri.U
