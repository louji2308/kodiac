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
        "status": "Cached SAM 3.1 tracks (fixture replay) on this page; live API path exists but needs a key",
    },
    {
        "model": "Muse Spark",
        "role": "Compiles a demo or an instruction into a .green test; judges appearance-only clauses",
        "status": "Not wired here (no key). Typed instructions use the deterministic template compiler, badged as such",
    },
    {
        "model": "Muse Voice",
        "role": "Anchors the spoken intent to timestamps",
        "status": "Not available on this page (no key); type the instruction instead",
    },
    {
        "model": "Muse Wonder",
        "role": "Adjudicates hard cases and keeps memory",
        "status": "Not available on this page (no key)",
    },
    {
        "model": "Muse Code",
        "role": "Runs the /goal loop that is blocked until Kodiac run returns PASS",
        "status": "Runs in the CLI/IDE, not on this page",
    },
]

LIMITS: list[str] = [
    "Without API keys this deployment grades only the curated clips (perception is replayed from recorded tracks); "
    "an arbitrary upload cannot be segmented here and gets a clear message instead of a made-up verdict.",
    "The occlusion brush blackens the real pixels of the clip. In fixture mode it also removes the covered pixels "
    "from the cached masks (badge: OCCLUSION EMULATED ON CACHED MASKS), because a keyless server cannot re-segment.",
    "Geometry on the curated clips is Tier C (uncalibrated camera); numbers are relative, and the card says so.",
    "The curated clips are kinematic-mock simulation footage, not real robots (badge: FIXTURE REPLAY).",
    "CAN'T TELL is a real answer: when the evidence is not good enough the verdict abstains instead of guessing.",
    "The timer shows the measured wall-clock of what actually ran. A cached replay shows its lookup time, "
    "never a grading time.",
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
