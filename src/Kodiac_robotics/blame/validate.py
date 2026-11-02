"""Summary validator and the blame orchestrator.

``validate_summary`` rejects any sentence that is not provably grounded in the FactTable:

* exactly one sentence, no line breaks, at most 30 words;
* every number (with its unit, if any) must equal a FactTable number at the precision written (1-decimal
  rounding for 1-decimal text); ``mm:ss.s`` times must equal t* (or the reference time); ``frame N`` must be a
  frame present in the table;
* every ``a ± b`` pair must be the value and sigma *of the same fact*, and at least one such pair must appear;
* object mentions must be declared objects (names, aliases, prompt words) or generic robot words;
* verbs must be licensed: "opened" needs an aperture event (sim span); "released"/"dropped"/"let go" need a
  measured ``moves_with`` True->False; "slipped" needs a slip fact; contact verbs ("collided", "hit", "knocked",
  "pushed", "bumped") are never licensed because nothing measures contact.

``blame_from_run`` orchestrates transition -> t* -> FactTable -> summary and returns ``None`` unless the run is a
FAIL with an attributable transition.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from Kodiac_robotics.contracts.core import (
    Blame,
    CodeLocation,
    FactTable,
    GreenTest,
    Hint,
    PredFrame,
    RunResult,
    Verdict,
)

MAX_WORDS = 30
_UNITS = r"cm/s|cm|mm|m|s|%|frames?"
_NUM = r"-?\d+(?:\.\d+)?"
_PM_RE = re.compile(rf"({_NUM})\s*(?:±|\+/-|\+-)\s*({_NUM})(?:\s*({_UNITS})(?![A-Za-z]))?")
_CLOCK_RE = re.compile(r"(?<![\d.:])(\d{1,2}):(\d{2}(?:\.\d+)?)(?![\d:])")
_FRAME_RE = re.compile(r"\bframes?\s+(\d+)\b", re.IGNORECASE)
_LOOSE_NUM_RE = re.compile(rf"(?<![A-Za-z_\d.])({_NUM})(?:\s*({_UNITS})(?![A-Za-z]))?(?![A-Za-z_\d])")
_IDENT_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|[a-z]+[A-Z][A-Za-z0-9]*|[A-Za-z]+\d+[A-Za-z0-9]*)\b"
)
_WORD_RE = re.compile(r"[A-Za-z]+")

GENERIC_ROBOT_WORDS = frozenset({"robot", "arm", "gripper", "effector", "hand", "fingers", "jaws", "table", "surface"})
OBJECT_NOUNS = frozenset(
    {
        "block", "blocks", "cube", "cubes", "cup", "cups", "mug", "mugs", "bowl", "bowls", "plate", "plates",
        "box", "boxes", "drawer", "drawers", "lid", "lids", "bottle", "bottles", "can", "cans", "ball", "balls",
        "tray", "trays", "bin", "bins", "basket", "baskets", "sponge", "sponges", "peg", "pegs", "hole", "holes",
        "shelf", "shelves", "cabinet", "door", "jar", "jars", "spoon", "fork", "knife", "pan", "pot", "towel",
        "cloth", "marker", "pen", "toy", "fruit", "apple", "banana", "orange", "carrot", "brick", "bricks",
    }
)
PREDICATE_WORDS = frozenset({"on", "inside", "near", "lifted", "moves_with", "dwell", "looks", "MANUAL"})
VOCAB_IDENTIFIERS = frozenset(
    {
        "moves_with", "align_xy", "align_xy_cm", "gap_cm", "min_cm", "slip_cm", "for_s", "max_cm",
        "max_speed_cm_s", "window_s", "depth_tol", "scale_ratio", "xy_offset_cm", "gap_z_cm", "lift_cm",
        "distance_cm", "speed_cm_s", "dwell_s", "depth_ratio", "dt_before_reference_s", "reference_xy_cm",
        "aperture_open_event", "blame_class",
    }
)

_OPEN_RE = re.compile(r"\bopen(?:ed|s|ing)?\b", re.IGNORECASE)
_RELEASE_RE = re.compile(
    r"\b(?:releas(?:e|ed|es|ing)|let(?:s)?\s+go|letting\s+go|detach(?:ed|es|ing)?|drop(?:ped|s|ping)?|"
    r"fell|falls?|falling)\b",
    re.IGNORECASE,
)
_SLIP_RE = re.compile(r"\bslip(?:ped|ping|s)?\b", re.IGNORECASE)
_CONTACT_RE = re.compile(
    r"\b(?:collid\w*|collision\w*|hit|hits|hitting|knock\w*|bump\w*|crash\w*|smash\w*|push(?:ed|es|ing)?|"
    r"struck|strike\w*)\b",
    re.IGNORECASE,
)


def _decimals(token: str) -> int:
    return len(token.split(".", 1)[1]) if "." in token else 0


def _matches(token: str, value: float) -> bool:
    """True iff ``value`` rounded to the token's precision prints as the token (``-0.0`` == ``0.0``)."""
    d = _decimals(token)
    try:
        x = round(float(value), d)
        y = round(float(token), d)
    except (TypeError, ValueError):
        return False
    x = 0.0 if x == 0 else x
    y = 0.0 if y == 0 else y
    return f"{x:.{d}f}" == f"{y:.{d}f}"


