"""One-sentence blame summary: deterministic template, or an injected LLM gated by the validator (ARCHITECTURE §9).

The LLM (Muse Spark in production) is an injected callable; offline there is none, so ``llm=None`` yields the
template with ``summary_source="template"``. An LLM sentence is accepted only if ``validate_summary`` returns no
violations; otherwise it is retried once with the violations appended, then the template is used. A template
sentence is never labelled ``"muse-spark"``.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

from Kodiac_robotics.blame.facts import parse_atom_key
from Kodiac_robotics.blame.validate import validate_summary
from Kodiac_robotics.contracts.core import FactTable, GreenTest

FACT_LABELS: dict[str, str] = {
    "xy_offset_cm": "xy offset",
    "gap_z_cm": "z gap",
    "depth_ratio": "depth ratio",
    "lift_cm": "lift",
    "slip_cm": "slip",
    "distance_cm": "distance",
    "speed_cm_s": "speed",
    "dwell_s": "dwell time",
}
_OP_TEXT = {"<=": "≤", ">=": "≥"}


def fmt_num(v: float) -> str:
    """One decimal; two when a value of at least 0.005 would otherwise print as 0.0."""
    if 0.005 <= abs(v) < 0.05:
        return f"{v:.2f}"
    out = f"{v:.1f}"
    return "0.0" if out == "-0.0" else out


def fmt_pm(fact: dict[str, Any]) -> str:
    """``value ± sigma`` copied from a fact."""
    return f"{fmt_num(float(fact['value']))} ± {fmt_num(float(fact['sigma']))}"


def fmt_clock(t_s: float) -> str:
    """``mm:ss.s``."""
    t = max(0.0, round(float(t_s), 1))
    minutes = int(t // 60)
    return f"{minutes:02d}:{t - 60 * minutes:04.1f}"


def _unit_suffix(unit: str) -> str:
    return "" if unit == "ratio" else f" {unit}"


def _measured(ft: FactTable, name: str) -> dict[str, Any] | None:
    fact = ft.facts.get(name)
    if fact is None or fact.get("sigma") is None or not isinstance(fact.get("value"), (int, float)):
        return None
    if isinstance(fact.get("value"), bool):
        return None
    return fact


def _cause_fact(ft: FactTable) -> tuple[str, dict[str, Any]] | None:
    for name, fact in ft.facts.items():
        if fact.get("role") == "cause" and _measured(ft, name) is not None:
            return name, fact
    for name in FACT_LABELS:
        fact = _measured(ft, name)
        if fact is not None:
            return name, fact
    return None


def _threshold_clause(name: str, fact: dict[str, Any]) -> str:
    label = FACT_LABELS.get(name, name)
    unit = _unit_suffix(str(fact.get("unit", "")))
    clause = f"{label} {fmt_pm(fact)}{unit}"
    if fact.get("threshold") is not None and fact.get("op") in _OP_TEXT:
        clause += f" vs {_OP_TEXT[fact['op']]} {fmt_num(float(fact['threshold']))}{unit}"
    return clause


def render_template_summary(ft: FactTable) -> str:
    """Deterministic one-sentence summary built only from FactTable values (always has a ``value ± σ`` pair)."""
    when = f"{fmt_clock(ft.t_star_s)}, frame {ft.frame}"
    pred, args = parse_atom_key(ft.literal)
    cls = str(ft.facts.get("blame_class", {}).get("value", ""))
    xy = _measured(ft, "xy_offset_cm")
    dt = _measured(ft, "dt_before_reference_s")
    gap = _measured(ft, "gap_z_cm")
    slip = _measured(ft, "slip_cm")

    if ft.transition == "T->F" and pred == "moves_with" and len(args) >= 2:
        eff, obj = args[0], args[1]
        target = xy["objects"][1] if xy is not None and len(xy.get("objects", [])) >= 2 else None
        if dt is not None and xy is not None and target and dt["value"] > 0:
            return (
                f"blame: {eff} released {obj} {fmt_pm(dt)} s before reaching {target} "
                f"(xy offset {fmt_pm(xy)} cm at {when})"
            )
        if cls == "place_z" and gap is not None and xy is not None and target:
            return (
                f"blame: {eff} released {obj} {fmt_pm(gap)} cm above {target} at {when}, "
                f"with xy offset {fmt_pm(xy)} cm"
            )
        if xy is not None and target:
            return f"blame: {eff} released {obj} {fmt_pm(xy)} cm from {target} in xy at {when}"
        if slip is not None:
            return f"blame: {eff} released {obj} at {when}, slip {fmt_pm(slip)} cm"

    cause = _cause_fact(ft)
    if cause is None:
        # No measured component survived the gates; report the timing estimate itself.
        sig_s = ft.sigma_frames / ft.fps
        return (
            f"blame: step {ft.step_name} failed on {ft.literal} at {fmt_num(ft.t_star_s)} ± {fmt_num(sig_s)} s "
            f"(frame {ft.frame}) with no reliable measurement"
        )
    name, fact = cause
    clause = _threshold_clause(name, fact)
    if ft.transition == "T->F":
        return f"blame: {ft.literal} broke at {when}: {clause}"
    if ft.transition == "order":
        return f"blame: step {ft.step_name} held out of order at {when}: {clause}"
    below_floor = abs(float(fact.get("margin", 0.0))) < float(fact.get("sigma", 0.0)) or fact.get("tri") == "U"
    if below_floor:
        return f"blame: step {ft.step_name} never confirmed: {clause} stayed within noise (best at {when})"
    return f"blame: step {ft.step_name} never held: {clause} at closest approach ({when})"


def build_prompt(ft: FactTable, test: GreenTest) -> str:
    """LLM prompt: the FactTable JSON and the .green text only."""
    from Kodiac_robotics.compiler.printer import print_green

    facts_json = json.dumps(ft.model_dump(mode="json"), indent=1, sort_keys=True, default=str)
    return (
        "You explain why a robot test failed in ONE sentence of at most 30 words that starts with 'blame:'.\n"
        "Rules: use ONLY numbers present in FACTS (rounded to 1 decimal) with their units; include at least one "
        "'value ± sigma' pair copied from one fact; name only objects declared in TEST; do not say 'opened' unless "
        "FACTS has aperture_open_event; do not claim collisions, intent or anything not in FACTS; write the time "
        "as mm:ss.s and cite the frame number.\n"
        f"TEST (.green):\n{print_green(test)}\n"
        f"FACTS (JSON):\n{facts_json}\n"
        "Sentence:"
    )


def summarize(
    ft: FactTable,
    test: GreenTest,
    *,
    llm: Callable[[str], str] | None = None,
) -> tuple[str, Literal["muse-spark", "template"]]:
    """LLM sentence if it validates (one retry with the violations), else the template."""
    if llm is None:
        return render_template_summary(ft), "template"
    prompt = build_prompt(ft, test)
    violations: list[str] = []
    for attempt in range(2):
        ask = prompt
        if attempt == 1:
            ask = (
                prompt
                + "\nYour previous sentence was rejected for:\n- "
                + "\n- ".join(violations)
                + "\nRewrite it following every rule."
            )
        try:
            text = (llm(ask) or "").strip()
        except Exception as exc:  # the injected client failed: fall back, never fabricate
            violations = [f"llm call failed: {type(exc).__name__}"]
            continue
        violations = validate_summary(text, ft, test)
        if not violations:
            return text, "muse-spark"
    return render_template_summary(ft), "template"


__all__ = ["render_template_summary", "summarize", "build_prompt", "fmt_num", "fmt_pm", "fmt_clock"]
