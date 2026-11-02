"""Fast-vs-full agreement for the two-stage bisect fast path (P06.S02, ARCHITECTURE.md §5.3, task card T02).

Runs ``pipeline.run.run`` (full path) and ``pipeline.bisect.run_fast`` on the SAME tracks and compares verdicts and the
decisive frame t* (first FAIL / CAN'T TELL step). Two blocks, never pooled into one number:

- golden: the 5 clips in tests/fixtures/clips replayed from tests/fixtures/tracks (synthetic fixture recordings, no SAM),
  against a spec family fixed in code before any result was seen (both example specs, each stackcube step, the 1-2
  prefix, each stackcube atom). Run twice: default policy (90-frame clips take the short-clip direct pass) and with the
  bisect forced on (MIN_BISECT_FRAMES = 0) so the bisect logic itself is measured.
- pool: calibration-split episodes of experiments/pool (KinematicMockEnv, is_mock=True). The pool has state .npz only,
  so tracks are boxes projected from privileged sim state (scripts/validate_engine.build_synthetic_tracks_from_obs).
  This measures whether the shortcut reproduces the full evaluator on identical tracks. It is NOT perception agreement.

Every timing is fixture/in-memory replay ("latency_kind": "fixture_replay_not_sam"); none is SAM 3.1 latency.

Usage: python scripts/agreement.py [--max-episodes N] [--out artifacts/p06/agreement.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from Kodiac_robotics.contracts.core import (
    Clip,
    ClipRef,
    Expr,
    GreenTest,
    RunResult,
    Step,
    Track,
    Verdict,
)
from Kodiac_robotics.engine.steps import _extract_atoms
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.pipeline import bisect
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.pipeline.run import run
from Kodiac_robotics.predicates.base import get_atom_key
from Kodiac_robotics.segment.fixture import FixtureBackend

REPO = Path(__file__).resolve().parents[1]
CLIPS_DIR = REPO / "tests" / "fixtures" / "clips"
POOL_DIR = REPO / "experiments" / "pool"
SPECS = [REPO / "examples" / "stackcube.green", REPO / "examples" / "stack_blocks.green"]
WORK = REPO / ".cache" / "agreement_runs"
TSTAR_TOL = 2
TARGET_VERDICT = 0.95
TARGET_TSTAR = 0.90
TARGET_N = 100  # ARCHITECTURE.md §5.3: agreement on >= 100 clips
USD_PER_VIDEO_FRAME = 0.20 / 1000  # TOOLS_AND_REQUIREMENTS.md §2.1 list price
USD_PER_IMAGE = 2.50 / 1000
FALLBACK_MODE = "fast->full_fallback"


class ReplaySegmenter:
    """In-memory replay of pre-built tracks behind the ``Segmenter`` protocol (stamped backend="fixture")."""

    def __init__(self, tracks: dict[str, Track]) -> None:
        self.tracks = tracks
        self._norm = {k.lower().replace("_", ""): k for k in tracks}

    def _pick(self, keys: Any, frames: Any, direction: str) -> dict[str, Track]:
        wanted = set(frames)
        out: dict[str, Track] = {}
        for k in keys:
            src = self.tracks.get(k) or self.tracks.get(self._norm.get(k.lower().replace("_", ""), ""))
            if src is not None:
                fr = {f: m for f, m in src.frames.items() if f in wanted}
                out[k] = Track(obj=k, frames=fr, backend="fixture", direction=direction, trace_id="replay")
        return out

    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]:
        return self._pick(prompts.keys(), frames, "forward")

    def track(self, clip: Clip, f0: int, f1: int, seeds: Any, direction: Any) -> dict[str, Track]:
        return self._pick(seeds.keys(), range(min(f0, f1), max(f0, f1) + 1), str(direction))


def spec_family() -> list[tuple[str, GreenTest]]:
    """Fixed spec family: both example specs, each stackcube step, the 1-2 prefix, each distinct stackcube atom."""
    base, _ = load_green_test(SPECS[0])
    specs: list[tuple[str, GreenTest]] = [(p.name, load_green_test(p)[0]) for p in SPECS]

    def sub(name: str, steps: list[Step]) -> GreenTest:
        renum = [s.model_copy(update={"index": i + 1}) for i, s in enumerate(steps)]
        return base.model_copy(update={"name": name, "steps": renum})

    seen_exprs: set[str] = set()
    for pos, s in enumerate(base.steps, start=1):
        specs.append((f"stackcube.step{pos}:{s.name}", sub(f"stackcube_step{pos}", [s])))
        seen_exprs.add(s.expr.model_dump_json())
    specs.append(("stackcube.steps1-2", sub("stackcube_prefix12", base.steps[:2])))
    for s in base.steps:
        for atom in _extract_atoms(s.expr):
            expr = Expr(op="atom", atom=atom)
            key = expr.model_dump_json()
            if key in seen_exprs:
                continue
            seen_exprs.add(key)
            step = s.model_copy(update={"name": atom.name or "atom", "expr": expr})
            specs.append((f"stackcube.atom:{get_atom_key(atom)}", sub(f"stackcube_atom_{atom.name}", [step])))
    return specs


_CASE_COUNTER = [0]


def case_dir(block: str) -> Path:
    """A fresh output dir per case (run.run appends to trace.jsonl and Windows may hold a just-written file)."""
    _CASE_COUNTER[0] += 1
    return WORK / block / f"{_CASE_COUNTER[0]:05d}"


def decisive(steps: list[Any]) -> int | None:
    return next((s.frame for s in steps if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL)), None)


def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def pct(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 1) if values else None


def compare(case: str, full: RunResult, fast: bisect.FastRun, n_frames: int) -> dict[str, Any]:
    t_full, t_fast = decisive(full.steps), decisive(fast.result.steps)
    return {
        "case": case,
        "n_frames": n_frames,
        "full_verdict": full.verdict.value,
        "fast_verdict": fast.result.verdict.value,
        "verdict_agree": full.verdict == fast.result.verdict,
        "full_tstar": t_full,
        "fast_tstar": t_fast,
        "tstar_within_2": (t_full is not None and t_fast is not None and abs(t_full - t_fast) <= TSTAR_TOL),
        "mode": fast.result.backends.get("mode"),
        "guards": fast.plan.guards_fired,
        "plan": fast.plan.model_dump(mode="json"),
        "sam_calls": fast.plan.n_sam_calls,
        "billed_frames": fast.billed_frames,
        "billed_video_frames": int(fast.result.backends.get("sam_billed_video_frames", 0)),
        "billed_images": int(fast.result.backends.get("sam_billed_images", 0)),
        "full_path_billed_frames": max(bisect.MIN_WINDOW_FRAMES, n_frames),
        "stage_timings_ms": fast.stage_timings_ms,
        "full_total_ms": full.timings_ms.get("total_ms"),
    }


def summarize(rows: list[dict[str, Any]], **labels: Any) -> dict[str, Any]:
    n = len(rows)
    k_v = sum(r["verdict_agree"] for r in rows)
    nonpass = [r for r in rows if r["full_verdict"] != "PASS"]
    k_t = sum(r["tstar_within_2"] for r in nonpass)
    fallbacks = [r for r in rows if r["mode"] == FALLBACK_MODE]
    stage_keys = sorted({k for r in rows for k in r["stage_timings_ms"]})
    latency = {
        k: {"p50": pct(v, 50), "p95": pct(v, 95), "n": len(v)}
        for k in stage_keys
        if (v := [r["stage_timings_ms"][k] for r in rows if k in r["stage_timings_ms"]])
    }
    guards: dict[str, int] = {}
    for r in rows:
        for g in r["guards"]:
            name = g.split("(")[0]
            guards[name] = guards.get(name, 0) + 1
    calls = [r["sam_calls"] for r in rows]
    billed = [r["billed_frames"] for r in rows]
    full_billed = [r["full_path_billed_frames"] for r in rows]
    cost = [r["billed_video_frames"] * USD_PER_VIDEO_FRAME + r["billed_images"] * USD_PER_IMAGE for r in rows]
    verdict_rate = k_v / n if n else 0.0
    tstar_rate = k_t / len(nonpass) if nonpass else 0.0
    return {
        **labels,
        "n": n,
        "verdict_agreement": round(verdict_rate, 4),
        "verdict_agreement_wilson95": wilson(k_v, n),
        "tstar_within_2_frames": round(tstar_rate, 4),
        "tstar_denominator": f"{len(nonpass)} pairs whose full-path verdict is FAIL or CANT_TELL",
        "tstar_within_2_frames_wilson95": wilson(k_t, len(nonpass)),
        "target_met": bool(n >= TARGET_N and verdict_rate >= TARGET_VERDICT and tstar_rate >= TARGET_TSTAR),
        "targets": {"n_min": TARGET_N, "verdict": TARGET_VERDICT, "tstar_within_2": TARGET_TSTAR},
        "fallback_to_full_rate": round(len(fallbacks) / n, 4) if n else None,
        "resolved_by_bisect_without_fallback": n - len(fallbacks),
        "guards_fired_counts": dict(sorted(guards.items())),
        "full_path_verdicts": {v: sum(r["full_verdict"] == v for r in rows) for v in ("PASS", "FAIL", "CANT_TELL")},
        "sam_calls": {"mean": round(float(np.mean(calls)), 2) if calls else None, "p50": pct(calls, 50), "max": max(calls, default=None)},
        "billed_frames": {"mean": round(float(np.mean(billed)), 1) if billed else None, "p50": pct(billed, 50), "max": max(billed, default=None)},
        "full_path_billed_frames_mean": round(float(np.mean(full_billed)), 1) if full_billed else None,
        "hypothetical_hosted_cost_usd_mean": round(float(np.mean(cost)), 4) if cost else None,
        "latency_ms": latency,
        "disagreements": [r for r in rows if not r["verdict_agree"] or (r["full_verdict"] != "PASS" and not r["tstar_within_2"])],
    }


def golden_rows(forced: bool) -> list[dict[str, Any]]:
    manifest = json.loads((CLIPS_DIR / "manifest.json").read_text(encoding="utf-8"))["clips"]
    original = bisect.MIN_BISECT_FRAMES
    bisect.MIN_BISECT_FRAMES = 0 if forced else original
    rows: list[dict[str, Any]] = []
    try:
        for spec_name, test in spec_family():
            for clip_name in sorted(manifest):
                clip = open_clip(CLIPS_DIR / clip_name)
                out = case_dir("golden")
                full = run(test=test, clip=clip, output_dir=out / "full")
                fast = bisect.run_fast(test, clip, FixtureBackend(), output_dir=out / "fast")
                rows.append(compare(f"{spec_name} @ {clip_name}", full, fast, clip.n_frames))
                shutil.rmtree(out, ignore_errors=True)
    finally:
        bisect.MIN_BISECT_FRAMES = original
    return rows


def _load_projector() -> Callable[..., dict[str, Track]]:
    spec = importlib.util.spec_from_file_location("_validate_engine", REPO / "scripts" / "validate_engine.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_synthetic_tracks_from_obs


def pool_rows(max_episodes: int | None) -> list[dict[str, Any]]:
    df = pd.read_parquet(POOL_DIR / "manifest.parquet")
    cal = df[df["split"] == "calibration"].sort_values("episode_id")
    if max_episodes is not None:
        cal = cal.head(max_episodes)
    project = _load_projector()
    test, _ = load_green_test(SPECS[0])
    rows: list[dict[str, Any]] = []
    for _, ep in cal.iterrows():
        npz = np.load(POOL_DIR / str(ep["state_uri"]))
        tracks = project(npz["obs_state"], npz["cam_K"])
        n = len(npz["obs_state"])
        clip = Clip(
            ref=ClipRef(uri=f"sim://pool/{ep['episode_id']}", source_kind="sim"),
            path_h264=str(POOL_DIR / str(ep["video_uri"])),  # not rendered: no MP4 exists, so gate G4 reads no pixels
            fps=float(ep["fps"]),
            n_frames=n,
            width=640,
            height=480,
            sha256=f"pool-{ep['episode_id']}",
        )
        cam = {"cam_K": npz["cam_K"], "cam_extrinsic": npz["cam_extrinsic"]}
        out = case_dir("pool")
        full = run(test=test, clip=clip, tracks=tracks, output_dir=out / "full", **cam)
        fast = bisect.run_fast(test, clip, ReplaySegmenter(tracks), output_dir=out / "fast", **cam)
        row = compare(str(ep["episode_id"]), full, fast, n)
        shutil.rmtree(out, ignore_errors=True)
        row["perturbation_type"] = str(ep["perturbation_type"]) or "none"
        row["oracle_success"] = bool(ep["oracle_success"])
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-episodes", type=int, default=None, help="limit pool episodes (default: all calibration)")
    ap.add_argument("--out", type=Path, default=REPO / "artifacts" / "p06" / "agreement.json")
    args = ap.parse_args()

    t0 = time.perf_counter()
    shutil.rmtree(WORK, ignore_errors=True)
    blocks = [
        summarize(
            golden_rows(forced=False),
            block="golden_default_policy",
            evidence_type="fixture_replay_synthetic_tracks",
            is_fixture=True,
            is_mock=False,
            latency_kind=bisect.LATENCY_KIND_FIXTURE,
            note="90-frame clips: bisect would bill >= 100 frames, so the default policy tracks them directly "
            "(G-budget:short_clip_direct). Agreement here is by construction; see the forced block for the bisect.",
        ),
        summarize(
            golden_rows(forced=True),
            block="golden_bisect_forced",
            evidence_type="fixture_replay_synthetic_tracks",
            is_fixture=True,
            is_mock=False,
            latency_kind=bisect.LATENCY_KIND_FIXTURE,
            note="Bisect forced on 90-frame clips. On these fixtures moves_with is U at Tier C (below noise floor), so "
            "any hypothesis anchored on 'grasp' is unverifiable densely and G-miss falls back to the full path.",
        ),
        summarize(
            pool_rows(args.max_episodes),
            block="pool_calibration_default_policy",
            evidence_type="synthetic_tracks_from_privileged_state",
            is_fixture=True,
            is_mock=True,
            latency_kind=bisect.LATENCY_KIND_FIXTURE,
            note="KinematicMockEnv episodes; boxes projected from privileged state; Tier A camera. Measures shortcut "
            "fidelity to the full evaluator on identical tracks, NOT perception agreement and NOT SAM latency.",
        ),
    ]
    head = blocks[2]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    except OSError:
        sha = "unknown"
    payload = {
        "artifact": "fast-vs-full agreement (two-stage bisect)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": sha,
        "command": "python scripts/agreement.py" + (f" --max-episodes {args.max_episodes}" if args.max_episodes else ""),
        "headline_block": head["block"],
        "n": head["n"],
        "verdict_agreement": head["verdict_agreement"],
        "tstar_within_2_frames": head["tstar_within_2_frames"],
        "fallback_to_full_rate": head["fallback_to_full_rate"],
        "target_met": head["target_met"],
        "evidence_type": head["evidence_type"],
        "is_fixture": True,
        "is_mock": True,
        "latency_kind": bisect.LATENCY_KIND_FIXTURE,
        "honesty": [
            "No API keys exist: no number in this file comes from SAM 3.1, Meta APIs or real video.",
            "Latencies are in-process replay timings (fixture_replay_not_sam); never quote them as live latency.",
            "Pool tracks are projected from privileged sim state (circular for perception); golden tracks are synthetic fixtures.",
            "t* = frame of the first FAIL / CANT_TELL step; compared only where the full-path verdict is not PASS.",
            "hypothetical_hosted_cost_usd = billed units x list price; nothing was billed.",
        ],
        "blocks": blocks,
        "runtime_s": round(time.perf_counter() - t0, 1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    shutil.rmtree(WORK, ignore_errors=True)
    for b in blocks:
        print(
            f"{b['block']}: n={b['n']} verdict={b['verdict_agreement']:.3f} tstar±2={b['tstar_within_2_frames']:.3f} "
            f"fallback={b['fallback_to_full_rate']} target_met={b['target_met']} [{b['evidence_type']}]"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
