"""Tests for proof/chart.py (T09): data marks only for MEASURED; watermarks otherwise."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from Kodiac_robotics.proof import chart as C
from Kodiac_robotics.proof import labels as L
from Kodiac_robotics.proof import stats as S

pytest.importorskip("matplotlib")
from PIL import Image  # noqa: E402

FX = Path(__file__).resolve().parents[1] / "fixtures" / "proof"
REPO = Path(__file__).resolve().parents[2]


def _hex(color: str) -> np.ndarray:
    return np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)], dtype=float)


def _count(png: Path, color: str, tol: float = 12.0) -> int:
    img = np.asarray(Image.open(png).convert("RGB"), dtype=float)
    return int((np.linalg.norm(img - _hex(color), axis=2) < tol).sum())


def _render(h: dict, tmp_path: Path, name: str) -> tuple[Path, str]:
    png, svg = tmp_path / f"{name}.png", tmp_path / f"{name}.svg"
    C.render_proof_chart(h, png, svg)
    return png, svg.read_text(encoding="utf-8")


def _measured_dict() -> dict:
    """TEST-ONLY hand-built MEASURED headline, rendered to tmp only (exercises the drawing branch)."""
    arms = {}
    for name, m in [("single_pass", 0.45), ("kodiac", 0.6), ("oracle", 0.7), ("accept_all", 0.35)]:
        arms[name] = {"mean": m, "ci": [m - 0.05, m + 0.05], "n_seeds": 3,
                      "min_episodes_per_seed": 200,
                      "seeds": {"42": {"mean": m}, "43": {"mean": m}, "44": {"mean": m}}}
    return {"status": "MEASURED", "synthetic": False, "is_mock": False, "arms": arms,
            "sentence": "TEST-ONLY", "dose_response": []}


def test_not_measured_draws_watermark_and_no_data(tmp_path: Path) -> None:
    png, svg = _render(S.headline({}), tmp_path, "nm")
    assert C.NOT_MEASURED_TEXT in svg
    assert _count(png, C.DATA_COLOR) == 0
    assert _count(png, C.WATERMARK_COLOR) > 2000
    assert "points of success" not in svg
    assert "<pattern" not in svg


def test_synthetic_draws_hatched_watermark_and_no_data(tmp_path: Path) -> None:
    h = S.headline(L.load_arm_evals(FX / "evals_SYNTHETIC"))
    assert h["status"] == S.STATUS_SYNTHETIC
    png, svg = _render(h, tmp_path, "syn")
    assert C.SYNTHETIC_TEXT in svg and C.NOT_MEASURED_TEXT not in svg
    assert _count(png, C.DATA_COLOR) == 0
    assert _count(png, C.WATERMARK_COLOR) > 2000
    assert "<pattern" in svg  # the hatch is emitted as an SVG fill pattern


def test_measured_branch_draws_data_marks(tmp_path: Path) -> None:
    png, svg = _render(_measured_dict(), tmp_path, "m")
    assert _count(png, C.DATA_COLOR) > 1000
    assert C.NOT_MEASURED_TEXT not in svg and C.SYNTHETIC_TEXT not in svg


def test_measured_scatter_mode_with_false_pass(tmp_path: Path) -> None:
    h = _measured_dict()
    for i, a in enumerate(h["arms"].values()):
        a["false_pass"] = {"value": 0.05 * (i + 1), "lo": 0.02 * (i + 1), "hi": 0.08 * (i + 1)}
    png, svg = _render(h, tmp_path, "sc")
    assert _count(png, C.DATA_COLOR) > 100
    assert "false-PASS rate" in svg


@pytest.mark.parametrize(
    "patch,mode",
    [
        ({"synthetic": True}, S.STATUS_SYNTHETIC),
        ({"is_mock": True}, S.STATUS_SYNTHETIC),
        ({"status": "WHATEVER"}, S.STATUS_NOT_MEASURED),
        ({"status": None}, S.STATUS_NOT_MEASURED),
    ],
)
def test_chart_mode_fails_closed(patch: dict, mode: str, tmp_path: Path) -> None:
    h = {**_measured_dict(), **patch}
    assert C.chart_mode(h) == mode
    png, _ = _render(h, tmp_path, "fc")
    assert _count(png, C.DATA_COLOR) == 0
    missing_flags = {k: v for k, v in _measured_dict().items() if k not in ("synthetic", "is_mock")}
    assert C.chart_mode(missing_flags) == S.STATUS_SYNTHETIC


def test_real_state_command_is_not_measured(tmp_path: Path) -> None:
    out = tmp_path / "headline.json"
    rc = C.main(["--real-state", "--root", str(REPO), "--out-json", str(out),
                 "--out-png", str(tmp_path / "c.png"), "--out-svg", str(tmp_path / "c.svg")])
    assert rc == 0
    h = json.loads(out.read_text(encoding="utf-8"))
    if h["inputs"]["eval_arms"]:
        pytest.skip("real eval files now exist; the honest state is no longer 'no arms'")
    assert h["status"] == S.STATUS_NOT_MEASURED
    assert h["Y_points"] is None and h["sentence"] is None and h["delta"] is None
    assert h["generated_by"] == C.REAL_STATE_COMMAND
    assert C.NOT_MEASURED_TEXT in (tmp_path / "c.svg").read_text(encoding="utf-8")
