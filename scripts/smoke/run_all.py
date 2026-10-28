"""Master runner for Kodiac smoke tests ST01–ST13.

Executes all 13 smoke tests, verifies Law 1 compliance, writes artifacts to artifacts/p01/smoke/,
and prints a summary report.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

try:
    from scripts.smoke import (
        st01_models,
        st02_sam_forward,
        st03_sam_backward,
        st04_spark_judge,
        st05_wonder_adjudicate,
        st06_voice_asr,
        st07_muse_code_hook,
        st08_modal_hello,
        st09_maniskill_render,
        st10_lerobot_droid,
        st11_gated_sam_weights,
        st12_partner_credits,
        st13_sdm,
    )
    from scripts.smoke.common import SmokeResult
except ImportError:
    import st01_models  # type: ignore[no-redef]
    import st02_sam_forward  # type: ignore[no-redef]
    import st03_sam_backward  # type: ignore[no-redef]
    import st04_spark_judge  # type: ignore[no-redef]
    import st05_wonder_adjudicate  # type: ignore[no-redef]
    import st06_voice_asr  # type: ignore[no-redef]
    import st07_muse_code_hook  # type: ignore[no-redef]
    import st08_modal_hello  # type: ignore[no-redef]
    import st09_maniskill_render  # type: ignore[no-redef]
    import st10_lerobot_droid  # type: ignore[no-redef]
    import st11_gated_sam_weights  # type: ignore[no-redef]
    import st12_partner_credits  # type: ignore[no-redef]
    import st13_sdm  # type: ignore[no-redef]
    from common import SmokeResult  # type: ignore[no-redef]

TEST_MODULES = [
    st01_models,
    st02_sam_forward,
    st03_sam_backward,
    st04_spark_judge,
    st05_wonder_adjudicate,
    st06_voice_asr,
    st07_muse_code_hook,
    st08_modal_hello,
    st09_maniskill_render,
    st10_lerobot_droid,
    st11_gated_sam_weights,
    st12_partner_credits,
    st13_sdm,
]


def run_all() -> list[SmokeResult]:
    results: list[SmokeResult] = []
    smoke_dir = Path("artifacts/p01/smoke")
    smoke_dir.mkdir(parents=True, exist_ok=True)

    console = Console(width=100)

    for mod in TEST_MODULES:
        res: SmokeResult = mod.run()
        results.append(res)

    # Build summary table
    table = Table(
        title="Kodiac Smoke Test Suite (ST01-ST13)",
        header_style="bold magenta",
        title_justify="left",
        box=box.ASCII,
    )
    table.add_column("Test ID", style="bold cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Status", justify="center")
    table.add_column("Mode", justify="center")
    table.add_column("Latency (ms)", justify="right")
    table.add_column("Notes", style="dim")

    for r in results:
        mode_str = "FIXTURE" if r.is_fixture else "LIVE"
        if r.ok:
            status_style = "[bold green]OK[/bold green]"
        elif r.status in ("PENDING_KEY", "PENDING_ENV", "PENDING_SIM_ENV"):
            status_style = f"[bold yellow]{r.status}[/bold yellow]"
        else:
            status_style = f"[bold red]{r.status}[/bold red]"

        lat_str = f"{r.latency_ms:.1f}" if r.latency_ms is not None else "-"
        table.add_row(r.test_id, r.name, status_style, mode_str, lat_str, r.notes)

    console.print()
    console.print(table)
    console.print()

    # Write summary.json
    summary_path = smoke_dir / "summary.json"
    summary_data = {
        "total": len(results),
        "live_passed": sum(1 for r in results if r.live_verified and r.ok),
        "fixtures": sum(1 for r in results if r.is_fixture),
        "tests": [r.to_dict() for r in results],
    }
    summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    console.print(f"[green]Saved summary to {summary_path}[/green]")

    return results


if __name__ == "__main__":
    run_all()
