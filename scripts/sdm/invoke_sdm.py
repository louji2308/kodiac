"""Senior Decision Maker (SDM) CLI Harness (Option A: OpenCode + DeepSeek V4.1 Flash).

Implements programmatic headless execution per AGENTS.md §6 and ADR-0002.
Verifies opencode binary presence, reads packet content, constructs the headless
command, and captures stdout into the ruling file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

DEFAULT_MODEL = "deepseek/deepseek-chat"


def get_opencode_version() -> Optional[str]:
    """Check opencode binary presence and return version string."""
    binary = shutil.which("opencode")
    if not binary:
        return None
    try:
        res = subprocess.run(
            ["opencode", "--version"],
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            timeout=10,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def build_command(
    packet_path: Optional[Path],
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """Construct headless OpenCode command according to ADR-0002."""
    prompt = (
        "Act as Senior Decision Maker (SDM). Review the attached packet "
        "and produce RULING.md strictly following AGENTS.md §6.3 format."
    )
    cmd = ["opencode", "run", prompt, "-m", model]
    if packet_path and packet_path.exists():
        cmd.extend(["-f", str(packet_path.resolve())])
    return cmd


def run_sdm(
    packet_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
) -> int:
    """Execute or dry-run SDM invocation via OpenCode."""
    version = get_opencode_version()
    if not version and not dry_run:
        print("[ERROR] 'opencode' CLI binary not found in PATH.", file=sys.stderr)
        return 1

    cmd = build_command(packet_path, model=model)
    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)

    if dry_run:
        print("[DRY RUN] SDM CLI Harness verification successful.")
        print(f"  Opencode binary: {shutil.which('opencode') or 'Not Found (Mock)'}")
        print(f"  Opencode version: {version or 'mock-1.0'}")
        print(f"  Target model: {model}")
        print(f"  Packet path: {packet_path}")
        print(f"  Output path: {output_path}")
        print(f"  Constructed command: {cmd_str}")
        return 0

    if not packet_path or not packet_path.exists():
        print(f"[ERROR] Packet file does not exist: {packet_path}", file=sys.stderr)
        return 1

    print(f"[INFO] Invoking SDM via OpenCode (model: {model})...")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            timeout=300,
        )
        if proc.returncode != 0:
            print(f"[ERROR] OpenCode exited with returncode {proc.returncode}", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        ruling_text = proc.stdout
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(ruling_text, encoding="utf-8")
            print(f"[SUCCESS] Ruling saved to {output_path}")
        else:
            print(ruling_text)
        return 0
    except Exception as e:
        print(f"[ERROR] Subprocess execution failed: {e}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Invoke Senior Decision Maker (SDM) via OpenCode headless CLI (ADR-0002)."
    )
    parser.add_argument(
        "--packet",
        type=Path,
        default=None,
        help="Path to SDM_PACKET.md escalation document.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path where RULING.md should be written.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Model identifier for OpenCode (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify binary, construct command, print execution plan, and exit 0 without running.",
    )

    args = parser.parse_args(argv)
    return run_sdm(
        packet_path=args.packet,
        output_path=args.output,
        model=args.model,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
