"""Proof chart renderer (ARCHITECTURE §1.4, IMPLEMENTATION_PLAN P08.S05) and the real-state command.

Fail-closed rendering (T09 card, Law 1):
* ``status == "MEASURED"`` with ``synthetic`` and ``is_mock`` both false: data marks are drawn.
* ``status == "SYNTHETIC_TEST_ONLY"`` (or MEASURED but flagged): hatched watermark, NO data marks.
* anything else: "NOT MEASURED: NO TRAINED ARMS YET" watermark, NO data marks.

Real current state (no labels, no trained arms, mock pool)::

    python -m Kodiac_robotics.proof.chart --real-state

writes ``experiments/results/headline.json`` and ``artifacts/p08/proof_chart.{png,svg}``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
from pathlib import Path
from typing import Any

from Kodiac_robotics.proof.stats import (
    STATUS_MEASURED,
    STATUS_NOT_MEASURED,
    STATUS_SYNTHETIC,
    headline,
)

DATA_COLOR = "#1F6FEB"
DOSE_COLOR = "#6E7781"
WATERMARK_COLOR = "#C62828"
NOT_MEASURED_TEXT = "NOT MEASURED: NO TRAINED ARMS YET"
SYNTHETIC_TEXT = "SYNTHETIC TEST DATA: NOT A RESULT"
INVARIANT_SENTENCE = "Same robot, same practice data, only the judge changed"
REAL_STATE_COMMAND = "python -m Kodiac_robotics.proof.chart --real-state"

#: Display order and labels for the judge points (ARCHITECTURE §1.4).
ARM_LABELS: dict[str, str] = {
    "single_pass": "Single-pass Spark",
    "robometer_4b": "Robometer-4B",
    "topreward": "TOPReward",
    "kodiac": "Kodiac",
    "kodiac_salvage": "Kodiac + salvage",
    "kodiac_open_weights": "Kodiac open-weights",
    "size_matched_control": "Size-matched control",
    "oracle": "Oracle",
    "accept_all": "Accept-all",
}


def chart_mode(headline_json: dict[str, Any]) -> str:
    """Which branch the renderer takes: ``MEASURED`` only for an unflagged measured headline."""
    status = headline_json.get("status")
    flagged = bool(headline_json.get("synthetic", True)) or bool(headline_json.get("is_mock", True))
    if status == STATUS_MEASURED and not flagged:
        return STATUS_MEASURED
    if status in (STATUS_SYNTHETIC, STATUS_MEASURED):
        return STATUS_SYNTHETIC
    return STATUS_NOT_MEASURED


def _footer(headline_json: dict[str, Any], mode: str) -> str:
    bits = [f"status: {mode}"]
    if headline_json.get("git_head"):
        bits.append(f"git {str(headline_json['git_head'])[:12]}")
    if headline_json.get("generated_by"):
        bits.append(str(headline_json["generated_by"]))
    return "  ·  ".join(bits)


def _draw_measured(ax: Any, h: dict[str, Any]) -> None:
    arms = h.get("arms", {})
    order = [a for a in ARM_LABELS if a in arms]
    have_fp = order and all(isinstance(arms[a].get("false_pass"), dict) for a in order)
    if have_fp:
        for a in order:
            fp = arms[a]["false_pass"]
            x = 100 * fp["value"]
            y = 100 * arms[a]["mean"]
            xerr = [[x - 100 * fp["lo"]], [100 * fp["hi"] - x]]
            yerr = [[y - 100 * arms[a]["ci"][0]], [100 * arms[a]["ci"][1] - y]]
            ax.errorbar(x, y, xerr=xerr, yerr=yerr, fmt="o", color=DATA_COLOR, capsize=4, ms=8)
            ax.annotate(ARM_LABELS[a], (x, y), textcoords="offset points", xytext=(8, 6))
        dose = h.get("dose_response", [])
        if dose and all("false_pass" in arms.get(d["arm"], {}) for d in dose):
            xs = [100 * arms[d["arm"]]["false_pass"]["value"] for d in dose]
            ys = [100 * d["mean"] for d in dose]
            ax.plot(xs, ys, "--", color=DOSE_COLOR, label="Oracle + k% injected false-PASS")
            ax.legend(loc="lower left")
        ax.set_xlabel("Measured false-PASS rate (%, Wilson 95% CI)")
    else:
        xs = list(range(len(order)))
        means = [100 * arms[a]["mean"] for a in order]
        lo = [m - 100 * arms[a]["ci"][0] for m, a in zip(means, order)]
        hi = [100 * arms[a]["ci"][1] - m for m, a in zip(means, order)]
        ax.bar(xs, means, color=DATA_COLOR, yerr=[lo, hi], capsize=5)
        for i, a in enumerate(order):
            seeds = arms[a].get("seeds", {})
            ax.scatter([i] * len(seeds), [100 * s["mean"] for s in seeds.values()], color="black", s=12)
        ax.set_xticks(xs, [ARM_LABELS[a] for a in order], rotation=20, ha="right")
    ax.set_ylabel("Downstream task success (%, 95% CI)")


def render_proof_chart(headline_json: dict, out_png: Path, out_svg: Path) -> None:
    """Render the proof chart to PNG and SVG (SVG text is kept as ``<text>`` for auditability)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mode = chart_mode(headline_json)
    with plt.rc_context({"svg.fonttype": "none", "font.size": 11}):
        fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
        ax.set_ylim(0, 100)
        if mode == STATUS_MEASURED:
            _draw_measured(ax, headline_json)
            fig.suptitle(headline_json.get("sentence") or INVARIANT_SENTENCE, fontsize=13)
            n_seeds = min((a["n_seeds"] for a in headline_json["arms"].values()), default=0)
            n_eps = min(
                (a["min_episodes_per_seed"] for a in headline_json["arms"].values()), default=0
            )
            ax.set_title(
                f"Simulation · ManiSkill3 StackCube · {n_seeds} seeds · "
                f"n={n_eps} eval episodes per seed",
                fontsize=10,
            )
        else:
            from matplotlib.patches import Rectangle

            ax.set_xlim(0, 100)
            ax.set_xlabel("Measured false-PASS rate (%)")
            ax.set_ylabel("Downstream task success (%)")
            fig.suptitle(f"Headline experiment: “{INVARIANT_SENTENCE}”", fontsize=13)
            if mode == STATUS_SYNTHETIC:
                ax.add_patch(
                    Rectangle(
                        (0, 0), 100, 100, fill=False, hatch="//", edgecolor=WATERMARK_COLOR,
                        linewidth=0, alpha=0.35,
                    )
                )
                text = SYNTHETIC_TEXT
            else:
                text = NOT_MEASURED_TEXT
            ax.text(
                50, 50, text, ha="center", va="center", rotation=20, fontsize=30,
                fontweight="bold", color=WATERMARK_COLOR,
                bbox={"facecolor": "white", "edgecolor": WATERMARK_COLOR, "linewidth": 3},
            )
            reasons = list(headline_json.get("reasons", []))[:4]
            if reasons:
                ax.text(
                    1, 2, "\n".join(f"• {r}" for r in reasons), fontsize=8, va="bottom",
                    color="#333333",
                )
        fig.text(0.01, 0.01, _footer(headline_json, mode), fontsize=8, color="#555555")
        fig.tight_layout(rect=(0, 0.03, 1, 0.95))
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Path(out_svg).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, dpi=100)
        fig.savefig(out_svg)
        plt.close(fig)


