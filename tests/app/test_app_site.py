"""Static site generation from the replay store; every card must carry honest FIXTURE/CACHED badge text."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from Kodiac_robotics.app.replay import ReplayStore
from Kodiac_robotics.app.site import build_site, render_index

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cards(page: str) -> list[str]:
    return re.findall(r"<figure>.*?</figure>", page, flags=re.S)


def test_site_builds_with_badges_on_every_card(seeded_replay_dir: Path, tmp_path: Path) -> None:
    index = build_site(ReplayStore(seeded_replay_dir), tmp_path / "site")
    page = index.read_text(encoding="utf-8")
    cards = _cards(page)
    assert len(cards) == 2
    for card in cards:
        assert "[FIXTURE REPLAY]" in card
        assert "⚡ CACHED" in card
        assert "not a live" in card
    assert "<!-- VIDEO_URL -->" in page and "<!-- LIVE_APP_URL -->" in page
    assert "<12" not in page and "&lt;12" not in page
    for sha in re.findall(r"replays/blobs/([0-9a-f]{64})\.png", page):
        assert (tmp_path / "site" / "replays" / "blobs" / f"{sha}.png").is_file()
    assert (tmp_path / "site" / ".nojekyll").exists()


def test_site_has_no_local_paths_or_fake_links(seeded_replay_dir: Path) -> None:
    page = render_index(ReplayStore(seeded_replay_dir).list())
    assert "LOUJAN" not in page and "C:\\" not in page
    hrefs = re.findall(r'href="([^"]+)"', page)
    assert all(h.startswith("replays/blobs/") for h in hrefs), hrefs


def test_committed_site_is_honest_if_present() -> None:
    index = REPO_ROOT / "site" / "index.html"
    if not index.is_file():
        pytest.skip("site/ has not been generated yet")
    page = index.read_text(encoding="utf-8")
    cards = _cards(page)
    assert cards, "site/index.html has no replay cards"
    for card in cards:
        assert "[FIXTURE REPLAY]" in card and "⚡ CACHED" in card
    assert "<!-- VIDEO_URL -->" in page
    assert "<12" not in page
    total = sum(p.stat().st_size for p in (REPO_ROOT / "site" / "replays").rglob("*") if p.is_file())
    assert total <= 2 * 1024 * 1024


@pytest.mark.slow
def test_precompute_script_builds_full_site(tmp_path: Path) -> None:
    env_tmp = str(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "precompute_replays.py"),
            "--replay-dir", str(tmp_path / "site" / "replays"),
            "--site-dir", str(tmp_path / "site"),
            "--work-dir", str(tmp_path / "work"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "TEMP": env_tmp, "TMP": env_tmp, "PYTHONIOENCODING": "utf-8"},
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    cards = _cards(page)
    assert len(cards) == 6
    assert all("[FIXTURE REPLAY]" in c and "⚡ CACHED" in c for c in cards)
    assert "CAN&#x27;T TELL" in page
