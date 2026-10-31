"""Muse Spark 1.3 Structure Compiler for Kodiac.

Compiles spoken VoiceTurn windows and object hints into a symbolic GreenTest AST.
STRICT INVARIANT (ADR-0011): Compiles task topology, object roles, and step sequencing ONLY.
Physical parameter floats are strictly emitted as placeholder value = -1.0.
Zero top-level imports of torchaudio or openai.
Per ARCHITECTURE.md §6.1-§6.3, ADR-0011, and P05.S04.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

import httpx

from Kodiac_robotics.compiler.asr import VoiceTurn
from Kodiac_robotics.config import Settings
from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)


def load_compile_prompt() -> str:
    """Load the master Spark compiler prompt template."""
    prompt_path = Path(__file__).parent / "prompts" / "compile_v1.md"
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "You are the Kodiac Test Structure Compiler. Compile voice turns into symbolic "
        "GreenTest AST with placeholder value = -1.0 for all numeric parameters."
    )


def validate_symbolic_invariants(test: GreenTest) -> None:
    """Enforce ADR-0011: Assert all numeric parameters have placeholder value == -1.0.

    Any hardcoded float from an LLM fails the build per ADR-0011 tripwire.
    """

    def _check_expr(expr: Expr) -> None:
        if expr.atom and expr.atom.params:
            for p in expr.atom.params:
                if p.value != -1.0:
                    raise ValueError(
                        f"ADR-0011 Invariant Violation: Parameter '{p.name}' has non-symbolic "
                        f"value {p.value}. All compiler Stage 1 parameters must be placeholder value = -1.0."
                    )
        for child in expr.children:
            _check_expr(child)

    for p in test.params:
        if p.value != -1.0:
            raise ValueError(
                f"ADR-0011 Invariant Violation: Global parameter '{p.name}' has non-symbolic "
                f"value {p.value}. Must be -1.0."
            )

    for step in test.steps:
        _check_expr(step.expr)


def enforce_symbolic_placeholders(test: GreenTest) -> GreenTest:
    """Sanitize any numeric parameters in AST to placeholder value = -1.0."""

    def _sanitize_expr(expr: Expr) -> Expr:
        if expr.atom and expr.atom.params:
            expr.atom.params = [
                Param(name=p.name, op=p.op, value=-1.0) for p in expr.atom.params
            ]
        for child in expr.children:
            _sanitize_expr(child)
        return expr

    sanitized_params = [Param(name=p.name, op=p.op, value=-1.0) for p in test.params]
    for step in test.steps:
        _sanitize_expr(step.expr)

    test.params = sanitized_params
    return test


def _extract_objects_from_text(turns: list[VoiceTurn], hints: list[str] | None = None) -> list[str]:
    """Extract candidate object names from hints and turns text."""
    objs: list[str] = []
    if hints:
        for h in hints:
            if h not in objs and h.lower() != "gripper":
                objs.append(h)

    for turn in turns:
        matches = re.findall(r"\b([a-zA-Z0-9_]+(?:cube|block|box|cup|plate|can|drawer|object)[a-zA-Z0-9_]*)\b", turn.transcript, re.IGNORECASE)
        for m in matches:
            if m not in objs and m.lower() != "gripper":
                objs.append(m)

        # Also detect cubeA, cubeB patterns
        named_matches = re.findall(r"\b(cube[A-Z]|block[A-Z]|target|container)\b", turn.transcript, re.IGNORECASE)
        for m in named_matches:
            if m not in objs and m.lower() != "gripper":
                objs.append(m)

    if not objs:
        objs = ["cubeA", "cubeB"]
    return objs


def _prov_source(turn_source: str) -> Literal["voice", "text", "compiler-default", "user-edit"]:
    if turn_source in ("voice", "fixture"):
        return "voice"
    if turn_source == "text":
        return "text"
    if turn_source == "user-edit":
        return "user-edit"
    return "compiler-default"


def _build_fixture_skeleton(
    turns: list[VoiceTurn],
    object_hints: list[str] | None = None,
) -> GreenTest:
    """Deterministic Stage 1 skeleton compiler for fixture mode."""
    objs = _extract_objects_from_text(turns, object_hints)
    obj_a = objs[0] if len(objs) > 0 else "cubeA"
    obj_b = objs[1] if len(objs) > 1 else "cubeB"

    object_decls = [
        ObjectDecl(name="gripper", role="effector"),
        ObjectDecl(name=obj_a, role="rigid"),
        ObjectDecl(name=obj_b, role="rigid"),
    ]

    # Map turns into steps with ADR-0011 symbolic placeholders (value = -1.0)
    steps: list[Step] = []

    if len(turns) >= 3:
        # Step 1: grasp / lift
        steps.append(
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="and",
                    children=[
                        Expr(
                            op="atom",
                            atom=Atom(kind="pred", name="moves_with", args=["gripper", obj_a]),
                        ),
                        Expr(
                            op="atom",
                            atom=Atom(
                                kind="pred",
                                name="lifted",
                                args=[obj_a],
                                params=[Param(name="min_cm", op=">=", value=-1.0)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=turns[0].transcript,
                    t_start=turns[0].t_start,
                    t_end=turns[0].t_end,
                    source=_prov_source(turns[0].source),
                ),
            )
        )
        # Step 2: place / on
        steps.append(
            Step(
                index=2,
                name="place",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="on",
                        args=[obj_a, obj_b],
                        params=[
                            Param(name="align_xy_cm", op="<=", value=-1.0),
                            Param(name="gap_cm", op="<=", value=-1.0),
                        ],
                    ),
                ),
                provenance=Provenance(
                    quote=turns[1].transcript,
                    t_start=turns[1].t_start,
                    t_end=turns[1].t_end,
                    source=_prov_source(turns[1].source),
                ),
            )
        )
        # Step 3: release / dwell
        steps.append(
            Step(
                index=3,
                name="release",
                expr=Expr(
                    op="and",
                    children=[
                        Expr(
                            op="not",
                            children=[
                                Expr(
                                    op="atom",
                                    atom=Atom(
                                        kind="pred",
                                        name="moves_with",
                                        args=["gripper", obj_a],
                                    ),
                                )
                            ],
                        ),
                        Expr(
                            op="atom",
                            atom=Atom(
                                kind="pred",
                                name="dwell",
                                args=[obj_a, obj_b],
                                params=[Param(name="for_s", op=">=", value=-1.0)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=turns[2].transcript,
                    t_start=turns[2].t_start,
                    t_end=turns[2].t_end,
                    source=_prov_source(turns[2].source),
                ),
            )
        )
    elif len(turns) == 2:
        steps.append(
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="atom",
                    atom=Atom(kind="pred", name="moves_with", args=["gripper", obj_a]),
                ),
                provenance=Provenance(
                    quote=turns[0].transcript,
                    t_start=turns[0].t_start,
                    t_end=turns[0].t_end,
                    source=_prov_source(turns[0].source),
                ),
            )
        )
        steps.append(
            Step(
                index=2,
                name="place",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="on",
                        args=[obj_a, obj_b],
                        params=[Param(name="align_xy_cm", op="<=", value=-1.0)],
                    ),
                ),
                provenance=Provenance(
                    quote=turns[1].transcript,
                    t_start=turns[1].t_start,
                    t_end=turns[1].t_end,
                    source=_prov_source(turns[1].source),
                ),
            )
        )
    elif len(turns) == 1:
        steps.append(
            Step(
                index=1,
                name="manipulate",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="on",
                        args=[obj_a, obj_b],
                        params=[Param(name="align_xy_cm", op="<=", value=-1.0)],
                    ),
                ),
                provenance=Provenance(
                    quote=turns[0].transcript,
                    t_start=turns[0].t_start,
                    t_end=turns[0].t_end,
                    source=_prov_source(turns[0].source),
                ),
            )
        )
    else:
        # Default fallback step
        steps.append(
            Step(
                index=1,
                name="action",
                expr=Expr(
                    op="atom",
                    atom=Atom(kind="pred", name="moves_with", args=["gripper", obj_a]),
                ),
                provenance=Provenance(
                    quote="manipulate object",
                    t_start=0.0,
                    t_end=1.0,
                    source="compiler-default",
                ),
            )
        )

    test = GreenTest(
        name=f"test_{obj_a}_{obj_b}",
        objects=object_decls,
        steps=steps,
        header_comment="# compiled by Muse Spark 1.3 (symbolic skeleton, ADR-0011)",
    )
    validate_symbolic_invariants(test)
    return test


def compile_speech_to_skeleton(
    turns: list[VoiceTurn],
    object_hints: list[str] | None = None,
    backend: Literal["api", "fixture"] = "fixture",
) -> GreenTest:
    """Prompts Muse Spark to compile VoiceTurns into symbolic GreenTest AST.

    STRICT INVARIANT: Physical parameter floats are emitted as placeholder value = -1.0.
    Prompt template stored in compiler/prompts/compile_v1.md.
    """
    if backend == "fixture":
        return _build_fixture_skeleton(turns, object_hints)

    if backend == "api":
        settings = Settings.load()
        api_key = (
            settings.model_api_key
            or os.environ.get("MODEL_API_KEY")
            or os.environ.get("KODIAC_MODEL_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "MODEL_API_KEY is not set. Set KODIAC_MODEL_API_KEY or MODEL_API_KEY, "
                "or switch to backend='fixture'."
            )

        system_prompt = load_compile_prompt()
        user_content = json.dumps(
            {
                "turns": [turn.model_dump() for turn in turns],
                "object_hints": object_hints or [],
            },
            indent=2,
        )

        url = f"{settings.judge_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.judge_model or "muse-spark-1.3",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            res_json = resp.json()

        content = res_json["choices"][0]["message"]["content"]
        ast_dict = json.loads(content)

        # Validate and construct GreenTest
        test = GreenTest.model_validate(ast_dict)

        # Enforce ADR-0011: all numeric parameter values must be -1.0
        validate_symbolic_invariants(test)
        return test

    raise ValueError(f"Unknown compiler backend '{backend}'. Must be 'api' or 'fixture'.")
