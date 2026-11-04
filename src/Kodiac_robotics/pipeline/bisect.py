"""Two-stage bisect fast path: "git bisect for robots" (KD-05, ARCHITECTURE.md §5.2, ADR-0008).

Stage 1   : K keyframes in ONE ``segment_frames`` call -> static proxies per step -> prefix-max progress -> bracket.
Stage 1.5 : single-frame probes halve the bracket on the carried literal L (target F_L(t) = "L false at t").
Stage 2   : one dense window (>= 50 frames, ``io.windows.cut_window`` padding arithmetic), seeds = masks on the LAST
            frame, ``direction="backward"``; the residual test (anchored on the last proxy-achieved step) is evaluated
            on densely tracked frames only.
Guards    : G-alias (effector resolved through alias prompts; carried-literal flicker -> earliest bracket),
            G-miss (object lost / anchor unverified -> extend back by 50 frames <= 2x -> full path),
            G-budget (SAM calls > budget, or a clip so short that bisect would bill more than one dense pass -> full path),
            G-pass (all steps seen at keyframes -> dense verification windows; PASS is never declared from keyframes).

Honesty notes:
- Keyframe proxies only place windows. Every verdict comes from dense per-frame predicates, gates and the step chain.
- ``pipeline.run.run`` cannot evaluate sparse tracks (its G2 scene scan treats every untracked frame as occluded), so
  dense windows are evaluated by ``_evaluate_dense``, which mirrors ``run.run`` restricted to densely tracked frames.
  ``tests/pipeline/test_bisect.py`` pins it to ``run.run`` on fully observed clips. All fallbacks call ``run.run``.
- With the fixture segmenter, every timing is fixture replay and says nothing about real SAM 3.1 latency.
"""

from __future__ import annotations

import math
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from pydantic import BaseModel

from Kodiac_robotics.contracts.core import (
    Atom,
    Clip,
    Event,
    GreenTest,
    ObjMask,
    PredFrame,
    ReasonCode,
    RunResult,
    ScaleModel,
    Segmenter,
    Step,
    StepResult,
    Track,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.logic import evaluate_expr_tree
from Kodiac_robotics.engine.steps import (
    _extract_atoms,
    _extract_negated_atom_keys,
    _extract_positive_relational_atoms,
    evaluate_step_chain,
)
from Kodiac_robotics.engine.trace import TraceWriter
from Kodiac_robotics.geometry.scale import TierCScaleModel, fit_scale_model
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.pipeline.run import _harmonize_track_keys
from Kodiac_robotics.pipeline.run import run as run_full
from Kodiac_robotics.predicates.base import (
    conjoin_components,
    euclidean_3d,
    get_atom_key,
    get_object_coords,
    get_param_value,
)
from Kodiac_robotics.predicates.dispatch import evaluate_atom
from Kodiac_robotics.render.card import render_verdict_card_v1
from Kodiac_robotics.uncertainty.gates import apply_gates

MIN_WINDOW_FRAMES = 50  # SAM 3.1 bills >= 50 frames per video request (TOOLS_AND_REQUIREMENTS.md §2.1)
HALVE_UNTIL_FRAMES = 50  # Stage 1.5 halves while f_b - f_a > 50 (ARCHITECTURE.md §5.2)
BRACKET_PAD_FRAMES = 3  # Stage 2 cuts [f_a - 3, f_b + 3] before padding
KEYFRAME_SPACING_S = 2.5  # K = max(k_keyframes, ceil(duration / 2.5 s))
PACK_REPEAT = 3  # io.windows.pack_frames repeats every keyframe 3x
G_MISS_EXTEND_FRAMES = 50
G_MISS_MAX_EXTENSIONS = 2
# Bisect bills at least one keyframe pack (50) plus one window (50). At or below this many frames one dense pass
# over the whole clip bills no more, so the fast path tracks the clip directly (recorded as a G-budget guard).
MIN_BISECT_FRAMES = 2 * MIN_WINDOW_FRAMES
EFFECTOR_ALIAS_PROMPTS = ("robot gripper", "gripper", "end effector", "hand")  # KD-18
CONTACT_MARGIN_FRAC = 0.15
LATENCY_KIND_FIXTURE = "fixture_replay_not_sam"
LATENCY_KIND_LIVE = "live_backend_wall_clock"
FAST_BADGE = "[FAST PATH · TWO-STAGE BISECT]"
FALLBACK_BADGE = "[FAST PATH → FULL-PATH FALLBACK]"
_RUN_KWARGS = frozenset({"camera", "cam_K", "cam_extrinsic", "output_dir", "render_card"})


class BisectPlan(BaseModel):
    stage1_frames: list[int]
    stage15_probes: list[int]
    window: tuple[int, int]
    n_sam_calls: int
    guards_fired: list[str]


class FastRun(BaseModel):
    result: RunResult
    plan: BisectPlan
    stage_timings_ms: dict[str, int]
    billed_frames: int


# ----------------------------------------------------------------------------------------------------------------------
# Window arithmetic
# ----------------------------------------------------------------------------------------------------------------------


def pad_window(f0: int, f1: int, n_frames: int, min_frames: int = MIN_WINDOW_FRAMES) -> tuple[int, int]:
    """Padded window bounds, identical to the arithmetic of ``io.windows.cut_window`` (no MP4 is written).

    Clamps [f0, f1] to the clip, then pads symmetrically to >= ``min_frames`` and shifts at the clip edges.
    """
    if n_frames <= 0:
        raise ValueError(f"invalid n_frames: {n_frames}")
    lo, hi = min(f0, f1), max(f0, f1)
    v0 = max(0, min(n_frames - 1, lo))
    v1 = max(0, min(n_frames - 1, hi))
    req = v1 - v0 + 1
    if req >= min_frames:
        return v0, v1
    deficit = min_frames - req
    pad_left = deficit // 2
    pad_right = deficit - pad_left
    c0, c1 = v0 - pad_left, v1 + pad_right
    if c0 < 0:
        p0 = 0
        c1 += -c0
    else:
        p0 = c0
    if c1 > n_frames - 1:
        overflow = c1 - (n_frames - 1)
        p1 = n_frames - 1
        p0 = max(0, p0 - overflow)
    else:
        p1 = c1
    return p0, p1


def keyframe_indices(n_frames: int, fps: float, k_keyframes: int) -> list[int]:
    """K = max(k_keyframes, ceil(duration / 2.5 s)) evenly spaced keyframes including the first and last frame."""
    if n_frames <= 0:
        return []
    duration_s = n_frames / max(fps, 1e-6)
    k = max(2, k_keyframes, math.ceil(duration_s / KEYFRAME_SPACING_S))
    k = min(k, n_frames)
    return sorted({int(round(i * (n_frames - 1) / (k - 1))) for i in range(k)})


def _merge_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for w0, w1 in sorted(windows):
        if merged and w0 <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], w1))
        else:
            merged.append((w0, w1))
    return merged


