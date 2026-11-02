"""MCP server exposing the `verify` tool (server name "Kodiac") for the Muse Code /goal loop.

`verify` runs the sim script through `sim.runner.run_script`, grades the produced clip with
`pipeline.run.run(mode=...)` and returns the RunResult JSON plus blame/hint/evidence paths.
It also writes `.Kodiac/last_verdict.json` (with the run nonce) in the project directory.

Honesty notes (Law 1):
  * Offline, perception for sim clips is NOT SAM: tracks are projected from the privileged
    sim state (`evidence_type = "sim_state_tracks"`). The pipeline's generic
    "[REPLAY: CACHED SAM 3.1 TRACKS]" badge is replaced by an accurate badge, and
    `[MOCK SIMULATION]` is added whenever the kinematic mock backend ran.
  * The sim oracle is never part of the response (it is eval-only, KD-13).
  * `.Kodiac/last_verdict.json` is informational. The done-gate never trusts it (KD-11).
  * Blame/hint appear only if `Kodiac_robotics.blame.blame_from_run` exists and succeeds;
    otherwise `"blame": null` and `blame_status` says why.

Errors are returned as structured `{"error": {code, message, hint}}` payloads, never as
stack traces. Stdout is reserved for the MCP stdio protocol, so any library output produced
during `verify` is redirected to stderr.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from Kodiac_robotics.contracts.core import (
    Component,
    PredFrame,
    RunResult,
    Tri,
    Verdict,
    VerifyRequest,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

SERVER_NAME = "Kodiac"
TOOL_NAME = "verify"
EVIDENCE_SIM_STATE = "sim_state_tracks"
BADGE_SIM_STATE = "[SIM STATE TRACKS: projected from privileged sim state, not SAM]"
BADGE_MOCK = "[MOCK SIMULATION]"
_CACHED_SAM_BADGE = "[REPLAY: CACHED SAM 3.1 TRACKS]"

# obs_state column layout of the sim env (see scripts/validate_engine.py)
# (name, obs columns, z offset from the tracked point to the object's lowest point); the engine measures the
# height of each object's bottom anchor, so cubes are projected from their base, not their centre.
_OBS_COLUMNS = (
    ("gripper", slice(0, 3), 0.0),
    ("cubeA", slice(8, 11), -0.02),
    ("cubeB", slice(15, 18), -0.02),
)
_OBJECT_SIZE_M = 0.04


def _error(code: str, message: str, hint: str | None = None) -> dict[str, Any]:
    return {
        "verdict": None,
        "error": {"code": code, "message": message[:500], "hint": hint},
    }


def _project_dir() -> Path:
    return Path.cwd()


def _resolve(project: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (project / p)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracks_from_state(
    state_path: Path, *, n_frames: int, height: int, width: int
) -> tuple[dict[str, Any], Any, Any]:
    """Project privileged sim state into per-frame boxes (synthetic tracks, NOT perception).

    Prefers `sim.runner.tracks_from_state` when T04's runner provides it, so `verify` and the
    done-gate perceive identically.
    """
    try:
        from Kodiac_robotics.sim import runner as sim_runner

        shared = getattr(sim_runner, "tracks_from_state", None)
    except ImportError:
        shared = None
    if shared is not None:
        return shared(state_path, n_frames=n_frames, height=height, width=width)
    return _local_tracks_from_state(state_path, n_frames=n_frames, height=height, width=width)


def _local_tracks_from_state(
    state_path: Path, *, n_frames: int, height: int, width: int
) -> tuple[dict[str, Any], Any, Any]:
    import numpy as np

    from Kodiac_robotics.contracts.core import ObjMask, Track
    from Kodiac_robotics.segment.rle import mask_to_rle

    with np.load(state_path) as npz:
        if "ee_pos" in npz.files:  # sim.runner layout
            obs = np.zeros((len(npz["ee_pos"]), 18), dtype=np.float64)
            obs[:, 0:3] = np.asarray(npz["ee_pos"], dtype=np.float64)[:, :3]
            obs[:, 8:11] = np.asarray(npz["cubeA_pose"], dtype=np.float64)[:, :3]
            obs[:, 15:18] = np.asarray(npz["cubeB_pose"], dtype=np.float64)[:, :3]
        else:  # legacy pool layout (scripts/validate_engine.py)
            obs = np.asarray(npz["obs_state"], dtype=np.float64)
        cam_K = np.asarray(npz["cam_K"], dtype=np.float64)
        cam_extrinsic = np.asarray(npz["cam_extrinsic"], dtype=np.float64)
    if len(obs) == 0:
        raise ValueError("sim state has no observations")

    fx, fy = float(cam_K[0, 0]), float(cam_K[1, 1])
    cx, cy = float(cam_K[0, 2]), float(cam_K[1, 2])
    tracks = {
        name: Track(obj=name, frames={}, backend="fixture", direction="forward", trace_id=f"sim-{name}")
        for name, _, _ in _OBS_COLUMNS
    }
    ext = cam_extrinsic
    for frame in range(n_frames):
        row = obs[min(frame, len(obs) - 1)]
        for name, cols, dz in _OBS_COLUMNS:
            anchor = np.array([row[cols][0], row[cols][1], row[cols][2] + dz, 1.0])
            p_cam = ext @ anchor
            zc = max(0.05, float(p_cam[2]))
            u = fx * float(p_cam[0]) / zc + cx
            v_bottom = fy * float(p_cam[1]) / zc + cy
            side_f = fx * _OBJECT_SIZE_M / zc  # exact apparent width: the scale model reads it from the box
            side = max(2, int(round(side_f)))
            x1 = max(0, min(width - 1, int(round(u - side / 2))))
            x2 = max(x1 + 1, min(width, x1 + side))
            y2 = max(1, min(height, int(round(v_bottom)) + 1))
            y1 = max(0, y2 - side)
            canvas = np.zeros((height, width), dtype=np.uint8)
            canvas[y1:y2, x1:x2] = 1
            tracks[name].frames[frame] = ObjMask(
                obj=name,
                frame=frame,
                score=0.98,
                bbox_xyxy=(u - side_f / 2, float(y1), u + side_f / 2, float(y2)),
                rle=mask_to_rle(canvas),
                area_px=int((x2 - x1) * (y2 - y1)),
                rle_size=(height, width),
            )
    return tracks, cam_K, cam_extrinsic


def load_spans(spans_path: str | Path | None) -> list[Any]:
    """Read the span log written by the sim runner (JSONL or a JSON array); [] if unreadable."""
    from Kodiac_robotics.sim.spans import SimSpan

    if not spans_path:
        return []
    path = Path(spans_path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if text.startswith("["):
            rows = json.loads(text)
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return [SimSpan.model_validate(r) for r in rows]
    except (OSError, ValueError, ValidationError):
        return []


def load_pred_frames(trace_path: str | Path) -> dict[str, list[PredFrame]]:
    """Rebuild per-atom PredFrame lists from the pipeline's trace.jsonl."""
    out: dict[str, list[PredFrame]] = {}
    path = Path(trace_path)
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("record_type") != "pred_frame":
                continue
            out.setdefault(rec["atom"], []).append(
                PredFrame(
                    frame=int(rec["frame"]),
                    atom_key=rec["atom"],
                    tri=Tri(rec["tri"]),
                    components=[Component.model_validate(c) for c in rec.get("components", [])],
                    trace_id=rec.get("trace_id", ""),
                )
            )
    return out


