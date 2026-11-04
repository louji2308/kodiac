"""Deterministic Rule-Based Template Fallback Compiler for Kodiac.

Provides instant offline AST recovery for standard robotic manipulation primitives
(pick, lift, place, stack, insert, let go, release, dwell).
Gated on recognized verbs; unrecognized verbs raise ValueError with diagnostic E003.
Applies mandatory Law 1 anti-fabrication badging across AST headers and provenance.
Per ARCHITECTURE.md §6.1-§6.3, ADR-0012, and P05.S08.
"""

from __future__ import annotations

import re
import sys

from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)

RECOGNIZED_VERBS: tuple[str, ...] = (
    "pick",
    "lift",
    "place",
    "stack",
    "insert",
    "let go",
    "release",
    "dwell",
    "put",
    "grasp",
    "drop",
)


def _check_verb_gating(text: str) -> str:
    """Validate that text contains at least one recognized manipulation primitive.

    Raises ValueError with E003 if no recognized verb is found.
    """
    text_lower = text.lower()
    for verb in RECOGNIZED_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", text_lower):
            return verb
    raise ValueError(
        f"E003: unsupported manipulation action in input '{text}'. "
        f"Template compiler is strictly gated on recognized verbs: {', '.join(RECOGNIZED_VERBS)}."
    )


def _extract_objects(
    text: str,
    explicit_objects: list[str] | None = None,
    primary_verb: str | None = None,
) -> list[str]:
    """Extract object identifiers from explicit list or text."""
    if explicit_objects:
        objs = [o for o in explicit_objects if o.lower() != "gripper"]
        if objs:
            return objs

    # Remove recognized verbs and prepositions to isolate nouns
    cleaned = text
    for w in [
        "pick",
        "up",
        "and",
        "then",
        "place",
        "stack",
        "insert",
        "into",
        "onto",
        "on",
        "in",
        "the",
        "a",
        "an",
        "it",
        "lift",
        "release",
        "dwell",
        "gripper",
        "let",
        "go",
        "of",
    ]:
        cleaned = re.sub(rf"\b{w}\b", " ", cleaned, flags=re.IGNORECASE)

    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]*\b", cleaned)
    seen: list[str] = []
    for t in tokens:
        if t not in seen and len(t) > 1 and t.lower() != "gripper":
            seen.append(t)

    if not seen:
        # Check for standard patterns like cubeA, cubeB or red_block, green_block
        matches = re.findall(
            r"\b([a-zA-Z0-9_]+(?:cube|block|box|cup|plate|can|drawer|object|peg|hole|surface|target)[a-zA-Z0-9_]*)\b",
            text,
            re.IGNORECASE,
        )
        for m in matches:
            if m not in seen and m.lower() != "gripper":
                seen.append(m)

    if not seen:
        if primary_verb in ("release", "let go", "drop", "dwell"):
            return ["object"]
        raise ValueError(
            f"E001: object not found in task description '{text}'. "
            "Please specify objects explicitly or include object names in text."
        )

    return seen


def template_compile(
    text: str,
    objects: list[str] | None = None,
    symbolic: bool = True,
) -> GreenTest:
    """Deterministic rule-based fallback compiler for robotic primitives.

    Args:
        text: Task description string.
        objects: Optional explicit object names.
        symbolic: If True, emits placeholder value = -1.0 for all numeric parameters (ADR-0011).
                  If False, emits normative defaults from ARCHITECTURE.md §6.2.

    Returns:
        GreenTest AST with mandatory Law 1 anti-fabrication badging.

    Raises:
        ValueError: with E003 if action is unsupported, or E001 if objects are missing.
    """
    # 1. Verb Gating Check (ADR-0012)
    primary_verb = _check_verb_gating(text)

    # 2. Extract Objects
    objs = _extract_objects(text, objects, primary_verb=primary_verb)
    obj_a = objs[0]
    obj_b = objs[1] if len(objs) > 1 else None

    # Print amber notice to stderr per ADR-0012
    sys.stderr.write("⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]\n")

    # 3. Build Objects Declarations
    is_container = bool(re.search(r"\b(into|in|inside|container|box|cup|bin|drawer)\b", text, re.IGNORECASE))
    target_role = "container" if is_container and obj_b else "rigid"

    object_decls = [
        ObjectDecl(name="gripper", role="effector"),
        ObjectDecl(name=obj_a, role="rigid"),
    ]
    if obj_b:
        object_decls.append(ObjectDecl(name=obj_b, role=target_role))

    # Parameter values (symbolic = -1.0 vs defaults)
    lift_val = -1.0 if symbolic else 2.0
    align_val = -1.0 if symbolic else 1.5
    dwell_val = -1.0 if symbolic else 0.5
    rim_val = -1.0 if symbolic else 0.5

    steps: list[Step] = []
    text_lower = text.lower()

    if primary_verb in ("stack", "place", "put") or (obj_b and "on" in text_lower):
        target = obj_b or "cubeB"
        # Step 1: grasp
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
                                params=[Param(name="min_cm", op=">=", value=lift_val)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
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
                        args=[obj_a, target],
                        params=[
                            Param(name="align_xy_cm", op="<=", value=align_val),
                        ],
                    ),
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
        # Step 3: release & dwell (generated for stack/place operations or explicit release commands)
        if primary_verb in ("stack", "place", "put") or "place on" in text_lower or "put on" in text_lower or any(w in text_lower for w in ("release", "drop", "let go", "unclamp")):
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
                                    args=[obj_a, target],
                                    params=[Param(name="for_s", op=">=", value=dwell_val)],
                                ),
                            ),
                        ],
                    ),
                    provenance=Provenance(
                        quote=text,
                        t_start=0.0,
                        t_end=0.0,
                        source="compiler-default",
                    ),
                )
            )
    elif primary_verb == "insert" or (obj_b and ("into" in text_lower or "in" in text_lower)):
        target = obj_b or "container"
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
                                params=[Param(name="min_cm", op=">=", value=lift_val)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
        steps.append(
            Step(
                index=2,
                name="insert",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="inside",
                        args=[obj_a, target],
                        params=[Param(name="rim_margin_cm", op=">=", value=rim_val)],
                    ),
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
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
                                args=[obj_a, target],
                                params=[Param(name="for_s", op=">=", value=dwell_val)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
    elif primary_verb in ("pick", "lift", "grasp"):
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
                                params=[Param(name="min_cm", op=">=", value=lift_val)],
                            ),
                        ),
                    ],
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
    elif primary_verb in ("release", "let go", "drop"):
        steps.append(
            Step(
                index=1,
                name="release",
                expr=Expr(
                    op="not",
                    children=[
                        Expr(
                            op="atom",
                            atom=Atom(kind="pred", name="moves_with", args=["gripper", obj_a]),
                        )
                    ],
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )
    elif primary_verb == "dwell":
        args = [obj_a]
        if obj_b:
            args.append(obj_b)
        steps.append(
            Step(
                index=1,
                name="dwell",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="dwell",
                        args=args,
                        params=[Param(name="for_s", op=">=", value=dwell_val)],
                    ),
                ),
                provenance=Provenance(
                    quote=text,
                    t_start=0.0,
                    t_end=0.0,
                    source="compiler-default",
                ),
            )
        )

    test_name = f"test_{obj_a}" + (f"_{obj_b}" if obj_b else "")
    return GreenTest(
        name=test_name,
        objects=object_decls,
        steps=steps,
        header_comment=f"# {test_name}.green — [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]",
    )
