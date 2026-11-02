"""t* refinement: frame-exact on synthetic ramps with known onset, honest (non-zero) bootstrap sigma."""

from __future__ import annotations

import numpy as np
import pytest

from Kodiac_robotics.blame.transitions import Transition, find_transition
from Kodiac_robotics.blame.tstar import (
    SIGMA_FLOOR_FRAMES,
    detach_onset,
    hinge_breakpoint,
    refine_tstar,
)
from Kodiac_robotics.contracts.core import Component, PredFrame, Tri

from .test_transitions import FPS, scenario


def ramp_frames(key: str, comp: str, unit: str, values: np.ndarray, threshold: float, sigma: float,
                upper: bool) -> list[PredFrame]:
    out: list[PredFrame] = []
    for f, v in enumerate(values.tolist()):
        margin = (threshold - v) if upper else (v - threshold)
        tri = Tri.T if margin > 0 else Tri.F
        c = Component(name=comp, value=v, threshold=threshold, margin=margin, sigma=sigma, unit=unit, tri=tri)
        out.append(PredFrame(frame=f, atom_key=key, tri=tri, components=[c], trace_id=f"tr{f}"))
    return out


def ramp(n: int, onset: int, level: float, slope: float) -> np.ndarray:
    """Constant before ``onset``; the first value off the line is at ``onset`` (first bad frame)."""
    t = np.arange(n, dtype=float)
    return level + slope * np.maximum(0.0, t - (onset - 1))


@pytest.mark.parametrize(
    ("n", "onset", "level", "slope", "noise"),
    [
        (60, 23, 8.0, 0.35, 0.0),    # lifted height dropping (noise-free)
        (45, 30, 0.5, 0.8, 0.0),     # xy offset growing late in the window
        (80, 12, 6.0, -0.25, 0.0),   # early onset, slow ramp
        (60, 37, 2.0, 0.6, 0.01),    # small seeded noise vs a steep ramp
    ],
)
def test_piecewise_breakpoint_is_frame_exact_on_ramps(n: int, onset: int, level: float, slope: float,
                                                     noise: float) -> None:
    y = ramp(n, onset, level, slope)
    if noise:
        y = y + np.random.default_rng(7).normal(0.0, noise, size=n)
    frames = ramp_frames("lifted(cubeA)", "lifted.height", "cm", y, 2.0, sigma=max(noise, 0.0), upper=False)
    tr = Transition(cls="broken_prerequisite", step_index=1, step_name="place", literal="lifted(cubeA)",
                    t_frame=min(n - 1, onset + 3), component="lifted.height")
    ts = refine_tstar(tr, frames, FPS, (0, n - 1), n_boot=200, seed=0)
    assert ts.method == "piecewise_breakpoint"
    assert ts.frame == onset
    assert ts.t_s == pytest.approx(onset / FPS, abs=1e-4)
    assert ts.sigma_frames >= SIGMA_FLOOR_FRAMES > 0


def test_hinge_breakpoint_direct() -> None:
    frames = np.arange(30)
    y = ramp(30, 11, 1.0, 0.5)
    fit = hinge_breakpoint(frames, y)
    assert fit is not None and fit[0] + 1 == 11 and fit[1] == pytest.approx(0.0, abs=1e-9)


def test_detach_onset_rule() -> None:
    frames = np.arange(20)
    r = np.where(frames < 9, 0.02, 0.4 * (frames - 8))
    s = np.full(20, 0.14)
    assert detach_onset(frames, r, s, t_confirm=12) == 9
    assert detach_onset(frames, np.full(20, 5.0), s, t_confirm=12) is None


def test_detach_onset_on_synthetic_release_is_frame_exact_with_positive_sigma() -> None:
    sc = scenario("b01_early_release")
    tr = find_transition(sc.result, sc.frames, sc.test, FPS)
    assert tr is not None and tr.cls == "broken_prerequisite"
    flat = [pf for lst in sc.frames.values() for pf in lst]
    ts = refine_tstar(tr, flat, FPS, (max(23, tr.t_frame - 30), tr.t_frame + 3), n_boot=200, seed=0)
    assert ts.method == "detach_onset"
    assert ts.frame == sc.release_frame + 1  # the cube leaves the gripper on the frame after the release command
    assert ts.sigma_frames > 0


def test_softscore_argmax_for_unmet_has_bootstrap_sigma_and_is_seeded() -> None:
    sc = scenario("b09_low_lift")
    tr = find_transition(sc.result, sc.frames, sc.test, FPS)
    assert tr is not None and tr.cls == "unmet"
    flat = [pf for lst in sc.frames.values() for pf in lst]
    a = refine_tstar(tr, flat, FPS, (0, 109), n_boot=100, seed=3)
    b = refine_tstar(tr, flat, FPS, (0, 109), n_boot=100, seed=3)
    assert a.method == "softscore_argmax"
    assert a.frame == tr.t_frame
    assert a == b
    assert a.sigma_frames >= SIGMA_FLOOR_FRAMES