def _norm_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.lower()
    if u in ("frame", "frames"):
        return "frame"
    return u


def _numeric_entries(ft: FactTable) -> list[tuple[float, str | None, str]]:
    """(value, unit, label) for every number the sentence may quote."""
    entries: list[tuple[float, str | None, str]] = []

    def num(x: Any) -> float | None:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        return float(x)

    for name, fact in ft.facts.items():
        unit = fact.get("unit")
        unit = None if unit in (None, "class", "event", "ratio") else str(unit)
        for field in ("value", "sigma", "threshold"):
            v = num(fact.get(field))
            if v is not None:
                entries.append((v, unit, f"{name}.{field}"))
                if fact.get("unit") == "ratio" and field == "value":
                    entries.append((v * 100.0, "%", f"{name}.percent"))
        for field in ("t_ref_s",):
            v = num(fact.get(field))
            if v is not None:
                entries.append((v, "s", f"{name}.{field}"))
        for field in ("frame", "t_ref_frame", "frames_occluded", "frames_checked", "line"):
            v = num(fact.get(field))
            if v is not None:
                entries.append((v, "frame" if "frame" in field else None, f"{name}.{field}"))
    entries.append((ft.t_star_s, "s", "t_star_s"))
    entries.append((ft.sigma_frames / ft.fps, "s", "sigma_t_s"))
    entries.append((ft.sigma_frames, "frame", "sigma_frames"))
    entries.append((float(ft.frame), "frame", "frame"))
    entries.append((float(ft.step_index), None, "step_index"))
    entries.append((float(ft.step_index + 1), None, "step_ordinal"))
    if ft.code_location is not None:
        entries.append((float(ft.code_location.line), None, "code_location.line"))
    return entries


def _pm_entries(ft: FactTable) -> list[tuple[float, float, str | None, str]]:
    out: list[tuple[float, float, str | None, str]] = []
    for name, fact in ft.facts.items():
        v, s = fact.get("value"), fact.get("sigma")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not isinstance(s, (int, float)):
            continue
        unit = fact.get("unit")
        out.append((float(v), float(s), None if unit in (None, "ratio") else str(unit), name))
    out.append((ft.t_star_s, ft.sigma_frames / ft.fps, "s", "t_star_s"))
    out.append((float(ft.frame), ft.sigma_frames, "frame", "frame"))
    return out


def _known_object_words(test: GreenTest) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    words: set[str] = set()
    for o in test.objects:
        for n in [o.name, *o.aliases]:
            names.add(n)
            names.add(n.lower())
        if o.prompt:
            words.update(w.lower() for w in _WORD_RE.findall(o.prompt))
    return names, words


