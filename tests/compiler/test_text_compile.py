"""Unit and integration tests for Text Compile Mode & Deterministic Template Fallback.

Validates bit-identical reproduction of examples/stackcube.green, verb gating (ADR-0012),
Law 1 anti-fabrication badging, symbolic parameter invariants (ADR-0011), and zero uninstalled imports.
Per ARCHITECTURE.md §5.1, §6.1-§6.3, ADR-0011, ADR-0012, and P05.S08.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from Kodiac_robotics.compiler.printer import print_green
from Kodiac_robotics.compiler.template_fallback import template_compile
from Kodiac_robotics.compiler.text_compile import text_compile


def test_zero_uninstalled_imports():
    """Assert zero top-level imports of torchaudio or openai."""
    assert "torchaudio" not in sys.modules, "torchaudio must not be imported at top level"
    assert "openai" not in sys.modules, "openai must not be imported at top level"


def test_text_compile_stackcube_bit_identical():
    """Verify text_compile with profile='stackcube' bit-identically matches examples/stackcube.green."""
    golden_path = Path("examples/stackcube.green")
    assert golden_path.is_file(), "examples/stackcube.green must exist"
    golden_text = golden_path.read_text(encoding="utf-8").strip()

    test = text_compile("stack cubeA on cubeB", profile="stackcube")
    printed_text = print_green(test).strip()

    assert printed_text == golden_text, (
        f"Bit-identical mismatch on stackcube.green:\n"
        f"--- Printed ---\n{printed_text}\n"
        f"--- Expected ---\n{golden_text}"
    )

    # Validate AST structure
    assert test.name == "stackcube"
    assert len(test.objects) == 3
    assert test.objects[0].name == "gripper" and test.objects[0].role == "effector"
    assert test.objects[1].name == "cubeA" and test.objects[1].size_cm == 4.0
    assert test.objects[2].name == "cubeB" and test.objects[2].size_cm == 4.0

    assert len(test.steps) == 3
    assert test.steps[0].name == "grasp"
    assert test.steps[1].name == "place"
    assert test.steps[2].name == "release"


def test_text_compile_stack_blocks_bit_identical():
    """Verify text_compile with profile='stack_blocks' bit-identically matches examples/stack_blocks.green."""
    golden_path = Path("examples/stack_blocks.green")
    assert golden_path.is_file(), "examples/stack_blocks.green must exist"
    golden_text = golden_path.read_text(encoding="utf-8").strip()

    test = text_compile("stack red on green", profile="stack_blocks")
    printed_text = print_green(test).strip()

    assert printed_text == golden_text, (
        f"Bit-identical mismatch on stack_blocks.green:\n"
        f"--- Printed ---\n{printed_text}\n"
        f"--- Expected ---\n{golden_text}"
    )


def test_template_compile_verb_gating_success():
    """Verify template_compile succeeds on valid robotics manipulation verbs."""
    for verb_phrase in [
        "pick up the red_block and lift it",
        "place cubeA on cubeB",
        "stack block1 on block2",
        "insert peg into hole",
        "let go of target",
        "release gripper",
        "dwell on surface",
    ]:
        test = template_compile(verb_phrase)
        assert len(test.steps) >= 1
        assert test.objects[0].name == "gripper"


def test_template_compile_verb_gating_rejection():
    """Verify template_compile strictly rejects non-manipulation actions with E003 (ADR-0012)."""
    unsupported_actions = [
        "fly the drone to the moon",
        "bake a chocolate cake",
        "dance in circles",
        "navigate to the kitchen",
        "sing a song",
    ]
    for action in unsupported_actions:
        with pytest.raises(ValueError, match="E003"):
            template_compile(action)


def test_template_compile_missing_objects_rejection():
    """Verify template_compile raises E001 when no objects can be detected."""
    with pytest.raises(ValueError, match="E001"):
        template_compile("pick up and place on")


def test_template_compile_badging_and_symbolic_placeholders(capsys):
    """Verify Law 1 badging and ADR-0011 symbolic placeholder values in template_compile."""
    test = template_compile("stack cubeA on cubeB", symbolic=True)

    # Law 1 badging: header comment
    assert test.header_comment is not None
    assert "[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]" in test.header_comment

    # Law 1 badging: provenance source
    for step in test.steps:
        assert step.provenance.source == "compiler-default"

    # ADR-0011: all numeric parameter values must be -1.0
    for step in test.steps:
        if step.expr.atom and step.expr.atom.params:
            for p in step.expr.atom.params:
                assert p.value == -1.0
        for child in step.expr.children:
            if child.atom and child.atom.params:
                for p in child.atom.params:
                    assert p.value == -1.0

    # Stderr amber warning notice
    captured = capsys.readouterr()
    assert "[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]" in captured.err


def test_template_compile_normative_defaults():
    """Verify template_compile with symbolic=False populates normative defaults from §6.2."""
    test = template_compile("stack cubeA on cubeB", symbolic=False)

    # Check step 1 (grasp/lift)
    step1 = test.steps[0]
    lift_param = step1.expr.children[1].atom.params[0]
    assert lift_param.name == "min_cm"
    assert lift_param.value == 2.0

    # Check step 2 (place)
    step2 = test.steps[1]
    align_param = step2.expr.atom.params[0]
    assert align_param.name == "align_xy_cm"
    assert align_param.value == 1.5

    # Check step 3 (release/dwell)
    step3 = test.steps[2]
    dwell_param = step3.expr.children[1].atom.params[0]
    assert dwell_param.name == "for_s"
    assert dwell_param.value == 0.5


def test_text_compile_custom_task():
    """Verify text_compile compiles arbitrary supported manipulation text into valid AST."""
    test = text_compile("pick up red_block and place on green_block")
    assert len(test.steps) == 3
    assert test.objects[0].name == "gripper"
    assert any(o.name == "red_block" for o in test.objects)
    assert any(o.name == "green_block" for o in test.objects)