# ----------------------------------------------------------------------------------------------------------------------
# Metered segmenter + observation store
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class _Meter:
    """Counts SAM calls and billed units around any ``Segmenter`` (fixture, api, modal)."""

    seg: Segmenter
    budget: int
    calls: int = 0
    billed_video_frames: int = 0
    billed_images: int = 0
    sam_ms: float = 0.0
    log: list[dict[str, Any]] = field(default_factory=list)

    def would_exceed(self, extra: int = 1) -> bool:
        return self.calls + extra > self.budget

    def segment(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]], kind: str) -> dict[str, Track]:
        t0 = time.perf_counter()
        out = self.seg.segment_frames(clip, sorted(frames), prompts)
        dt = (time.perf_counter() - t0) * 1000.0
        self.calls += 1
        self.sam_ms += dt
        if len(frames) == 1:
            self.billed_images += 1  # single-frame image-mode probe
        else:
            self.billed_video_frames += max(MIN_WINDOW_FRAMES, PACK_REPEAT * len(frames))  # packed keyframe MP4
        self.log.append({"kind": kind, "frames": sorted(frames), "ms": round(dt, 3)})
        return out

    def track(
        self,
        clip: Clip,
        f0: int,
        f1: int,
        seeds: dict[str, ObjMask],
        direction: Literal["forward", "backward", "both"],
        kind: str,
    ) -> dict[str, Track]:
        t0 = time.perf_counter()
        out = self.seg.track(clip, f0, f1, seeds, direction)
        dt = (time.perf_counter() - t0) * 1000.0
        self.calls += 1
        self.sam_ms += dt
        self.billed_video_frames += max(MIN_WINDOW_FRAMES, f1 - f0 + 1)
        self.log.append({"kind": kind, "window": [f0, f1], "direction": direction, "ms": round(dt, 3)})
        return out

    @property
    def billed_frames(self) -> int:
        return self.billed_video_frames + self.billed_images


@dataclass
class _Obs:
    """Every mask the fast path has actually received, plus the set of densely tracked frames."""

    n_frames: int
    masks: dict[str, dict[int, ObjMask]] = field(default_factory=dict)
    dense: set[int] = field(default_factory=set)
    backends: set[str] = field(default_factory=set)

    def add(self, tracks: dict[str, Track], dense_range: tuple[int, int] | None = None) -> None:
        for name, tr in tracks.items():
            self.backends.add(tr.backend)
            slot = self.masks.setdefault(name, {})
            for f, m in tr.frames.items():
                if 0 <= int(f) < self.n_frames:
                    slot[int(f)] = m
        if dense_range is not None:
            self.dense.update(range(dense_range[0], dense_range[1] + 1))

    def tracks(self) -> dict[str, Track]:
        backend = sorted(self.backends)[0] if self.backends else "fixture"
        return {
            name: Track(obj=name, frames=dict(sorted(fr.items())), backend=backend, direction="both", trace_id=f"fast-{name}")
            for name, fr in self.masks.items()
        }

    def seeds_at(self, frame: int) -> dict[str, ObjMask]:
        return {name: fr[frame] for name, fr in self.masks.items() if frame in fr}


# ----------------------------------------------------------------------------------------------------------------------
# Prompts, proxies, progress
# ----------------------------------------------------------------------------------------------------------------------


