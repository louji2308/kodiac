"""Review flow, digest determinism, narration validator, export, publish guard."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest
from audit_helpers import STACK_GREEN, load_episodes, stub_run_fn

import Kodiac_robotics.audit as audit_pkg
from Kodiac_robotics.audit.digest import (
    digest_json,
    failure_norm_digest,
    narrate,
    render_report,
    validate_narration_numbers,
    wilson_interval,
)
from Kodiac_robotics.audit.export import export_verdicts
from Kodiac_robotics.audit.publish import PublishRefused, publish
from Kodiac_robotics.audit.review import apply_reviews, build_candidates_html
from Kodiac_robotics.audit.rows import DEMO_BANNER, load_verdicts, to_verdict_row
from Kodiac_robotics.audit.run import audit_run
from Kodiac_robotics.contracts.core import Verdict

DS = "fixture/demo-stack"
VERDICTS = {0: Verdict.FAIL, 1: Verdict.FAIL, 2: Verdict.CANT_TELL, 3: Verdict.PASS, 5: Verdict.FAIL}


@pytest.fixture
def audit_dir(tmp_path: Path) -> Path:
    audit_run(
        DS,
        "stack",
        "cam_top",
        10,
        episodes=load_episodes(),
        out_dir=tmp_path,
        test_for_task=lambda t: STACK_GREEN,
        run_fn=stub_run_fn(VERDICTS),
    )
    return tmp_path


def _write_reviews(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def _rev(idx: int, decision: str, reviewer: str = "A. Human") -> dict:
    return {
        "dataset": DS,
        "episode_index": idx,
        "camera": "cam_top",
        "decision": decision,
        "reviewer": reviewer,
    }


# ---------------------------------------------------------------- review


def test_candidates_html_only_fail_rows_banner_and_escaping(audit_dir: Path) -> None:
    pq = audit_dir / "verdicts.parquet"
    df = load_verdicts(pq)
    df.loc[df["episode_index"] == 0, "task"] = "<script>alert(1)</script>"
    df.to_parquet(pq, index=False)
    out = audit_dir / "candidates.html"
    build_candidates_html(pq, out)
    text = out.read_text(encoding="utf-8")
    assert DEMO_BANNER in text
    assert text.count("<tr data-i=") == 2  # episodes 0 and 1 only (cam_top FAILs)
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "evidence/" in text and "http://" not in text and "https://" not in text
    build_candidates_html(pq, audit_dir / "again.html")
    assert (audit_dir / "again.html").read_text(encoding="utf-8") == text


def test_human_verified_only_from_reviewer_file(audit_dir: Path) -> None:
    pq = audit_dir / "verdicts.parquet"
    assert load_verdicts(pq)["human_verified"].isna().all()

    # a tampered parquet that already claims verification is reset
    forged = load_verdicts(pq)
    forged["human_verified"] = True
    forged.to_parquet(pq, index=False)

    reviews = _write_reviews(
        audit_dir / "reviews.jsonl",
        [_rev(0, "confirmed"), _rev(1, "rejected"), _rev(1, "unsure")],
    )
    out = apply_reviews(pq, reviews)
    by = {int(r["episode_index"]): r["human_verified"] for r in out.to_dict("records")}
    assert by[0] is True
    assert by[1] is None  # last decision (unsure) wins
    assert by[2] is None and by[3] is None
    assert out.loc[out["episode_index"] == 0, "reviewer"].iloc[0] == "A. Human"

    empty = apply_reviews(pq, _write_reviews(audit_dir / "none.jsonl", []))
    assert empty["human_verified"].isna().all()


def test_reviews_are_validated(audit_dir: Path) -> None:
    pq = audit_dir / "verdicts.parquet"
    bad = [
        [_rev(0, "maybe")],
        [_rev(0, "confirmed", reviewer="  ")],
        [_rev(3, "confirmed")],  # PASS row cannot be reviewed
        [_rev(99, "confirmed")],  # unknown episode
        [{"dataset": DS, "episode_index": 0, "camera": "cam_top", "decision": "confirmed"}],
    ]
    for i, recs in enumerate(bad):
        with pytest.raises(ValueError):
            apply_reviews(pq, _write_reviews(audit_dir / f"bad{i}.jsonl", recs))
    junk = audit_dir / "junk.jsonl"
    junk.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        apply_reviews(pq, junk)


# ---------------------------------------------------------------- digest


def _reviewed(audit_dir: Path, decisions: list[dict]) -> pd.DataFrame:
    return apply_reviews(
        audit_dir / "verdicts.parquet", _write_reviews(audit_dir / "r.jsonl", decisions)
    )


def test_digest_counts_wilson_and_determinism(audit_dir: Path) -> None:
    df = _reviewed(audit_dir, [_rev(0, "confirmed"), _rev(1, "rejected")])
    d = failure_norm_digest(df)
    assert d["N"] == 4 and d["n_flagged"] == 2 and d["n_verified"] == 1
    assert d["n_rejected"] == 1 and d["n_unreviewed"] == 0
    assert d["n_cant_tell"] == 1 and d["n_pass"] == 1
    assert d["is_demonstration_data"] is True
    lo, _ = wilson_interval(1, 4)
    assert d["X_lower_bound"] == round(lo, 6)
    assert d["histogram_by_step"][0]["step"] == "release"
    assert d["histogram_by_step"][0]["count"] == 1
    assert d["histogram_by_step_predicate"][0]["predicate"] == "moves_with.slip"
    assert digest_json(d) == digest_json(failure_norm_digest(df))
    assert digest_json(d).encode() == digest_json(failure_norm_digest(df.copy())).encode()


def test_unverified_flags_never_counted(audit_dir: Path) -> None:
    df = load_verdicts(audit_dir / "verdicts.parquet")
    d = failure_norm_digest(df)
    assert d["n_flagged"] == 2 and d["n_verified"] == 0 and d["n_unreviewed"] == 2
    assert d["X_lower_bound"] is None and d["histogram_by_step"] == []
    text, source = narrate(d, None)
    assert source == "template"
    assert "none are hand-verified" in text and "no failure rate is claimed" in text
    assert "%" not in text
    assert DEMO_BANNER in text


def test_wilson_matches_known_value() -> None:
    lo, hi = wilson_interval(8, 10)
    assert lo == pytest.approx(0.4901625, abs=1e-5) and hi == pytest.approx(0.9433178, abs=1e-5)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


def test_errored_episodes_excluded_from_N(audit_dir: Path) -> None:
    df = load_verdicts(audit_dir / "verdicts.parquet")
    df.loc[df["episode_index"] == 2, "error"] = "RuntimeError: boom"
    d = failure_norm_digest(df)
    assert d["N"] == 3 and d["n_errors"] == 1


def test_narration_validator_rejects_invented_number(audit_dir: Path) -> None:
    df = _reviewed(audit_dir, [_rev(0, "confirmed")])
    d = failure_norm_digest(df)
    top = d["histogram_by_step"][0]
    ok = f"Of {d['N']} episodes, {d['n_verified']} verified at step {top['step']}."
    assert validate_narration_numbers(ok, d) == []
    assert validate_narration_numbers("Roughly 73% of episodes failed.", d) == ["73"]

    seen: list[str] = []

    def good_wonder(prompt: str) -> str:
        seen.append(prompt)
        return ok

    text, source = narrate(d, good_wonder)
    assert source == "muse-wonder" and ok in text and DEMO_BANNER in text
    assert d["sampling"] in seen[0]

    text, source = narrate(d, lambda p: "A staggering 91.5% of episodes failed.")
    assert source == "template" and "91.5" not in text

    def broken(prompt: str) -> str:
        raise TimeoutError

    assert narrate(d, broken)[1] == "template"
    assert narrate(d, lambda p: "   ")[1] == "template"


def test_template_narration_numbers_validate_and_report(audit_dir: Path) -> None:
    df = _reviewed(audit_dir, [_rev(0, "confirmed"), _rev(1, "confirmed")])
    d = failure_norm_digest(df)
    text, source = narrate(d, None)
    assert source == "template" and validate_narration_numbers(text, d) == []
    assert "at least" in text and "Wilson lower bound" in text
    report = render_report(d, text, source)
    assert DEMO_BANNER in report and "Narration source: template" in report


# ---------------------------------------------------------------- export


def test_export_validates_against_verdictrow(audit_dir: Path, tmp_path: Path) -> None:
    df = _reviewed(audit_dir, [_rev(0, "confirmed"), _rev(1, "rejected")])
    out = tmp_path / "export"
    path = export_verdicts(df, out, evidence_root=audit_dir)
    assert path.name == "Kodiac_verdicts.parquet"
    back = pd.read_parquet(path)
    assert len(back) == len(df) == 4
    for rec in back.to_dict("records"):
        to_verdict_row(rec)
    assert back["is_demonstration_data"].all()
    assert back.loc[back["episode_index"] == 0, "human_verified"].iloc[0] == True  # noqa: E712
    manifest = json.loads((out / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert manifest["is_demonstration_data"] is True
    assert len(manifest["evidence"]) == 2
    assert all(len(e["sha256"]) == 64 for e in manifest["evidence"])
    # deterministic bytes
    export_verdicts(df, tmp_path / "export2", evidence_root=audit_dir)
    assert (out / "evidence_manifest.json").read_bytes() == (
        tmp_path / "export2" / "evidence_manifest.json"
    ).read_bytes()


def test_export_rejects_invalid_rows(audit_dir: Path, tmp_path: Path) -> None:
    df = load_verdicts(audit_dir / "verdicts.parquet")
    df.loc[0, "verdict"] = "MAYBE"
    with pytest.raises(ValueError):
        export_verdicts(df, tmp_path / "bad")


# ---------------------------------------------------------------- publish


@pytest.fixture
def real_report(tmp_path: Path) -> Path:
    p = tmp_path / "report.md"
    p.write_text("# Report\n\nHand-verified flags for a real dataset.\n", encoding="utf-8")
    return p


def test_publish_refusal_matrix(
    tmp_path: Path, real_report: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    approvals = tmp_path / "human_approval"
    approvals.mkdir()

    for ticket in (None, "", "   "):
        with pytest.raises(PublishRefused, match="ticket"):
            publish(real_report, approval_ticket=ticket, dry_run=False, approval_dir=approvals)

    (approvals / "T-1").write_text("approved by a human", encoding="utf-8")
    with pytest.raises(PublishRefused, match="dry_run"):
        publish(real_report, approval_ticket="T-1", dry_run=True, approval_dir=approvals)
    with pytest.raises(PublishRefused, match="dry_run"):
        publish(real_report, approval_ticket="T-1", approval_dir=approvals)  # default is dry_run
    with pytest.raises(PublishRefused, match="approval file"):
        publish(real_report, approval_ticket="T-2", dry_run=False, approval_dir=approvals)
    for evil in ("../T-1", "..\\T-1", "a/b", ".."):
        with pytest.raises(PublishRefused, match="malformed"):
            publish(real_report, approval_ticket=evil, dry_run=False, approval_dir=approvals)
    with pytest.raises(PublishRefused, match="report not found"):
        publish(tmp_path / "nope.md", approval_ticket="T-1", dry_run=False, approval_dir=approvals)

    monkeypatch.setenv("CI", "true")
    with pytest.raises(PublishRefused, match="CI"):
        publish(real_report, approval_ticket="T-1", dry_run=False, approval_dir=approvals)


def test_publish_refuses_demonstration_and_empty_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    approvals = tmp_path / "ap"
    approvals.mkdir()
    (approvals / "T-1").write_text("ok", encoding="utf-8")
    demo = tmp_path / "demo.md"
    demo.write_text(f"> {DEMO_BANNER}\n", encoding="utf-8")
    with pytest.raises(PublishRefused, match="DEMONSTRATION"):
        publish(demo, approval_ticket="T-1", dry_run=False, approval_dir=approvals)
    blank = tmp_path / "blank.md"
    blank.write_text("\n", encoding="utf-8")
    with pytest.raises(PublishRefused, match="empty"):
        publish(blank, approval_ticket="T-1", dry_run=False, approval_dir=approvals)


def test_publish_allowed_path_returns_text_only(
    tmp_path: Path, real_report: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    approvals = tmp_path / "ap"
    approvals.mkdir()
    (approvals / "T-9").write_text("approved", encoding="utf-8")
    text = publish(real_report, approval_ticket="T-9", dry_run=False, approval_dir=approvals)
    assert text == real_report.read_text(encoding="utf-8")


def test_audit_package_has_no_network_imports() -> None:
    banned = {
        "requests", "httpx", "urllib", "urllib3", "socket", "http", "aiohttp",
        "huggingface_hub", "ftplib", "smtplib", "websockets", "openai",
    }  # fmt: skip
    pkg_dir = Path(audit_pkg.__file__).parent
    files = sorted(pkg_dir.glob("*.py"))
    assert {f.name for f in files} >= {"run.py", "review.py", "digest.py", "export.py", "publish.py"}
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in banned, f"{f.name} imports {n}"