def _allowed_noun(noun: str, names: set[str], prompt_words: set[str]) -> bool:
    n = noun.lower()
    singular = n[:-1] if n.endswith("s") else n
    if n in prompt_words or singular in prompt_words:
        return True
    return any(singular and singular in name.lower() for name in names)


def validate_summary(text: str, ft: FactTable, test: GreenTest) -> list[str]:
    """Return the list of violations ([] = valid)."""
    violations: list[str] = []
    if not text or not text.strip():
        return ["empty summary"]
    s = text.strip()

    # ---- shape: one sentence, <= 30 words ----
    if "\n" in s or "\r" in s:
        violations.append("summary must be a single line")
    if re.search(r"[.!?;](?=\s+\S)", s):
        violations.append("summary must be exactly one sentence")
    words = [w for w in s.split() if re.search(r"[A-Za-z0-9]", w)]
    if len(words) > MAX_WORDS:
        violations.append(f"summary has {len(words)} words (max {MAX_WORDS})")

    work = s
    entries = _numeric_entries(ft)

    # ---- timestamps (mm:ss.s) ----
    def clock_ok(m: re.Match[str]) -> bool:
        secs_tok = m.group(2)
        total = int(m.group(1)) * 60 + float(secs_tok)
        d = _decimals(secs_tok)
        cands = [ft.t_star_s] + [v for v, u, lbl in entries if u == "s" and lbl.endswith("t_ref_s")]
        return any(abs(round(c, d) - total) < 1e-6 for c in cands)

    for m in list(_CLOCK_RE.finditer(work)):
        if not clock_ok(m):
            violations.append(f"time '{m.group(0)}' does not match t* or the reference time")
    work = _CLOCK_RE.sub(" ", work)

    # ---- value ± sigma pairs ----
    pm_entries = _pm_entries(ft)
    n_pairs_ok = 0
    for m in list(_PM_RE.finditer(work)):
        a, b, unit = m.group(1), m.group(2), _norm_unit(m.group(3))
        ok = False
        for v, sig, u, _name in pm_entries:
            if _matches(a, v) and _matches(b, sig) and (unit is None or u is None or _norm_unit(u) == unit):
                ok = True
                break
        if ok:
            n_pairs_ok += 1
        else:
            violations.append(f"'{m.group(0).strip()}' is not a value ± sigma pair of any single fact")
    if n_pairs_ok == 0:
        violations.append("summary must contain at least one 'value ± sigma' pair copied from the facts")
    work = _PM_RE.sub(" ", work)

    # ---- frame references ----
    for m in list(_FRAME_RE.finditer(work)):
        tok = m.group(1)
        if not any(u == "frame" and _matches(tok, v) for v, u, _ in entries):
            violations.append(f"'frame {tok}' is not a frame in the fact table")
    work = _FRAME_RE.sub(" ", work)

    # ---- identifiers (objects / predicates) ----
    names, prompt_words = _known_object_words(test)
    step_names = {st.name for st in test.steps}
    for m in _IDENT_RE.finditer(work):
        tok = m.group(0)
        if tok in names or tok.lower() in names or tok in VOCAB_IDENTIFIERS or tok in PREDICATE_WORDS:
            continue
        if tok in step_names:
            continue
        violations.append(f"unknown object or identifier '{tok}'")
    lowered_words = [w.lower() for w in _WORD_RE.findall(_IDENT_RE.sub(" ", work))]
    for w in lowered_words:
        if w in OBJECT_NOUNS and w not in GENERIC_ROBOT_WORDS and not _allowed_noun(w, names, prompt_words):
            violations.append(f"object '{w}' is not declared in the test")

    # ---- licensed verbs (step names are not verbs) ----
    verb_text = work
    for name in sorted(step_names, key=len, reverse=True):
        verb_text = re.sub(rf"\bstep\s+'?{re.escape(name)}'?", " ", verb_text, flags=re.IGNORECASE)
    pred, _ = _parse_literal(ft.literal)
    measured_detach = ft.transition == "T->F" and pred == "moves_with"
    aperture = ft.facts.get("aperture_open_event", {}).get("value") is True
    if _OPEN_RE.search(verb_text) and not aperture:
        violations.append("verb 'opened' is unlicensed: no aperture event or sim span in the facts")
    m_rel = _RELEASE_RE.search(verb_text)
    if m_rel and not measured_detach:
        violations.append(f"verb '{m_rel.group(0)}' is unlicensed: no measured moves_with True->False")
    if _SLIP_RE.search(verb_text) and "slip_cm" not in ft.facts:
        violations.append("verb 'slipped' is unlicensed: no slip measurement in the facts")
    m_contact = _CONTACT_RE.search(verb_text)
    if m_contact:
        violations.append(f"verb '{m_contact.group(0)}' is unlicensed: contact is never measured")

    # ---- every remaining number must be a fact number with a compatible unit ----
    for m in _LOOSE_NUM_RE.finditer(work):
        tok, unit = m.group(1), _norm_unit(m.group(2))
        ok = any(
            _matches(tok, v) and (unit is None or (u is not None and _norm_unit(u) == unit))
            for v, u, _ in entries
        )
        if not ok:
            violations.append(f"number '{m.group(0).strip()}' is not in the fact table")

    return violations


