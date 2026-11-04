"""Shared, honesty-reviewed copy for the hosted page and the static site.

Statuses describe what THIS build does today. No API keys exist in this repository's environment, so
perception is replayed from recorded tracks and every card says so through its badges.
"""

from __future__ import annotations

TAGLINE = "Robots can finally fail a test."

MODEL_TABLE: list[dict[str, str]] = [
    {
        "model": "SAM 3.1",
        "role": "Measures: segments and tracks every object, frame by frame",
        "status": "Live interactive mask & anchor engine on this page (replays recorded SAM 3.1 tracks by default; connects to live MODEL_API_KEY endpoint when configured)",
    },
    {
        "model": "Muse Spark",
        "role": "Compiles a demo or an instruction into a .green test; judges appearance-only clauses",
        "status": "Live in-browser .green compiler with MODEL_API_KEY connector + deterministic two-pass 2.5σ slack compiler fallback (badged transparently)",
    },
    {
        "model": "Muse Voice",
        "role": "Anchors the spoken intent to timestamps",
        "status": "Live Web Speech API / Muse Voice microphone capture in Studio Tab 2 (or type any natural-language instruction)",
    },
    {
        "model": "Muse Wonder",
        "role": "Adjudicates hard cases and keeps memory",
        "status": "Live FactTable & validated blame summary engine in Studio Tab 3 (connects to MODEL_API_KEY or deterministic validator)",
    },
    {
        "model": "Muse Code",
        "role": "Runs the /goal loop that is blocked until Kodiac run returns PASS",
        "status": "Interactive 10-bug repair loop & 18/18 anti-cheat Done-Gate explorer in Studio Tab 4 + CLI (`Kodiac gate` / `Kodiac mcp`)",
    },
]

LIMITS: list[str] = [
    "Without an external perception API key, perception on the curated clips replays recorded SAM 3.1 tracks (badge: [FIXTURE REPLAY]); paste a MODEL_API_KEY in the top bar or connect a local `Kodiac app` server for live API calls.",
    "The interactive Occlusion Brush blackens pixels on the video canvas and recomputes mask coverage and Kleene 3-valued gates (G1–G6) live in your browser (badge: OCCLUSION EMULATED ON CACHED MASKS).",
    "Geometry supports Tier A (calibrated 3D camera), Tier B (calibrated 2D tabletop scale), and Tier C (uncalibrated monocular prior with 2.5x uncertainty inflation).",
    "Curated clips are kinematic-mock simulation episodes (badge: FIXTURE REPLAY); Tab 4 also includes 5 audited public real-robot failures from DROID and LeRobot SO-100.",
    "CAN'T TELL is a first-class verdict: when evidence is occluded or below the measurement noise floor (|m| < σ), Kodiac abstains with a typed reason code instead of guessing.",
    "Every live evaluation displays its measured wall-clock execution time; precomputed gallery cards carry the ⚡ CACHED badge and report their original recording time.",
]

PRIVACY = (
    "Uploads are processed in memory and on disk only to grade them, are never used for training, "
    "and are deleted automatically within 24 hours. Logs store salted hashes, never IP addresses or filenames."
)

CACHED_EXPLAINER = (
    "⚡ CACHED means this card was precomputed earlier and is being replayed instantly. "
    "It is not a live grade. Use Grade to run the engine now (with a measured timer)."
)

FIXTURE_EXPLAINER = (
    "[FIXTURE REPLAY] means the perception step replayed recorded SAM 3.1 tracks for this curated clip instead "
    "of calling a live segmentation API."
)

EXAMPLE_TESTS: dict[str, dict[str, str]] = {
    "stackcube": {
        "label": "stackcube: pick cube A, place on cube B, release",
        "file": "stackcube.green",
    },
    "stack_blocks": {
        "label": "stack_blocks: grasp, place, release (block names)",
        "file": "stack_blocks.green",
    },
}

__all__ = [
    "CACHED_EXPLAINER",
    "EXAMPLE_TESTS",
    "FIXTURE_EXPLAINER",
    "LIMITS",
    "MODEL_TABLE",
    "PRIVACY",
    "TAGLINE",
]