def _try_blame(result: RunResult, test_obj: Any, trace_path: str, fps: float, spans: list[Any]) -> tuple[Any, str]:
    """Return (Blame | None, status). Absent module or failure never breaks `verify`."""
    if result.verdict != Verdict.FAIL:
        return None, "not_applicable: verdict is not FAIL"
    try:
        from Kodiac_robotics.blame import blame_from_run
    except ImportError:
        try:
            from Kodiac_robotics.blame.validate import blame_from_run
        except ImportError:
            return None, "unavailable: Kodiac_robotics.blame.blame_from_run is not installed"
    kwargs: dict[str, Any] = {"spans": spans}
    try:
        from Kodiac_robotics.blame.codeloc import locate_code

        kwargs["code_locator"] = lambda frame, component: locate_code(spans, frame, component)
    except ImportError:
        pass
    try:
        from Kodiac_robotics.blame.hint import make_hint

        kwargs["hint_fn"] = make_hint
    except ImportError:
        pass
    try:
        blame = blame_from_run(result, test_obj, load_pred_frames(trace_path), fps, **kwargs)
    except Exception as exc:  # noqa: BLE001 - blame must never crash the tool
        logger.exception("blame_from_run failed")
        return None, f"failed: {type(exc).__name__}: {str(exc)[:200]}"
    if blame is None:
        return None, "no_blame: blame_from_run returned None"
    return blame, "ok"


def _failure_summary(result: RunResult) -> dict[str, Any] | None:
    """Measured facts of the first non-passing step, straight from the RunResult."""
    for step in result.steps:
        if step.verdict in (Verdict.FAIL, Verdict.CANT_TELL):
            return {
                "step_index": step.index,
                "step": step.name,
                "verdict": step.verdict.value,
                "frame": step.frame,
                "t_s": step.t_s,
                "reasons": [r.value for r in step.reasons],
                "decisive": [
                    {
                        "component": c.name,
                        "value": c.value,
                        "threshold": c.threshold,
                        "margin": c.margin,
                        "sigma": c.sigma,
                        "unit": c.unit,
                    }
                    for c in step.decisive
                ],
            }
    return None


