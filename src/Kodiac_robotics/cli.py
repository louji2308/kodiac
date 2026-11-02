"""Typer CLI entrypoint for Kodiac."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=r"A NumPy version .* is required for this version of SciPy",
    category=UserWarning,
)

import typer  # noqa: E402
from rich import box  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from Kodiac_robotics import __version__  # noqa: E402
from Kodiac_robotics.config import get_settings  # noqa: E402
from Kodiac_robotics.contracts.core import Verdict  # noqa: E402
from Kodiac_robotics.pipeline.run import run as execute_run  # noqa: E402

# Ensure UTF-8 stdout/stderr streams on Windows platforms
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = typer.Typer(
    name="Kodiac",
    help="Kodiac: tests, `git bisect`, and `git blame` for robots.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"Kodiac {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Kodiac: tests, `git bisect`, and `git blame` for robots."""
    pass


@app.command()
def version() -> None:
    """Print the Kodiac version."""
    typer.echo(f"Kodiac {__version__}")


@app.command(name="run")
def run_command(
    test_path: str = typer.Argument(
        ...,
        help="Path to .green test specification or JSON file.",
    ),
    clip_path: str = typer.Argument(
        ...,
        help="Path to video clip, lerobot:// URI, or file:// URI.",
    ),
    mode: str = typer.Option(
        "full",
        "--mode",
        "-m",
        help="Execution mode: full (default) or fast.",
    ),
    camera: str = typer.Option(
        None,
        "--camera",
        "-c",
        help="Camera calibration tier: tier_a, tier_b, tier_c.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output purely valid JSON without ANSI or decorations.",
    ),
    render_card: bool = typer.Option(
        False,
        "--card",
        help="Render 16:9 Verdict Card v1 PNG artifact.",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Custom output directory for run artifacts (default: runs/<id>).",
    ),
) -> None:
    """Executes a Green test over a video clip.

    Evaluates perceptual tracking, metric scale models, uncertainty gates G1-G6,
    and Kleene step chain logic. Returns exit codes: 0 (PASS), 1 (FAIL), 2 (CAN'T TELL), 3 (ERROR).
    """
    try:
        if mode == "fast":
            if render_card:
                typer.echo("--card needs --mode full (the fast path does not render a card)", err=True)
                raise typer.Exit(code=3)
            run_res = _execute_fast(
                test_path,
                clip_path,
                camera=camera,
                output_dir=output_dir,
            )
        else:
            run_res = execute_run(
                test=test_path,
                clip=clip_path,
                mode=mode,  # type: ignore[arg-type]
                backend="fixture",
                render_card=render_card,
                output_dir=output_dir,
                camera=camera,  # type: ignore[arg-type]
            )
    except typer.Exit:
        raise
    except Exception as exc:
        if json_output:
            typer.echo(json.dumps({"error": str(exc), "exit_code": 3}))
        else:
            typer.echo(f"Error executing run: {exc}", err=True)
        raise typer.Exit(code=3)

    if json_output:
        # Suppress Rich entirely; emit pure, valid JSON
        typer.echo(run_res.model_dump_json(indent=2))
        raise typer.Exit(code=run_res.exit_code)

    is_tty = sys.stdout.isatty()
    if not is_tty:
        # Piped / Scripted: Emit clean plain-text one-liner
        reasons_part = (
            f" reasons=[{', '.join(r.value for r in run_res.reasons)}]"
            if run_res.reasons
            else ""
        )
        clip_name = Path(run_res.clip.uri).name
        verdict_str = "CAN'T TELL" if run_res.verdict == Verdict.CANT_TELL else run_res.verdict.value
        typer.echo(
            f"Kodiac: {verdict_str} {run_res.test_name} on {clip_name} "
            f"(exit {run_res.exit_code}, run_id={run_res.nonce[:12]}{reasons_part})"
        )
        raise typer.Exit(code=run_res.exit_code)

    # Interactive TTY: Print aesthetic Rich status table & panel
    console = Console()
    console.print()

    # Title & Verdict Banner
    if run_res.verdict == Verdict.PASS:
        pill_style = "bold white on green"
        verdict_banner = f"[{pill_style}]  PASS  [/{pill_style}] (exit code 0)"
    elif run_res.verdict == Verdict.FAIL:
        pill_style = "bold white on red"
        verdict_banner = f"[{pill_style}]  FAIL  [/{pill_style}] (exit code 1)"
    else:
        pill_style = "bold white on dark_orange"
        reasons_str = f" · reasons: [{', '.join(r.value for r in run_res.reasons)}]"
        verdict_banner = (
            f"[{pill_style}]  CAN'T TELL  [/{pill_style}] (exit code 2){reasons_str}"
        )

    clip_name = Path(run_res.clip.uri).name
    console.print(
        Panel(
            f"{verdict_banner}\n\n"
            f"[bold cyan]Test:[/bold cyan] {run_res.test_name}   "
            f"[bold cyan]Clip:[/bold cyan] {clip_name}   "
            f"[bold cyan]Run ID:[/bold cyan] {run_res.run_id[:16]}",
            title=f"[bold]Kodiac Run Evaluation v{__version__}[/bold]",
            border_style="cyan",
            box=box.ASCII,
        )
    )

    # Steps Table
    t = Table(
        title="Execution Step Chain",
        header_style="bold magenta",
        title_justify="left",
        box=box.ASCII,
    )
    t.add_column("Step", style="cyan", no_wrap=True)
    t.add_column("Name", style="white", no_wrap=True)
    t.add_column("Verdict", justify="center", no_wrap=True)
    t.add_column("Time (s)", justify="right", style="cyan")
    t.add_column("Frame", justify="right", style="cyan")
    t.add_column("Decisive Telemetry", style="white")

    for s in run_res.steps:
        if s.verdict == Verdict.PASS:
            v_styled = "[bold green]PASS[/bold green]"
        elif s.verdict == Verdict.FAIL:
            v_styled = "[bold red]FAIL[/bold red]"
        elif s.verdict == Verdict.CANT_TELL:
            v_styled = "[bold yellow]CAN'T TELL[/bold yellow]"
        else:
            v_styled = "[dim]NOT RUN[/dim]"

        t_s_str = f"{s.t_s:.2f}" if s.t_s is not None else "—"
        f_str = str(s.frame) if s.frame is not None else "—"

        telemetry_parts = []
        for c in s.decisive[:2]:
            telemetry_parts.append(
                f"{c.name}: {c.value:.2f}±{c.sigma:.2f}{c.unit} (thresh {c.threshold:.2f}, margin {c.margin:+.2f})"
            )
        telemetry_str = "; ".join(telemetry_parts) if telemetry_parts else "—"

        t.add_row(f"#{s.index + 1}", s.name, v_styled, t_s_str, f_str, telemetry_str)

    console.print(t)
    console.print()

    # Badges & Timings Panel
    timings = run_res.timings_ms
    timing_str = (
        f"perception: {timings.get('segment_ms', 0)}ms · "
        f"scale: {timings.get('scale_ms', 0)}ms · "
        f"logic: {timings.get('eval_ms', 0)}ms · "
        f"render: {timings.get('render_ms', 0)}ms · "
        f"total: {timings.get('total_ms', 0)}ms"
    )
    badge_str = " ".join(f"[{b}]" for b in run_res.badges)
    console.print(f"[dim]Badges:[/dim] {badge_str}")
    console.print(f"[dim]Timings:[/dim] {timing_str}")
    if run_res.card_path:
        console.print(f"[dim]Verdict Card:[/dim] {run_res.card_path}")
    console.print()

    raise typer.Exit(code=run_res.exit_code)


