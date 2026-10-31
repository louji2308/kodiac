# T03: Keyframe Grounding, Slack Engine, Demo Self-Test, & CLI Integration
phase: P05 · owner: IMPL-3 · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P05.S05, P05.S06, P05.S09, P05.S11, P05.S12 · ADR-0011, ADR-0013
depends_on: [T01, T02] · blocks: []
owns_paths:
  - src/Kodiac_robotics/compiler/typecheck.py
  - src/Kodiac_robotics/compiler/slack.py
  - src/Kodiac_robotics/compiler/selftest.py
  - src/Kodiac_robotics/cli.py (subcommand test only)
  - tests/compiler/test_typecheck.py
  - tests/compiler/test_slack.py
  - tests/compiler/test_selftest.py
  - tests/cli/test_cli_test.py
  - video/tapes/test.tape
reads_only:
  - src/Kodiac_robotics/compiler/grammar.lark
  - src/Kodiac_robotics/compiler/parser.py
  - src/Kodiac_robotics/compiler/printer.py
  - src/Kodiac_robotics/compiler/lint.py
  - src/Kodiac_robotics/compiler/lock.py
  - src/Kodiac_robotics/compiler/asr.py
  - src/Kodiac_robotics/compiler/spark_compile.py
  - src/Kodiac_robotics/compiler/template_fallback.py
  - src/Kodiac_robotics/compiler/text_compile.py
  - src/Kodiac_robotics/contracts/core.py
  - ARCHITECTURE.md §6.1–§6.3
  - .agents/phases/P05-compiler/RULING.md
timebox: 240 min (3-strike rule applies)

## Mission
Integrate the complete `Kodiac test` compiler pipeline: ground declared object roles on demo keyframes with SAM 3.1 and embodiment aliasing (Invariant I16); extract empirical demo metrics using kinematic phase segmentation (apex elevation and settled terminal window); calculate certified physical tolerances with physical sanity caps (ADR-0013); verify demo self-test PASS (margin >= 2σ); and wire the production CLI `Kodiac test` subcommand with clean UNIX stream separation and real-time sub-step timers.

## Interface Contract (FROZEN per ARCHITECTURE.md §6.1–§6.3 & RULING.md)
```python
from pathlib import Path
from typing import Any, Literal
from Kodiac_robotics.contracts.core import GreenTest, Diagnostic, RunResult
from Kodiac_robotics.segment.video import Clip

# compiler/typecheck.py
def typecheck_and_ground_objects(
    clip: Clip,
    test: GreenTest,
) -> tuple[GreenTest, dict[str, Any]]:
    """Grounds AST object names to SAM 3.1 track IDs. Invokes detect_embodiment(clip)
    to map canonical 'gripper' to human hand or robot gripper (Invariant I16).
    Records container rim ellipses and initial scale k0. Raises E001/E002 on failure."""
    ...

# compiler/slack.py
def measure_demo_metrics(
    clip: Clip,
    test: GreenTest,
) -> dict[str, float]:
    """Runs Pass 1 unconstrained metric logging over demo clip.
    MANDATORY DIRECTIVE: Uses kinematic phase segmentation (apex for lift,
    settled terminal window for placement/dwell) rather than speech timestamps.
    Returns physical extrema: h_max, delta_xy, z_gap, v_settle."""
    ...

def derive_thresholds(
    skeleton: GreenTest,
    demo_metrics: dict[str, float],
    profile: Literal["strict", "nominal", "loose"] = "nominal",
) -> tuple[GreenTest, dict[str, Any]]:
    """Derives physical parameter values with safety margins (margin >= 2σ):
      align_xy_cm = max(1.5, round(delta_xy + 2.5*sigma, 1))
      gap_cm = max(0.5, round(z_gap + 2.5*sigma, 1))
      min_cm = max(1.0, floor(0.6 * h_max))
    Enforces Physical Sanity Caps:
      align_xy_cm <= 4.0 cm, gap_cm <= 2.0 cm, min_cm <= 8.0 cm, max_speed <= 2.5 cm/s.
    Exceeding any sanity cap raises E005. Returns (calibrated_test, slack_summary)."""
    ...

# compiler/selftest.py
def run_demo_selftest(
    test: GreenTest,
    clip: Clip,
) -> tuple[bool, RunResult, list[Diagnostic]]:
    """Read-only verifier running measurement engine on calibrated test.
    Asserts margin >= 2*sigma and Verdict == PASS. Returns (passed, run_result, diagnostics)."""
    ...
```

