"""Typer CLI entrypoint for Kodiac."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from Kodiac_robotics import __version__
from Kodiac_robotics.config import get_settings
from Kodiac_robotics.contracts.core import Verdict
from Kodiac_robotics.pipeline.run import run as execute_run

warnings.filterwarnings("ignore", category=UserWarning)

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
        run_res = execute_run(
            test=test_path,
            clip=clip_path,
            mode=mode,  # type: ignore[arg-type]
            backend="fixture",
            render_card=render_card,
            output_dir=output_dir,
            camera=camera,  # type: ignore[arg-type]
        )
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


if __name__ == "__main__":
    app()