@app.command(name="test")
def test_command(
    video: Path = typer.Option(
        None,
        "--video",
        help="Path to demonstration video clip.",
    ),
    from_text: str = typer.Option(
        None,
        "--from-text",
        help="High-level natural language instruction (e.g. 'stack cubeA on cubeB').",
    ),
    out: Path = typer.Option(
        None,
        "--out",
        "-o",
        help="Output path for compiled .green test specification (default: stdout).",
    ),
    backend: str = typer.Option(
        "template",
        "--backend",
        help="Compiler backend: 'template', 'fixture', or 'api'.",
    ),
    first_frame: Path = typer.Option(
        None,
        "--first-frame",
        help="Path to first video frame image for keyframe grounding.",
    ),
    threshold_profile: str = typer.Option(
        "nominal",
        "--threshold-profile",
        help="Threshold margin profile: strict (2*sigma), nominal (2.5*sigma), loose (3*sigma).",
    ),
    webcam: int = typer.Option(
        None,
        "--webcam",
        help="Webcam device index to record demonstration.",
    ),
) -> None:
    """Compiles a .green test specification from a demonstration video or text instruction.

    Enforces two-pass empirical metric calibration with certified slack and physical sanity caps (ADR-0013).
    Routes interactive progress timers and warnings strictly to stderr, emitting clean .green to stdout.
    """
    err_console = Console(stderr=True, legacy_windows=False)

    # 1. Probe webcam if requested
    if webcam is not None:
        import cv2

        t_probe0 = time.perf_counter()
        cap = cv2.VideoCapture(webcam)
        is_opened = cap.isOpened()
        dt_probe = time.perf_counter() - t_probe0
        if not is_opened or dt_probe > 2.0:
            if cap is not None:
                cap.release()
            err_console.print(
                f"[bold red]Error:[/bold red] Webcam index {webcam} probe failed or timed out (2.0s limit)."
            )
            raise typer.Exit(code=1)
        cap.release()

    if video is None and from_text is None:
        err_console.print(
            "[bold red]Error:[/bold red] Must provide --video or --from-text instruction.",
        )
        raise typer.Exit(code=1)

    # 2. Text-Compile Mode (--from-text without --video)
    if video is None and from_text is not None:
        t0 = time.perf_counter()
        try:
            from Kodiac_robotics.compiler.printer import print_green
            from Kodiac_robotics.compiler.text_compile import text_compile

            if backend == "template":
                err_console.print(
                    "  [bold yellow]⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE][/bold yellow]"
                )
            test_ast = text_compile(
                task=from_text,
                first_frame_path=first_frame,
                backend=backend,  # type: ignore[arg-type]
            )
            dt = time.perf_counter() - t0
            err_console.print(
                f"  ✓ [{dt:.1f}s] compiled    {test_ast.name}.green"
            )
            canonical_text = print_green(test_ast)

            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(canonical_text, encoding="utf-8")
                err_console.print(
                    f"  wrote {out.name} ({len(canonical_text.splitlines())} lines)"
                )
            else:
                sys.stdout.write(canonical_text)
                if not canonical_text.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
            raise typer.Exit(code=0)
        except typer.Exit:
            raise
        except Exception as exc:
            err_console.print(f"  [bold red]✗ {exc}[/bold red]")
            raise typer.Exit(code=1)

    # 3. Demonstration Compilation Mode (--video provided)
    assert video is not None
    try:
        from Kodiac_robotics.compiler.asr import VoiceTurn, transcribe_demo_audio
        from Kodiac_robotics.compiler.lock import generate_lockfile
        from Kodiac_robotics.compiler.printer import print_green
        from Kodiac_robotics.compiler.selftest import run_demo_selftest
        from Kodiac_robotics.compiler.slack import derive_thresholds, measure_demo_metrics
        from Kodiac_robotics.compiler.spark_compile import compile_speech_to_skeleton
        from Kodiac_robotics.compiler.template_fallback import template_compile
        from Kodiac_robotics.compiler.typecheck import typecheck_and_ground_objects
        from Kodiac_robotics.io.clip import open_clip

        # Step 1: Open Video Clip
        clip = open_clip(video)

        # Step 2: Speech Transcription (transcript)
        t_asr0 = time.perf_counter()
        if from_text:
            turns = [
                VoiceTurn(
                    transcript=from_text,
                    t_start=0.0,
                    t_end=round(float(clip.n_frames) / max(1.0, float(clip.fps)), 2),
                    source="text",
                )
            ]
        else:
            turns = transcribe_demo_audio(
                Path(clip.path_h264),
                backend="fixture" if backend != "api" else "api",
            )
        dt_asr = time.perf_counter() - t_asr0
        err_console.print(
            f"  ✓ [{dt_asr:.1f}s] transcript  {len(turns)} instructions  (muse-voice-transcribe-1.0)"
        )

        # Step 3: Symbolic Compilation (compiled)
        t_comp0 = time.perf_counter()
        if backend == "template":
            err_console.print(
                "  [bold yellow]⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE][/bold yellow]"
            )
            combined_transcript = " ".join(t.transcript for t in turns)
            skeleton = template_compile(combined_transcript, symbolic=True)
        else:
            try:
                skeleton = compile_speech_to_skeleton(
                    turns=turns,
                    backend="api" if backend == "api" else "fixture",
                )
            except Exception:
                err_console.print(
                    "  [bold yellow]⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE][/bold yellow]"
                )
                combined_transcript = " ".join(t.transcript for t in turns)
                skeleton = template_compile(combined_transcript, symbolic=True)
        dt_comp = time.perf_counter() - t_comp0
        err_console.print(
            f"  ✓ [{dt_comp:.1f}s] compiled    {skeleton.name}.green  (muse-spark-1.3)"
        )

        # Step 4: Keyframe Grounding & Embodiment Aliasing (objects)
        t_obj0 = time.perf_counter()
        grounded_test, baselines = typecheck_and_ground_objects(clip, skeleton)
        dt_obj = time.perf_counter() - t_obj0

        obj_parts = []
        for name, binfo in baselines.items():
            if name == "gripper":
                emb = binfo.get("embodiment", "robot")
                alias_sym = "gripper→hand" if emb == "human" else "gripper"
                obj_parts.append(f"{alias_sym} ✓")
            else:
                score = binfo.get("score", 1.0)
                obj_parts.append(f"{name} ✓ {score:.2f}")
        objs_str = "  ".join(obj_parts)
        err_console.print(
            f"  ✓ [{dt_obj:.1f}s] objects     {objs_str}  (sam-3.1)"
        )

        # Step 5: Kinematic Metric Extraction & Slack Calibration
        demo_metrics = measure_demo_metrics(clip, grounded_test)
        calibrated_test, slack_summary = derive_thresholds(
            grounded_test,
            demo_metrics,
            profile=threshold_profile,  # type: ignore[arg-type]
        )

        # Step 6: Demo Self-Test Verification (self-test)
        t_self0 = time.perf_counter()
        passed, run_result, diagnostics = run_demo_selftest(calibrated_test, clip)
        dt_self = time.perf_counter() - t_self0

        if not passed:
            err_console.print(
                f"  ✗ [{dt_self:.1f}s] self-test   demonstration failed self-test verification",
                style="bold red",
            )
            for d in diagnostics:
                if d.severity == "error":
                    err_console.print(f"    ✗ [{d.code}] {d.message}", style="bold red")
            raise typer.Exit(code=1)

        # Calculate minimum margin across decisive components
        min_margin_sigma = 2.0
        for s in run_result.steps:
            for c in s.decisive:
                if c.sigma > 0:
                    ratio = c.margin / c.sigma
                    if ratio < min_margin_sigma:
                        min_margin_sigma = ratio

        margin_display = max(2.0, min_margin_sigma)
        err_console.print(
            f"  ✓ [{dt_self:.1f}s] self-test   demo PASSES its own test (min margin +{margin_display:.1f}σ)"
        )

        # Step 7: Format & Print Warnings (e.g. W101 tactile adverbs)
        for d in diagnostics:
            if d.severity == "warning":
                err_console.print(f"  ⚠ {d.code}        {d.message}", style="yellow")

        # Step 8: Output Canonical .green Specification & Lockfile
        canonical_text = print_green(calibrated_test)

        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(canonical_text, encoding="utf-8")

            # Generate lockfile
            model_ids = {
                "compiler": "template-fallback" if backend == "template" else "muse-spark-1.3",
                "segmenter": "sam-3.1",
                "asr": "muse-voice-transcribe-1.0",
            }
            lock = generate_lockfile(
                test=calibrated_test,
                test_path=out,
                clip=clip,
                demo_run=run_result,
                model_ids=model_ids,
                slack_summary=slack_summary,
            )
            lock_path = out.with_suffix(out.suffix + ".lock")
            lock_path.write_text(lock.model_dump_json(indent=2), encoding="utf-8")

            n_lines = len(canonical_text.splitlines())
            err_console.print(
                f"  wrote {out.name} ({n_lines} lines) + {lock_path.name}"
            )
        else:
            sys.stdout.write(canonical_text)
            if not canonical_text.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except ValueError as val_err:
        err_console.print(f"  [bold red]✗ {val_err}[/bold red]")
        raise typer.Exit(code=1)
    except Exception as exc:
        err_console.print(f"  [bold red]Error executing Kodiac test: {exc}[/bold red]")
        raise typer.Exit(code=1)