def _parse_literal(literal: str) -> tuple[str, list[str]]:
    from Kodiac_robotics.blame.facts import parse_atom_key

    return parse_atom_key(literal)


# ==============================================================================
# Orchestrator
# ==============================================================================


def _flatten(pred_frames: dict[str, list[PredFrame]] | list[PredFrame]) -> list[PredFrame]:
    if isinstance(pred_frames, dict):
        out: list[PredFrame] = []
        for lst in pred_frames.values():
            out.extend(lst)
        return out
    return list(pred_frames)


def _apply_spans(ft: FactTable, spans: list[Any], fps: float) -> list[str]:
    """Sim-span disambiguation for moves_with True->False (ARCHITECTURE §9). Mutates ``ft.facts``."""
    notes: list[str] = []
    pred, _ = _parse_literal(ft.literal)
    if not (ft.transition == "T->F" and pred == "moves_with") or not spans:
        return notes
    t_star = ft.t_star_s
    opens = [s for s in spans if getattr(s, "actuation_class", "") == "gripper.open"]
    causal = [s for s in opens if t_star - 1.0 <= float(s.t_start_s) <= t_star + 3.0 / fps]
    release = causal[-1] if causal else None
    if release is None:
        return notes
    ft.facts["aperture_open_event"] = {
        "value": True,
        "unit": "event",
        "source": "sim_span",
        "span_id": int(release.span_id),
        "file": str(release.file),
        "line": int(release.line),
        "code": str(release.code),
        "t_s": float(release.t_start_s),
    }
    place_moves = [
        s
        for s in spans
        if getattr(s, "actuation_class", "") == "arm.move_to" and "place" in str(getattr(s, "code", ""))
    ]
    first_place = min(place_moves, key=lambda s: s.step_start) if place_moves else None
    previous = str(ft.facts.get("blame_class", {}).get("value", ""))
    if first_place is None or int(release.step_start) < int(first_place.step_start):
        ft.facts["blame_class"] = {
            "value": "release_before_place",
            "unit": "class",
            "basis": f"sim span {release.span_id} ({release.code}, line {release.line}) ran before "
            + (f"span {first_place.span_id} ({first_place.code})" if first_place else "any move_to(place)"),
            "source": "sim_span",
        }
    else:
        xy = ft.facts.get("xy_offset_cm")
        gap = ft.facts.get("gap_z_cm")
        if xy is not None and gap is not None and xy["value"] <= xy["threshold"] and gap["value"] > gap["threshold"]:
            ft.facts["blame_class"] = {
                "value": "place_z",
                "unit": "class",
                "basis": f"release after span {first_place.span_id} ({first_place.code}); aligned in xy but "
                "gap_z_cm > gap_cm",
                "source": "sim_span",
            }
    new = str(ft.facts["blame_class"]["value"])
    if previous and previous != new:
        notes.append(f"blame_class '{previous}' (measurement rule) overridden to '{new}' by sim span order")
    return notes