def object_label(name: str) -> str:
    """snake_case label used as the segmenter key (``cubeA`` -> ``cube_a``)."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def build_prompts(test: GreenTest) -> tuple[dict[str, list[str]], list[str]]:
    """Text prompts per declared object; effectors get the KD-18 alias set. Returns (prompts, alias_resolved_names)."""
    prompts: dict[str, list[str]] = {}
    alias_names: list[str] = []
    for decl in test.objects:
        cands: list[str] = []
        if decl.prompt:
            cands.append(decl.prompt)
        label = object_label(decl.name)
        cands += [decl.name, label, label.replace("_", " ")]
        cands += list(decl.aliases)
        if decl.role == "effector":
            cands += list(EFFECTOR_ALIAS_PROMPTS)
            if decl.name.lower().replace("_", " ") not in EFFECTOR_ALIAS_PROMPTS and not decl.prompt:
                alias_names.append(decl.name)
        seen: set[str] = set()
        prompts[decl.name] = [c for c in cands if not (c in seen or seen.add(c))]
    return prompts, alias_names


def _usable(m: ObjMask | None) -> bool:
    return m is not None and m.area_px > 0 and m.score >= 0.2


def contact_proxy(tracks: dict[str, Track], a: str, b: str, frame: int) -> Tri:
    """Static stand-in for ``moves_with`` at a keyframe: do the two boxes touch (with a 15% margin)?"""
    ta, tb = tracks.get(a), tracks.get(b)
    ma = ta.frames.get(frame) if ta else None
    mb = tb.frames.get(frame) if tb else None
    if not (_usable(ma) and _usable(mb)):
        return Tri.U
    assert ma is not None and mb is not None
    ax0, ay0, ax1, ay1 = ma.bbox_xyxy
    bx0, by0, bx1, by1 = mb.bbox_xyxy
    margin = CONTACT_MARGIN_FRAC * min(max(ax1 - ax0, ay1 - ay0), max(bx1 - bx0, by1 - by0))
    touching = ax0 - margin <= bx1 and bx0 - margin <= ax1 and ay0 - margin <= by1 and by0 - margin <= ay1
    return Tri.T if touching else Tri.F


def stillness_proxy(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    prev_frame: int | None,
    fps: float,
    ctx: dict[str, Any],
) -> Tri:
    """Static stand-in for ``dwell(A, ...)``: dwell.py only asks that A stays still for ``for_s`` (later args unused),
    so the proxy asks whether A moved less than ``max_speed_cm_s * dt + 2 sigma`` since the previous keyframe."""
    if prev_frame is None:
        return Tri.U
    a = atom.args[0]
    cur = get_object_coords(a, tracks, scale, frame, ctx)
    prev = get_object_coords(a, tracks, scale, prev_frame, ctx)
    if cur is None or prev is None:
        return Tri.U
    dt = (frame - prev_frame) / max(fps, 1e-6)
    if dt < get_param_value(atom.params, "for_s", 0.5):
        return Tri.U
    moved = euclidean_3d(cur[0], cur[1], cur[2], prev[0], prev[1], prev[2])
    allowed = get_param_value(atom.params, "max_speed_cm_s", 1.0) * dt + 2.0 * math.hypot(cur[3], prev[3])
    return Tri.T if moved <= allowed else Tri.F


def _proxy_atom(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    prev_frame: int | None,
    fps: float,
    ctx: dict[str, Any],
) -> Tri:
    if atom.kind == "looks":
        return Tri.U
    if atom.kind == "manual":
        return Tri.T
    if atom.name == "moves_with":
        return contact_proxy(tracks, atom.args[0], atom.args[1], frame)
    if atom.name == "dwell":
        return stillness_proxy(atom, tracks, scale, frame, prev_frame, fps, ctx)
    return evaluate_atom(atom, tracks, scale, frame, fps, ctx).tri


def _eval_context(test: GreenTest) -> dict[str, Any]:
    return {
        "object_sizes": {o.name: (o.size_cm or 4.0) for o in test.objects},
        "object_heights": {o.name: (o.size_cm or 4.0) for o in test.objects},
    }


def _fit_scale(clip: Clip, tracks: dict[str, Track], test: GreenTest, run_kwargs: dict[str, Any]) -> ScaleModel:
    if run_kwargs.get("camera") == "tier_c":
        scale: ScaleModel = TierCScaleModel(tracks=tracks, objects=test.objects, clip=clip)
    else:
        scale = fit_scale_model(
            clip=clip,
            tracks=tracks,
            objects=test.objects,
            cam_K=run_kwargs.get("cam_K"),
            cam_extrinsic=run_kwargs.get("cam_extrinsic"),
        )
    orig = scale.to_table_frame
    cache: dict[tuple[str, int], tuple[float, float, float, float]] = {}

    def cached(obj: str, frame: int) -> tuple[float, float, float, float]:
        key = (obj, frame)
        if key not in cache:
            cache[key] = orig(obj, frame)
        return cache[key]

    scale.to_table_frame = cached  # type: ignore[method-assign]
    return scale


def step_proxies(
    test: GreenTest, clip: Clip, tracks: dict[str, Track], frames: list[int], run_kwargs: dict[str, Any]
) -> dict[int, list[Tri]]:
    """Per keyframe, the static proxy of every step (Kleene)."""
    harmonized = _harmonize_track_keys(tracks, test)
    scale = _fit_scale(clip, harmonized, test, run_kwargs)
    ctx = _eval_context(test)
    out: dict[int, list[Tri]] = {}
    ordered = sorted(frames)
    for i, f in enumerate(ordered):
        prev = ordered[i - 1] if i > 0 else None
        row: list[Tri] = []
        for step in test.steps:
            values = {
                get_atom_key(a): _proxy_atom(a, harmonized, scale, f, prev, clip.fps, ctx)
                for a in _extract_atoms(step.expr)
            }
            row.append(evaluate_expr_tree(step.expr, values))
        out[f] = row
    return out


def progress_from_proxies(proxies: dict[int, list[Tri]], n_steps: int) -> list[int | None]:
    """Prefix-max progress: first keyframe at which each step's proxy held, in step order (monotone by construction)."""
    seen: list[int | None] = [None] * n_steps
    s = 0
    for f in sorted(proxies):
        while s < n_steps and proxies[f][s] == Tri.T:
            seen[s] = f
            s += 1
    return seen


