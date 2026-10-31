"""Tests for .green language parser and AST builder."""

from __future__ import annotations

from pathlib import Path

import lark
import pytest

from Kodiac_robotics.compiler.parser import parse_green, validate_semantics
from Kodiac_robotics.contracts.core import GreenTest


def test_parse_stackcube_golden() -> None:
    """Tests parsing of ManiSkill Panda StackCube proof specification."""
    test = parse_green(Path("examples/stackcube.green"))
    assert isinstance(test, GreenTest)
    assert test.name == "stackcube"
    assert len(test.objects) == 3
    assert test.objects[0].name == "gripper"
    assert test.objects[0].role == "effector"
    assert test.objects[1].name == "cubeA"
    assert test.objects[1].size_cm == 4.0
    assert test.objects[2].name == "cubeB"
    assert test.objects[2].size_cm == 4.0

    assert len(test.steps) == 3
    assert test.steps[0].name == "grasp"
    assert test.steps[1].name == "place"
    assert test.steps[2].name == "release"

    # Step 1: moves_with(gripper, cubeA) and lifted(cubeA, min_cm=2.0)
    step1_expr = test.steps[0].expr
    assert step1_expr.op == "and"
    assert len(step1_expr.children) == 2
    atom1 = step1_expr.children[0].atom
    assert atom1 is not None and atom1.name == "moves_with"
    assert atom1.args == ["gripper", "cubeA"]

    atom2 = step1_expr.children[1].atom
    assert atom2 is not None and atom2.name == "lifted"
    assert atom2.args == ["cubeA"]
    assert len(atom2.params) == 1
    assert atom2.params[0].name == "min_cm"
    assert atom2.params[0].op == "="
    assert atom2.params[0].value == 2.0


def test_parse_stack_blocks_golden() -> None:
    """Tests parsing of webcam demonstration compiled specification with provenance."""
    test = parse_green(Path("examples/stack_blocks.green"))
    assert isinstance(test, GreenTest)
    assert test.name == "stack_blocks"
    assert len(test.objects) == 3
    assert test.objects[1].name == "red_block"
    assert test.objects[2].name == "green_block"

    assert len(test.steps) == 3
    # Step 1 provenance
    s1 = test.steps[0]
    assert s1.provenance.quote == "pick up the red block"
    assert s1.provenance.t_start == pytest.approx(1.2)
    assert s1.provenance.t_end == pytest.approx(4.0)
    assert s1.provenance.source == "voice"

    # Step 2 provenance
    s2 = test.steps[1]
    assert s2.provenance.quote == "put it on the green one"
    assert s2.provenance.t_start == pytest.approx(4.1)
    assert s2.provenance.t_end == pytest.approx(7.5)

    # Step 3 provenance and extra provenance
    s3 = test.steps[2]
    assert s3.provenance.quote == "let go"
    assert s3.provenance.t_start == pytest.approx(7.6)
    assert s3.provenance.t_end == pytest.approx(10.4)
    assert len(s3.extra_provenance) == 1
    assert s3.extra_provenance[0].quote == "(+dwell: compiler default)"


def test_parse_timestamp_variations() -> None:
    """Tests parsing timestamps with hyphen vs Unicode en-dash, minutes:seconds, and seconds."""
    text_endash = """# Timestamp Test
objects: [gripper, block]
1. pick: moves_with(gripper, block) # "pick" [0:01.5–0:04.2]
"""
    test1 = parse_green(text_endash)
    assert test1.steps[0].provenance.t_start == pytest.approx(1.5)
    assert test1.steps[0].provenance.t_end == pytest.approx(4.2)

    text_hyphen = """# Timestamp Test
objects: [gripper, block]
1. pick: moves_with(gripper, block) # "pick" [1.5-4.2]
"""
    test2 = parse_green(text_hyphen)
    assert test2.steps[0].provenance.t_start == pytest.approx(1.5)
    assert test2.steps[0].provenance.t_end == pytest.approx(4.2)


def test_parse_indented_steps_syntax() -> None:
    """Tests that indented step syntax with 'steps:' keyword parses verbatim."""
    indented = """# Indented Test
objects: [gripper, cube(size_cm=5)]
steps:
  1. grasp: moves_with(gripper, cube)
  2. release: not moves_with(gripper, cube)
"""
    test = parse_green(indented)
    assert len(test.steps) == 2
    assert test.steps[0].name == "grasp"
    assert test.steps[1].name == "release"


def test_parse_blank_lines_and_comments() -> None:
    """Tests parsing with interspersed blank lines and comments."""
    text = """# Header line 1
# Header line 2

objects: [gripper, target]

# Pre-steps comment
steps:
  1. s1: moves_with(gripper, target)

  # Mid-step comment
  2. s2: not moves_with(gripper, target)
"""
    test = parse_green(text)
    assert len(test.steps) == 2
    assert test.header_comment is not None
    assert "Header line 1" in test.header_comment
    assert "Header line 2" in test.header_comment


def test_parse_object_attributes() -> None:
    """Tests parsing all supported object declaration attributes."""
    text = """# Obj Attrs
objects: [
  gripper(role=effector),
  mug(role=container, prompt="ceramic white mug", alias=["cup", "coffee cup"], height_cm=10.5),
  table(role=surface, size_cm=100)
]
1. s: dwell(gripper)
"""
    test = parse_green(text)
    assert len(test.objects) == 3
    mug = test.objects[1]
    assert mug.name == "mug"
    assert mug.role == "container"
    assert mug.prompt == "ceramic white mug"
    assert mug.aliases == ["cup", "coffee cup"]
    assert mug.height_cm == pytest.approx(10.5)


def test_parse_looks_and_manual_atoms() -> None:
    """Tests parsing of looks() and MANUAL() atoms."""
    text = """# Visual & Manual Checks
objects: [gripper, drawer, peg]
1. check_drawer: looks(drawer, "closed" | "ajar")
2. check_force:  MANUAL("ensure contact force < 5N")
"""
    test = parse_green(text)
    assert len(test.steps) == 2

    # Step 1: looks
    atom1 = test.steps[0].expr.atom
    assert atom1 is not None and atom1.kind == "looks"
    assert atom1.args == ["drawer"]
    assert atom1.looks_pos == "closed"
    assert atom1.looks_neg == "ajar"

    # Step 2: manual
    atom2 = test.steps[1].expr.atom
    assert atom2 is not None and atom2.kind == "manual"
    assert atom2.manual_text == "ensure contact force < 5N"


def test_parse_boolean_precedence() -> None:
    """Tests boolean operator precedence (not binds tighter than and, and tighter than or)."""
    text = """# Precedence
objects: [gripper, a, b]
1. test: not moves_with(gripper, a) and on(a, b) or dwell(b)
"""
    test = parse_green(text)
    expr = test.steps[0].expr
    assert expr.op == "or"
    assert len(expr.children) == 2
    left = expr.children[0]
    assert left.op == "and"
    assert len(left.children) == 2
    assert left.children[0].op == "not"


def test_parse_syntax_error() -> None:
    """Tests that malformed .green syntax raises lark.exceptions.LarkError."""
    bad_text = """# Syntax Error
objects: [gripper, a
1. s: moves_with(gripper, a)
"""
    with pytest.raises(lark.exceptions.LarkError):
        parse_green(bad_text)


def test_validate_semantics_clean() -> None:
    """Tests that golden specifications produce zero semantic error diagnostics."""
    test = parse_green(Path("examples/stackcube.green"))
    diags = validate_semantics(test)
    errors = [d for d in diags if d.severity == "error"]
    assert len(errors) == 0
