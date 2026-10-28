"""Unit tests for Kleene 3-valued logic engine."""

from __future__ import annotations

from Kodiac_robotics.contracts.core import Atom, Expr, Tri
from Kodiac_robotics.engine.logic import (
    evaluate_conjunction,
    evaluate_expr_tree,
    kleene_and,
    kleene_not,
    kleene_or,
)
from Kodiac_robotics.predicates.base import get_atom_key


def test_kleene_not():
    """Verify Kleene NOT truth table."""
    assert kleene_not(Tri.T) == Tri.F
    assert kleene_not(Tri.F) == Tri.T
    assert kleene_not(Tri.U) == Tri.U


def test_kleene_and():
    """Verify Kleene AND truth table with False domination."""
    # T and X
    assert kleene_and(Tri.T, Tri.T) == Tri.T
    assert kleene_and(Tri.T, Tri.F) == Tri.F
    assert kleene_and(Tri.T, Tri.U) == Tri.U

    # F and X (False dominates)
    assert kleene_and(Tri.F, Tri.T) == Tri.F
    assert kleene_and(Tri.F, Tri.F) == Tri.F
    assert kleene_and(Tri.F, Tri.U) == Tri.F

    # U and X
    assert kleene_and(Tri.U, Tri.T) == Tri.U
    assert kleene_and(Tri.U, Tri.F) == Tri.F
    assert kleene_and(Tri.U, Tri.U) == Tri.U


def test_kleene_or():
    """Verify Kleene OR truth table with True domination."""
    # T or X (True dominates)
    assert kleene_or(Tri.T, Tri.T) == Tri.T
    assert kleene_or(Tri.T, Tri.F) == Tri.T
    assert kleene_or(Tri.T, Tri.U) == Tri.T

    # F or X
    assert kleene_or(Tri.F, Tri.T) == Tri.T
    assert kleene_or(Tri.F, Tri.F) == Tri.F
    assert kleene_or(Tri.F, Tri.U) == Tri.U

    # U or X
    assert kleene_or(Tri.U, Tri.T) == Tri.T
    assert kleene_or(Tri.U, Tri.F) == Tri.U
    assert kleene_or(Tri.U, Tri.U) == Tri.U


def test_evaluate_conjunction():
    """Verify evaluation of conjunction of possibly negated Tri literals."""
    # Empty conjunction is vacuously True
    assert evaluate_conjunction([]) == Tri.T

    # (is_positive, val)
    # T and (not F) -> T and T -> T
    assert evaluate_conjunction([(True, Tri.T), (False, Tri.F)]) == Tri.T

    # T and F -> F
    assert evaluate_conjunction([(True, Tri.T), (True, Tri.F)]) == Tri.F

    # T and U -> U
    assert evaluate_conjunction([(True, Tri.T), (True, Tri.U)]) == Tri.U

    # F and U -> F (False dominates)
    assert evaluate_conjunction([(True, Tri.F), (True, Tri.U)]) == Tri.F

    # (not U) and T -> U and T -> U
    assert evaluate_conjunction([(False, Tri.U), (True, Tri.T)]) == Tri.U


def test_evaluate_expr_tree():
    """Verify recursive evaluation of boolean AST expression trees."""
    atom_a = Atom(kind="pred", name="moves_with", args=["gripper", "red_block"])
    atom_b = Atom(kind="pred", name="lifted", args=["red_block"])
    key_a = get_atom_key(atom_a)
    key_b = get_atom_key(atom_b)

    # Expr: atom_a and (not atom_b)
    expr = Expr(
        op="and",
        children=[
            Expr(op="atom", atom=atom_a),
            Expr(op="not", children=[Expr(op="atom", atom=atom_b)]),
        ],
    )

    # When a is T, b is F -> T and (not F) = T and T = T
    values_1 = {key_a: Tri.T, key_b: Tri.F}
    assert evaluate_expr_tree(expr, values_1) == Tri.T

    # When a is T, b is T -> T and (not T) = T and F = F
    values_2 = {key_a: Tri.T, key_b: Tri.T}
    assert evaluate_expr_tree(expr, values_2) == Tri.F

    # When a is U, b is F -> U and (not F) = U and T = U
    values_3 = {key_a: Tri.U, key_b: Tri.F}
    assert evaluate_expr_tree(expr, values_3) == Tri.U