def _carried_atoms(steps: list[Step], anchor: int, failing: int) -> list[Atom]:
    negated = _extract_negated_atom_keys(steps[failing].expr) if failing < len(steps) else set()
    out: list[Atom] = []
    for st in steps[: anchor + 1]:
        for a in _extract_positive_relational_atoms(st.expr):
            k = get_atom_key(a)
            if k not in negated and k not in {get_atom_key(x) for x in out}:
                out.append(a)
    return out


def _carry_start(steps: list[Step], anchor: int, failing: int) -> int | None:
    """Earliest step <= anchor that introduces a carried literal the engine checks in some step in (j, failing].

    engine/steps.py checks every carried literal on EVERY frame of a later step's search unless that step negates it,
    and breaks at the first F. Keyframes cannot locate that first F, so the dense window must start before the
    achievement of this step for t* to be exact.
    """
    for j in range(anchor + 1):
        for atom in _extract_positive_relational_atoms(steps[j].expr):
            key = get_atom_key(atom)
            if any(key not in _extract_negated_atom_keys(steps[t].expr) for t in range(j + 1, failing + 1)):
                return j
    return None


def _checks_carried(steps: list[Step], t: int) -> bool:
    """Does the search of step t check a literal carried from an earlier step?"""
    negated = _extract_negated_atom_keys(steps[t].expr)
    return any(
        get_atom_key(a) not in negated for st in steps[:t] for a in _extract_positive_relational_atoms(st.expr)
    )


def _support_frames(atom: Atom, fps: float) -> int:
    """Frames of history a temporal predicate reads (moves_with.py:62/89, dwell.py:56-85)."""
    if atom.kind != "pred":
        return 0
    if atom.name == "moves_with":
        return max(3, max(2, int(round(get_param_value(atom.params, "window_s", 0.33) * fps))))
    if atom.name == "dwell":
        for_s = get_param_value(atom.params, "for_s", 0.5)
        return int(math.ceil(for_s * fps)) + max(3, int(round(0.15 * fps)))
    return 0


def _support_ok(f: int, back: int, dense: set[int]) -> bool:
    return all(g in dense for g in range(max(0, f - back), f + 1))


# ----------------------------------------------------------------------------------------------------------------------
# Dense evaluator (mirror of pipeline.run.run lines 170-333, restricted to densely tracked frames)
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class _Eval:
    verdict: Verdict
    steps: list[StepResult]
    reasons: list[ReasonCode]
    events: list[Event]
    pred_frames: dict[str, list[PredFrame]]
    scale: ScaleModel


def _evaluate_dense(
    test: GreenTest,
    steps: list[Step],
    clip: Clip,
    tracks: dict[str, Track],
    dense: set[int],
    run_kwargs: dict[str, Any],
) -> _Eval:
    harmonized = _harmonize_track_keys(tracks, test)
    scale = _fit_scale(clip, harmonized, test, run_kwargs)

    raw_first_frame: np.ndarray | None = None
    if 0 in dense:
        try:
            cap = cv2.VideoCapture(clip.path_h264)
            ok, fr0 = cap.read()
            if ok:
                raw_first_frame = fr0
            cap.release()
        except Exception:
            raw_first_frame = None

    scene_occluded = False
    for decl in test.objects:
        if decl.role == "effector":
            continue
        tr = harmonized.get(decl.name)
        if tr is None or not tr.frames:
            scene_occluded = True
            break
        a0 = max(1, tr.frames[min(tr.frames)].area_px)
        for f in sorted(dense):
            m = tr.frames.get(f)
            if m is None or m.score < 0.5 or float(np.clip(1.0 - m.area_px / a0, 0.0, 1.0)) > 0.40:
                scene_occluded = True
                break
        if scene_occluded:
            break

    ctx = _eval_context(test)
    atoms: list[Atom] = []
    for st in steps:
        atoms.extend(_extract_atoms(st.expr))

    pred_frames: dict[str, list[PredFrame]] = {}
    triggered: set[ReasonCode] = set()
    for atom in atoms:
        key = get_atom_key(atom)
        if key in pred_frames:
            continue
        back = _support_frames(atom, clip.fps)
        rows: list[PredFrame] = []
        for f in range(clip.n_frames):
            if f not in dense or not _support_ok(f, back, dense):
                rows.append(PredFrame(frame=f, atom_key=key, tri=Tri.U, components=[], trace_id="tr_fast_untracked"))
                continue
            pf = evaluate_atom(atom, harmonized, scale, f, clip.fps, context=ctx)
            for c in pf.components:
                c.margin = round(c.margin, 6)
                c.sigma = round(c.sigma, 6)
            gated, reasons = apply_gates(
                pf.components, harmonized, scale, f, raw_frame=raw_first_frame if f == 0 else None
            )
            triggered.update(reasons)
            rows.append(
                PredFrame(frame=f, atom_key=key, tri=conjoin_components(gated), components=gated, trace_id=pf.trace_id)
            )
        pred_frames[key] = rows

    verdict, step_results, top_reasons, events = evaluate_step_chain(steps, pred_frames, clip.fps)

    final_reasons: list[ReasonCode] = []
    if scene_occluded and verdict != Verdict.PASS:
        verdict = Verdict.CANT_TELL
        final_reasons = [ReasonCode.OCCLUDED]
        for s in step_results:
            if s.verdict in (Verdict.FAIL, None):
                s.verdict = Verdict.CANT_TELL
                s.reasons = [ReasonCode.OCCLUDED]
    elif verdict == Verdict.CANT_TELL:
        if top_reasons:
            final_reasons = list(top_reasons)
        else:
            for s in step_results:
                final_reasons.extend(s.reasons)
            if not final_reasons and triggered:
                final_reasons = list(triggered)
            if not final_reasons:
                final_reasons = [ReasonCode.NOT_VISIBLE]
    return _Eval(verdict, step_results, final_reasons, events, pred_frames, scale)


