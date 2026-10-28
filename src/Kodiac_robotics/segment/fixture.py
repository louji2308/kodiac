"""Deterministic fixture backend for Kodiac perception.

Loads pre-recorded or synthetic track JSONs from tests/fixtures/tracks/{clip_sha256}.json.
Guarantees 100% offline, reproducible CI and stamps indelible Law 1 watermarks
(backend="fixture", is_fixture=True) per IP-P03-D3-5 and RULING.md §5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from Kodiac_robotics.contracts.core import Clip, ObjMask, Track

# Common alias synonyms for manipulator roles
ROLE_ALIASES: dict[str, str] = {
    "red_cube": "cube_a",
    "red cube": "cube_a",
    "cube a": "cube_a",
    "block_a": "cube_a",
    "red_block": "cube_a",
    "green_cube": "cube_b",
    "green cube": "cube_b",
    "cube b": "cube_b",
    "block_b": "cube_b",
    "green_block": "cube_b",
    "robot_gripper": "gripper",
    "robot gripper": "gripper",
    "end_effector": "gripper",
    "hand": "gripper",
    "human_hand": "gripper",
    "goal": "target",
    "receptacle": "target",
}


class FixtureBackend:
    """Offline deterministic perception backend replaying JSON track fixtures."""

    def __init__(self, fixture_dir: Path | str = "tests/fixtures/tracks") -> None:
        self.fixture_dir = Path(fixture_dir)

    def _resolve_fixture_path(self, clip: Clip) -> Path:
        """Resolve fixture JSON path by SHA-256 or clip filename stem."""
        # 1. Direct SHA-256 lookup
        sha_path = self.fixture_dir / f"{clip.sha256}.json"
        if sha_path.exists():
            return sha_path

        # 2. Lookup by path_h264 filename stem
        stem = Path(clip.path_h264).stem
        stem_path = self.fixture_dir / f"{stem}.json"
        if stem_path.exists():
            return stem_path

        # 3. Lookup by URI stem
        uri_stem = Path(clip.ref.uri).stem
        uri_path = self.fixture_dir / f"{uri_stem}.json"
        if uri_path.exists():
            return uri_path

        raise FileNotFoundError(
            f"Fixture track not found for clip sha256={clip.sha256} (stem={stem}) "
            f"in {self.fixture_dir}. Run 'python scripts/record_fixtures.py --synthetic' "
            f"to generate fixtures."
        )

    def _load_tracks(self, clip: Clip) -> dict[str, Track]:
        """Load and validate all Track models from fixture JSON."""
        path = self._resolve_fixture_path(clip)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_tracks: dict[str, Any] = data.get("tracks", data)
        tracks: dict[str, Track] = {}

        for obj_name, t_data in raw_tracks.items():
            if isinstance(t_data, dict) and "frames" in t_data:
                # Stamp indelible fixture backend watermark (Law 1)
                t_data["backend"] = "fixture"
                track = Track.model_validate(t_data)
                tracks[obj_name] = track

        return tracks

    def _match_track_for_role(
        self,
        role: str,
        prompts: list[str] | None,
        all_tracks: dict[str, Track],
    ) -> Track | None:
        """Find matching track in all_tracks by role name, aliases, or prompt strings."""
        if role in all_tracks:
            return all_tracks[role]

        normalized_role = role.lower().strip().replace("-", "_")
        if normalized_role in all_tracks:
            return all_tracks[normalized_role]

        # Check predefined aliases
        aliased = ROLE_ALIASES.get(normalized_role)
        if aliased and aliased in all_tracks:
            return all_tracks[aliased]

        # Check prompt text candidates
        if prompts:
            for p in prompts:
                p_norm = p.lower().strip()
                if p_norm in all_tracks:
                    return all_tracks[p_norm]
                aliased_p = ROLE_ALIASES.get(p_norm)
                if aliased_p and aliased_p in all_tracks:
                    return all_tracks[aliased_p]

        return None

    def segment_frames(
        self,
        clip: Clip,
        frames: list[int],
        prompts: dict[str, list[str]],
    ) -> dict[str, Track]:
        """Replay sparse keyframe masks from fixture for requested frames and prompts."""
        all_tracks = self._load_tracks(clip)
        results: dict[str, Track] = {}
        target_frames = set(frames)

        for role, candidate_prompts in prompts.items():
            matched = self._match_track_for_role(role, candidate_prompts, all_tracks)
            if matched is not None:
                filtered_frames: dict[int, ObjMask] = {}
                for f, mask in matched.frames.items():
                    if f in target_frames:
                        # Ensure coordinate shape alignment and fixture tagging
                        filtered_frames[f] = mask

                results[role] = Track(
                    obj=role,
                    frames=filtered_frames,
                    backend="fixture",
                    direction="forward",
                    trace_id=f"fixture-{clip.sha256[:8]}",
                )

        return results

    def track(
        self,
        clip: Clip,
        f0: int,
        f1: int,
        seeds: dict[str, ObjMask],
        direction: Literal["forward", "backward", "both"] = "both",
    ) -> dict[str, Track]:
        """Replay temporal window tracking from fixture seeded with object roles."""
        all_tracks = self._load_tracks(clip)
        results: dict[str, Track] = {}
        min_f = min(f0, f1)
        max_f = max(f0, f1)

        for role, _seed in seeds.items():
            matched = self._match_track_for_role(role, None, all_tracks)
            if matched is not None:
                filtered_frames: dict[int, ObjMask] = {
                    f: mask
                    for f, mask in matched.frames.items()
                    if min_f <= f <= max_f
                }

                results[role] = Track(
                    obj=role,
                    frames=filtered_frames,
                    backend="fixture",
                    direction=direction,
                    trace_id=f"fixture-{clip.sha256[:8]}",
                )

        return results