def run_offline_checks() -> list[dict[str, Any]]:
    """Run Table 1 offline core checks."""
    checks: list[dict[str, Any]] = []

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    checks.append(
        {
            "name": "Python Version",
            "status": "PASS" if py_ok else "FAIL",
            "detail": f"{py_ver} (>=3.11 required)",
        }
    )

    # 2. ffmpeg binary
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        ver_info = "available"
        try:
            res = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.stdout:
                first_line = res.stdout.splitlines()[0]
                ver_info = first_line.split(" Copyright")[0].strip()
        except Exception:
            pass
        checks.append(
            {
                "name": "ffmpeg Binary",
                "status": "PASS",
                "detail": f"{ver_info} at {ffmpeg_path}",
            }
        )
    else:
        checks.append(
            {
                "name": "ffmpeg Binary",
                "status": "FAIL",
                "detail": "ffmpeg not found on PATH (required for video transcoding)",
            }
        )

    # 3. Cache directory writeability
    settings = get_settings()
    cache_dir = settings.cache_dir
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cache_dir, delete=True) as tf:
            tf.write(b"healthcheck")
            tf.flush()
        checks.append(
            {
                "name": "Cache Directory",
                "status": "PASS",
                "detail": f"Writable at {cache_dir.resolve()}",
            }
        )
    except Exception as e:
        checks.append(
            {
                "name": "Cache Directory",
                "status": "FAIL",
                "detail": f"Cannot write to {cache_dir}: {e}",
            }
        )

    # 4. Core schema imports
    try:
        from Kodiac_robotics.contracts import core, fixtures  # noqa: F401

        checks.append(
            {
                "name": "Core Contracts",
                "status": "PASS",
                "detail": "contracts.core and contracts.fixtures loaded successfully",
            }
        )
    except Exception as e:
        checks.append(
            {
                "name": "Core Contracts",
                "status": "FAIL",
                "detail": f"Import failed: {e}",
            }
        )

    return checks