def _message(payload: dict[str, Any]) -> str:
    verdict = payload["verdict"]
    badges = " ".join(payload.get("badges", []))
    if verdict == "PASS":
        head = "PASS: Kodiac run passed this script."
    elif verdict == "FAIL":
        fail = payload.get("failure") or {}
        head = f"FAIL at step {fail.get('step_index', '?')} ({fail.get('step', '?')})."
        blame = payload.get("blame")
        if blame:
            head += f" {blame['summary']}"
        hint = payload.get("hint")
        if hint:
            head += f" Hint: change {hint['variable']}" + (f" ({hint['move']})" if hint.get("move") else "") + "."
    else:
        head = "CAN'T TELL: Kodiac abstained and did not guess."
    return f"{head} {badges}".strip()


def _cache_key(script: Path | None, test: Path, req: VerifyRequest, clip: Path | None) -> str:
    h = hashlib.sha256()
    for part in (
        script.read_bytes() if script else b"",
        test.read_bytes(),
        str(req.seed).encode(),
        req.mode.encode(),
        str(clip).encode() if clip else b"",
    ):
        h.update(hashlib.sha256(part).digest())
    return h.hexdigest()[:32]


def _write_verdict(project: Path, payload: dict[str, Any]) -> Path:
    path = project / ".Kodiac" / "last_verdict.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _verify_impl(req: VerifyRequest) -> dict[str, Any]:
    from Kodiac_robotics.pipeline.loader import load_green_test

    project = _project_dir()
    test_path = _resolve(project, req.test)
    if not test_path.is_file():
        return _error("test_not_found", f"Test file not found: {req.test}", "Pass the path of a .green file.")
    try:
        test_obj, _ = load_green_test(test_path)
    except Exception as exc:  # noqa: BLE001 - parse errors become structured errors
        return _error("test_invalid", f"Cannot parse {req.test}: {str(exc)[:300]}", "Fix the .green syntax.")
    if not test_obj.steps:
        return _error("test_invalid", f"{req.test} has no steps; an empty test would pass vacuously.", "Write at least one step.")

    if req.sim_script and req.clip:
        return _error("ambiguous_input", "Give either sim_script or clip, not both.")
    if not req.sim_script and not req.clip:
        return _error("missing_input", "Give sim_script (run the simulator) or clip (grade a video).")

    script_path: Path | None = None
    clip_path: Path | None = None
    if req.sim_script:
        script_path = _resolve(project, req.sim_script)
        if not script_path.is_file():
            return _error("script_not_found", f"Sim script not found: {req.sim_script}")
    else:
        assert req.clip is not None
        clip_path = _resolve(project, req.clip)
        if not clip_path.is_file():
            return _error("clip_not_found", f"Clip not found: {req.clip}")

    cache_file = project / ".Kodiac" / "verify_cache" / f"{_cache_key(script_path, test_path, req, clip_path)}.json"
    if not req.fresh and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["cached"] = True
            cached.setdefault("badges", []).append("[CACHED VERDICT: fresh=false]")
            return cached
        except (OSError, ValueError):
            pass

    work = project / ".Kodiac" / "verify" / f"{int(time.time())}-{secrets.token_hex(3)}"
    work.mkdir(parents=True, exist_ok=True)

    from Kodiac_robotics.contracts.core import Clip, ClipRef
    from Kodiac_robotics.io.clip import open_clip
    from Kodiac_robotics.pipeline.run import run

    spans: list[Any] = []
    sim_info: dict[str, Any] | None = None
    if script_path is not None:
        from Kodiac_robotics.sim.runner import run_script

        try:
            sim = run_script(script_path, req.seed, work / "sim", backend="auto")
        except Exception as exc:  # noqa: BLE001
            logger.exception("sim run failed")
            return _error(
                "sim_failed",
                f"Sim script crashed: {type(exc).__name__}: {str(exc)[:300]}",
                "Fix the exception in the script, then call verify again.",
            )
        clip_obj: Clip = open_clip(ClipRef(uri=sim.video_path, source_kind="sim"))
        tracks, cam_K, cam_extrinsic = tracks_from_state(
            Path(sim.state_path), n_frames=clip_obj.n_frames, height=clip_obj.height, width=clip_obj.width
        )
        spans = load_spans(sim.spans_path)
        sim_info = {
            "backend": sim.backend,
            "is_mock": sim.is_mock,
            "seed": sim.seed,
            "script_sha256": sim.script_sha256,
            "n_frames": sim.n_frames,
            "fps": sim.fps,
            "video_path": sim.video_path,
            "state_path": sim.state_path,
            "spans_path": sim.spans_path,
        }
        result = run(
            test=test_path,
            clip=clip_obj,
            mode=req.mode,
            tracks=tracks,
            camera="tier_a",
            cam_K=cam_K,
            cam_extrinsic=cam_extrinsic,
            render_card=True,
            output_dir=work / "run",
        )
        badges = [b for b in result.badges if b != _CACHED_SAM_BADGE] + [BADGE_SIM_STATE]
        if sim.is_mock:
            badges.append(BADGE_MOCK)
        backends = {**result.backends, "perception": "sim_state_projection", "sim": sim.backend}
        evidence_type = EVIDENCE_SIM_STATE
        result = result.model_copy(update={"badges": badges, "backends": backends})
    else:
        assert clip_path is not None
        backend: Literal["api", "modal", "fixture"] = os.environ.get("KODIAC_SEGMENT_BACKEND", "fixture")  # type: ignore[assignment]
        if backend not in ("api", "modal", "fixture"):
            return _error("bad_backend", f"KODIAC_SEGMENT_BACKEND={backend!r} is not api|modal|fixture")
        result = run(test=test_path, clip=clip_path, mode=req.mode, backend=backend, render_card=True, output_dir=work / "run")
        evidence_type = "fixture_replay" if result.is_fixture else "perception"

    blame, blame_status = _try_blame(result, test_obj, result.trace_path, sim_info["fps"] if sim_info else 30.0, spans)
    if blame is not None:
        result = result.model_copy(update={"blame": blame})

    payload = result.model_dump(mode="json")
    payload.update(
        {
            "hint": blame.hint.model_dump(mode="json") if blame is not None and blame.hint else None,
            "blame_status": blame_status,
            "failure": _failure_summary(result) if result.verdict != Verdict.PASS else None,
            "evidence_type": evidence_type,
            "is_mock": bool(sim_info and sim_info["is_mock"]),
            "sim": sim_info,
            "cached": False,
            "evidence": {
                "result_json": str(work / "run" / "result.json"),
                "trace": result.trace_path,
                "card": result.card_path,
                "video": sim_info["video_path"] if sim_info else str(clip_path),
                "state": sim_info["state_path"] if sim_info else None,
                "spans": sim_info["spans_path"] if sim_info else None,
            },
            "done_rule": "Done ONLY when this verdict is PASS and the Stop-hook gate agrees.",
        }
    )
    payload["message"] = _message(payload)
    (work / "run").mkdir(parents=True, exist_ok=True)
    (work / "run" / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_verdict(project, payload)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def verify(req: VerifyRequest) -> dict[str, Any]:
    """Run the sim script (or grade a clip) and return the RunResult JSON + blame/hint/evidence.

    Never raises: failures come back as `{"verdict": None, "error": {...}}`.
    """
    try:
        with contextlib.redirect_stdout(sys.stderr):
            return _verify_impl(req)
    except FileNotFoundError as exc:
        return _error("file_not_found", str(exc))
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace into the model
        logger.exception("verify failed")
        return _error("internal_error", f"{type(exc).__name__}: {str(exc)[:300]}", "Run `Kodiac run --debug` to see the trace.")


def build_server() -> FastMCP:
    """Build the FastMCP server "Kodiac" with the single tool `verify`."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        SERVER_NAME,
        instructions=(
            "Kodiac grades physical behaviour. Call `verify` after every edit to the sim script; "
            "the goal is done only when the verdict is PASS."
        ),
    )

    @server.tool(
        name=TOOL_NAME,
        description=(
            "Run the sim script and grade the resulting video with a .green test. Returns "
            "PASS / FAIL / CAN'T TELL with measured evidence, blame (onset frame + cause) and a hint "
            "when available. Never guesses: CAN'T TELL means unresolved."
        ),
    )
    def verify_tool(
        test: str,
        sim_script: str | None = None,
        seed: int = 0,
        clip: str | None = None,
        mode: Literal["fast", "full"] = "full",
        fresh: bool = True,
    ) -> dict[str, Any]:
        try:
            req = VerifyRequest(test=test, sim_script=sim_script, seed=seed, clip=clip, mode=mode, fresh=fresh)
        except ValidationError as exc:
            return _error("invalid_request", exc.errors()[0].get("msg", "invalid request"))
        return verify(req)

    return server


def main() -> None:
    """stdio entry point (`Kodiac mcp`)."""
    build_server().run(transport="stdio")


__all__ = ["build_server", "load_pred_frames", "load_spans", "main", "tracks_from_state", "verify"]
