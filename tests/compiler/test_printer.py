"""Tests for canonical .green printer and round-trip identity."""

from __future__ import annotations

from pathlib import Path

from Kodiac_robotics.compiler.parser import parse_green
from Kodiac_robotics.compiler.printer import print_green
from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)


def test_printer_golden_stackcube_identity() -> None:
    """Asserts 100% bit-identical round-trip identity on examples/stackcube.green."""
    raw = Path("examples/stackcube.green").read_text(encoding="utf-8")
    test = parse_green(raw)
    printed = print_green(test)
    assert printed == raw


def test_printer_golden_stack_blocks_identity() -> None:
    """Asserts 100% bit-identical round-trip identity on examples/stack_blocks.green."""
    raw = Path("examples/stack_blocks.green").read_text(encoding="utf-8")
    test = parse_green(raw)
    printed = print_green(test)
    assert printed == raw


def test_printer_ast_idempotency() -> None:
    """Asserts that parse(print(parse(text))) produces an identical AST."""
    raw = Path("examples/stackcube.green").read_text(encoding="utf-8")
    t1 = parse_green(raw)
    printed = print_green(t1)
    t2 = parse_green(printed)
    assert t1 == t2


def test_printer_column_alignment() -> None:
    """Asserts column 12 step prefix alignment and column 91 provenance alignment."""
    raw = Path("examples/stack_blocks.green").read_text(encoding="utf-8")
    test = parse_green(raw)
    printed = print_green(test)
    lines = printed.splitlines()

    # Step lines
    for line in lines[2:]:
        # Step expression starts at character index 12
        assert line[12] not in (" ", "")
        # Provenance '#' is at index 91 (or after space if long)
        hash_idx = line.find("#")
        assert hash_idx in (91, 92)


def test_printer_custom_ast_serialization() -> None:
    """Tests printing an artificially constructed GreenTest AST."""
    test = GreenTest(
        name="custom_test",
        header_comment="# custom_test.green — Synthetic Test",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(
                name="box",
                role="container",
                prompt="cardboard box",
                aliases=["carton"],
                size_cm=15.0,
            ),
        ],
        steps=[
            Step(
                index=0,
                name="insert",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="inside",
                        args=["gripper", "box"],
                        params=[Param(name="rim_margin_cm", op=">=", value=1.0)],
                    ),
                ),
                provenance=Provenance(
                    quote="put into box",
                    t_start=0.5,
                    t_end=2.0,
                    source="voice",
                ),
            ),
        ],
    )
    printed = print_green(test)
    assert "# custom_test.green — Synthetic Test" in printed
    assert "objects: [gripper, box(role=container, prompt=\"cardboard box\", alias=[\"carton\"], size_cm=15)]" in printed
    assert "1. insert:  inside(gripper, box, rim_margin_cm>=1.0)" in printed
    assert '# "put into box" [0:00.5\u20130:02.0]' in printed

    # Verify that parse_green recovers the exact AST
    recovered = parse_green(printed)
    assert recovered == test