# ----------------------------------------------------------------------------------------------------------------------
# Fast path
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class _Ctx:
    test: GreenTest
    test_sha: str
    clip: Clip
    meter: _Meter
    obs: _Obs
    prompts: dict[str, list[str]]
    run_kwargs: dict[str, Any]
    seed: int
    guards: list[str] = field(default_factory=list)
    probes: list[int] = field(default_factory=list)
    stage1: list[int] = field(default_factory=list)
    window: tuple[int, int] = (0, 0)
    timings: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.labels = {d.name: object_label(d.name) for d in self.test.objects}
        self.unlabels = {v: k for k, v in self.labels.items()}
        self.label_prompts = {self.labels[k]: v for k, v in self.prompts.items()}

    def _unlabel(self, raw: dict[str, Track]) -> dict[str, Track]:
        out: dict[str, Track] = {}
        for key, tr in raw.items():
            name = self.unlabels.get(key, key)
            out[name] = tr if name == key else tr.model_copy(update={"obj": name})
        return out

    def seg(self, frames: list[int], kind: str) -> dict[str, Track]:
        return self._unlabel(self.meter.segment(self.clip, frames, self.label_prompts, kind))

    def trk(
        self, w0: int, w1: int, seeds: dict[str, ObjMask], direction: Literal["forward", "backward", "both"], kind: str
    ) -> dict[str, Track]:
        labelled = {self.labels.get(k, k): v for k, v in seeds.items()}
        return self._unlabel(self.meter.track(self.clip, w0, w1, labelled, direction, kind))


def _early_limit(step: Step, fps: float) -> int:
    n_on = max(2, int(round(0.10 * fps)))
    back = max([_support_frames(a, fps) for a in _extract_atoms(step.expr)] + [0])
    return back + n_on + 2


def _ensure_seeds(ctx: _Ctx, frames: list[int]) -> None:
    """Make sure every window's last frame has masks (one packed/image call for the frames still missing)."""
    declared = [d.name for d in ctx.test.objects]
    need = sorted({f for f in frames if any(f not in ctx.obs.masks.get(name, {}) for name in declared)})
    if need:
        ctx.obs.add(ctx.seg(need, kind="seed"))


def _track_window(ctx: _Ctx, w0: int, w1: int, kind: str) -> None:
    seeds = ctx.obs.seeds_at(w1)
    ctx.obs.add(ctx.trk(w0, w1, seeds, "backward", kind=kind), dense_range=(w0, w1))


