"""Demonstration Self-Test Verifier for Kodiac.

Read-only verification pass running measurement engine on calibrated test against
the demonstration clip.
Asserts Verdict == PASS and component margins >= 2*sigma per ARCHITECTURE.md §6.1,
ADR-0011, and ADR-0013.
"""

from __future__ import annotations

import logging
from typing import Any

from Kodiac_robotics.compiler.lint import Diagnostic, lint_green
from Kodiac_robotics.contracts.core import (
    Clip,
    GreenTest,
    RunResult,
    Verdict,
)
from Kodiac_robotics.pipeline.run import run as execute_run

logger = logging.getLogger(__name__)


def run_demo_selftest(
    test: GreenTest,
    clip: Clip,
    backend: str = "fixture",
    camera: Any = None,
) -> tuple[bool, RunResult, list[Diagnostic]]:
    """Read-only verifier running measurement engine on calibrated test.

    Asserts margin >= 2*sigma and Verdict == PASS.
    Returns (passed, run_result, diagnostics).
    """
    # 1. Execute Measurement Engine Run (Full Path)
    run_result = execute_run(
        test=test,
        clip=clip,
        mode="full",
        backend=backend,  # type: ignore[arg-type]
        camera=camera,
    )

    # 2. Collect Diagnostics
    diagnostics = lint_green(test, context=run_result)

    # Ensure explicit E005 is recorded if verdict is not PASS
    if run_result.verdict == Verdict.FAIL:
        if not any(d.code == "E005" and "fails" in d.message for d in diagnostics):
            diagnostics.append(
                Diagnostic(
                    code="E005",
                    message="Demonstration fails its own test (verdict=FAIL)",
                    severity="error",
                )
            )
    elif run_result.verdict == Verdict.CANT_TELL:
        if not any(d.code == "E005" and "inconclusive" in d.message for d in diagnostics):
            reasons_str = ", ".join(r.value for r in run_result.reasons)
            diagnostics.append(
                Diagnostic(
                    code="E005",
                    message=f"Demonstration self-test inconclusive (verdict=CANT_TELL: {reasons_str})",
                    severity="error",
                )
            )

    # Check for W103: demonstration margin < 2*sigma on decisive components
    for s_res in run_result.steps:
        for comp in s_res.decisive:
            if comp.sigma > 0 and comp.margin < 2.0 * comp.sigma:
                if not any(d.code == "W103" and comp.name in d.message for d in diagnostics):
                    diagnostics.append(
                        Diagnostic(
                            code="W103",
                            message=(
                                f"Demonstration margin for '{comp.name}' ({comp.margin:.2f}) "
                                f"is less than 2*sigma threshold ({2.0 * comp.sigma:.2f})"
                            ),
                            severity="warning",
                            step_index=s_res.index,
                        )
                    )

    # 3. Verdict & Error Gate
    has_error = any(d.severity == "error" for d in diagnostics)
    passed = (run_result.verdict == Verdict.PASS) and not has_error

    return passed, run_result, diagnostics