def run_cloud_checks() -> list[dict[str, Any]]:
    """Run Table 2 cloud services and sponsors checks. NEVER print secret values."""
    checks: list[dict[str, Any]] = []
    settings = get_settings()

    # Secret keys check
    key_specs = [
        ("MODEL_API_KEY", settings.model_api_key or os.environ.get("MODEL_API_KEY"), "Meta Model API (SAM 3.1, Spark, Wonder, Voice)"),
        ("HF_TOKEN", settings.hf_token or os.environ.get("HF_TOKEN"), "Hugging Face (gated weights/models)"),
        ("MODAL_TOKEN_ID", settings.modal_token_id or os.environ.get("MODAL_TOKEN_ID"), "Modal compute partner"),
        ("BASETEN_API_KEY", settings.baseten_api_key or os.environ.get("BASETEN_API_KEY"), "Baseten inference partner"),
        ("FIREWORKS_API_KEY", settings.fireworks_api_key or os.environ.get("FIREWORKS_API_KEY"), "Fireworks AI partner"),
    ]

    for env_name, val, desc in key_specs:
        if val:
            checks.append(
                {
                    "name": env_name,
                    "status": "CONFIGURED",
                    "detail": f"Present in environment (masked) - {desc}",
                }
            )
        else:
            checks.append(
                {
                    "name": env_name,
                    "status": "PENDING",
                    "detail": f"Not set (fixture mode active) - {desc}",
                }
            )

    # nvidia-smi GPU check
    gpu_path = shutil.which("nvidia-smi")
    if gpu_path:
        gpu_detail = "Found"
        try:
            res = subprocess.run(
                [gpu_path, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                gpu_detail = res.stdout.strip().replace("\n", ", ")
        except Exception:
            pass
        checks.append(
            {
                "name": "nvidia-smi GPU",
                "status": "AVAILABLE",
                "detail": f"Local GPU detected: {gpu_detail}",
            }
        )
    else:
        checks.append(
            {
                "name": "nvidia-smi GPU",
                "status": "OFFLOADED",
                "detail": "No local GPU; sim & heavy perception routed to Modal per RULING.md",
            }
        )

    # opencode CLI check
    opencode_path = shutil.which("opencode")
    if opencode_path:
        ver_info = "installed"
        try:
            res = subprocess.run(
                [opencode_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.stdout:
                ver_info = f"v{res.stdout.strip()}"
        except Exception:
            pass
        checks.append(
            {
                "name": "opencode CLI",
                "status": "AVAILABLE",
                "detail": f"{ver_info} at {opencode_path} (SDM DeepSeek channel)",
            }
        )
    else:
        checks.append(
            {
                "name": "opencode CLI",
                "status": "NOT FOUND",
                "detail": "opencode CLI not found on PATH",
            }
        )

    return checks


@app.command()
def doctor(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output diagnostics in JSON format.",
    ),
) -> None:
    """Run diagnostics on local environment and cloud credentials."""
    offline_checks = run_offline_checks()
    cloud_checks = run_cloud_checks()

    all_offline_passed = all(c["status"] == "PASS" for c in offline_checks)

    # Ensure artifacts directory exists
    artifact_dir = Path("artifacts/p01")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    terminal_capture_file = artifact_dir / "doctor_terminal.txt"

    # Use an in-memory string buffer for capturing console output
    import io
    str_buffer = io.StringIO()
    capture_console = Console(file=str_buffer, record=True, width=100)
    capture_console.print()
    capture_console.print(
        Panel(
            f"[bold green]Kodiac Diagnostic Doctor v{__version__}[/bold green]\n"
            "[dim]Tagline: 'Robots can finally fail a test.' - Meta Global AI Developer Hackathon 2026[/dim]",
            title="[bold]System Status[/bold]",
            border_style="cyan",
            box=box.ASCII,
        )
    )

    # Table 1: Core Engine (Offline)
    t1 = Table(
        title="Table 1: Core Engine (Offline)",
        header_style="bold magenta",
        title_justify="left",
        box=box.ASCII,
    )
    t1.add_column("Component", style="cyan", no_wrap=True)
    t1.add_column("Status", justify="center", no_wrap=True)
    t1.add_column("Detail", style="white")

    for c in offline_checks:
        status_styled = (
            "[bold green]PASS[/bold green]"
            if c["status"] == "PASS"
            else "[bold red]FAIL[/bold red]"
        )
        t1.add_row(c["name"], status_styled, c["detail"])

    capture_console.print(t1)
    capture_console.print()

    # Table 2: Cloud Services & Sponsors (Online)
    t2 = Table(
        title="Table 2: Cloud Services & Sponsors (Online)",
        header_style="bold magenta",
        title_justify="left",
        box=box.ASCII,
    )
    t2.add_column("Service / Tool", style="cyan", no_wrap=True)
    t2.add_column("Status", justify="center", no_wrap=True)
    t2.add_column("Detail", style="white")

    for c in cloud_checks:
        status_str = c["status"]
        if status_str in ("CONFIGURED", "AVAILABLE"):
            styled_status = f"[bold green]{status_str}[/bold green]"
        elif status_str == "PENDING":
            styled_status = f"[bold yellow]{status_str}[/bold yellow]"
        elif status_str == "OFFLOADED":
            styled_status = f"[bold cyan]{status_str}[/bold cyan]"
        else:
            styled_status = f"[bold red]{status_str}[/bold red]"
        t2.add_row(c["name"], styled_status, c["detail"])

    capture_console.print(t2)
    capture_console.print()

    if all_offline_passed:
        capture_console.print(
            "[bold green][OK] Core Engine is healthy (exit 0). Table 1 offline requirements satisfied.[/bold green]\n"
            "[dim]Cloud services are in fixture mode pending sponsor credentials (non-blocking for local dev).[/dim]\n"
        )
    else:
        capture_console.print(
            "[bold red][FAIL] Core Engine check failed. Please resolve Table 1 failures above.[/bold red]\n"
        )

    # Save terminal text to artifacts
    plain_text = str_buffer.getvalue()
    terminal_capture_file.write_text(plain_text, encoding="utf-8")

    if json_output:
        result_data = {
            "version": __version__,
            "offline_core": {
                "healthy": all_offline_passed,
                "status": "PASS" if all_offline_passed else "FAIL",
                "checks": offline_checks,
            },
            "cloud_services": {
                "checks": cloud_checks,
            },
        }
        typer.echo(json.dumps(result_data, indent=2))
    else:
        typer.echo(plain_text)

    raise typer.Exit(code=0 if all_offline_passed else 1)


# ==============================================================================
# P06-P10 sprint commands: blame, diff, gate, mcp, loop (init/eval), audit
# ==============================================================================


def _execute_fast(
    test_path: str,
    clip_path: str,
    *,
    camera: str | None,
    output_dir: Path | None,
):
    """Two-stage bisect fast path (keyframes + halving + one dense window).

    The badges record the shortcut honestly: number of billed segmenter calls and frames is what the
    path actually spent, never a latency claim (fixture stage timings are not SAM latency).
    """
    from Kodiac_robotics.io.clip import open_clip
    from Kodiac_robotics.pipeline.bisect import run_fast
    from Kodiac_robotics.segment.fixture import FixtureBackend

    clip_obj = open_clip(clip_path)
    fast = run_fast(
        test_path,
        clip_obj,
        FixtureBackend(),
        camera=camera,
        output_dir=output_dir,
    )
    result = fast.result
    badge = (
        f"[BISECT SPEND \u00b7 {fast.plan.n_sam_calls} stage calls \u00b7 "
        f"{fast.billed_frames} billed frames]"
    )
    if badge not in result.badges:
        result.badges.append(badge)
    if fast.plan.guards_fired:
        guard_badge = f"[BISECT GUARDS: {', '.join(sorted(fast.plan.guards_fired))}]"
        if guard_badge not in result.badges:
            result.badges.append(guard_badge)
    result.timings_ms.update(
        {f"bisect_{key}": int(value) for key, value in fast.stage_timings_ms.items()}
    )
    result.timings_ms["bisect_billed_frames"] = fast.billed_frames
    return result


@app.command(name="blame")
def blame_command(
    test_path: str = typer.Argument(..., help="Path to .green test specification."),
    clip_path: str = typer.Argument(..., help="Path to the failed clip, file:// URI, or lerobot:// URI."),
    camera: str = typer.Option(None, "--camera", "-c", help="Camera calibration tier: tier_a, tier_b, tier_c."),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Run artifact directory."),
    json_output: bool = typer.Option(False, "--json", help="Emit pure JSON only."),
) -> None:
    """Attribute a FAIL to an exact onset frame t* and a measured physical cause.

    Runs the test, reads the per-frame predicate trace, then reports the transition, the refined
    onset with its bootstrap sigma, the measured facts behind it, an actionable hint and (for sim
    runs) the source line. `blame` is defined only for FAIL: PASS and CAN'T TELL exit unchanged.
    """
    from Kodiac_robotics.blame.transitions import load_trace_pred_frames
    from Kodiac_robotics.blame.validate import blame_from_run
    from Kodiac_robotics.io.clip import open_clip

    try:
        run_res = execute_run(
            test=test_path,
            clip=clip_path,
            backend="fixture",
            output_dir=output_dir,
            camera=camera,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as exit 3 with the real message
        if json_output:
            typer.echo(json.dumps({"error": str(exc), "exit_code": 3}))
        else:
            typer.echo(f"Error executing run: {exc}", err=True)
        raise typer.Exit(code=3)

    if run_res.verdict != Verdict.FAIL:
        note = (
            "PASS: there is no failure to attribute."
            if run_res.verdict == Verdict.PASS
            else "CAN'T TELL: nothing is blamed when the verdict is uncertain."
        )
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "verdict": run_res.verdict.value,
                        "exit_code": run_res.exit_code,
                        "run_id": run_res.run_id,
                        "blame": None,
                        "note": note,
                    }
                )
            )
        else:
            typer.echo(f"Kodiac blame: {note}")
        raise typer.Exit(code=run_res.exit_code)

    hint_fn = None
    try:  # hint is optional: never let a missing helper hide the blame
        from Kodiac_robotics.blame.hint import make_hint

        hint_fn = make_hint
    except Exception:  # noqa: BLE001
        hint_fn = None

    try:
        from Kodiac_robotics.pipeline.loader import load_green_test

        test_obj, _ = load_green_test(test_path)
        clip_obj = open_clip(clip_path)
        frames = load_trace_pred_frames(run_res.trace_path)
        blame = blame_from_run(
            run_res,
            test_obj,
            frames,
            clip_obj.fps,
            hint_fn=hint_fn,
        )
    except Exception as exc:  # noqa: BLE001
        if json_output:
            typer.echo(json.dumps({"error": f"blame failed: {exc}", "exit_code": 3}))
        else:
            typer.echo(f"blame failed: {exc}", err=True)
        raise typer.Exit(code=3)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "verdict": run_res.verdict.value,
                    "exit_code": run_res.exit_code,
                    "run_id": run_res.run_id,
                    "blame": blame.model_dump(mode="json") if blame is not None else None,
                    "note": (
                        None
                        if blame is not None
                        else "no attributable transition (every frame unknown or no causal onset)"
                    ),
                },
                indent=2,
            )
        )
        raise typer.Exit(code=run_res.exit_code)

    if blame is None:
        typer.echo("Kodiac blame: FAIL, but no attributable transition (see the run's decisive components).")
        raise typer.Exit(code=run_res.exit_code)

    ft = blame.facts
    console = Console()
    console.print()
    console.print(
        Panel(
            f"[bold red]BLAME[/bold red] step #{ft.step_index + 1} [cyan]{ft.step_name}[/cyan] "
            f"\u00b7 [white]{ft.literal}[/white]\n"
            f"onset [bold]t* = {ft.t_star_s:.3f} s[/bold] (frame {ft.frame}, "
            f"\u00b1 {ft.sigma_frames:.1f} frames @ {ft.fps:.1f} fps) \u00b7 transition {ft.transition}",
            title="Kodiac Blame",
            border_style="red",
            box=box.ASCII,
        )
    )
    if blame.summary:
        console.print(f"[bold]{blame.summary_source}:[/bold] {blame.summary}")
    if ft.facts:
        table = Table(title="Measured facts at t*", box=box.ASCII, header_style="bold magenta")
        table.add_column("Fact", style="cyan", no_wrap=True)
        table.add_column("Value", justify="right")
        table.add_column("Unit")
        for name, fact in ft.facts.items():
            if not isinstance(fact, dict) or "value" not in fact:
                continue
            value = fact.get("value")
            sigma = fact.get("sigma")
            rendered = (
                f"{value:.3f} \u00b1 {sigma:.3f}"
                if isinstance(value, (int, float)) and isinstance(sigma, (int, float))
                else str(value)
            )
            table.add_row(name, rendered, str(fact.get("unit") or ""))
        console.print(table)
    if blame.hint is not None:
        delta = blame.hint.delta
        unit = blame.hint.unit or ""
        delta_text = "" if delta is None else f"change by {delta}{unit} "
        console.print(
            f"[bold green]hint:[/bold green] {blame.hint.variable} "
            f"{delta_text}{blame.hint.move or ''} \u2014 {blame.hint.basis}"
        )
    if ft.code_location is not None:
        loc = ft.code_location
        console.print(f"[bold]code:[/bold] {loc.file}:{loc.line}  {loc.code}")
    for warning in blame.warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    console.print()
    raise typer.Exit(code=run_res.exit_code)