def _git_head(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return res.stdout.strip() or None


def build_real_headline(root: Path) -> dict[str, Any]:
    """Headline from whatever real inputs exist in the repo right now (fails closed)."""
    from Kodiac_robotics.proof.labels import load_arm_evals, load_oracle

    evals_dir = root / "experiments" / "evals"
    labels_dir = root / "experiments" / "labels"
    manifest = root / "experiments" / "pool" / "manifest.parquet"
    arms = load_arm_evals(evals_dir)
    h = headline(arms)
    label_files = sorted(p.name for p in labels_dir.glob("*.parquet")) if labels_dir.is_dir() else []
    pool: dict[str, Any] = {"path": "experiments/pool/manifest.parquet", "present": manifest.is_file()}
    if manifest.is_file():
        oracle = load_oracle(manifest)
        pool.update(
            n_episodes=len(oracle),
            n_calibration=sum(1 for s in oracle.splits.values() if s == "calibration"),
            n_train=sum(1 for s in oracle.splits.values() if s == "train"),
            is_mock=oracle.is_mock,
        )
        if oracle.is_mock:
            h["is_mock"] = True
            h["reasons"].append(
                f"practice pool is kinematic mock (is_mock=True, {len(oracle)} episodes): "
                "not valid for the headline (PREREG §2 requires ManiSkill3 physics)"
            )
    else:
        h["reasons"].append("practice pool manifest not present locally")
    if not label_files:
        h["reasons"].append("no judge labels on the practice pool (experiments/labels/*.parquet)")
    h["inputs"] = {
        "evals_dir": "experiments/evals",
        "eval_arms": sorted(arms),
        "judge_label_files": label_files,
        "pool": pool,
    }
    h["generated_by"] = REAL_STATE_COMMAND
    h["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    h["git_head"] = _git_head(root)
    return h


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the Kodiac proof chart.")
    parser.add_argument("--real-state", action="store_true", help="build from the repo's real inputs")
    parser.add_argument("--headline", type=Path, help="render an existing headline.json instead")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-png", type=Path)
    parser.add_argument("--out-svg", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    out_json = args.out_json or root / "experiments" / "results" / "headline.json"
    out_png = args.out_png or root / "artifacts" / "p08" / "proof_chart.png"
    out_svg = args.out_svg or root / "artifacts" / "p08" / "proof_chart.svg"
    if args.real_state:
        h = build_real_headline(root)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(h, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif args.headline:
        h = json.loads(args.headline.read_text(encoding="utf-8"))
    else:
        parser.error("pass --real-state or --headline PATH")
    render_proof_chart(h, out_png, out_svg)
    print(f"status={chart_mode(h)} json={out_json if args.real_state else args.headline}")
    print(f"chart={out_png} {out_svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
