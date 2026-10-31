"""Unit and integration tests for Muse Spark 1.3 Structure Compiler (P05.S04).

Enforces ADR-0011 Invariant: Muse Spark compiles task topology and step sequences ONLY.
Metric parameters MUST have value = -1.0 (symbolic placeholder).
LLM is strictly prohibited from guessing physical numbers.
Asserts zero uninstalled imports of torchaudio and openai.
Per ARCHITECTURE.md §6.1-§6.3, ADR-0011, and P05.S04.
"""

from __future__ import annotations

import json
import sys

import httpx
import pytest

from Kodiac_robotics.compiler.asr import VoiceTurn
from Kodiac_robotics.compiler.spark_compile import (
    compile_speech_to_skeleton,
    enforce_symbolic_placeholders,
    load_compile_prompt,
    validate_symbolic_invariants,
)
from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)


def test_zero_uninstalled_imports():
    """Assert zero top-level imports of torchaudio or openai."""
    assert "torchaudio" not in sys.modules, "torchaudio must not be imported at top level"
    assert "openai" not in sys.modules, "openai must not be imported at top level"


def test_load_compile_prompt():
    """Verify prompt template compile_v1.md contains ADR-0011 rules."""
    prompt = load_compile_prompt()
    assert "ADR-0011" in prompt
    assert "-1.0" in prompt
    assert "STRICTLY FORBIDDEN" in prompt or "placeholder" in prompt


def test_validate_symbolic_invariants_valid():
    """Verify validate_symbolic_invariants passes when all parameters are -1.0."""
    prov = Provenance(source="voice")
    test = GreenTest(
        name="test_clean",
        objects=[ObjectDecl(name="gripper", role="effector"), ObjectDecl(name="cubeA", role="rigid")],
        steps=[
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="lifted",
                        args=["cubeA"],
                        params=[Param(name="min_cm", op=">=", value=-1.0)],
                    ),
                ),
                provenance=prov,
            ),
            Step(
                index=2,
                name="place",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="on",
                        args=["cubeA", "cubeB"],
                        params=[
                            Param(name="align_xy_cm", op="<=", value=-1.0),
                            Param(name="gap_cm", op="<=", value=-1.0),
                        ],
                    ),
                ),
                provenance=prov,
            ),
        ],
    )
    # Must not raise
    validate_symbolic_invariants(test)


def test_validate_symbolic_invariants_rejects_hallucinated_floats():
    """Verify validate_symbolic_invariants raises ValueError on hallucinated floats per ADR-0011."""
    prov = Provenance(source="voice")
    test = GreenTest(
        name="test_hallucinated",
        objects=[ObjectDecl(name="gripper", role="effector"), ObjectDecl(name="cubeA", role="rigid")],
        steps=[
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="lifted",
                        args=["cubeA"],
                        # Hallucinated 2.5cm instead of -1.0!
                        params=[Param(name="min_cm", op=">=", value=2.5)],
                    ),
                ),
                provenance=prov,
            )
        ],
    )
    with pytest.raises(ValueError, match="ADR-0011 Invariant Violation"):
        validate_symbolic_invariants(test)


def test_enforce_symbolic_placeholders():
    """Verify enforce_symbolic_placeholders resets non-placeholder values to -1.0."""
    prov = Provenance(source="voice")
    test = GreenTest(
        name="test_sanitize",
        objects=[ObjectDecl(name="gripper", role="effector"), ObjectDecl(name="cubeA", role="rigid")],
        steps=[
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="lifted",
                        args=["cubeA"],
                        params=[Param(name="min_cm", op=">=", value=4.5)],
                    ),
                ),
                provenance=prov,
            )
        ],
    )
    sanitized = enforce_symbolic_placeholders(test)
    assert sanitized.steps[0].expr.atom.params[0].value == -1.0
    validate_symbolic_invariants(sanitized)


