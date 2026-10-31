"""Normative parser and AST builder for .green test specifications.

Parses .green text or files into GreenTest AST using Lark grammar with:
- LALR parsing with automatic Earley fallback
- Unicode en-dash normalization in timestamps
- Post-parse semantic visitor for arity, role, and parameter validation
- Full diagnostic generation (E001-E005, W101-W105)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import lark

from Kodiac_robotics.compiler.lint import Diagnostic, lint_green
from Kodiac_robotics.contracts.core import (
    Atom,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"
_GRAMMAR_TEXT = _GRAMMAR_PATH.read_text(encoding="utf-8")

# Caching parsers
_LALR_PARSER = lark.Lark(_GRAMMAR_TEXT, parser="lalr")
_EARLEY_PARSER = lark.Lark(_GRAMMAR_TEXT, parser="earley")


def _parse_time_str(s: str) -> float:
    """Parse 'M:SS.S' or 'S.S' into float seconds."""
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        return float(parts[0]) * 60.0 + float(parts[1])
    return float(s)


class GreenTransformer(lark.Transformer):
    """Transforms Lark parse tree into frozen GreenTest AST models."""

    def __init__(self, default_name: str = "specification") -> None:
        super().__init__()
        self._default_name = default_name

    def start(self, items: list[Any]) -> GreenTest:
        header_comments: str | None = items[0]
        objects: list[ObjectDecl] = []
        params: list[Param] = []
        steps: list[Step] = []

        for it in items[1:]:
            if isinstance(it, list) and it:
                if isinstance(it[0], ObjectDecl):
                    objects = it
                elif isinstance(it[0], Param):
                    params = it
            elif isinstance(it, Step):
                steps.append(it)

        # Derive test name from header or fallback
        name = self._default_name
        if header_comments:
            m = re.search(r"^#\s*([a-zA-Z0-9_-]+)(?:\.green)?", header_comments)
            if m:
                name = m.group(1)

        return GreenTest(
            version="0.1",
            name=name,
            objects=objects,
            steps=steps,
            params=params,
            header_comment=header_comments,
        )

    def header_comments(self, items: list[Any]) -> str | None:
        comments = [str(it).strip() for it in items if str(it).strip()]
        return "\n".join(comments) if comments else None

    def objects_line(self, items: list[Any]) -> list[ObjectDecl]:
        return [it for it in items if isinstance(it, ObjectDecl)]

    def object_decl(self, items: list[Any]) -> ObjectDecl:
        name = str(items[0])
        attrs: dict[str, Any] = {}
        for it in items[1:]:
            if isinstance(it, tuple):
                attrs[it[0]] = it[1]

        role = attrs.get("role")
        if role is None:
            role = "effector" if name == "gripper" else "rigid"

        return ObjectDecl(
            name=name,
            role=role,
            prompt=attrs.get("prompt"),
            aliases=attrs.get("aliases", []),
            size_cm=attrs.get("size_cm"),
            height_cm=attrs.get("height_cm"),
        )

    def obj_attr(self, items: list[Any]) -> tuple[str, Any]:
        return items[0]

    def attr_size_cm(self, items: list[Any]) -> tuple[str, float]:
        return ("size_cm", float(items[0]))

    def attr_height_cm(self, items: list[Any]) -> tuple[str, float]:
        return ("height_cm", float(items[0]))

    def attr_role(self, items: list[Any]) -> tuple[str, str]:
        return ("role", str(items[0]))

    def attr_prompt(self, items: list[Any]) -> tuple[str, str]:
        return ("prompt", str(items[0]).strip("'\""))

    def attr_alias(self, items: list[Any]) -> tuple[str, list[str]]:
        aliases = [str(x).strip("'\"") for x in items if isinstance(x, (str, lark.Token))]
        return ("aliases", aliases)

    def params_line(self, items: list[Any]) -> list[Param]:
        return [it for it in items if isinstance(it, Param)]

    def step(self, items: list[Any]) -> Step:
        idx = int(items[0]) - 1
        name = str(items[1])
        expr: Expr = items[2]
        prov_text = items[3] if len(items) > 3 and items[3] is not None else None

        quote: str | None = None
        t_start: float | None = None
        t_end: float | None = None
        extra_prov: list[Provenance] = []

        if prov_text:
            text = str(prov_text).strip()
            if text.startswith("#"):
                text = text[1:].strip()

            # 1. Extract quote in quotes
            qm = re.search(r'"([^"]*)"', text)
            if not qm:
                qm = re.search(r"'([^']*)'", text)
            if qm:
                quote = qm.group(1)
                text = text[: qm.start()] + text[qm.end() :]

            # 2. Extract timestamp [t0–t1] or [t0-t1]
            tm = re.search(r"\[\s*([0-9:.]+)\s*[–-]\s*([0-9:.]+)\s*\]", text)
            if tm:
                t_start = _parse_time_str(tm.group(1))
                t_end = _parse_time_str(tm.group(2))
                text = text[: tm.start()] + text[tm.end() :]

            # 3. Remaining free text (e.g. (+dwell: compiler default))
            rem = text.strip()
            if rem:
                extra_prov.append(Provenance(quote=rem, source="compiler-default"))

        source = "voice" if (quote or t_start is not None) else "compiler-default"
        prov = Provenance(
            quote=quote,
            t_start=t_start,
            t_end=t_end,
            source=source,
        )

        return Step(
            index=idx,
            name=name,
            expr=expr,
            provenance=prov,
            extra_provenance=extra_prov,
        )

    def expr(self, items: list[Any]) -> Expr:
        children = [it for it in items if isinstance(it, Expr)]
        if len(children) == 1:
            return children[0]
        return Expr(op="or", children=children)

    def and_expr(self, items: list[Any]) -> Expr:
        children = [it for it in items if isinstance(it, Expr)]
        if len(children) == 1:
            return children[0]
        return Expr(op="and", children=children)

    def not_expr(self, items: list[Any]) -> Expr:
        if len(items) == 2:
            return Expr(op="not", children=[items[1]])
        return items[0]

    def atom(self, items: list[Any]) -> Expr:
        if isinstance(items[0], Expr):
            return items[0]
        return Expr(op="atom", atom=items[0])

    def predicate(self, items: list[Any]) -> Atom:
        pred_name = str(items[0])
        args: list[str] = []
        params: list[Param] = []
        for it in items[1:]:
            if isinstance(it, Param):
                params.append(it)
            elif isinstance(it, (str, lark.Token)):
                args.append(str(it))
        return Atom(kind="pred", name=pred_name, args=args, params=params)

    def pred_arg(self, items: list[Any]) -> Any:
        return items[0]

    def param(self, items: list[Any]) -> Param:
        return Param(name=str(items[0]), op=str(items[1]), value=float(items[2]))

    def looks(self, items: list[Any]) -> Atom:
        obj = str(items[0])
        pos = str(items[1]).strip("'\"")
        neg = str(items[2]).strip("'\"") if len(items) > 2 and items[2] else None
        return Atom(kind="looks", args=[obj], looks_pos=pos, looks_neg=neg)

    def manual(self, items: list[Any]) -> Atom:
        req = str(items[0]).strip("'\"")
        return Atom(kind="manual", manual_text=req)


def _normalize_green_text(text: str) -> str:
    """Pre-processes and normalizes raw .green text before parsing.

    - Normalizes Unicode en-dashes (–) and em-dashes (—) to hyphens (-) in timestamps
    - Collapses multiline object declarations inside objects: [...]
    """
    # 1. Normalize timestamp brackets [t0-t1]
    text = re.sub(r"\[\s*([0-9:.]+)\s*[–—]\s*([0-9:.]+)\s*\]", r"[\1-\2]", text)

    # 2. Collapse multiline objects list using balanced bracket matching
    m = re.search(r"objects\s*:\s*\[", text)
    if m:
        start_bracket = m.end() - 1
        depth = 0
        end_bracket = -1
        for i in range(start_bracket, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end_bracket = i
                    break
        if end_bracket != -1:
            inner = text[start_bracket + 1 : end_bracket]
            collapsed_inner = re.sub(r"[\r\n]+[\t ]*", " ", inner).strip()
            text = text[: start_bracket + 1] + collapsed_inner + text[end_bracket:]

    return text


def parse_green(text_or_path: str | Path) -> GreenTest:
    """Parses .green text or file path into a GreenTest AST using Lark grammar.

    Normalizes Unicode en-dashes (–) and hyphens (-) in timestamps.
    Raises lark.exceptions.LarkError on syntax failure with line/col diagnostics.
    """
    default_name = "specification"

    if isinstance(text_or_path, Path):
        text = text_or_path.read_text(encoding="utf-8")
        default_name = text_or_path.stem
    elif isinstance(text_or_path, str):
        # Check if text_or_path is an existing path without newlines
        if "\n" not in text_or_path and (Path(text_or_path).is_file() or text_or_path.endswith(".green")):
            p = Path(text_or_path)
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                default_name = p.stem
            else:
                text = text_or_path
        else:
            text = text_or_path
    else:
        raise TypeError(f"Expected str or Path, got {type(text_or_path)}")

    norm_text = _normalize_green_text(text)

    # Try LALR parser first, fallback to Earley parser
    try:
        tree = _LALR_PARSER.parse(norm_text)
    except lark.exceptions.LarkError as lalr_err:
        try:
            tree = _EARLEY_PARSER.parse(norm_text)
        except lark.exceptions.LarkError:
            # Raise original LALR error with line/col details
            raise lalr_err from None

    transformer = GreenTransformer(default_name=default_name)
    return transformer.transform(tree)


def validate_semantics(test: GreenTest) -> list[Diagnostic]:
    """Runs compile-time post-parse semantic checks on a GreenTest AST."""
    return lint_green(test)
