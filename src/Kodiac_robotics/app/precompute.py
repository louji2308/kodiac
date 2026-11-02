"""Precompute the curated cached replays by running the real pipeline (fixture perception backend).

Each replay is the output of ``pipeline.run.run`` on a golden clip, so its badges, timings and verdict are
genuine; what is *not* live is the perception (recorded SAM 3.1 tracks), and the badges say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from Kodiac_robotics.app.occlusion import Rect
from Kodiac_robotics.app.replay import ReplayEntry
from Kodiac_robotics.app.service import GradeService
from Kodiac_robotics.app.settings import AppSettings
from Kodiac_robotics.contracts.core import Verdict

KNOWN_CORRECT_RUN_NOTE = (
    "Known limitation, shown as measured: the engine currently returns this verdict on the reference clip "
    "because the grasp predicate (moves_with) is below its noise floor on the recorded fixture tracks. "
    "It is not a PASS."
)


@dataclass(frozen=True)
class ReplaySpec:
    test_id: str
    clip_id: str
    title: str
    suffix: str = ""
    rects: list[Rect] = field(default_factory=list)
    note: str = ""

    @property
    def replay_id(self) -> str:
        return f"{self.test_id}__{self.clip_id}{self.suffix}"


CURATED_SPECS: list[ReplaySpec] = [
    ReplaySpec("stackcube", "correct_run", "Reference clip: the correct run"),
    ReplaySpec("stackcube", "b01_early_release", "Seeded bug B1: released too early"),
    ReplaySpec("stackcube", "b02_xy_misalignment", "Seeded bug B2: placed off-centre"),
    ReplaySpec("stackcube", "b09_lift_failure", "Seeded bug B9: lifted too little"),
    ReplaySpec("stackcube", "occluded_clip", "Scene occluded during transport"),
    ReplaySpec(
        "stackcube",
        "correct_run",
        "Occlusion brush painted over the target block",
        suffix="_brushed",
        rects=[(380, 280, 500, 360)],
        note="A rectangle painted over the target block on every frame; masks emulated on cached tracks.",
    ),
]


def precompute_replays(
    settings: AppSettings, specs: list[ReplaySpec] | None = None
) -> list[ReplayEntry]:
    """Run each spec through the real pipeline and store the result + card in ``settings.replay_dir``."""
    service = GradeService(settings)
    clips = service.curated_clips()
    entries: list[ReplayEntry] = []
    for spec in specs or CURATED_SPECS:
        if spec.clip_id not in clips:
            raise FileNotFoundError(f"curated clip not found: {spec.clip_id}")
        outcome = service.grade(
            clip_id=spec.clip_id,
            test_id=spec.test_id,
            occlusion_rects=spec.rects or None,
        )
        if outcome.card_path is None:
            raise RuntimeError(f"no card rendered for {spec.replay_id}")
        note = spec.note
        if spec.clip_id == "correct_run" and not spec.rects and outcome.run.verdict != Verdict.PASS:
            note = KNOWN_CORRECT_RUN_NOTE
        entry = service.store.put(
            spec.replay_id,
            outcome.run,
            outcome.card_path.read_bytes(),
            title=spec.title,
            clip_label=clips[spec.clip_id].description,
            note=note,
        )
        entries.append(entry)
    return entries


__all__ = ["CURATED_SPECS", "KNOWN_CORRECT_RUN_NOTE", "ReplaySpec", "precompute_replays"]

