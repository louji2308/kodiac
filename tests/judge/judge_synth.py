"""Deterministic SYNTHETIC drawer scenes and the fixture builder for the judge tests.

Everything here is procedurally drawn and labelled from ground truth; no model is involved.
Regenerate the committed fixture with:  python tests/judge/judge_synth.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from Kodiac_robotics.judge.backends import synthetic_entries, write_fixture_file
from Kodiac_robotics.judge.crops import make_crop
from Kodiac_robotics.segment.rle import mask_to_rle

H, W = 240, 320
Q_POS = "Is the drawer flush?"
Q_NEG = "Is the drawer ajar?"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "judge" / "drawer_synthetic.json"

# case -> (primary truth, escalator truth or None)
CASES: dict[str, tuple[str, str | None]] = {
    "flush": ("pos", None),
    "ajar": ("neg", None),
    "blur_escalates_to_flush": ("ambiguous", "pos"),
    "dark_stays_unresolved": ("ambiguous", "ambiguous"),
}


def render_scene(case: str) -> tuple[np.ndarray, str, tuple[int, int]]:
    """Return (frame_bgr, drawer_mask_rle, rle_size) for a synthetic drawer scene."""
    rng = np.random.default_rng(abs(hash_case(case)) % (2**32))
    frame = np.full((H, W, 3), (90, 95, 100), np.uint8)
    cv2.rectangle(frame, (60, 50), (260, 190), (60, 80, 120), -1)  # cabinet body
    off = 22 if case == "ajar" else 0
    x0, y0, x1, y1 = 75, 85 + off, 245, 150 + off
    if case == "ajar":
        cv2.rectangle(frame, (75, 85), (245, 85 + off), (10, 10, 10), -1)  # visible dark gap
    cv2.rectangle(frame, (x0, y0), (x1, y1), (150, 170, 200), -1)  # drawer front
    cv2.rectangle(frame, (140, (y0 + y1) // 2 - 4), (180, (y0 + y1) // 2 + 4), (40, 40, 40), -1)  # handle
    mask = np.zeros((H, W), np.uint8)
    mask[y0:y1, x0:x1] = 1
    if case == "blur_escalates_to_flush":
        frame = cv2.GaussianBlur(frame, (0, 0), 9)
    if case == "dark_stays_unresolved":
        frame = (frame.astype(np.float32) * 0.12).astype(np.uint8)
    noise = rng.integers(0, 4, frame.shape, dtype=np.uint8)
    frame = cv2.add(frame, noise)
    return frame, mask_to_rle(mask), (H, W)


def hash_case(case: str) -> int:
    return sum((i + 1) * ord(c) for i, c in enumerate(case))


def scene_crop(case: str) -> bytes:
    frame, rle, size = render_scene(case)
    return make_crop(frame, rle, size)


def build_fixture(path: Path = FIXTURE_PATH) -> None:
    entries: list[dict] = []
    for case, (prim, esc) in CASES.items():
        crop = scene_crop(case)
        entries += synthetic_entries(crop, Q_POS, Q_NEG, prim)  # type: ignore[arg-type]
        if esc is not None:
            entries += synthetic_entries(crop, Q_POS, Q_NEG, esc, role="escalator")  # type: ignore[arg-type]
    write_fixture_file(
        path,
        entries,
        "SYNTHETIC drawer flush/ajar judge replay fixtures keyed by (crop sha256, question). "
        "Answers derive from the procedural scene's ground-truth label, NOT from any model.",
    )


if __name__ == "__main__":
    build_fixture()
    print(f"wrote {FIXTURE_PATH}")
