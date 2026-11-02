"""Precompute the curated cached replays and build the static site.

Runs the golden clips through ``pipeline.run.run`` (fixture perception backend, no network, no keys) into a
ReplayStore (default ``site/replays/``) and renders ``site/index.html`` from it.

    python scripts/precompute_replays.py [--replay-dir site/replays] [--site-dir site] [--no-site]
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from Kodiac_robotics.app.precompute import CURATED_SPECS, precompute_replays  # noqa: E402
from Kodiac_robotics.app.replay import ReplayStore  # noqa: E402
from Kodiac_robotics.app.settings import AppSettings  # noqa: E402
from Kodiac_robotics.app.site import build_site  # noqa: E402


def _robust_write_atomic(self: ReplayStore, path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    for attempt in range(12):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 11:
                path.write_bytes(data)
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                return
            time.sleep(0.05 * (attempt + 1))


ReplayStore._write_atomic = _robust_write_atomic  # type: ignore[assignment]

SIZE_BUDGET_BYTES = 2 * 1024 * 1024


def _tree_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=REPO_ROOT / "site" / "replays")
    parser.add_argument("--site-dir", type=Path, default=REPO_ROOT / "site")
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / ".cache" / "app")
    parser.add_argument("--no-site", action="store_true", help="only fill the replay store")
    args = parser.parse_args(argv)

    settings = AppSettings(
        replay_dir=args.replay_dir,
        upload_dir=args.work_dir / "uploads",
        run_dir=args.work_dir / "runs",
        mount_ui=False,
    )
    entries = precompute_replays(settings, CURATED_SPECS)
    for e in entries:
        print(f"{e.id:42s} {e.verdict:10s} engine {e.run_total_ms / 1000:5.2f}s  fixture={e.is_fixture}")

    pruned = ReplayStore(args.replay_dir).prune()
    if pruned:
        print(f"pruned {pruned} stale blob(s)")

    if not args.no_site:
        index = build_site(ReplayStore(args.replay_dir), args.site_dir)
        print(f"site written: {index}")
        data_dir = args.site_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "replays.json").write_text(
            (args.site_dir / "replays.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    size = _tree_size(args.replay_dir)
    print(f"replay store size: {size / 1024:.0f} KiB (budget {SIZE_BUDGET_BYTES // 1024} KiB)")
    if size > SIZE_BUDGET_BYTES:
        print("ERROR: replay store exceeds the 2 MB budget", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
