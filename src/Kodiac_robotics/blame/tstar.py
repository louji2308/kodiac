"""t* refinement inside the dense window, with a seeded bootstrap sigma (ARCHITECTURE §5.4, §7.3).

Onset convention (git-bisect style): ``t*`` is the **first bad frame**, i.e. the first frame whose value is off the
pre-change regime.

* ``detach_onset`` (``moves_with`` True->False): ``t* = 1 + max{t <= t_confirm : R(t) <= sigma_R(t)}`` where ``R`` is
  the measured relative displacement (``moves_with.slip`` value) and ``t_confirm`` is the onset of the literal's
  final False run.
* ``piecewise_breakpoint`` (threshold components): continuous two-segment (hinge) least-squares fit
  ``y = a + b t + c max(0, t - tau)`` over the window; ``t* = tau + 1`` (the kink ``tau`` is the last frame on the
  old line).
* ``softscore_argmax`` (unmet conditions): ``t*`` = argmax of the condition's softscore (already computed by the
  transition finder).

``sigma_frames`` is the standard deviation of ``t*`` over ``n_boot`` seeded parametric-bootstrap replicates in which
each measurement is perturbed by its own reported sigma (and, for the breakpoint fit, at least the fit's RMS
residual). Quantisation floor: ``sigma_frames >= 0.5`` frame, so it is never reported as 0.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel

from Kodiac_robotics.blame.transitions import (
    Transition,
    component_score,
    index_pred_frames,
    reliable_components,
)
from Kodiac_robotics.contracts.core import Component, PredFrame

SIGMA_FLOOR_FRAMES = 0.5


class TStar(BaseModel):
    """Refined failure onset."""

    frame: int
    t_s: float
    sigma_frames: float
    method: Literal["detach_onset", "piecewise_breakpoint", "softscore_argmax"]


def _component_series(
    pred_frames: list[PredFrame], literal: str, component: str | None, window: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(frames, values, sigmas) of one component of one atom inside the window (reliable values only)."""
    key = literal[4:] if literal.startswith("not ") else literal
    index = index_pred_frames(pred_frames)
    slot = index.get(key, {})
    fs: list[int] = []
    vs: list[float] = []
    ss: list[float] = []
    lo, hi = window
    for f in range(lo, hi + 1):
        pf = slot.get(f)
        if pf is None:
            continue
        comps = reliable_components(pf)
        c: Component | None = None
        if component is not None:
            c = next((x for x in comps if x.name == component), None)
        elif comps:
            c = min(comps, key=component_score)
        if c is None:
            continue
        fs.append(f)
        vs.append(float(c.value))
        ss.append(float(c.sigma))
    return np.asarray(fs, dtype=int), np.asarray(vs, dtype=float), np.asarray(ss, dtype=float)


def detach_onset(frames: np.ndarray, r: np.ndarray, sigma_r: np.ndarray, t_confirm: int) -> int | None:
    """``1 + max{t <= t_confirm : R(t) <= sigma_R(t)}``; None if R never sat inside the noise band."""
    mask = (frames <= t_confirm) & (r <= sigma_r)
    if not np.any(mask):
        return None
    return int(frames[mask].max()) + 1


def _hinge_designs(frames: np.ndarray) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """(tau, design A, pseudo-inverse of A) for every admissible kink (>= 2 samples on each side)."""
    n = len(frames)
    t = frames.astype(float)
    out: list[tuple[int, np.ndarray, np.ndarray]] = []
    for tau in frames[1:-2]:
        a = np.column_stack([np.ones(n), t, np.maximum(0.0, t - float(tau))])
        out.append((int(tau), a, np.linalg.pinv(a)))
    return out


def hinge_breakpoint_batch(frames: np.ndarray, ys: np.ndarray) -> np.ndarray | None:
    """Best kink per column of ``ys`` (shape (n, B)); earliest kink wins ties. None if < 4 samples."""
    if len(frames) < 4:
        return None
    designs = _hinge_designs(frames)
    sse = np.empty((len(designs), ys.shape[1]), dtype=float)
    for i, (_, a, pinv) in enumerate(designs):
        resid = ys - a @ (pinv @ ys)
        sse[i] = np.sum(resid**2, axis=0)
    taus = np.asarray([d[0] for d in designs], dtype=int)
    # Earliest kink among (numerically) tied minima: noise-free ramps must be frame-exact.
    best = sse.min(axis=0)
    tol = 1e-9 * np.maximum(1.0, best)
    winners = np.argmax(sse <= best + tol, axis=0)
    return taus[winners]


def hinge_breakpoint(frames: np.ndarray, y: np.ndarray) -> tuple[int, float, np.ndarray] | None:
    """Best kink ``tau`` of a continuous 2-segment linear fit. Returns (tau, sse, fitted) or None."""
    if len(frames) < 4:
        return None
    best: tuple[int, float, np.ndarray] | None = None
    for tau, a, pinv in _hinge_designs(frames):
        fitted = a @ (pinv @ y)
        sse = float(np.sum((y - fitted) ** 2))
        if best is None or sse < best[1] - 1e-9 * max(1.0, best[1]):
            best = (tau, sse, fitted)
    return best


