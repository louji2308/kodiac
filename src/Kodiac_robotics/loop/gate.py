"""Done-gate: the Muse Code ``Stop`` hook that blocks "done" until a fresh ``Kodiac run`` returns PASS (KD-11, §5.5).

``gate_check(workspace, hook_payload) -> (exit_code, message)`` with exit 0 = allow the stop, exit 2 = block it and feed
``message`` (verdict, blame, code location, hint) back to the agent. It never returns 3: every internal error fails
closed with exit 2 ``GATE ERROR: ...``.

Decision procedure (it never trusts a file the agent can write):

1. No pins for the workspace -> exit 0 (never blocks unrelated sessions). Pins present but missing/corrupt -> exit 2.
2. ``blocks >= max_blocks`` -> ``GATE EXHAUSTED: goal NOT verified``, ``.Kodiac/gate_exhausted``, exit 0.
3. Env file (``KODIAC_ENV_FILE`` or the one pinned at init) must exist and parse if configured; values are never
   printed and never passed to the script under test.
4. Test sha256, config sha256 and the Kodiac engine-source digest must equal the pins.
5. The pinned script (current contents) is re-run through ``sim.runner.run_script_with_digests`` (isolated child +
   parent-side replay), then graded with ``pipeline.run.run`` on tracks projected from the gate's own replayed state.
6. PASS iff verdict == PASS and test sha == pin and config sha == pin and ``clip.source_kind == "sim"`` and the graded
   clip is the video just produced from ``sha256(current script)`` (digest-checked). Otherwise ``blocks += 1``, exit 2.
   ``stop_hook_active`` never auto-passes. ``.Kodiac/last_verdict.json`` is never read.

Honesty: on the kinematic mock every message carries ``[MOCK SIMULATION]`` and the result carries ``[MOCK SIMULATION]``
and ``[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]`` badges. The privileged oracle is never part of the decision
and never shown to the agent; it is stored outside the workspace (``last_result`` in the pin file) as a cross-check.
No verdict card is rendered here: ``render/card.py`` stamps a ``[sam-3.1]`` badge on every card, which would be false
for synthetic tracks.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import secrets
import sys
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import (
    Blame,
    Clip,
    ClipRef,
    CodeLocation,
    GateState,
    GreenLock,
    GreenTest,
    ObjMask,
    PredFrame,
    RunResult,
    StepResult,
    Track,
    Verdict,
)
from Kodiac_robotics.loop.pins import (
    PinError,
    config_sha256,
    current_config,
    default_config_files,
    engine_sha256,
    load_pins,
    save_pins,
    write_pins,
)
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.pipeline.run import run as pipeline_run
from Kodiac_robotics.segment.rle import mask_to_rle
from Kodiac_robotics.sim.runner import (
    MOCK_LABEL,
    SimRunError,
    SimRunResult,
    load_spans,
    resolve_backend,
    run_script_with_digests,
)
from Kodiac_robotics.sim.spans import SimSpan, find_blame_span

EXIT_ALLOW = 0
EXIT_BLOCK = 2

MOCK_TAG = "[MOCK SIMULATION]"
SYNTHETIC_TRACKS_BADGE = "[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]"
_CACHED_SAM_BADGE = "[REPLAY: CACHED SAM 3.1 TRACKS]"
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Secret values loaded from the env file during the current gate_check, redacted from any message.
_ACTIVE_SECRETS: list[str] = []


class GateError(RuntimeError):
    """An internal condition that makes the gate fail closed (exit 2, ``GATE ERROR``)."""


class _Refusal(Exception):
    """A definite refusal (exit 2, ``GATE BLOCKED``) with a first line and detail lines."""

    def __init__(
        self,
        kind: str,
        first_line: str,
        details: list[str] | None = None,
        record: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(first_line)
        self.kind = kind
        self.first_line = first_line
        self.details = details or []
        self.record = record or {}


# ==============================================================================
# Synthetic tracks from the gate's own replayed sim state (loop-demo path, NOT perception)
# ==============================================================================

_TRACK_SPECS = (
    ("cubeA", "cubeA_pose", 0.04, True),
    ("cubeB", "cubeB_pose", 0.04, True),
    ("gripper", "ee_pos", 0.04, False),
)


def synthetic_tracks_from_state(
    state: Mapping[str, Any],
    *,
    height: int = 512,
    width: int = 512,
) -> dict[str, Track]:
    """Project privileged sim positions through the render camera into masks that Tier A inverts exactly.

    Each mask is a square whose bottom anchor is the projection of the object's support point (cube bottom centre, or
    the gripper fingertip) and whose float bbox width encodes the true camera depth (``fx * size / z``), so Tier A
    recovers positions to sub-pixel quantisation (~1 mm at the mock camera). Objects partly outside the frame are left
    out of that frame (not visible) rather than given wrong geometry. These are NOT perception outputs.
    """
    if not bool(np.asarray(state.get("camera_known", True))):
        raise GateError("sim state has no camera calibration; cannot project it into tracks")
    K = np.asarray(state["cam_K"], dtype=np.float64)
    E = np.asarray(state["cam_extrinsic"], dtype=np.float64)
    if K.shape != (3, 3) or E.shape != (4, 4):
        raise GateError(f"bad camera matrices in sim state: K {K.shape}, extrinsic {E.shape}")
    R, t = E[:3, :3], E[:3, 3]
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]

    tracks: dict[str, Track] = {}
    canvas = np.zeros((height, width), dtype=np.uint8)
    for name, key, size_m, is_cube in _TRACK_SPECS:
        pos = np.asarray(state[key], dtype=np.float64)[:, :3].copy()
        if is_cube:
            pos[:, 2] -= size_m / 2.0
        frames: dict[int, ObjMask] = {}
        for f, p in enumerate(pos):
            pc = R @ p + t
            z = float(pc[2])
            if z <= 1e-3:
                continue
            u = fx * pc[0] / z + cx
            v = fy * pc[1] / z + cy
            w = fx * size_m / z
            wi = max(2, int(round(w)))
            x1 = int(round(u - (wi - 1) / 2.0))
            x2 = x1 + wi
            y2 = int(round(v))
            y1 = y2 - wi + 1
            if x1 < 0 or y1 < 0 or x2 > width or y2 >= height:
                continue
            canvas[y1 : y2 + 1, x1:x2] = 1
            frames[f] = ObjMask(
                obj=name,
                frame=f,
                score=1.0,
                bbox_xyxy=(float(u - w / 2.0), float(v - w), float(u + w / 2.0), float(v)),
                rle=mask_to_rle(canvas),
                area_px=int(wi * wi),
                rle_size=(height, width),
            )
            canvas[y1 : y2 + 1, x1:x2] = 0
        tracks[name] = Track(
            obj=name,
            frames=frames,
            backend="fixture",
            direction="forward",
            trace_id=f"synthetic-from-sim-state-{name}",
        )
    return tracks


def tracks_from_state(
    state_path: Path | str,
    *,
    n_frames: int | None = None,
    height: int = 512,
    width: int = 512,
) -> tuple[dict[str, Track], np.ndarray, np.ndarray]:
    """Load a ``run_script`` ``state.npz`` and return ``(synthetic tracks, cam_K, cam_extrinsic)`` (see above)."""
    state = dict(np.load(Path(state_path), allow_pickle=False))
    rows = len(state["cubeA_pose"])
    if n_frames is not None and rows != n_frames:
        raise GateError(f"state has {rows} rows but {n_frames} frames were expected")
    tracks = synthetic_tracks_from_state(state, height=height, width=width)
    return tracks, np.asarray(state["cam_K"]), np.asarray(state["cam_extrinsic"])


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def grade_sim_run(
    test_path: Path,
    sim: SimRunResult,
    out_dir: Path,
    *,
    digests: Mapping[str, str] | None = None,
    config_sha256_value: str | None = None,
) -> RunResult:
    """Grade a ``run_script`` episode with ``pipeline.run.run`` (full path, Tier A) and return an honestly labelled result.

    If ``digests`` (from ``run_script_with_digests``) is given, the state and video must still match them byte for byte.
    Writes ``result.json`` (with corrected badges) into ``out_dir``; pipeline side effects are confined to ``out_dir``.
    """
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    state_bytes = Path(sim.state_path).read_bytes()
    if digests is not None and _sha(state_bytes) != digests.get("state"):
        raise GateError("state.npz changed after the sim run")
    video_bytes = Path(sim.video_path).read_bytes()
    video_sha = _sha(video_bytes)
    if digests is not None and video_sha != digests.get("video"):
        raise GateError("episode video changed after the sim run")
    state = dict(np.load(io.BytesIO(state_bytes), allow_pickle=False))
    if len(state["cubeA_pose"]) != sim.n_frames:
        raise GateError(f"state rows ({len(state['cubeA_pose'])}) != frames ({sim.n_frames})")

    cap = cv2.VideoCapture(sim.video_path)
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    if width <= 0 or height <= 0:
        raise GateError("episode video is unreadable")

    tracks = synthetic_tracks_from_state(state, height=height, width=width)
    clip = Clip(
        ref=ClipRef(uri=str(Path(sim.video_path)), source_kind="sim"),
        path_h264=str(Path(sim.video_path)),
        fps=float(sim.fps),
        n_frames=int(sim.n_frames),
        width=width,
        height=height,
        sha256=video_sha,
    )
    with contextlib.chdir(out):
        raw = pipeline_run(
            Path(test_path),
            clip,
            mode="full",
            tracks=tracks,
            render_card=False,
            output_dir=out,
            camera="tier_a",
            cam_K=np.asarray(state["cam_K"]),
            cam_extrinsic=np.asarray(state["cam_extrinsic"]),
        )

    badges = [b for b in raw.badges if b != _CACHED_SAM_BADGE]
    for b in ("[SIM]", SYNTHETIC_TRACKS_BADGE, *((MOCK_TAG,) if sim.is_mock else ())):
        if b not in badges:
            badges.append(b)
    backends = dict(raw.backends)
    backends["perception"] = "synthetic_from_sim_state"
    backends["sim"] = sim.backend
    update: dict[str, Any] = {"badges": badges, "backends": backends, "is_fixture": True}
    if config_sha256_value is not None:
        update["config_sha256"] = config_sha256_value
    result = raw.model_copy(update=update)
    text = result.model_dump_json(indent=2)
    (out / "result.json").write_text(text, encoding="utf-8")
    side_effect = out / ".Kodiac" / "last_verdict.json"
    if side_effect.exists():
        side_effect.write_text(text, encoding="utf-8")
    return result


def provenance_problems(
    result: RunResult,
    sim: SimRunResult,
    *,
    pinned_test_sha256: str,
    script_sha256_now: str,
    video_sha256_expected: str,
) -> list[str]:
    """Reasons the graded result cannot be attributed to the pinned test and the current script ([] = clean)."""
    problems: list[str] = []
    if result.test_sha256 != pinned_test_sha256:
        problems.append("graded test is not the pinned test")
    if result.clip.source_kind != "sim":
        problems.append(f"clip source_kind is {result.clip.source_kind!r}, not 'sim'")
    if os.path.normcase(str(Path(result.clip.uri))) != os.path.normcase(str(Path(sim.video_path))):
        problems.append("graded clip is not the video this gate run just produced")
    video = Path(sim.video_path)
    if not video.is_file() or _sha(video.read_bytes()) != video_sha256_expected:
        problems.append("episode video changed after it was produced")
    if sim.script_sha256 != script_sha256_now:
        problems.append("episode was produced from a different script than the current one")
    return problems


# ==============================================================================
# Explanations (blame + code location + hint + diff), all optional, never fatal
# ==============================================================================


def _load_pred_frames(trace_path: Path) -> dict[str, list[PredFrame]]:
    frames: dict[str, list[PredFrame]] = {}
    with open(trace_path, "rb") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("record_type") != "pred_frame":
                continue
            pf = PredFrame(
                frame=int(rec["frame"]),
                atom_key=str(rec["atom"]),
                tri=rec["tri"],
                components=rec["components"],
                trace_id=str(rec["trace_id"]),
            )
            frames.setdefault(pf.atom_key, []).append(pf)
    for lst in frames.values():
        lst.sort(key=lambda p: p.frame)
    return frames


def _try_blame(
    result: RunResult, test: GreenTest, fps: float, spans: list[SimSpan]
) -> tuple[Blame | None, str | None]:
    blame_from_run = None
    for mod in ("Kodiac_robotics.blame", "Kodiac_robotics.blame.validate"):
        try:
            blame_from_run = getattr(__import__(mod, fromlist=["blame_from_run"]), "blame_from_run", None)
        except Exception:
            blame_from_run = None
        if blame_from_run is not None:
            break
    if blame_from_run is None:
        return None, "blame module not available yet"
    extra: dict[str, Any] = {}
    if spans:
        extra["spans"] = spans  # sim-span disambiguation (ARCHITECTURE §9): release-before-place vs place_z
    try:
        from Kodiac_robotics.blame.hint import make_hint

        extra["hint_fn"] = make_hint
    except Exception:
        pass
    try:
        pred_frames = _load_pred_frames(Path(result.trace_path))
        try:
            blame = blame_from_run(result, test, pred_frames, fps, **extra)
        except TypeError:
            blame = blame_from_run(result, test, pred_frames, fps)
    except Exception as exc:
        return None, f"blame failed ({type(exc).__name__})"
    if blame is not None and not isinstance(blame, Blame):
        return None, "blame returned an unexpected type"
    return blame, None if blame is not None else "blame found no transition"


def _code_location(spans: list[SimSpan], blame: Blame | None, frame: int | None, predicate: str | None, fps: float) -> CodeLocation | None:
    if blame is not None:
        try:
            from Kodiac_robotics.blame.codeloc import locate_from_fact_table

            loc = locate_from_fact_table(spans, blame.facts)
            if isinstance(loc, CodeLocation):
                return loc
        except Exception:
            pass
        if blame.facts.code_location is not None:
            return blame.facts.code_location
        frame = blame.facts.frame
    if frame is None or not spans:
        return None
    s = find_blame_span(spans, frame, predicate, fps=fps)
    if s is None:
        return None
    return CodeLocation(file=s.file, line=s.line, code=s.code, span_id=s.span_id)


def _decisive_step(result: RunResult) -> StepResult | None:
    for s in result.steps:
        if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL):
            return s
    return None


def _fmt_component(c: Any) -> str:
    return (
        f"{c.name} = {c.value:.2f} ± {c.sigma:.2f} {c.unit} "
        f"(threshold {c.threshold:.2f}, margin {c.margin:+.2f}{', ' + c.reason.value if c.reason else ''})"
    )


def _explain(result: RunResult, test: GreenTest, test_path: Path, sim: SimRunResult) -> list[str]:
    lines: list[str] = []
    for s in result.steps:
        verdict = s.verdict.value if s.verdict is not None else "not evaluated"
        where = f" @ frame {s.frame} ({s.frame / sim.fps:.2f} s)" if s.frame is not None else ""
        lines.append(f"  step {s.index + 1} {s.name}: {verdict}{where}")
        if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL):
            for c in s.decisive[:3]:
                lines.append(f"     {_fmt_component(c)}")
            if s.reasons:
                lines.append(f"     reasons: {', '.join(r.value for r in s.reasons)}")
    if result.reasons:
        lines.append(f"  verdict reasons: {', '.join(r.value for r in result.reasons)}")

    try:
        spans = load_spans(sim.spans_path)
    except Exception:
        spans = []
    blame, why_not = _try_blame(result, test, sim.fps, spans)
    if blame is not None:
        summary = re.sub(r"^\s*blame:\s*", "", blame.summary)
        lines.append(f"  blame: {summary} (summary: {blame.summary_source})")
        ft = blame.facts
        lines.append(f"  t* = frame {ft.frame} ({ft.t_star_s:.2f} s ± {ft.sigma_frames:.1f} frames), {ft.step_name}: {ft.literal}")
    else:
        lines.append(f"  blame: unavailable ({why_not}); decisive measurements above")

    step = _decisive_step(result)
    predicate = None
    if step is not None and step.decisive:
        predicate = min(step.decisive, key=lambda c: c.margin).name.split(".")[0]
    loc = _code_location(spans, blame, step.frame if step else None, predicate, sim.fps)
    if loc is not None:
        lines.append(f"  code: {loc.file}:{loc.line} -> {loc.code}")

    hint = blame.hint if blame is not None else None
    if hint is None and blame is not None:
        try:
            from Kodiac_robotics.blame.hint import make_hint

            hint = make_hint(blame.facts)
        except Exception:
            hint = None
    if hint is not None:
        delta = f" by {hint.delta} {hint.unit or ''}".rstrip() if hint.delta is not None else ""
        move = f" ({hint.move})" if hint.move else ""
        lines.append(f"  hint: change {hint.variable}{delta}{move}; basis: {hint.basis}")

    lock_path = Path(str(test_path) + ".lock")
    if lock_path.is_file():
        try:
            from Kodiac_robotics.blame.diff import diff_events

            lock = GreenLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
            text = diff_events(lock.demo_events, result.events, camera_tier="A")
            if text:
                lines.append("  diff (demo vs attempt):")
                lines.extend(f"    {ln}" for ln in text.splitlines()[:20])
        except Exception:
            pass
    return lines


# ==============================================================================
# Env file (secrets) handling
# ==============================================================================


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file. Errors name the line number, never its content."""
    if not path.is_file():
        raise GateError(f"env file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError(f"env file unreadable: {path} ({type(exc).__name__})") from exc
    values: dict[str, str] = {}
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _ENV_KEY.match(key):
            raise GateError(f"env file {path} line {i} is not KEY=VALUE")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


@contextlib.contextmanager
def _scoped_environ(values: Mapping[str, str]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _env_file_path(pins: Mapping[str, Any]) -> Path | None:
    for var in ("KODIAC_ENV_FILE", "Kodiac_ENV_FILE"):
        value = os.environ.get(var)
        if value:
            return Path(value).expanduser()
    pinned = pins.get("env_file")
    return Path(pinned) if pinned else None


def _redact(text: str) -> str:
    for value in _ACTIVE_SECRETS:
        if len(value) >= 4:
            text = text.replace(value, "***")
    return text


# ==============================================================================
# gate_init / gate_check
# ==============================================================================


def _resolve_in(workspace: Path, p: Path | str) -> Path:
    path = Path(p)
    return (path if path.is_absolute() else workspace / path).resolve()


def gate_init(workspace: Path, test: Path, sim_script: Path, seed: int = 0, max_blocks: int = 8) -> GateState:
    """Pin ``test`` (+ config, engine source), ``sim_script`` and ``seed`` for ``workspace`` outside the workspace."""
    ws = Path(workspace).resolve()
    if not ws.is_dir():
        raise NotADirectoryError(f"workspace is not a directory: {ws}")
    test_p = _resolve_in(ws, test)
    script_p = _resolve_in(ws, sim_script)
    if not test_p.is_file():
        raise FileNotFoundError(f"test file not found: {test_p}")
    if not script_p.is_file():
        raise FileNotFoundError(f"sim script not found: {script_p}")
    test_obj, _ = load_green_test(test_p)
    if not test_obj.steps:
        raise ValueError(f"test {test_p} has no steps")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed!r}")
    if isinstance(max_blocks, bool) or not isinstance(max_blocks, int) or max_blocks < 1:
        raise ValueError(f"max_blocks must be a positive integer, got {max_blocks!r}")
    for var in ("KODIAC_ENV_FILE", "Kodiac_ENV_FILE"):
        if os.environ.get(var):
            _load_env_file(Path(os.environ[var]).expanduser())
            break
    return write_pins(
        ws,
        test=test_p,
        sim_script=script_p,
        seed=seed,
        config_files=default_config_files(ws, test_p),
        max_blocks=max_blocks,
    )


def _rel(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_log(workspace: Path, entry: dict[str, Any]) -> None:
    """Informational log in the workspace; never read by the gate."""
    p = workspace / ".Kodiac" / "gate_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _evaluate(ws: Path, state: GateState, pins: dict[str, Any], tag: str) -> dict[str, Any]:
    """Run every check; returns the PASS record or raises _Refusal / GateError."""
    env_path = _env_file_path(pins)
    env_values = _load_env_file(env_path) if env_path is not None else {}
    _ACTIVE_SECRETS.extend(v for v in env_values.values() if v)

    with _scoped_environ(env_values):
        test_path = Path(pins["test"]["path"])
        if not test_path.is_file():
            raise GateError(f"pinned test file missing: {test_path}")
        test_bytes = test_path.read_bytes()
        test_sha = _sha(test_bytes)
        rel_test = _rel(test_path, ws)
        if test_sha != state.pinned_test_sha256:
            raise _Refusal(
                "test_modified",
                f"GATE BLOCKED{tag}: test modified since `Kodiac gate --init` ({rel_test}: pinned sha256 "
                f"{state.pinned_test_sha256[:12]}, now {test_sha[:12]}); goal NOT verified",
                [f"  restore {rel_test} to the pinned version; the gate never grades an edited test "
                 "(only a human re-running `Kodiac gate --init` can change the pinned test)"],
            )

        entries_now = current_config(pins["config"]["files"])
        cfg_sha = config_sha256(entries_now)
        if cfg_sha != state.pinned_config_sha256:
            pinned = {os.path.normcase(e["path"]): e["sha256"] for e in pins["config"]["files"]}
            changed = [
                _rel(Path(str(e["path"])), ws)
                for e in entries_now
                if pinned.get(os.path.normcase(str(e["path"]))) != e["sha256"]
            ]
            raise _Refusal(
                "config_modified",
                f"GATE BLOCKED{tag}: config modified since `Kodiac gate --init` ({', '.join(changed) or 'config set'}); "
                "goal NOT verified",
                ["  thresholds and config are pinned with the test; restore them to the pinned versions"],
            )

        if engine_sha256() != pins["engine_sha256"]:
            raise _Refusal(
                "engine_modified",
                f"GATE BLOCKED{tag}: Kodiac engine source modified since `Kodiac gate --init`; goal NOT verified",
                ["  the grader's own code (sim, predicates, engine, pipeline, gate) changed; restore it or have a "
                 "human re-run `Kodiac gate --init`"],
            )

        script_path = Path(pins["sim_script"]["path"])
        if not script_path.is_file():
            raise GateError(f"pinned sim script missing: {script_path}")
        script_sha = _sha(script_path.read_bytes())
        rel_script = _rel(script_path, ws)
        seed = int(pins["seed"])

        run_dir = ws / ".Kodiac" / "gate_runs" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
        run_dir.mkdir(parents=True, exist_ok=False)
        try:
            sim, digests = run_script_with_digests(script_path, seed, run_dir / "sim", backend=pins.get("backend", "auto"))
        except SimRunError as exc:
            raise GateError(f"sim run failed: {exc}") from exc
        tag = f" {MOCK_TAG}" if sim.is_mock else ""

        if sim.script_sha256 != script_sha or _sha(script_path.read_bytes()) != script_sha:
            raise _Refusal(
                "script_changed",
                f"GATE BLOCKED{tag}: {rel_script} changed while the gate was verifying it; goal NOT verified",
            )

        snapshot = run_dir / test_path.name
        snapshot.write_bytes(test_bytes)
        test_obj, _ = load_green_test(snapshot)
        result = grade_sim_run(snapshot, sim, run_dir / "run", digests=digests, config_sha256_value=cfg_sha)

        problems = provenance_problems(
            result,
            sim,
            pinned_test_sha256=state.pinned_test_sha256,
            script_sha256_now=_sha(script_path.read_bytes()),
            video_sha256_expected=digests["video"],
        )
        record = {
            "verdict": result.verdict.value,
            "run_id": result.run_id,
            "nonce": result.nonce,
            "run_dir": str(run_dir),
            "script_sha256": sim.script_sha256,
            "backend": sim.backend,
            "is_mock": sim.is_mock,
            "oracle_success_crosscheck": sim.oracle_success,
        }
        if problems:
            raise _Refusal(
                "provenance",
                f"GATE BLOCKED{tag}: provenance check failed ({'; '.join(problems)}); goal NOT verified",
                record=record,
            )

        header = [
            f"  run {result.run_id} · script sha256 {sim.script_sha256[:12]} · seed {seed} · backend {sim.backend}"
            + (f" ({MOCK_LABEL})" if sim.is_mock else "")
            + " · tracks synthetic from sim state (not perception)",
        ]
        if result.verdict != Verdict.PASS:
            verdict_word = "CAN'T TELL" if result.verdict == Verdict.CANT_TELL else result.verdict.value
            try:
                details = _explain(result, test_obj, test_path, sim)
            except Exception as exc:
                details = [f"  explanation unavailable ({type(exc).__name__})"]
            raise _Refusal(
                "verdict_not_pass",
                f"GATE BLOCKED{tag}: {result.test_name} {verdict_word} on a fresh re-run of {rel_script} (seed {seed}); "
                "goal NOT verified",
                header + details,
                record=record,
            )

        record["first_line"] = (
            f"GATE PASS{tag}: {result.test_name} PASS on a fresh re-run of {rel_script} (seed {seed}); goal verified"
        )
        record["details"] = header + [f"  steps: {', '.join(f'{s.name} PASS' for s in result.steps)}"]
        return record


def _gate_check(workspace: Path, hook_payload: dict[str, Any] | None) -> tuple[int, str]:
    ws = Path(workspace).resolve()
    try:
        loaded = load_pins(ws)
    except PinError as exc:
        return EXIT_BLOCK, (
            f"GATE ERROR: {exc} (fail closed; goal NOT verified)\n"
            "  a human must re-run `Kodiac gate --init` to restore the pins"
        )
    if loaded is None:
        return EXIT_ALLOW, "gate: no `Kodiac gate --init` state for this workspace; not gating"
    state, pins = loaded
    stop_active = bool(hook_payload.get("stop_hook_active")) if isinstance(hook_payload, dict) else False

    try:
        predicted_mock = resolve_backend(str(pins.get("backend", "auto"))) == "kinematic_mock"
    except SimRunError:
        predicted_mock = False
    tag = f" {MOCK_TAG}" if predicted_mock else ""

    if state.blocks >= state.max_blocks:
        note = ""
        try:
            marker = ws / ".Kodiac" / "gate_exhausted"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps({"at": _now(), "blocks": state.blocks, "max_blocks": state.max_blocks, "verified": False}),
                encoding="utf-8",
            )
        except OSError as exc:
            note = f"\n  (could not write .Kodiac/gate_exhausted: {type(exc).__name__})"
        return EXIT_ALLOW, (
            f"GATE EXHAUSTED: goal NOT verified ({state.blocks}/{state.max_blocks} blocks used); the stop is allowed only "
            f"so the session can end; treat this run as a FAILURE{note}"
        )

    kind = "error"
    record: dict[str, Any] = {}
    try:
        record = _evaluate(ws, state, pins, tag)
        passed = True
        first_line = record.pop("first_line")
        details = record.pop("details")
        kind = "pass"
    except _Refusal as ref:
        passed = False
        kind = ref.kind
        first_line = ref.first_line
        details = ref.details
        record = ref.record
    except Exception as exc:  # noqa: BLE001 - any evaluation failure fails closed and counts as a block
        passed = False
        reason = str(exc) if isinstance(exc, (GateError, SimRunError)) else f"{type(exc).__name__}: {str(exc)[:300]}"
        first_line = f"GATE ERROR: {reason} (fail closed; goal NOT verified)"
        details = []

    if passed:
        state.last_nonce = record.get("nonce")
    else:
        state.blocks += 1
    pins = dict(pins)
    pins["state"] = state.model_dump()
    pins["last_result"] = {"at": _now(), "kind": kind, "first_line": first_line, "stop_hook_active": stop_active, **record}
    save_pins(ws, pins)

    if pins.get("previous_pins"):
        first = pins["previous_pins"][0]
        details = details + [
            f"  note: pins were re-initialised {len(pins['previous_pins'])}x since the first `Kodiac gate --init` "
            f"(first pinned test sha256 {str(first.get('test_sha256'))[:12]})"
        ]
    if passed:
        footer = [f"  blocks used: {state.blocks}/{state.max_blocks}"]
    else:
        footer = [
            f"  blocks {state.blocks}/{state.max_blocks} · fix the cause and stop again; the gate re-runs the pinned script "
            "from scratch on every stop and never trusts cached verdicts or files in the workspace"
        ]
    try:
        _append_log(
            ws,
            {
                "at": _now(),
                "exit_code": EXIT_ALLOW if passed else EXIT_BLOCK,
                "kind": kind,
                "first_line": first_line,
                "verdict": record.get("verdict"),
                "run_id": record.get("run_id"),
                "script_sha256": record.get("script_sha256"),
                "backend": record.get("backend"),
                "is_mock": record.get("is_mock"),
                "stop_hook_active": stop_active,
                "blocks": state.blocks,
                "max_blocks": state.max_blocks,
            },
        )
    except Exception:
        pass
    return (EXIT_ALLOW if passed else EXIT_BLOCK), "\n".join([first_line, *details, *footer])


def gate_check(workspace: Path, hook_payload: dict | None = None) -> tuple[int, str]:
    """Stop-hook decision: ``(0, message)`` allows the stop, ``(2, message)`` blocks it. Never returns 3."""
    try:
        code, message = _gate_check(Path(workspace), hook_payload)
    except BaseException as exc:  # noqa: BLE001 - fail closed on anything, including SystemExit/KeyboardInterrupt
        code = EXIT_BLOCK
        detail = str(exc)[:300]
        message = f"GATE ERROR: internal error ({type(exc).__name__}: {detail}) (fail closed; goal NOT verified)"
    try:
        if code not in (EXIT_ALLOW, EXIT_BLOCK):
            message = f"GATE ERROR: internal exit code {code!r} mapped to 2 (fail closed; goal NOT verified)\n{message}"
            code = EXIT_BLOCK
        message = _redact(message if isinstance(message, str) else str(message))
    except BaseException:  # noqa: BLE001
        code, message = EXIT_BLOCK, "GATE ERROR: could not format the gate message (fail closed; goal NOT verified)"
    finally:
        _ACTIVE_SECRETS.clear()
    return code, message


# ==============================================================================
# CLI adapter (ORCH wires `Kodiac gate` to this)
# ==============================================================================


def main(argv: list[str] | None = None) -> int:
    """``Kodiac gate [--workspace W]`` (Stop hook; hook JSON on stdin) or ``Kodiac gate --init --test T --sim S``.

    ``--max-blocks`` at check time is accepted for hook compatibility but ignored: the value pinned at ``--init`` is
    authoritative, so editing the hook config cannot shorten the loop. Never exits 3.
    """
    parser = argparse.ArgumentParser(prog="Kodiac gate", add_help=True)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--test", default=None)
    parser.add_argument("--sim", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-blocks", type=int, default=8)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print("GATE ERROR: bad gate arguments (fail closed; goal NOT verified)", file=sys.stderr)
        return EXIT_BLOCK
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    if args.init:
        if not args.test or not args.sim:
            print("gate --init needs --test and --sim", file=sys.stderr)
            return EXIT_BLOCK
        try:
            st = gate_init(workspace, Path(args.test), Path(args.sim), seed=args.seed, max_blocks=args.max_blocks)
        except Exception as exc:
            print(f"gate --init failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_BLOCK
        print(f"gate pinned: test sha256 {st.pinned_test_sha256[:12]} · config sha256 {st.pinned_config_sha256[:12]} "
              f"· max_blocks {st.max_blocks}")
        return EXIT_ALLOW

    payload: dict[str, Any] | None = None
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                parsed = json.loads(raw)
                payload = parsed if isinstance(parsed, dict) else None
    except Exception:
        payload = None
    code, message = gate_check(workspace, payload)
    print(message, file=sys.stderr)
    return code


__all__ = [
    "EXIT_ALLOW",
    "EXIT_BLOCK",
    "GateError",
    "SYNTHETIC_TRACKS_BADGE",
    "gate_check",
    "gate_init",
    "grade_sim_run",
    "main",
    "provenance_problems",
    "synthetic_tracks_from_state",
    "tracks_from_state",
]