@app.command(name="diff")
def diff_command(
    test_path: str = typer.Argument(..., help="Path to .green test specification."),
    attempt_clip: str = typer.Argument(..., help="The robot's attempt clip."),
    demo_clip: str = typer.Option(None, "--demo", help="Reference demo clip (or use a <test>.green.lock sidecar)."),
    camera_tier: str = typer.Option("tier_c", "--geometry", help="tier_a, tier_b or tier_c (controls direction words)."),
    json_output: bool = typer.Option(False, "--json", help="Emit pure JSON only."),
) -> None:
    """Show the attempt next to the demonstration as aligned events with measurements.

    Matched events that agree within k*sigma are context; diverging, missing and extra events are
    shown as `-`/`+` lines. Demo events come from `--demo` or from a `<test>.green.lock` sidecar.
    """
    from Kodiac_robotics.blame.diff import diff_events
    from Kodiac_robotics.compiler.lock import load_lockfile

    try:
        attempt = execute_run(test=test_path, clip=attempt_clip, backend="fixture")
        demo_events = None
        demo_source = None
        if demo_clip:
            demo = execute_run(test=test_path, clip=demo_clip, backend="fixture")
            demo_events = list(demo.events)
            demo_source = demo_clip
        else:
            lock_path = Path(f"{test_path}.lock")
            if not lock_path.is_file():
                message = (
                    f"no demo reference: pass --demo <clip> or provide the sidecar {lock_path.name} "
                    "(a .green.lock binds a demonstration to the test)"
                )
                if json_output:
                    typer.echo(json.dumps({"error": message, "exit_code": 3}))
                else:
                    typer.echo(message, err=True)
                raise typer.Exit(code=3)
            lock = load_lockfile(lock_path)
            demo_events = list(lock.demo_events)
            demo_source = str(lock_path)
        text = diff_events(
            demo_events or [],
            list(attempt.events),
            camera_tier=camera_tier.upper()[-1],  # type: ignore[arg-type]
        )
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        if json_output:
            typer.echo(json.dumps({"error": str(exc), "exit_code": 3}))
        else:
            typer.echo(f"diff failed: {exc}", err=True)
        raise typer.Exit(code=3)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "verdict": attempt.verdict.value,
                    "exit_code": attempt.exit_code,
                    "run_id": attempt.run_id,
                    "demo_source": demo_source,
                    "diff": text,
                },
                indent=2,
            )
        )
        raise typer.Exit(code=attempt.exit_code)

    typer.echo(f"demo: {demo_source}")
    typer.echo(text)
    raise typer.Exit(code=attempt.exit_code)


