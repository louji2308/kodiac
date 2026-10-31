"""Canonical printer for .green test specifications.

Serializes GreenTest AST back into canonical .green text satisfying:
- Round-trip idempotency: parse_green(print_green(t)) == t
- Bit-identical reproduction on examples/stackcube.green and examples/stack_blocks.green
"""

from __future__ import annotations

from Kodiac_robotics.contracts.core import Atom, Expr, GreenTest, ObjectDecl, Param


def _format_object(obj: ObjectDecl) -> str:
    attrs: list[str] = []
    # Role: only include if non-default
    if obj.name == "gripper":
        if obj.role != "effector":
            attrs.append(f"role={obj.role}")
    else:
        if obj.role != "rigid":
            attrs.append(f"role={obj.role}")

    if obj.prompt is not None:
        attrs.append(f'prompt="{obj.prompt}"')
    if obj.aliases:
        aliases_str = ", ".join(f'"{a}"' for a in obj.aliases)
        attrs.append(f"alias=[{aliases_str}]")
    if obj.size_cm is not None:
        size_str = str(int(obj.size_cm)) if obj.size_cm.is_integer() else str(obj.size_cm)
        attrs.append(f"size_cm={size_str}")
    if obj.height_cm is not None:
        height_str = str(int(obj.height_cm)) if obj.height_cm.is_integer() else str(obj.height_cm)
        attrs.append(f"height_cm={height_str}")

    if attrs:
        return f"{obj.name}({', '.join(attrs)})"
    return obj.name


def _format_param(p: Param) -> str:
    val_str = str(p.value)
    return f"{p.name}{p.op}{val_str}"


def _format_atom(atom: Atom) -> str:
    if atom.kind == "pred":
        items = list(atom.args) + [_format_param(p) for p in atom.params]
        return f"{atom.name}({', '.join(items)})"
    elif atom.kind == "looks":
        state_part = f'"{atom.looks_pos}"'
        if atom.looks_neg:
            state_part += f' | "{atom.looks_neg}"'
        obj_arg = atom.args[0] if atom.args else ""
        return f"looks({obj_arg}, {state_part})"
    elif atom.kind == "manual":
        return f'MANUAL("{atom.manual_text}")'
    raise ValueError(f"Unknown atom kind: {atom.kind}")


def _format_expr(expr: Expr, parent_op: str | None = None) -> str:
    if expr.op == "atom":
        assert expr.atom is not None
        return _format_atom(expr.atom)
    elif expr.op == "not":
        assert len(expr.children) == 1
        child = expr.children[0]
        child_str = _format_expr(child, parent_op="not")
        if child.op in ("and", "or"):
            return f"not ({child_str})"
        return f"not {child_str}"
    elif expr.op == "and":
        parts = [_format_expr(c, parent_op="and") for c in expr.children]
        res = " and ".join(parts)
        if parent_op == "not":
            return f"({res})"
        return res
    elif expr.op == "or":
        parts = [_format_expr(c, parent_op="or") for c in expr.children]
        res = " or ".join(parts)
        if parent_op in ("and", "not"):
            return f"({res})"
        return res
    raise ValueError(f"Unknown expr op: {expr.op}")


def _format_time(t: float) -> str:
    m = int(t // 60)
    s = t % 60
    return f"{m}:{s:04.1f}"


def print_green(test: GreenTest) -> str:
    """Serializes GreenTest AST back into canonical 4-line .green text.

    Must satisfy round-trip idempotency: parse_green(print_green(t)) == t.
    """
    out: list[str] = []

    # 1. Header comment
    if test.header_comment:
        out.append(test.header_comment.strip())
    else:
        out.append(f"# {test.name}.green")

    # 2. Objects line
    objs_str = ", ".join(_format_object(o) for o in test.objects)
    out.append(f"objects: [{objs_str}]")

    # 3. Params line (if present)
    if test.params:
        params_str = ", ".join(_format_param(p) for p in test.params)
        out.append(f"params: {params_str}")

    # 4. Steps
    for idx, step in enumerate(test.steps):
        prefix = f"{idx + 1}. {step.name}:"
        prefix_padded = f"{prefix:<12}"
        expr_str = _format_expr(step.expr)
        line_core = prefix_padded + expr_str

        # Provenance
        prov_parts: list[str] = []
        if step.provenance.quote:
            prov_parts.append(f'"{step.provenance.quote}"')
        if step.provenance.t_start is not None and step.provenance.t_end is not None:
            t0 = _format_time(step.provenance.t_start)
            t1 = _format_time(step.provenance.t_end)
            prov_parts.append(f"[{t0}\u2013{t1}]")

        for ep in step.extra_provenance:
            if ep.quote:
                prov_parts.append(ep.quote)

        if prov_parts:
            prov_str = "# " + " ".join(prov_parts)
            pad_len = max(91 - len(line_core), 1)
            line = line_core + (" " * pad_len) + prov_str
        else:
            line = line_core

        out.append(line)

    return "\n".join(out) + "\n"
