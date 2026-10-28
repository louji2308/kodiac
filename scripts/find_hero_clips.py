#!/usr/bin/env python3
"""CLI tool to scan DROID and LeRobot datasets for candidate hero failure clips.

Extracts real teleoperated robot failure footage, exporting structured candidate cards,
thumbnails, and preview clips to artifacts/p02/hero_candidates/index.md.

Usage:
    uv run --no-sync python scripts/find_hero_clips.py --mock --output artifacts/p02/hero_candidates/index.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so modal.hero_search can be imported cleanly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modal.hero_search import build_hero_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan real robot datasets for candidate hero failure clips."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="artifacts/p02/hero_candidates/index.md",
        help="Path for generated Markdown index (default: artifacts/p02/hero_candidates/index.md)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run in offline mock mode using local fixtures and synthetic clips",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=None,
        help="Specific dataset names to scan (e.g. alexander-soare/droid_100 lerobot/so100_pick_place)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Scanning for hero failure candidates (mock={args.mock})...")
    cards = build_hero_candidates(
        output_index_path=args.output,
        mock=args.mock,
        datasets=args.datasets,
    )
    print(f"\nDiscovered {len(cards)} candidate failure clips (REAL ROBOT FOOTAGE ONLY):")
    for card in cards:
        print(
            f"  - [{card.candidate_id}] {card.dataset} ep_{card.episode_index:03d} "
            f"({card.robot}): {card.failure_predicate} @ {card.failure_time_s:.2f}s"
        )
    print(f"\nCandidate index written to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