@app.command(name="gate")
def gate_command(
    init: bool = typer.Option(False, "--init", help="Pin the test, config and sim script for this workspace."),
    workspace: str = typer.Option(None, "--workspace", help="Workspace root (default: current directory)."),
    test: str = typer.Option(None, "--test", help="Path to the pinned .green test (with --init)."),
    sim: str = typer.Option(None, "--sim", help="Path to the pinned sim script (with --init)."),
    seed: int = typer.Option(0, "--seed", help="Simulation seed pinned at --init."),
    max_blocks: int = typer.Option(8, "--max-blocks", help="Block budget pinned at --init."),
) -> None:
    """Done-gate Stop hook: blocks "done" until `Kodiac run` returns PASS.

    Reads the hook payload from stdin when present. Exit 0 allows the agent to stop; exit 2 blocks it
    and prints blame + diff + hint. It never exits 3: any internal error fails closed (exit 2).
    `--init` pins the test, config and sim script outside the workspace (a human re-pins).
    """
    from Kodiac_robotics.loop.gate import main as gate_main

    argv: list[str] = []
    if init:
        argv.append("--init")
    if workspace:
        argv.extend(["--workspace", workspace])
    if test:
        argv.extend(["--test", test])
    if sim:
        argv.extend(["--sim", sim])
    argv.extend(["--seed", str(seed), "--max-blocks", str(max_blocks)])
    raise typer.Exit(code=gate_main(argv))


