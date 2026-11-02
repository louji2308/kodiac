"""Sim execution primitive for the done-gate and the MCP ``verify`` tool (ARCHITECTURE §5.5, §10, KD-11, KD-12).

``run_script(script, seed, out_dir, backend)`` executes a robot program and records a gradeable episode in ``out_dir``:
``video.mp4`` (30 fps), ``state.npz`` (privileged state, one row per video frame), ``spans.jsonl`` and ``meta.json``.
The program exposes ``run(robot)``. The reference ``examples/sim/pick_place.py`` predates that convention and exposes
``execute_pick_place(robot)``, which is accepted as the fallback entry point.

How it works (anti-cheat by construction):

1. The script runs in an isolated child interpreter (``python -I -B``, a whitelisted environment that carries no API
   keys, cwd inside the run directory). The child only records the actions the script commanded through the Robot API
   and the ``@span`` code locations.
2. The parent then replays those actions, step by step, in a fresh environment that it built itself and that the script
   never touched. Every artifact (frames, privileged state, oracle) comes from this replay. A script that monkeypatches
   the env, the oracle, the engine or the gate, writes simulator state directly ("teleports" a cube), or writes fake
   result files changes nothing the grader reads: only the commanded actions survive, and they are re-simulated.
3. Actions are sanity-checked (finite, at most ``MAX_ACTIONS`` steps, at most ``MAX_STEP_M`` of end-effector travel per
   control step, ``|gripper command| <= 1``) so a script cannot teleport the arm through the permissive kinematic model.
4. The script bytes are hashed before the run and re-hashed after it; a script that rewrites itself mid-run is rejected.

Honesty notes (Law 1, ADR-0004, KD-13):

- ``kinematic_mock`` is a pure-NumPy kinematic stand-in, NOT SAPIEN physics. Every frame carries the burned-in
  ``[MOCK SIMULATION · NOT SAPIEN PHYSICS]`` banner and ``meta.json`` carries ``is_mock: true``. ``auto`` selects
  ManiSkill only if ``mani_skill`` and ``gymnasium`` are importable; otherwise (as on the CPU dev machine) the mock.
- ``oracle_success`` is privileged ground truth (``env.oracle_success()``) for evaluation and honesty cross-checks only.
  The done-gate verdict comes from ``pipeline.run.run``, never from the oracle.
- ``state.npz`` is privileged simulator state. The done-gate grades *synthetic* object tracks projected from it through
  the known render camera (``loop.gate.synthetic_tracks_from_state``). That is the loop-demo path, NOT perception
  evidence, and it is labelled that way wherever it surfaces.
- The ManiSkill branch goes through the same replay code but is untested here (``mani_skill`` is not installed).
- ``spans.jsonl`` comes from the child, i.e. it is script-controlled metadata. It feeds blame code locations only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import traceback
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from Kodiac_robotics.sim.spans import SimSpan

FPS = 30.0
CHILD_TIMEOUT_S = 300.0
MAX_ACTIONS = 3600  # 120 s of control at 30 Hz
MAX_STEP_M = 0.05  # 5 cm of commanded end-effector travel per 1/30 s step (1.5 m/s)
MAX_GRIPPER_CMD = 1.0
MAX_SPANS_BYTES = 5_000_000
MAX_ACTIONS_BYTES = MAX_ACTIONS * 7 * 8 + 4096
ENTRY_POINTS = ("run", "execute_pick_place")
MOCK_LABEL = "[MOCK SIMULATION · NOT SAPIEN PHYSICS]"

EXIT_OK = 0
EXIT_SCRIPT_ERROR = 1
EXIT_BACKEND_UNAVAILABLE = 17
EXIT_NO_ENTRY_POINT = 18

ARTIFACT_NAMES = ("video.mp4", "state.npz", "spans.jsonl", "meta.json")

# Environment variables the child interpreter may see. Everything else (API keys, KODIAC_*, tokens) is withheld.
_CHILD_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "APPDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "LANG",
    "LC_ALL",
)

_PKG_SRC_ROOT = str(Path(__file__).resolve().parents[2])

# `-I` drops the user site-packages, where this environment's dependencies may live, so the child receives the
# parent's import path explicitly (with this package's own source root first, so it runs the same Kodiac code).
_CHILD_BOOTSTRAP = (
    "import sys, json; sys.path[:0] = json.loads(sys.argv[1]); "
    "from Kodiac_robotics.sim.runner import _child_main; "
    "raise SystemExit(_child_main(sys.argv[2:]))"
)


def _child_sys_path() -> str:
    entries = [_PKG_SRC_ROOT] + [p for p in sys.path if p and p != _PKG_SRC_ROOT]
    return json.dumps(entries)


class SimRunError(RuntimeError):
    """The script could not be executed or produced an episode that cannot be graded."""


class SimRunResult(BaseModel):
    """Artifacts of one recorded episode (frozen ORCH contract, BRIEF.md)."""

    video_path: str
    state_path: str
    spans_path: str
    oracle_success: bool
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    script_sha256: str
    seed: int
    n_frames: int
    fps: float


@dataclass
class _ChildRun:
    returncode: int
    stderr_tail: str
    actions_path: Path
    spans_path: Path
    report_path: Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def maniskill_available() -> bool:
    """True iff ManiSkill and gymnasium are importable (checked without importing them)."""
    try:
        return (
            importlib.util.find_spec("mani_skill") is not None
            and importlib.util.find_spec("gymnasium") is not None
        )
    except (ImportError, ValueError):
        return False


def resolve_backend(backend: str) -> Literal["maniskill", "kinematic_mock"]:
    if backend == "auto":
        return "maniskill" if maniskill_available() else "kinematic_mock"
    if backend == "maniskill":
        return "maniskill"
    if backend == "kinematic_mock":
        return "kinematic_mock"
    raise SimRunError(f"unknown sim backend {backend!r} (expected auto | kinematic_mock | maniskill)")


def _make_env(backend: Literal["maniskill", "kinematic_mock"]) -> Any:
    if backend == "kinematic_mock":
        from Kodiac_robotics.sim.env import KinematicMockEnv

        return KinematicMockEnv()
    from Kodiac_robotics.sim.env import ManiSkillEnv

    return ManiSkillEnv()


# ==============================================================================
# Child side: runs the untrusted script, records commanded actions and spans
# ==============================================================================


def _child_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kodiac-sim-child")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--display-path", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--backend", choices=["maniskill", "kinematic_mock"], required=True)
    parser.add_argument("--actions-out", required=True)
    parser.add_argument("--spans-out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args(argv)

    from Kodiac_robotics.sim.robot import RobotController

    try:
        env = _make_env(args.backend)
    except Exception as exc:
        print(f"sim backend {args.backend} unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_BACKEND_UNAVAILABLE

    try:
        robot = RobotController(env, capture_frames=False)
        robot.reset(seed=args.seed)

        source = Path(args.snapshot).read_bytes()
        module = types.ModuleType("kodiac_sim_script")
        module.__file__ = args.display_path
        sys.modules[module.__name__] = module
        exec(compile(source, args.display_path, "exec"), module.__dict__)

        entry_name = next((n for n in ENTRY_POINTS if callable(getattr(module, n, None))), None)
        if entry_name is None:
            print(
                f"script defines none of the entry points {ENTRY_POINTS}; expose `def run(robot): ...`",
                file=sys.stderr,
            )
            return EXIT_NO_ENTRY_POINT
        getattr(module, entry_name)(robot)

        if robot.actions:
            actions = np.stack([np.asarray(a, dtype=np.float32).reshape(-1) for a in robot.actions])
        else:
            actions = np.zeros((0, 7), dtype=np.float32)
        np.save(args.actions_out, actions, allow_pickle=False)
        with open(args.spans_out, "w", encoding="utf-8") as fh:
            for s in robot.spans:
                fh.write(s.model_dump_json() + "\n")
        final = env.privileged_state()
        report = {
            "entry_point": entry_name,
            "n_actions": int(actions.shape[0]),
            "final_cubeA_xyz": [float(v) for v in final.cubeA_pose[:3]],
            "backend": args.backend,
        }
        Path(args.report_out).write_text(json.dumps(report), encoding="utf-8")
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        return EXIT_SCRIPT_ERROR
    return EXIT_OK


# ==============================================================================
# Parent side: isolated execution, validation, replay, artifact writing
# ==============================================================================


def _child_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _CHILD_ENV_KEYS if k in os.environ}
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _tail(path: Path, n_chars: int = 1500) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-n_chars:].strip()


def _run_child(
    script_path: Path,
    script_bytes: bytes,
    seed: int,
    backend: Literal["maniskill", "kinematic_mock"],
    out_dir: Path,
) -> _ChildRun:
    work = out_dir / f"_child_{backend}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    snapshot = work / "script_snapshot.py"
    snapshot.write_bytes(script_bytes)
    actions_path = work / "actions.npy"
    spans_path = work / "spans.jsonl"
    report_path = work / "report.json"
    stdout_path = work / "stdout.log"
    stderr_path = work / "stderr.log"

    cmd = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        _CHILD_BOOTSTRAP,
        _child_sys_path(),
        "--snapshot",
        str(snapshot),
        "--display-path",
        str(script_path),
        "--seed",
        str(seed),
        "--backend",
        backend,
        "--actions-out",
        str(actions_path),
        "--spans-out",
        str(spans_path),
        "--report-out",
        str(report_path),
    ]
    with open(stdout_path, "wb") as out_fh, open(stderr_path, "wb") as err_fh:
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=out_fh,
                stderr=err_fh,
                env=_child_env(),
                cwd=str(work),
                timeout=CHILD_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SimRunError(
                f"sim script exceeded the {CHILD_TIMEOUT_S:.0f} s limit and was killed"
            ) from exc
    return _ChildRun(
        returncode=proc.returncode,
        stderr_tail=_tail(stderr_path),
        actions_path=actions_path,
        spans_path=spans_path,
        report_path=report_path,
    )


def _child_failure_message(child: _ChildRun) -> str:
    if child.returncode == EXIT_NO_ENTRY_POINT:
        head = "sim script has no entry point"
    elif child.returncode == EXIT_BACKEND_UNAVAILABLE:
        head = "sim backend unavailable"
    else:
        head = f"sim script crashed (child exit code {child.returncode})"
    lines = [ln for ln in child.stderr_tail.splitlines() if ln.strip()]
    detail = " | ".join(lines[-3:]) if lines else "no stderr output"
    return f"{head}: {detail}"


def validate_actions(actions: np.ndarray) -> np.ndarray:
    """Check a commanded action log; returns it as float32 (n, 7) or raises SimRunError."""
    arr = np.asarray(actions)
    if arr.ndim != 2 or arr.shape[1] != 7:
        raise SimRunError(f"action log must have shape (n, 7), got {arr.shape}")
    if not np.issubdtype(arr.dtype, np.floating):
        raise SimRunError(f"action log must be floating point, got dtype {arr.dtype}")
    arr = arr.astype(np.float32)
    n = int(arr.shape[0])
    if n == 0:
        raise SimRunError("sim script commanded no robot actions")
    if n > MAX_ACTIONS:
        raise SimRunError(f"sim script commanded {n} control steps (limit {MAX_ACTIONS} = 120 s at 30 Hz)")
    if not np.all(np.isfinite(arr)):
        raise SimRunError("action log contains NaN or infinite values")
    travel = np.linalg.norm(arr[:, :3].astype(np.float64), axis=1)
    worst = int(np.argmax(travel))
    if float(travel[worst]) > MAX_STEP_M:
        raise SimRunError(
            f"control step {worst} commands {travel[worst] * 100:.1f} cm of end-effector travel in 1/30 s "
            f"(limit {MAX_STEP_M * 100:.0f} cm per step); teleporting the arm is not a valid robot motion"
        )
    grip = np.abs(arr[:, 6].astype(np.float64))
    if float(grip.max()) > MAX_GRIPPER_CMD + 1e-6:
        raise SimRunError(f"gripper command magnitude {grip.max():.3f} exceeds {MAX_GRIPPER_CMD}")
    return arr


def _load_actions(path: Path) -> np.ndarray:
    if not path.is_file():
        raise SimRunError("sim script produced no action log (did it exit before finishing?)")
    data = path.read_bytes()
    if len(data) > MAX_ACTIONS_BYTES:
        raise SimRunError(f"action log too large ({len(data)} bytes)")
    try:
        arr = np.load(io.BytesIO(data), allow_pickle=False)
    except Exception as exc:
        raise SimRunError(f"action log unreadable: {type(exc).__name__}") from exc
    return validate_actions(arr)


def _load_spans(path: Path) -> list[SimSpan]:
    if not path.is_file():
        raise SimRunError("sim script produced no span log")
    data = path.read_bytes()
    if len(data) > MAX_SPANS_BYTES:
        raise SimRunError(f"span log too large ({len(data)} bytes)")
    spans: list[SimSpan] = []
    for i, line in enumerate(data.decode("utf-8", errors="strict").splitlines()):
        if not line.strip():
            continue
        try:
            spans.append(SimSpan.model_validate_json(line))
        except Exception as exc:
            raise SimRunError(f"span log line {i + 1} is not a valid SimSpan") from exc
    return spans


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SimRunError("sim child wrote no report")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SimRunError("sim child report unreadable") from exc
    if not isinstance(report, dict):
        raise SimRunError("sim child report is not a JSON object")
    return report


def _ee_position(env: Any) -> np.ndarray:
    ee = getattr(env, "ee_pos", None)
    if ee is not None:
        return np.asarray(ee, dtype=np.float64).reshape(3)
    try:
        inner = getattr(env.env, "unwrapped", env.env)
        p = inner.agent.tcp.pose.p
        p = p.cpu().numpy() if hasattr(p, "cpu") else np.asarray(p)
        return np.asarray(p, dtype=np.float64).reshape(-1)[:3]
    except Exception as exc:
        raise SimRunError(f"cannot read the end-effector position from backend {type(env).__name__}") from exc


def _frame(env: Any) -> np.ndarray:
    frame = env.render()
    if hasattr(frame, "cpu"):
        frame = frame.cpu().numpy()
    arr = np.asarray(frame)
    while arr.ndim > 3 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise SimRunError(f"renderer returned a frame of shape {arr.shape}, expected (H, W, 3)")
    return np.ascontiguousarray(arr.astype(np.uint8))


class _VideoSink:
    """Streams RGB frames into an H.264 yuv420p MP4 (ffmpeg) or an mp4v MP4 (OpenCV fallback)."""

    def __init__(self, path: Path, fps: float) -> None:
        self.path = path
        self.fps = fps
        self.codec = ""
        self.n_frames = 0
        self._shape: tuple[int, ...] | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._writer: Any = None
        self._log_path = path.with_suffix(".ffmpeg.log")
        self._log_fh: Any = None

    def _open(self, width: int, height: int) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg and width % 2 == 0 and height % 2 == 0:
            self._log_fh = open(self._log_path, "wb")
            self._proc = subprocess.Popen(
                [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{width}x{height}", "-r", str(self.fps), "-i", "-",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(self.fps),
                    str(self.path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._log_fh,
            )
            self.codec = "h264/yuv420p (ffmpeg)"
            return
        try:
            import cv2
        except Exception as exc:
            raise SimRunError("neither ffmpeg nor OpenCV is available to write the episode video") from exc
        self._writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height))
        if not self._writer.isOpened():
            raise SimRunError("OpenCV could not open a video writer (ffmpeg not found)")
        self.codec = "mp4v (OpenCV fallback; ffmpeg not found)"

    def write(self, frame: np.ndarray) -> None:
        if self._shape is None:
            self._shape = frame.shape
            self._open(frame.shape[1], frame.shape[0])
        if frame.shape != self._shape:
            raise SimRunError(f"frame size changed mid-episode: {frame.shape} vs {self._shape}")
        if self._proc is not None:
            assert self._proc.stdin is not None
            try:
                self._proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as exc:
                raise SimRunError(f"ffmpeg stopped accepting frames: {_tail(self._log_path, 300)}") from exc
        else:
            import cv2

            self._writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        self.n_frames += 1

    def close(self) -> None:
        if self._proc is not None:
            assert self._proc.stdin is not None
            try:
                self._proc.stdin.close()
            except OSError:
                pass
            rc = self._proc.wait(timeout=120)
            if self._log_fh is not None:
                self._log_fh.close()
            if rc != 0:
                raise SimRunError(f"ffmpeg failed (exit {rc}): {_tail(self._log_path, 300)}")
            self._log_path.unlink(missing_ok=True)
        elif self._writer is not None:
            self._writer.release()
        if not self.path.is_file() or self.path.stat().st_size == 0:
            raise SimRunError("episode video was not written")

    def abort(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.wait(timeout=30)
        if self._log_fh is not None and not self._log_fh.closed:
            self._log_fh.close()
        if self._writer is not None:
            self._writer.release()


def _replay(
    backend: Literal["maniskill", "kinematic_mock"],
    seed: int,
    actions: np.ndarray,
    video_path: Path,
) -> dict[str, Any]:
    """Re-simulate the commanded actions in a fresh env owned by this process."""
    env = _make_env(backend)
    env.reset(seed=seed)
    sink = _VideoSink(video_path, FPS)
    states = [env.privileged_state()]
    ee = [_ee_position(env)]
    try:
        sink.write(_frame(env))
        for a in actions:
            env.step(a.copy())
            states.append(env.privileged_state())
            ee.append(_ee_position(env))
            sink.write(_frame(env))
        sink.close()
    except BaseException:
        sink.abort()
        raise
    cam_K = getattr(env, "cam_K", None)
    cam_ext = getattr(env, "cam_extrinsic", None)
    return {
        "states": states,
        "ee": np.stack(ee),
        "oracle_success": bool(env.oracle_success()),
        "is_mock": bool(getattr(env, "is_mock", backend == "kinematic_mock")),
        "camera_known": cam_K is not None and cam_ext is not None,
        "cam_K": np.asarray(cam_K if cam_K is not None else np.eye(3), dtype=np.float64),
        "cam_extrinsic": np.asarray(cam_ext if cam_ext is not None else np.eye(4), dtype=np.float64),
        "codec": sink.codec,
        "n_video_frames": sink.n_frames,
    }


def _state_npz_bytes(replay: dict[str, Any], actions: np.ndarray, seed: int) -> bytes:
    states = replay["states"]
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        actions=actions.astype(np.float32),
        ee_pos=replay["ee"].astype(np.float64),
        cubeA_pose=np.asarray([s.cubeA_pose for s in states], dtype=np.float64),
        cubeB_pose=np.asarray([s.cubeB_pose for s in states], dtype=np.float64),
        cubeA_vel=np.asarray([s.cubeA_vel for s in states], dtype=np.float64),
        gripper_width=np.asarray([s.gripper_width for s in states], dtype=np.float64),
        in_contact=np.asarray([s.in_contact for s in states], dtype=bool),
        step=np.asarray([s.step for s in states], dtype=np.int64),
        t_s=np.asarray([s.t_s for s in states], dtype=np.float64),
        cam_K=replay["cam_K"],
        cam_extrinsic=replay["cam_extrinsic"],
        camera_known=np.bool_(replay["camera_known"]),
        frame_aligned=np.bool_(True),
        fps=np.float64(FPS),
        seed=np.int64(seed),
        is_mock=np.bool_(replay["is_mock"]),
    )
    return buf.getvalue()


def run_script(
    script: Path,
    seed: int,
    out_dir: Path,
    backend: Literal["auto", "kinematic_mock", "maniskill"] = "auto",
) -> SimRunResult:
    """Run ``script`` on the chosen backend and record a gradeable episode (see module docstring)."""
    result, _ = run_script_with_digests(script, seed, out_dir, backend)
    return result


def run_script_with_digests(
    script: Path,
    seed: int,
    out_dir: Path,
    backend: Literal["auto", "kinematic_mock", "maniskill"] = "auto",
) -> tuple[SimRunResult, dict[str, str]]:
    """``run_script`` plus the sha256 of every artifact as written, so a grader can detect later tampering."""
    script_path = Path(script).resolve()
    if not script_path.is_file():
        raise SimRunError(f"sim script not found: {script_path}")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or int(seed) < 0:
        raise SimRunError(f"seed must be a non-negative integer, got {seed!r}")
    seed = int(seed)
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACT_NAMES:
        (out / name).unlink(missing_ok=True)

    script_bytes = script_path.read_bytes()
    script_sha = sha256_bytes(script_bytes)
    concrete = resolve_backend(backend)
    fallback_reason: str | None = None

    child = _run_child(script_path, script_bytes, seed, concrete, out)
    if child.returncode == EXIT_BACKEND_UNAVAILABLE and backend == "auto" and concrete == "maniskill":
        fallback_reason = child.stderr_tail[-300:]
        concrete = "kinematic_mock"
        child = _run_child(script_path, script_bytes, seed, concrete, out)
    if child.returncode != EXIT_OK:
        raise SimRunError(_child_failure_message(child))

    if sha256_bytes(script_path.read_bytes()) != script_sha:
        raise SimRunError("sim script changed on disk while it was running; the episode cannot be attributed to it")

    actions = _load_actions(child.actions_path)
    spans = _load_spans(child.spans_path)
    report = _load_report(child.report_path)

    video_path = out / "video.mp4"
    replay = _replay(concrete, seed, actions, video_path)
    n_frames = len(replay["states"])
    if replay["n_video_frames"] != n_frames:
        raise SimRunError(f"video has {replay['n_video_frames']} frames but the state log has {n_frames}")

    state_bytes = _state_npz_bytes(replay, actions, seed)
    state_path = out / "state.npz"
    state_path.write_bytes(state_bytes)
    spans_bytes = "".join(s.model_dump_json() + "\n" for s in spans).encode("utf-8")
    spans_path = out / "spans.jsonl"
    spans_path.write_bytes(spans_bytes)
    video_sha = sha256_bytes(video_path.read_bytes())

    divergence_m: float | None = None
    child_final = report.get("final_cubeA_xyz")
    if isinstance(child_final, list) and len(child_final) == 3:
        try:
            replay_final = np.asarray(replay["states"][-1].cubeA_pose[:3], dtype=np.float64)
            divergence_m = float(np.linalg.norm(np.asarray(child_final, dtype=np.float64) - replay_final))
        except (TypeError, ValueError):
            divergence_m = None

    is_mock = bool(replay["is_mock"])
    meta: dict[str, Any] = {
        "schema": "kodiac.sim_run/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script_path": str(script_path),
        "script_sha256": script_sha,
        "entry_point": report.get("entry_point"),
        "seed": seed,
        "backend": concrete,
        "env_backend": concrete,
        "is_mock": is_mock,
        "label": MOCK_LABEL if is_mock else "ManiSkill3 SAPIEN physics",
        "backend_requested": backend,
        "backend_fallback_reason": fallback_reason,
        "evidence_type": "kinematic_mock_replay" if is_mock else "maniskill_replay",
        "fps": FPS,
        "n_frames": n_frames,
        "n_actions": int(actions.shape[0]),
        "video_codec": replay["codec"],
        "camera_known": bool(replay["camera_known"]),
        "oracle_success": bool(replay["oracle_success"]),
        "oracle_note": "privileged env.oracle_success(); eval and honesty cross-checks only; never the gate verdict",
        "grading_note": "artifacts come from a parent-side replay of the commanded Robot-API actions",
        "child_replay_divergence_m": divergence_m,
        "spans_source": "child process (script-controlled metadata; blame code locations only)",
        "sha256": {
            "script": script_sha,
            "video": video_sha,
            "state": sha256_bytes(state_bytes),
            "spans": sha256_bytes(spans_bytes),
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    result = SimRunResult(
        video_path=str(video_path),
        state_path=str(state_path),
        spans_path=str(spans_path),
        oracle_success=bool(replay["oracle_success"]),
        backend=concrete,
        is_mock=is_mock,
        script_sha256=script_sha,
        seed=seed,
        n_frames=n_frames,
        fps=FPS,
    )
    return result, dict(meta["sha256"])


def load_spans(path: Path | str) -> list[SimSpan]:
    """Parse a ``spans.jsonl`` written by ``run_script``."""
    return _load_spans(Path(path))


__all__ = [
    "FPS",
    "MOCK_LABEL",
    "SimRunError",
    "SimRunResult",
    "load_spans",
    "maniskill_available",
    "resolve_backend",
    "run_script",
    "run_script_with_digests",
    "validate_actions",
]


if __name__ == "__main__":
    raise SystemExit(_child_main(sys.argv[1:]))