def test_compile_speech_to_skeleton_fixture_mode():
    """Verify compile_speech_to_skeleton in fixture mode emits symbolic AST with all value = -1.0."""
    turns = [
        VoiceTurn(transcript="pick up cubeA and lift it", t_start=0.5, t_end=2.5, source="voice"),
        VoiceTurn(transcript="place cubeA on cubeB", t_start=3.0, t_end=5.5, source="voice"),
        VoiceTurn(transcript="release gripper and dwell", t_start=6.0, t_end=8.0, source="voice"),
    ]
    test = compile_speech_to_skeleton(turns, object_hints=["cubeA", "cubeB"], backend="fixture")

    assert len(test.steps) == 3
    assert test.steps[0].name == "grasp"
    assert test.steps[1].name == "place"
    assert test.steps[2].name == "release"

    # Strict check: all parameters must be -1.0
    for step in test.steps:
        if step.expr.atom and step.expr.atom.params:
            for p in step.expr.atom.params:
                assert p.value == -1.0, f"Step '{step.name}' param '{p.name}' is {p.value}, not -1.0"
        for child in step.expr.children:
            if child.atom and child.atom.params:
                for p in child.atom.params:
                    assert p.value == -1.0, f"Child atom param '{p.name}' is {p.value}, not -1.0"

    # Check objects
    obj_names = {o.name: o.role for o in test.objects}
    assert "gripper" in obj_names and obj_names["gripper"] == "effector"
    assert "cubeA" in obj_names
    assert "cubeB" in obj_names


def test_compile_speech_to_skeleton_api_missing_key(monkeypatch):
    """Verify compile_speech_to_skeleton raises ValueError if MODEL_API_KEY is missing."""
    monkeypatch.delenv("KODIAC_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    turns = [VoiceTurn(transcript="pick up block", t_start=0.0, t_end=1.0, source="voice")]
    with pytest.raises(ValueError, match="MODEL_API_KEY is not set"):
        compile_speech_to_skeleton(turns, backend="api")


def test_compile_speech_to_skeleton_api_mocked(monkeypatch):
    """Verify compile_speech_to_skeleton handles valid API JSON response adhering to ADR-0011."""
    monkeypatch.setenv("MODEL_API_KEY", "mock_key")
    monkeypatch.setenv("KODIAC_MODEL_API_KEY", "mock_key")

    mock_llm_payload = {
        "name": "test_stack",
        "objects": [
            {"name": "gripper", "role": "effector"},
            {"name": "red_box", "role": "rigid"},
            {"name": "blue_box", "role": "rigid"},
        ],
        "steps": [
            {
                "index": 1,
                "name": "grasp",
                "expr": {
                    "op": "atom",
                    "atom": {
                        "kind": "pred",
                        "name": "lifted",
                        "args": ["red_box"],
                        "params": [{"name": "min_cm", "op": ">=", "value": -1.0}],
                    },
                },
                "provenance": {
                    "quote": "lift the red box",
                    "t_start": 0.5,
                    "t_end": 2.0,
                    "source": "voice",
                },
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": json.dumps(mock_llm_payload)}}
                ]
            }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, headers=None, json=None):
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    turns = [VoiceTurn(transcript="lift the red box", t_start=0.5, t_end=2.0, source="voice")]
    test = compile_speech_to_skeleton(turns, backend="api")

    assert test.name == "test_stack"
    assert len(test.steps) == 1
    assert test.steps[0].expr.atom.params[0].value == -1.0


def test_compile_speech_to_skeleton_api_rejects_hallucinated_numbers(monkeypatch):
    """Verify compiler aborts with ADR-0011 error if the LLM hallucinates physical numbers."""
    monkeypatch.setenv("MODEL_API_KEY", "mock_key")

    mock_llm_payload = {
        "name": "test_hallucination",
        "objects": [{"name": "gripper", "role": "effector"}, {"name": "cube", "role": "rigid"}],
        "steps": [
            {
                "index": 1,
                "name": "place",
                "expr": {
                    "op": "atom",
                    "atom": {
                        "kind": "pred",
                        "name": "on",
                        "args": ["cube", "table"],
                        "params": [
                            # LLM hallucinated 0.8 cm instead of -1.0!
                            {"name": "align_xy_cm", "op": "<=", "value": 0.8}
                        ],
                    },
                },
                "provenance": {"quote": "place cube", "t_start": 0.0, "t_end": 1.0, "source": "voice"},
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": json.dumps(mock_llm_payload)}}
                ]
            }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, headers=None, json=None):
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    turns = [VoiceTurn(transcript="place cube on table", t_start=0.0, t_end=1.0, source="voice")]
    with pytest.raises(ValueError, match="ADR-0011 Invariant Violation"):
        compile_speech_to_skeleton(turns, backend="api")