## Steps
1. **P05.S05 `src/Kodiac_robotics/compiler/typecheck.py`:** Ground objects on 2–3 keyframes using SAM 3.1. Detect embodiment via `detect_embodiment(clip)` from `segment/prompts.py`: if human embodiment, query `"human hand"` while keeping canonical AST identifier `gripper` (Invariant I16). Fit container rim ellipse via `cv2.fitEllipse`.
2. **P05.S06 `src/Kodiac_robotics/compiler/slack.py`:** Implement two-pass calibration (ADR-0011 & ADR-0013).
   - Implement **Kinematic Phase Segmentation**:
     - Apex detection: Find frame $t_{\text{apex}}$ where elevation $h(t)$ is maximum -> extract $h_{\text{max}}$.
     - Settled terminal window: Scan backward from clip end for kinematic plateau where lateral distance $\|\Delta XY(t)\|$ stabilizes and velocity $\le 2.5$ cm/s for $\ge 0.5$ s -> extract settled $\Delta_{xy}$, $z_{\text{gap}}$, and $v_{\text{settle}}$.
   - Compute thresholds with certified slack ($\text{margin} \ge 2\sigma$).
   - Enforce **Physical Sanity Caps** (`align_xy <= 4.0cm`, `gap <= 2.0cm`, `min_cm <= 8.0cm`, `v_settle <= 2.5cm/s`). If violated, raise `E005: demonstration exceeds physical sanity cap`.
3. **P05.S09 `src/Kodiac_robotics/compiler/selftest.py`:** Execute read-only evaluation pass using `pipeline/run.py` on calibrated test. Require `verdict == PASS` and `margin >= 2σ`.
4. **P05.S11 `src/Kodiac_robotics/cli.py`:** Wire `Kodiac test` subcommand:
   - Accept `--video`, `--from-text`, `--out`, `--backend`, `--first-frame`, `--threshold-profile`, `--webcam`.
   - Implement 2.0s probe timeout for `--webcam`.
   - **Stream separation:** Stream interactive progress timers (`✓ [1.2s] transcript...`) and diagnostics to `stderr` using Rich `Console(stderr=True)`. Emit clean canonical `.green` test text to `stdout` (or write to `--out`).
5. **P05.S12 Verification & Golden Tape:** Validate end-to-end compilation latency on $\le 15$ s clips ($< 12.0$ s budget). Author `video/tapes/test.tape`. Run unit and integration tests.

## Definition of Done
- [ ] Kinematic phase segmentation correctly measures apex elevation and settled terminal window.
- [ ] Physical sanity caps reject out-of-bounds demonstrations with `E005`.
- [ ] Self-test verifies `Verdict == PASS` with margin $\ge 2\sigma$ on all golden demo clips.
- [ ] CLI `Kodiac test` cleanly separates stderr progress/timers from stdout `.green` output.
- [ ] End-to-end compilation latency is $< 12.0$ s.
- [ ] `uv run --no-sync pytest tests/compiler/ tests/cli/test_cli_test.py -q` passes 100%.
- [ ] Committed with message `feat(p05/t03): keyframe grounding, slack engine, demo selftest and cli`.

## Verification Commands
```bash
uv run --no-sync pytest tests/compiler/test_typecheck.py tests/compiler/test_slack.py tests/compiler/test_selftest.py tests/cli/test_cli_test.py -v
uv run --no-sync Kodiac test --from-text "stack cubeA on cubeB" --first-frame tests/fixtures/clips/b01_early_release.mp4
uv run --no-sync ruff check src/Kodiac_robotics/ tests/
```

## Report
*(to be filled by IMPL-3 at DONE)*