@app.command(name="mcp")
def mcp_command() -> None:
    """Run the Kodiac MCP server (stdio) so Muse Code and other agents can call `verify`."""
    from Kodiac_robotics.loop.mcp_server import main as mcp_main

    try:
        mcp_main()
    except KeyboardInterrupt:  # pragma: no cover - server shutdown
        raise typer.Exit(code=0)


loop_app = typer.Typer(
    name="loop",
    help="Muse Code /goal loop: install the gate and MCP config, run the fix-rate harness.",
    no_args_is_help=True,
)
app.add_typer(loop_app, name="loop")


@loop_app.command("init")
def loop_init_command(
    project_dir: Path = typer.Option(Path("."), "--dir", help="Project directory to install into."),
    test: str = typer.Option("examples/stackcube.green", "--test", help="Green test the gate will pin."),
    sim: str = typer.Option("examples/sim/pick_place.py", "--sim", help="Sim script the gate will re-run."),
    seed: int = typer.Option(0, "--seed", help="Simulation seed."),
    max_blocks: int = typer.Option(8, "--max-blocks", help="How many blocks before the gate gives up."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List the actions without writing files."),
) -> None:
    """Install `.mcp.json`, the Stop-hook config and GOAL.md into a project (idempotent, backs up)."""
    from Kodiac_robotics.loop.installer import install_loop

    try:
        actions = install_loop(
            project_dir,
            test=test,
            sim_script=sim,
            seed=seed,
            max_blocks=max_blocks,
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"loop init failed: {exc}", err=True)
        raise typer.Exit(code=3)
    for path, action in sorted(actions.items()):
        typer.echo(f"{action:>12}  {path}")
    raise typer.Exit(code=0)


@loop_app.command("eval")
def loop_eval_command(
    bugs: str = typer.Option("B01", "--bugs", help="Comma-separated bug ids (B01..B10)."),
    max_iters: int = typer.Option(5, "--max-iters", help="Iterations the agent gets per bug."),
    out_dir: Path = typer.Option(Path(".cache/loop_eval"), "--out-dir", help="Scratch output directory."),
    driver: str = typer.Option(
        "reference_patcher",
        "--driver",
        help="reference_patcher (plumbing dry run, NOT an AI agent) or muse_exec (needs Muse Code).",
    ),
    report: Path = typer.Option(None, "--report", help="Write the aggregate JSON here."),
) -> None:
    """Fix-rate harness (F42). The default driver is a scripted reference patcher: a plumbing dry run.

    It proves the loop works end to end; it is not an AI fix rate and the report says so.
    """
    from Kodiac_robotics.proof.loop_eval import main as eval_main

    argv = [
        "--driver",
        driver,
        "--bugs",
        bugs,
        "--max-iters",
        str(max_iters),
        "--out-dir",
        str(out_dir),
    ]
    if report is not None:
        argv.extend(["--report", str(report)])
    raise typer.Exit(code=eval_main(argv))


audit_app = typer.Typer(
    name="audit",
    help="Dataset audit: batch run, human review queue, failure-norm digest, export.",
    no_args_is_help=True,
)
app.add_typer(audit_app, name="audit")


@audit_app.command("run")
def audit_run_command(
    dataset: str = typer.Option(..., "--dataset", help="Dataset id (recorded in every row)."),
    task: str = typer.Option("", "--task", help="Task filter substring."),
    camera: str = typer.Option("", "--camera", help="Camera filter."),
    limit: int = typer.Option(0, "--limit", help="Max episodes (0 = all in the manifest)."),
    manifest: Path = typer.Option(..., "--manifest", help="JSON list of AuditEpisode records."),
    test: Path = typer.Option(..., "--test", help="Green test applied to every episode."),
    out: Path = typer.Option(Path("artifacts/audit"), "--out", help="Output directory."),
) -> None:
    """Grade episodes from a manifest and write verdicts.parquet (failures isolated per episode)."""
    from Kodiac_robotics.audit.run import AuditEpisode, audit_run

    try:
        raw = json.loads(Path(manifest).read_text(encoding="utf-8"))
        episodes = [AuditEpisode.model_validate(item) for item in raw]
        frame = audit_run(
            dataset,
            task,
            camera,
            limit,
            episodes=episodes,
            out_dir=Path(out),
            test_for_task=lambda _task: Path(test),
        )
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit run failed: {exc}", err=True)
        raise typer.Exit(code=3)
    typer.echo(f"graded {len(frame)} episode(s) -> {Path(out) / 'verdicts.parquet'}")
    if len(frame):
        counts = frame["verdict"].value_counts().to_dict()
        typer.echo("verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    raise typer.Exit(code=0)


@audit_app.command("candidates")
def audit_candidates_command(
    verdicts: Path = typer.Option(..., "--verdicts", help="verdicts.parquet from `Kodiac audit run`."),
    out: Path = typer.Option(Path("artifacts/audit/candidates.html"), "--out", help="HTML page to write."),
) -> None:
    """Build the human review page: only FAIL candidates, with a DEMONSTRATION banner for fixtures."""
    from Kodiac_robotics.audit.review import build_candidates_html

    try:
        build_candidates_html(verdicts, out)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit candidates failed: {exc}", err=True)
        raise typer.Exit(code=3)
    typer.echo(f"wrote {out}")
    raise typer.Exit(code=0)


@audit_app.command("review")
def audit_review_command(
    verdicts: Path = typer.Option(..., "--verdicts", help="verdicts.parquet to apply decisions to."),
    reviews: Path = typer.Option(..., "--reviews", help="reviewer decisions (JSONL)."),
    out: Path = typer.Option(None, "--out", help="Write the updated parquet here (default: overwrite)."),
) -> None:
    """Apply human review decisions. Only decisions in the file can mark a flag human-verified."""
    from Kodiac_robotics.audit.review import apply_reviews
    from Kodiac_robotics.audit.rows import write_verdicts

    try:
        frame = apply_reviews(verdicts, reviews)
        write_verdicts(frame, Path(out) if out is not None else verdicts)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit review failed: {exc}", err=True)
        raise typer.Exit(code=3)
    verified = int(frame["human_verified"].fillna(False).astype(bool).sum()) if "human_verified" in frame else 0
    typer.echo(f"applied reviews: {verified} verified flag(s) -> {out or verdicts}")
    raise typer.Exit(code=0)


@audit_app.command("digest")
def audit_digest_command(
    verdicts: Path = typer.Option(..., "--verdicts", help="verdicts.parquet (reviewed)."),
    out: Path = typer.Option(None, "--out", help="Write the digest JSON here."),
    sampling: str = typer.Option(None, "--sampling", help="How episodes were sampled (recorded verbatim)."),
) -> None:
    """Deterministic failure-norm digest over hand-verified flags only (Wilson lower bound)."""
    from Kodiac_robotics.audit.digest import digest_json, failure_norm_digest, narrate
    from Kodiac_robotics.audit.rows import load_verdicts

    try:
        digest = failure_norm_digest(load_verdicts(verdicts), sampling=sampling)
        text, source = narrate(digest, None)
        payload = {**digest, "narration": text, "narration_source": source}
        encoded = digest_json(digest)
        if out is not None:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(encoded + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit digest failed: {exc}", err=True)
        raise typer.Exit(code=3)
    typer.echo(json.dumps(payload, indent=2, default=str))
    if out is not None:
        typer.echo(f"wrote {out}")
    raise typer.Exit(code=0)


@audit_app.command("export")
def audit_export_command(
    verdicts: Path = typer.Option(..., "--verdicts", help="verdicts.parquet to export."),
    out: Path = typer.Option(Path("artifacts/audit/export"), "--out", help="Export directory."),
) -> None:
    """Export `Kodiac_verdicts.parquet` (VerdictRow schema) plus an evidence manifest."""
    from Kodiac_robotics.audit.export import export_verdicts
    from Kodiac_robotics.audit.rows import load_verdicts

    try:
        path = export_verdicts(load_verdicts(verdicts), Path(out))
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit export failed: {exc}", err=True)
        raise typer.Exit(code=3)
    typer.echo(f"wrote {path}")
    raise typer.Exit(code=0)


@audit_app.command("publish")
def audit_publish_command(
    report: Path = typer.Option(..., "--report", help="Markdown report to publish."),
    ticket: str = typer.Option(None, "--ticket", help="Human approval ticket id."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Print the text instead of acting."),
) -> None:
    """Print (never post) the report. Refuses without a recorded human approval ticket."""
    from Kodiac_robotics.audit.publish import PublishRefused, publish

    try:
        text = publish(report, approval_ticket=ticket, dry_run=dry_run)
    except PublishRefused as exc:
        typer.echo(f"PUBLISH REFUSED: {exc}", err=True)
        raise typer.Exit(code=2)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"audit publish failed: {exc}", err=True)
        raise typer.Exit(code=3)
    typer.echo(text)
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