def _honest_sigma(samples: list[int]) -> float:
    if len(samples) < 2:
        return SIGMA_FLOOR_FRAMES
    return float(max(SIGMA_FLOOR_FRAMES, float(np.std(np.asarray(samples, dtype=float), ddof=1))))


def refine_tstar(
    transition: Transition,
    pred_frames: list[PredFrame],
    fps: float,
    window: tuple[int, int],
    n_boot: int = 200,
    seed: int = 0,
) -> TStar:
    """Refine the transition frame inside ``window`` (inclusive) and estimate sigma_t* by seeded bootstrap."""
    rng = np.random.default_rng(seed)
    lo, hi = int(window[0]), int(window[1])
    if hi < lo:
        lo, hi = hi, lo

    if transition.cls == "unmet":
        return _refine_softscore(transition, pred_frames, fps, (lo, hi), n_boot, rng)

    is_moves_with = transition.literal.removeprefix("not ").startswith("moves_with(")
    if is_moves_with and transition.cls == "broken_prerequisite":
        frames, r, s = _component_series(pred_frames, transition.literal, "moves_with.slip", (lo, hi))
        onset = detach_onset(frames, r, s, transition.t_frame) if len(frames) else None
        if onset is not None and onset <= transition.t_frame:
            boots: list[int] = []
            for _ in range(n_boot):
                r_b = r + rng.normal(0.0, 1.0, size=len(r)) * s
                ob = detach_onset(frames, r_b, s, transition.t_frame)
                if ob is not None:
                    boots.append(ob)
            return TStar(
                frame=onset,
                t_s=round(onset / fps, 4),
                sigma_frames=round(_honest_sigma(boots), 4),
                method="detach_onset",
            )
        # R never sat inside its noise band before the confirmed break (or the break was a motionless F):
        # fall back to the hinge fit on the same series.

    return _refine_breakpoint(transition, pred_frames, fps, (lo, hi), n_boot, rng)


def _refine_breakpoint(
    transition: Transition,
    pred_frames: list[PredFrame],
    fps: float,
    window: tuple[int, int],
    n_boot: int,
    rng: np.random.Generator,
) -> TStar:
    frames, values, sigmas = _component_series(pred_frames, transition.literal, transition.component, window)
    fit = hinge_breakpoint(frames, values) if len(frames) >= 4 else None
    if fit is None:
        f = int(transition.t_frame)
        return TStar(frame=f, t_s=round(f / fps, 4), sigma_frames=SIGMA_FLOOR_FRAMES * 2, method="piecewise_breakpoint")
    tau, sse, fitted = fit
    onset = tau + 1
    rms = float(np.sqrt(sse / max(1, len(frames) - 3)))
    noise = np.maximum(sigmas, rms)
    boots: list[int] = []
    if n_boot > 0 and float(noise.max()) > 0.0:
        ys = fitted[:, None] + rng.normal(0.0, 1.0, size=(len(frames), n_boot)) * noise[:, None]
        taus_b = hinge_breakpoint_batch(frames, ys)
        if taus_b is not None:
            boots = [int(x) + 1 for x in taus_b.tolist()]
    return TStar(
        frame=onset,
        t_s=round(onset / fps, 4),
        sigma_frames=round(_honest_sigma(boots), 4),
        method="piecewise_breakpoint",
    )


def _refine_softscore(
    transition: Transition,
    pred_frames: list[PredFrame],
    fps: float,
    window: tuple[int, int],
    n_boot: int,
    rng: np.random.Generator,
) -> TStar:
    lo, hi = window
    scores = {f: v for f, v in transition._softscore.items() if lo <= f <= hi}
    if not scores:
        # Transition built without the step softscore (e.g. deserialized): use the cause component alone.
        frames, values, sigmas = _component_series(pred_frames, transition.literal, transition.component, window)
        index = index_pred_frames(pred_frames)
        key = transition.literal[4:] if transition.literal.startswith("not ") else transition.literal
        for f in frames.tolist():
            pf = index.get(key, {}).get(f)
            if pf is None:
                continue
            comp = next((c for c in reliable_components(pf) if c.name == transition.component), None)
            if comp is not None:
                scores[f] = component_score(comp)
    if not scores:
        f = int(transition.t_frame)
        return TStar(frame=f, t_s=round(f / fps, 4), sigma_frames=SIGMA_FLOOR_FRAMES * 2, method="softscore_argmax")
    fr = np.asarray(sorted(scores), dtype=int)
    sc = np.asarray([scores[f] for f in fr.tolist()], dtype=float)
    onset = int(fr[int(np.argmax(sc))])
    boots: list[int] = []
    # The softscore is in sigma units, so unit-variance noise is the matching parametric perturbation.
    for _ in range(n_boot):
        boots.append(int(fr[int(np.argmax(sc + rng.normal(0.0, 1.0, size=len(sc))))]))
    return TStar(
        frame=onset,
        t_s=round(onset / fps, 4),
        sigma_frames=round(_honest_sigma(boots), 4),
        method="softscore_argmax",
    )


__all__ = ["TStar", "refine_tstar", "detach_onset", "hinge_breakpoint", "SIGMA_FLOOR_FRAMES"]