def _refine_window(tr: Any, result: RunResult, fps: float, n_total: int) -> tuple[int, int]:
    from Kodiac_robotics.blame.transitions import n_on_frames

    n_on = n_on_frames(fps)
    w0 = 0
    for sr in result.steps:
        if sr.index == tr.step_index:
            break
        if sr.verdict == Verdict.PASS and sr.frame is not None:
            w0 = int(sr.frame) + 1
    hi_all = max(0, n_total - 1)
    if tr.cls == "unmet":
        return (w0, hi_all)
    back = int(round(1.0 * fps))
    lo = max(w0 if tr.cls == "broken_prerequisite" else 0, tr.t_frame - back)
    return (lo, min(hi_all, tr.t_frame + n_on))


def blame_from_run(
    result: RunResult,
    test: GreenTest,
    pred_frames: dict[str, list[PredFrame]] | list[PredFrame],
    fps: float,
    **kw: Any,
) -> Blame | None:
    """FAIL run -> Blame. Returns None for PASS / CAN'T TELL, or when no transition is attributable.

    Keyword options: ``llm`` (Callable[[str], str]), ``spans`` (list[SimSpan]), ``code_location`` (CodeLocation),
    ``code_locator`` (Callable[[int, str], CodeLocation | None], e.g. T03's ``locate_code`` bound to spans),
    ``hint_fn`` (Callable[[FactTable], Hint | None]), ``reference_frames`` (list[PredFrame], e.g. from
    ``facts.reference_pred_frames``), ``dataset_index``, ``action_chunk``, ``n_boot`` (200), ``seed`` (0).
    """
    from Kodiac_robotics.blame.facts import build_fact_table
    from Kodiac_robotics.blame.summary import summarize
    from Kodiac_robotics.blame.transitions import find_transition, index_pred_frames, total_frames
    from Kodiac_robotics.blame.tstar import refine_tstar

    if result.verdict != Verdict.FAIL:
        return None
    flat = _flatten(pred_frames)
    tr = find_transition(result, flat, test, fps)
    if tr is None:
        return None
    n_total = total_frames(index_pred_frames(flat))
    window = _refine_window(tr, result, fps, n_total)
    ts = refine_tstar(tr, flat, fps, window, n_boot=int(kw.get("n_boot", 200)), seed=int(kw.get("seed", 0)))

    code_location: CodeLocation | None = kw.get("code_location")
    locator: Callable[[int, str], CodeLocation | None] | None = kw.get("code_locator")
    if code_location is None and locator is not None:
        code_location = locator(ts.frame, tr.component or "")

    refs: list[PredFrame] = list(kw.get("reference_frames") or [])
    ft = build_fact_table(
        result,
        tr,
        ts,
        flat + refs,
        code_location=code_location,
        dataset_index=kw.get("dataset_index"),
        action_chunk=kw.get("action_chunk"),
        fps=fps,
    )
    warnings = list(tr.warnings)
    spans = kw.get("spans")
    if spans:
        warnings.extend(_apply_spans(ft, list(spans), fps))

    text, source = summarize(ft, test, llm=kw.get("llm"))
    hint_fn: Callable[[FactTable], Hint | None] | None = kw.get("hint_fn")
    hint = hint_fn(ft) if hint_fn is not None else None
    if result.is_fixture:
        warnings.append("fixture replay: measurements come from recorded tracks, not a live SAM 3.1 call")
    return Blame(facts=ft, summary=text, summary_source=source, hint=hint, warnings=warnings)


__all__ = ["validate_summary", "blame_from_run", "MAX_WORDS"]