def _full_fallback(ctx: _Ctx, reason: str) -> RunResult:
    """Dense pass over the whole clip, evaluated by ``pipeline.run.run`` (the full path)."""
    ctx.guards.append(reason)
    t0 = time.perf_counter()
    n = ctx.clip.n_frames
    seeds = ctx.obs.seeds_at(n - 1)
    if not seeds:
        ctx.obs.add(ctx.seg([n - 1], kind="seed"))
        seeds = ctx.obs.seeds_at(n - 1)
    for name, fr in ctx.obs.masks.items():
        if name not in seeds and fr:
            seeds[name] = fr[max(fr)]
    dense = ctx.trk(0, n - 1, seeds, "both", kind="full_fallback")
    ctx.obs.add(dense, dense_range=(0, n - 1))
    ctx.window = (0, n - 1)
    ctx.timings["fallback_ms"] = ctx.timings.get("fallback_ms", 0.0) + (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    kwargs = {k: v for k, v in ctx.run_kwargs.items() if k in _RUN_KWARGS}
    res = run_full(ctx.test, ctx.clip, tracks=dense, **kwargs)
    ctx.timings["eval_ms"] = ctx.timings.get("eval_ms", 0.0) + (time.perf_counter() - t1) * 1000.0
    return res


def _finalize_fallback(ctx: _Ctx, res: RunResult) -> RunResult:
    badges = list(res.badges) + [FAST_BADGE, FALLBACK_BADGE]
    if "fixture" in ctx.obs.backends and "[FIXTURE REPLAY]" not in badges:
        badges.append("[FIXTURE REPLAY]")
    backends = dict(res.backends)
    backends.update(_backend_info(ctx, mode="fast->full_fallback"))
    out = res.model_copy(update={"badges": badges, "backends": backends, "is_fixture": res.is_fixture or "fixture" in ctx.obs.backends})
    _write_result(out, Path(res.trace_path).parent)
    return out


def _backend_info(ctx: _Ctx, mode: str) -> dict[str, str]:
    perception = ",".join(sorted(ctx.obs.backends)) or "none"
    return {
        "perception": perception,
        "mode": mode,
        "latency_kind": LATENCY_KIND_FIXTURE if "fixture" in ctx.obs.backends else LATENCY_KIND_LIVE,
        "seed": str(ctx.seed),
        "sam_calls": str(ctx.meter.calls),
        "sam_billed_video_frames": str(ctx.meter.billed_video_frames),
        "sam_billed_images": str(ctx.meter.billed_images),
    }


def _write_result(res: RunResult, out_dir: Path) -> None:
    payload = res.model_dump_json(indent=2)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(payload, encoding="utf-8")
    dot = Path(".Kodiac")
    dot.mkdir(parents=True, exist_ok=True)
    (dot / "last_verdict.json").write_text(payload, encoding="utf-8")


def _assemble(
    ctx: _Ctx,
    ev: _Eval,
    first_step: int,
    seen: list[int | None],
    anchor_from_start: bool,
    eval_ms: float,
    total_t0: float,
) -> RunResult:
    """Build the RunResult for an accepted dense-window evaluation (step indices re-attached to the full test)."""
    steps_out: list[StepResult] = []
    for i in range(first_step):
        st = ctx.test.steps[i]
        steps_out.append(
            StepResult(
                index=st.index,
                name=st.name,
                verdict=None,
                evidence=[f"fast path: step proxy held at keyframe {seen[i]}; not densely re-evaluated (two-stage bisect)"],
            )
        )
    events = list(ev.events)
    for j, sr in enumerate(ev.steps):
        if j == 0 and first_step > 0 and anchor_from_start and sr.verdict == Verdict.PASS:
            w0 = ctx.window[0]
            sr = sr.model_copy(
                update={
                    "frame": None,
                    "t_s": None,
                    "evidence": [
                        f"fast path: condition held densely from window start f={w0}; achieved at or before f={w0} "
                        f"(proxy first held at keyframe {seen[first_step]})"
                    ],
                }
            )
            events = [e for e in events if e.step != sr.index]
        steps_out.append(sr)

    nonce = secrets.token_hex(8)
    out_dir = Path(ctx.run_kwargs["output_dir"]) if ctx.run_kwargs.get("output_dir") else Path("runs") / nonce
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    with TraceWriter(trace_path) as writer:
        for e in events:
            writer.write_event(e)
        for key, rows in ev.pred_frames.items():
            for pf in rows:
                if pf.frame in ctx.obs.dense:
                    writer.write_pred_frame(pf.frame, key, pf)

    badges = [FAST_BADGE]
    if "fixture" in ctx.obs.backends:
        badges.append("[FIXTURE REPLAY]")
    for b in getattr(ev.scale, "badges", []):
        if b not in badges:
            badges.append(b)
    backends = _backend_info(ctx, mode="fast")
    backends["scale_tier"] = str(getattr(ev.scale, "tier", "C"))
    exit_code: Literal[0, 1, 2, 3] = 0 if ev.verdict == Verdict.PASS else (1 if ev.verdict == Verdict.FAIL else 2)

    def build(card_path: str | None, render_ms: float) -> RunResult:
        return RunResult(
            run_id=nonce,
            test_name=ctx.test.name,
            test_sha256=ctx.test_sha,
            config_sha256="0" * 64,
            clip=ctx.clip.ref,
            verdict=ev.verdict,
            exit_code=exit_code,
            steps=steps_out,
            reasons=ev.reasons,
            events=events,
            timings_ms={
                "segment_ms": int(round(ctx.meter.sam_ms)),
                "eval_ms": int(round(eval_ms)),
                "render_ms": int(round(render_ms)),
                "total_ms": int(round((time.perf_counter() - total_t0) * 1000)),
            },
            backends=backends,
            badges=badges,
            nonce=nonce,
            is_fixture="fixture" in ctx.obs.backends,
            card_path=card_path,
            trace_path=str(trace_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    result = build(None, 0.0)
    if ctx.run_kwargs.get("render_card"):
        t_r = time.perf_counter()
        decisive = next((s.frame for s in steps_out if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL) and s.frame is not None), None)
        if decisive is None:
            decisive = max([s.frame for s in steps_out if s.frame is not None] + [0])
        frame_bgr: np.ndarray | None = None
        try:
            cap = cv2.VideoCapture(ctx.clip.path_h264)
            cap.set(cv2.CAP_PROP_POS_FRAMES, decisive)
            ok, img = cap.read()
            if ok:
                frame_bgr = img
            cap.release()
        except Exception:
            frame_bgr = None
        if frame_bgr is None:
            frame_bgr = np.full((ctx.clip.height, ctx.clip.width, 3), 40, dtype=np.uint8)
        card = out_dir / "card.png"
        render_verdict_card_v1(result, ctx.clip, frame_bgr, card)
        result = build(str(card), (time.perf_counter() - t_r) * 1000.0)
    _write_result(result, out_dir)
    return result


def _window_problem(
    ev: _Eval, has_anchor: bool, anchor_seen: int | None, w0: int, w1: int, early: int
) -> tuple[str | None, bool]:
    """Returns (problem, anchor_from_start). Problems: anchor_unverified | anchor_late | contradicted | outside."""
    anchor_from_start = False
    if has_anchor:
        a = ev.steps[0]
        if a.verdict != Verdict.PASS or a.frame is None:
            return "anchor_unverified", False
        anchor_from_start = a.frame <= w0 + early
        if not anchor_from_start and anchor_seen is not None and w0 > anchor_seen:
            return "anchor_late", False
    bad = next((s for s in ev.steps if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL)), None)
    if bad is None:
        return "contradicted", anchor_from_start
    if bad.verdict == Verdict.CANT_TELL and w0 > 0:
        return "gap_before", anchor_from_start
    if bad.frame is None or not (w0 <= bad.frame <= w1):
        return "outside", anchor_from_start
    return None, anchor_from_start


def run_fast(
    test: GreenTest | Path,
    clip: Clip,
    segmenter: Segmenter,
    *,
    k_keyframes: int = 6,
    budget_calls: int = 6,
    seed: int = 0,
    **run_kwargs: Any,
) -> FastRun:
    """Two-stage bisect fast path. ``run_kwargs`` (camera, cam_K, cam_extrinsic, output_dir, render_card) pass through
    to ``pipeline.run.run`` on fallback and drive the dense evaluator identically.

    The plan is a pure function of (test, clip, segmenter outputs, k_keyframes, budget_calls); ``seed`` is recorded in
    ``RunResult.backends["seed"]`` for provenance (no stochastic step exists in the plan).
    """
    unknown = set(run_kwargs) - _RUN_KWARGS
    if unknown:
        raise TypeError(f"run_fast got unsupported keyword(s): {sorted(unknown)}")
    total_t0 = time.perf_counter()
    test_obj, test_sha = load_green_test(test)
    prompts, alias_names = build_prompts(test_obj)
    ctx = _Ctx(
        test=test_obj,
        test_sha=test_sha,
        clip=clip,
        meter=_Meter(seg=segmenter, budget=budget_calls),
        obs=_Obs(n_frames=clip.n_frames),
        prompts=prompts,
        run_kwargs=dict(run_kwargs),
        seed=seed,
    )
    n = clip.n_frames
    n_steps = len(test_obj.steps)

    def done(result: RunResult) -> FastRun:
        timings = {k: int(round(v)) for k, v in ctx.timings.items()}
        timings["sam_ms"] = int(round(ctx.meter.sam_ms))
        timings["total_ms"] = int(round((time.perf_counter() - total_t0) * 1000))
        plan = BisectPlan(
            stage1_frames=ctx.stage1,
            stage15_probes=ctx.probes,
            window=ctx.window,
            n_sam_calls=ctx.meter.calls,
            guards_fired=ctx.guards,
        )
        return FastRun(result=result, plan=plan, stage_timings_ms=timings, billed_frames=ctx.meter.billed_frames)

    def fallback(reason: str) -> FastRun:
        return done(_finalize_fallback(ctx, _full_fallback(ctx, reason)))

    if n <= MIN_BISECT_FRAMES or n_steps == 0:
        return fallback(f"G-budget:short_clip_direct(n_frames={n}<={MIN_BISECT_FRAMES})")

    # ---- Stage 1: keyframes in one call -----------------------------------------------------------------------------
    t1 = time.perf_counter()
    kfs = keyframe_indices(n, clip.fps, k_keyframes)
    ctx.stage1 = kfs
    ctx.obs.add(ctx.seg(kfs, kind="stage1_keyframes"))
    for name in alias_names:
        if ctx.obs.masks.get(name):
            ctx.guards.append(f"G-alias:effector_resolved({name}<-{'|'.join(EFFECTOR_ALIAS_PROMPTS)})")
    lost = [
        d.name
        for d in test_obj.objects
        if d.role != "effector" and any(f not in ctx.obs.masks.get(d.name, {}) for f in kfs)
    ]
    if lost:
        ctx.timings["stage1_ms"] = (time.perf_counter() - t1) * 1000.0
        return fallback(f"G-miss:object_lost_at_keyframes({','.join(lost)})")
    proxies = step_proxies(test_obj, clip, ctx.obs.tracks(), kfs, ctx.run_kwargs)
    seen = progress_from_proxies(proxies, n_steps)
    k = sum(1 for s in seen if s is not None)
    harmonized_kf = _harmonize_track_keys(ctx.obs.tracks(), test_obj)
    ctx.timings["stage1_ms"] = (time.perf_counter() - t1) * 1000.0

    def bracket_start(j: int) -> int:
        sj = seen[j]
        assert sj is not None
        prev = max([f for f in kfs if f < sj] + [0])
        return prev - BRACKET_PAD_FRAMES - _early_limit(test_obj.steps[j], clip.fps)

    def bracket_end(j: int) -> int:
        sj = seen[j]
        assert sj is not None
        return sj + BRACKET_PAD_FRAMES

    # ---- G-pass: every step's proxy held -> dense verification windows ----------------------------------------------
    if k == n_steps:
        t2 = time.perf_counter()
        windows = [pad_window(bracket_start(j), bracket_end(j), n) for j in range(n_steps)]
        # A step whose search checks a carried literal is covered without gaps from the previous step's bracket to its
        # own: the engine fails at the first F of a carried literal, which keyframes cannot see.
        windows += [
            pad_window(bracket_start(t - 1), bracket_end(t), n)
            for t in range(1, n_steps)
            if _checks_carried(test_obj.steps, t)
        ]
        merged = _merge_windows(windows)
        if ctx.meter.would_exceed(1 + len(merged)):
            ctx.timings["verify_ms"] = (time.perf_counter() - t2) * 1000.0
            return fallback(f"G-budget:verification_windows({len(merged)})_exceed_budget({budget_calls})")
        ctx.guards.append(f"G-pass:dense_verification_windows({len(merged)})")
        _ensure_seeds(ctx, [w1 for _, w1 in merged])
        for w0, w1 in merged:
            _track_window(ctx, w0, w1, kind="verify_window")
        ctx.window = (merged[0][0], merged[-1][1])
        ctx.timings["verify_ms"] = (time.perf_counter() - t2) * 1000.0
        te = time.perf_counter()
        ev = _evaluate_dense(test_obj, test_obj.steps, clip, ctx.obs.tracks(), ctx.obs.dense, ctx.run_kwargs)
        eval_ms = (time.perf_counter() - te) * 1000.0
        ctx.timings["eval_ms"] = eval_ms
        if ev.verdict != Verdict.PASS:
            return fallback(f"G-pass:verification_not_pass({ev.verdict.value})")
        return done(_assemble(ctx, ev, 0, seen, False, eval_ms, total_t0))

    # ---- FAIL candidate: failing step k, anchor k-1 -----------------------------------------------------------------
    anchor = k - 1
    has_anchor = anchor >= 0
    anchor_seen = seen[anchor] if has_anchor else None
    carried = _carried_atoms(test_obj.steps, anchor, k) if has_anchor else []
    lead = BRACKET_PAD_FRAMES + (_early_limit(test_obj.steps[anchor], clip.fps) if has_anchor else 0)

    t15 = time.perf_counter()
    bracket: tuple[int, int] | None = None
    target: Atom | None = None
    for atom in carried:
        after = [f for f in kfs if anchor_seen is not None and f > anchor_seen]
        vals = [(f, contact_proxy(harmonized_kf, atom.args[0], atom.args[1], f)) for f in after]
        first_f = next((i for i, (_, v) in enumerate(vals) if v == Tri.F), None)
        if first_f is None:
            continue
        f_b = vals[first_f][0]
        f_a = max([f for f in kfs if f < f_b])
        if any(v == Tri.T for _, v in vals[first_f + 1 :]):
            ctx.guards.append(f"G-alias:carried_flicker({get_atom_key(atom)})->earliest_bracket")
        if bracket is None or f_b < bracket[1]:
            bracket, target = (f_a, f_b), atom

    if bracket is not None and target is not None:
        f_a, f_b = bracket
        while f_b - f_a > HALVE_UNTIL_FRAMES:
            if ctx.meter.would_exceed():
                ctx.timings["stage15_ms"] = (time.perf_counter() - t15) * 1000.0
                return fallback(f"G-budget:calls_exceeded_at_probe(budget={budget_calls})")
            m = (f_a + f_b) // 2
            ctx.probes.append(m)
            ctx.obs.add(ctx.seg([m], kind="stage15_probe"))
            v = contact_proxy(_harmonize_track_keys(ctx.obs.tracks(), test_obj), target.args[0], target.args[1], m)
            if v == Tri.F:
                f_b = m
            elif v == Tri.T:
                f_a = m
            else:
                ctx.guards.append(f"G-miss:probe_unresolved(f={m})->keep_bracket")
                break
        start, end = f_a - lead, f_b + BRACKET_PAD_FRAMES
    else:
        # Failing step never held at any keyframe: the engine decides "unmet" at the last frame, so the window ends there.
        start, end = n - 1, n - 1
    # A carried literal checked up to the failure must be watched densely from the step that introduced it.
    carry_start = _carry_start(test_obj.steps, anchor, k) if has_anchor else None
    if carry_start is not None:
        start = min(start, bracket_start(carry_start))
        ctx.guards.append(f"carry-window:dense_from_step({test_obj.steps[carry_start].name})")
    w0, w1 = pad_window(start, end, n)
    ctx.timings["stage15_ms"] = (time.perf_counter() - t15) * 1000.0

    # ---- Stage 2: dense backward window + residual evaluation (G-miss extends back <= 2x) ------------------------
    t2 = time.perf_counter()
    if ctx.meter.would_exceed(2):
        ctx.timings["stage2_ms"] = (time.perf_counter() - t2) * 1000.0
        return fallback(f"G-budget:calls_exceeded_at_stage2(budget={budget_calls})")
    _ensure_seeds(ctx, [w1])
    _track_window(ctx, w0, w1, kind="stage2_window")
    ctx.window = (w0, w1)
    ctx.timings["stage2_ms"] = (time.perf_counter() - t2) * 1000.0

    first_step = carry_start if carry_start is not None else (anchor if has_anchor else 0)
    residual = test_obj.steps[first_step:]
    anchor_seen = seen[first_step] if has_anchor else None
    early = _early_limit(test_obj.steps[first_step], clip.fps) if has_anchor else 0
    eval_ms = 0.0
    for attempt in range(G_MISS_MAX_EXTENSIONS + 1):
        te = time.perf_counter()
        ev = _evaluate_dense(test_obj, residual, clip, ctx.obs.tracks(), ctx.obs.dense, ctx.run_kwargs)
        eval_ms += (time.perf_counter() - te) * 1000.0
        ctx.timings["eval_ms"] = eval_ms
        problem, from_start = _window_problem(ev, has_anchor, anchor_seen, ctx.window[0], ctx.window[1], early)
        if problem is None:
            return done(_assemble(ctx, ev, first_step, seen, from_start, eval_ms, total_t0))
        if problem in ("contradicted", "outside") or ctx.window[0] == 0 or attempt == G_MISS_MAX_EXTENSIONS:
            return fallback(f"G-miss:{problem}(window={ctx.window[0]}-{ctx.window[1]})")
        if ctx.meter.would_exceed():
            return fallback(f"G-budget:calls_exceeded_at_extension(budget={budget_calls})")
        old0 = ctx.window[0]
        new0 = max(0, old0 - G_MISS_EXTEND_FRAMES)
        ctx.guards.append(f"G-miss:{problem}->extend_back({new0}-{old0})")
        te2 = time.perf_counter()
        _track_window(ctx, new0, old0, kind="g_miss_extension")
        ctx.window = (new0, ctx.window[1])
        ctx.timings["stage2_ms"] = ctx.timings.get("stage2_ms", 0.0) + (time.perf_counter() - te2) * 1000.0
    return fallback("G-miss:extensions_exhausted")


__all__ = [
    "BisectPlan",
    "FastRun",
    "build_prompts",
    "contact_proxy",
    "keyframe_indices",
    "pad_window",
    "progress_from_proxies",
    "run_fast",
    "step_proxies",
]
