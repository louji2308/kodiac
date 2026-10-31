"""Parser and loader for .green test specifications and GreenTest models.

Supports direct GreenTest instances, JSON schemas, and native .green DSL files.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)


def _parse_time_str(ts: str) -> float:
    """Parse timestamp string (e.g. '0:01.2' or '1.5') to seconds float."""
    ts = ts.strip()
    if ":" in ts:
        parts = ts.split(":")
        return float(parts[0]) * 60.0 + float(parts[1])
    return float(ts)


def _parse_atom(atom_str: str) -> Atom:
    """Parse a single atom string like 'on(cubeA, cubeB, align_xy_cm<=3.33, gap_cm<=0.5)'."""
    atom_str = atom_str.strip()
    m = re.match(r"^([a-zA-Z0-9_-]+)\s*\((.*?)\)$", atom_str)
    if not m:
        # Check looks or manual atom formats
        if atom_str.startswith("looks(") and atom_str.endswith(")"):
            inner = atom_str[6:-1].strip()
            return Atom(kind="looks", looks_pos=inner)
        if atom_str.startswith("MANUAL(") and atom_str.endswith(")"):
            inner = atom_str[7:-1].strip().strip("'\"")
            return Atom(kind="manual", manual_text=inner)
        raise ValueError(f"Cannot parse predicate atom: {atom_str}")

    pred_name = m.group(1)
    inner_args = m.group(2).strip()

    args: list[str] = []
    params: list[Param] = []

    if inner_args:
        # Split args by comma respecting no nested parentheses
        parts = [p.strip() for p in inner_args.split(",") if p.strip()]
        for part in parts:
            pm = re.match(r"^([a-zA-Z0-9_]+)\s*(<=|>=|=)\s*([+-]?[0-9]*\.?[0-9]+)$", part)
            if pm:
                p_name = pm.group(1)
                p_op = pm.group(2)
                p_val = float(pm.group(3))
                params.append(Param(name=p_name, op=p_op, value=p_val))
            else:
                args.append(part)

    return Atom(kind="pred", name=pred_name, args=args, params=params)


def _parse_expr_string(expr_str: str) -> Expr:
    """Parse a boolean expression string over atoms with 'and', 'or', 'not'."""
    expr_str = expr_str.strip()

    # Handle outer parentheses
    if expr_str.startswith("(") and expr_str.endswith(")"):
        # Check if parentheses are matching
        depth = 0
        matches_outer = True
        for i, ch in enumerate(expr_str):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(expr_str) - 1:
                    matches_outer = False
                    break
        if matches_outer:
            return _parse_expr_string(expr_str[1:-1].strip())

    # Split on top-level ' or '
    tokens = _split_top_level(expr_str, " or ")
    if len(tokens) > 1:
        return Expr(op="or", children=[_parse_expr_string(t) for t in tokens])

    # Split on top-level ' and '
    tokens = _split_top_level(expr_str, " and ")
    if len(tokens) > 1:
        return Expr(op="and", children=[_parse_expr_string(t) for t in tokens])

    # Handle 'not '
    if expr_str.startswith("not ") or expr_str.startswith("not("):
        inner = expr_str[4:].strip()
        return Expr(op="not", children=[_parse_expr_string(inner)])

    # Leaf atom
    return Expr(op="atom", atom=_parse_atom(expr_str))


def _split_top_level(text: str, delimiter: str) -> list[str]:
    """Split text by delimiter only when not enclosed within parentheses."""
    parts: list[str] = []
    depth = 0
    start = 0
    delim_len = len(delimiter)
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and text[i : i + delim_len] == delimiter:
            parts.append(text[start:i].strip())
            start = i + delim_len
            i += delim_len
            continue
        i += 1
    parts.append(text[start:].strip())
    return parts if len(parts) > 1 else [text]


def parse_green_text(text: str, default_name: str = "specification") -> GreenTest:
    """Parse the text of a .green file into a GreenTest model."""
    text_stripped = text.strip()
    if text_stripped.startswith("{"):
        return GreenTest.model_validate_json(text_stripped)

    objects: list[ObjectDecl] = []
    steps: list[Step] = []
    header_comment: list[str] = []
    name = default_name

    lines = text.splitlines()
    for line in lines:
        raw = line.strip()
        if not raw:
            continue

        if raw.startswith("#"):
            if not objects and not steps:
                header_comment.append(raw)
                # Check if header contains name (e.g. '# stackcube.green — ...')
                name_m = re.match(r"^#\s*([a-zA-Z0-9_-]+)(?:\.green)?", raw)
                if name_m and default_name == "specification":
                    name = name_m.group(1)
            continue

        # Parse objects line: 'objects: [gripper, cubeA(size_cm=4), cubeB(size_cm=4)]'
        if raw.startswith("objects:"):
            obj_content = raw[len("objects:") :].strip()
            if "#" in obj_content:
                obj_content = obj_content.split("#", 1)[0].strip()
            if obj_content.startswith("[") and obj_content.endswith("]"):
                obj_content = obj_content[1:-1].strip()

            items = [item.strip() for item in obj_content.split(",") if item.strip()]
            for item in items:
                m = re.match(r"^([a-zA-Z0-9_-]+)(?:\((.*?)\))?$", item)
                if not m:
                    continue
                obj_name = m.group(1)
                kwargs_str = m.group(2)
                size_cm: float | None = None
                height_cm: float | None = None
                role = "effector" if obj_name == "gripper" else "rigid"
                prompt: str | None = None
                aliases: list[str] = []

                if kwargs_str:
                    for part in kwargs_str.split(";"):
                        # Sub-split by comma if not inside quotes
                        for sub in part.split(","):
                            if "=" in sub:
                                k, v = sub.split("=", 1)
                                k, v = k.strip(), v.strip().strip("'\"")
                                if k == "size_cm":
                                    size_cm = float(v)
                                elif k == "height_cm":
                                    height_cm = float(v)
                                elif k == "role":
                                    role = v  # type: ignore[assignment]
                                elif k == "prompt":
                                    prompt = v
                                elif k == "aliases":
                                    aliases = [a.strip() for a in v.split("|")]

                objects.append(
                    ObjectDecl(
                        name=obj_name,
                        role=role,
                        prompt=prompt,
                        aliases=aliases,
                        size_cm=size_cm,
                        height_cm=height_cm,
                    )
                )
            continue

        # Parse step line: '1. grasp:   moves_with(gripper, cubeA) and lifted(cubeA, min_cm=2.0) # "quote" [0:01-0:04]'
        step_match = re.match(r"^(\d+)\.\s*([a-zA-Z0-9_-]+)\s*:\s*(.+)$", raw)
        if step_match:
            step_idx = int(step_match.group(1)) - 1
            step_name = step_match.group(2)
            expr_and_comm = step_match.group(3)

            quote: str | None = None
            t_start: float | None = None
            t_end: float | None = None

            if "#" in expr_and_comm:
                expr_part, comm_part = expr_and_comm.split("#", 1)
                expr_str = expr_part.strip()
                comm_str = comm_part.strip()

                qm = re.search(r"\"(.*?)\"", comm_str)
                if qm:
                    quote = qm.group(1)
                tm = re.search(r"\[([0-9:.]+)[–-]([0-9:.]+)\]", comm_str)
                if tm:
                    t_start = _parse_time_str(tm.group(1))
                    t_end = _parse_time_str(tm.group(2))
            else:
                expr_str = expr_and_comm.strip()

            prov = Provenance(
                quote=quote,
                t_start=t_start,
                t_end=t_end,
                source="voice" if quote else "compiler-default",
            )
            expr = _parse_expr_string(expr_str)
            steps.append(
                Step(
                    index=step_idx,
                    name=step_name,
                    expr=expr,
                    provenance=prov,
                )
            )

    header = "\n".join(header_comment) if header_comment else None
    return GreenTest(
        version="0.1",
        name=name,
        objects=objects,
        steps=steps,
        header_comment=header,
    )


def load_green_test(test: GreenTest | Path | str) -> tuple[GreenTest, str]:
    """Load a GreenTest specification and return (test_instance, sha256_hash)."""
    if isinstance(test, GreenTest):
        raw_bytes = test.model_dump_json().encode("utf-8")
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        return test, sha256

    if isinstance(test, Path) or (isinstance(test, str) and (Path(test).is_file() or "\n" not in test)):
        p = Path(test).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Test specification file not found: {p}")
        raw_bytes = p.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        text = raw_bytes.decode("utf-8")
        parsed = parse_green_text(text, default_name=p.stem)
        return parsed, sha256

    # In-memory text representation
    raw_bytes = test.encode("utf-8")
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    parsed = parse_green_text(test)
    return parsed, sha256


__all__ = ["load_green_test", "parse_green_text"]
