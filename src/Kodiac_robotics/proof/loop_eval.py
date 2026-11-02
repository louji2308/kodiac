"""Fix-rate evaluation harness for the Muse Code /goal loop (F42).

For every seeded bug B01..B10 the harness
  1. copies a fresh workspace (only `examples/sim/pick_place.py` and the `.green` tests; never the
     bug patches, so an agent cannot read the answer),
  2. injects the bug,
  3. pins the done-gate (`loop.gate.gate_init`, pins stored outside the workspace),
  4. hands the workspace to a `driver` for at most `max_iters` iterations,
  5. accepts the bug as FIXED only if the gate passes AND the sim oracle succeeds AND the
     test files are byte-identical to the start AND the driver stayed within `max_iters`,
  6. writes a transcript `transcripts/B##.md` and an aggregate JSON.

Drivers
  * `reference_patcher`: restores the pristine script. It is a scripted function, NOT an AI agent.
    A run with it is a *plumbing dry-run* and never yields a fix rate (`agent_fix_rate: null`).
  * `muse_exec_driver`: runs a user-supplied command template that launches Muse Code headless in
    the workspace. No default command ships because Muse Code's CLI is [UNVERIFIED] here; an
    example to verify against `muse exec --help` before use:
        muse exec --cwd {workspace} --prompt-file {goal} --max-turns {max_iters}
    It refuses to run unless `KODIAC_ALLOW_MUSE_SPEND=1` and prints the estimated iterations first.
    Iterations are counted from the `verify` runs the agent made (`.Kodiac/verify/*`).

The sim oracle is read here only to check the fix (eval-only, KD-13); it is never part of the
gate's verdict.

Dry-run command (committed artifact):
    python -m Kodiac_robotics.proof.loop_eval --driver reference_patcher \
        --out-dir .cache/loop_eval_dryrun --report artifacts/p07/loop_eval_dryrun.json
(with --report, transcripts are also published next to it in artifacts/p07/transcripts/B##.md)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

SPEND_ENV = "KODIAC_ALLOW_MUSE_SPEND"
MUSE_TEMPLATE_ENV = "KODIAC_MUSE_EXEC_TEMPLATE"
GATE_HOME_ENV = "KODIAC_GATE_HOME"
DEFAULT_TEST = "examples/stackcube.green"
DEFAULT_SCRIPT = "examples/sim/pick_place.py"
BUG_IDS = [f"B{i:02d}" for i in range(1, 11)]
DRY_RUN_NOTE = "NOT a Muse Code fix rate"


class BugOutcome(BaseModel):
    bug: str
    fixed: bool
    iterations: int
    gate_pass: bool
    oracle_success: bool
    hash_unchanged: bool
    transcript_path: str
    driver: str
    injection: str = ""
    bug_manifests: bool | None = None
    sim_backend: str = ""
    is_mock: bool | None = None
    note: str = ""


class DriverResult(BaseModel):
    iterations: int
    transcript: str = ""
    driver: str


Driver = Callable[[Path, str], DriverResult]


class SpendGuardError(RuntimeError):
    """Raised when a money-spending driver is launched without explicit opt-in."""


class MuseDriverUnavailable(RuntimeError):
    """Raised when no verified Muse Code launch command was supplied."""


class InjectionError(RuntimeError):
    """Raised when a bug cannot be injected into the workspace script."""


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ bug injection
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _apply_unified_diff(original: str, patch_text: str) -> str:
    """Apply a single-file unified diff with exact context. Raises ValueError if it does not fit."""
    lines = original.split("\n")
    out: list[str] = []
    cursor = 0
    plines = patch_text.splitlines()
    i = 0
    while i < len(plines) and not _HUNK.match(plines[i]):
        i += 1
    if i == len(plines):
        raise ValueError("patch has no hunks")
    while i < len(plines):
        m = _HUNK.match(plines[i])
        if not m:
            raise ValueError(f"unexpected line in patch: {plines[i][:40]!r}")
        i += 1
        old_len = int(m.group(2)) if m.group(2) is not None else 1
        new_len = int(m.group(4)) if m.group(4) is not None else 1
        old_block: list[str] = []
        new_block: list[str] = []
        while i < len(plines) and not plines[i].startswith("@@"):
            row = plines[i]
            i += 1
            if row.startswith("\\"):
                continue
            tag, body = (row[:1], row[1:]) if row else (" ", "")
            if tag == " ":
                old_block.append(body)
                new_block.append(body)
            elif tag == "-":
                old_block.append(body)
            elif tag == "+":
                new_block.append(body)
            else:
                raise ValueError(f"corrupt patch line: {row[:40]!r}")
        if len(old_block) != old_len or len(new_block) != new_len:
            raise ValueError("hunk header does not match hunk body")
        start = int(m.group(1)) - 1
        if lines[start : start + len(old_block)] != old_block:
            raise ValueError(f"hunk at line {start + 1} does not match the script")
        out.extend(lines[cursor:start])
        out.extend(new_block)
        cursor = start + len(old_block)
    out.extend(lines[cursor:])
    return "\n".join(out)


_EXEC_SIG = re.compile(r"(def execute_pick_place\([^)]*?bug_id\s*:\s*str\s*\|\s*None\s*=\s*)None")


def inject_bug(script: Path, bug: str, patch_path: Path | None) -> str:
    """Inject `bug` into `script` in place. Returns "patch" or "bug_id_pin".

    The shipped examples/sim/bugs/B##.patch files target an older layout of pick_place.py and do not
    apply to the current one, so when the patch does not fit we pin `bug_id` as the default of
    `execute_pick_place` (the script's own bug switch). Which method ran is reported, never hidden.
    """
    text = script.read_text(encoding="utf-8")
    if patch_path is not None and patch_path.is_file():
        try:
            script.write_text(_apply_unified_diff(text, patch_path.read_text(encoding="utf-8")), encoding="utf-8")
            return "patch"
        except ValueError:
            pass
    pinned, n = _EXEC_SIG.subn(lambda m: f'{m.group(1)}"{bug}"', text, count=1)
    if n != 1:
        raise InjectionError(f"cannot inject {bug}: patch does not apply and {script.name} has no bug_id switch")
    script.write_text(pinned, encoding="utf-8")
    return "bug_id_pin"


# ------------------------------------------------------------------ drivers
def reference_patcher(workspace: Path, bug: str) -> DriverResult:
    """Scripted reference: restore the pristine script. NOT an AI agent; proves the plumbing only."""
    clean = _repo_root() / DEFAULT_SCRIPT
    target = workspace / DEFAULT_SCRIPT
    before = _sha256(target)
    shutil.copyfile(clean, target)
    return DriverResult(
        iterations=1,
        driver="reference_patcher",
        transcript=(
            f"reference_patcher restored the pristine {DEFAULT_SCRIPT} "
            f"(sha256 {before[:12]} -> {_sha256(target)[:12]}). Scripted, not an AI agent."
        ),
    )


reference_patcher.spends_money = False  # type: ignore[attr-defined]


def estimate_iterations(bugs: list[str], max_iters: int) -> int:
    return len(bugs) * max_iters


def require_spend_guard(bugs: list[str], max_iters: int, env: dict[str, str] | None = None) -> int:
    """Refuse unless KODIAC_ALLOW_MUSE_SPEND=1; print the estimated iterations. Returns the estimate."""
    estimate = estimate_iterations(bugs, max_iters)
    print(
        f"[loop-eval] real-agent run: up to {estimate} agent iterations ({len(bugs)} bugs x {max_iters}).",
        file=sys.stderr,
    )
    if (env if env is not None else os.environ).get(SPEND_ENV) != "1":
        raise SpendGuardError(
            f"Refusing to launch the Muse Code driver: set {SPEND_ENV}=1 to confirm you accept the cost "
            f"(estimate: up to {estimate} iterations)."
        )
    return estimate


def muse_exec_driver(max_iters: int, command_template: str | None = None, timeout_s: int = 1800) -> Driver:
    """Driver that launches Muse Code headless via a user-verified command template.

    Placeholders: {workspace} {goal} {max_iters}. No default template is shipped (unverified CLI).
    """
    template = command_template or os.environ.get(MUSE_TEMPLATE_ENV)

    def driver(workspace: Path, bug: str) -> DriverResult:
        if not template:
            raise MuseDriverUnavailable(
                f"No Muse Code launch command: set {MUSE_TEMPLATE_ENV} to a verified command, e.g. "
                "'muse exec --cwd {workspace} --prompt-file {goal} --max-turns {max_iters}' "
                "(example only, [UNVERIFIED])."
            )
        cmd = template.format(workspace=str(workspace), goal=str(workspace / "GOAL.md"), max_iters=max_iters)
        proc = subprocess.run(  # noqa: S603 - command is supplied by the operator
            cmd if os.name == "nt" else shlex.split(cmd),
            cwd=workspace, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
        runs = workspace / ".Kodiac" / "verify"
        iterations = len([p for p in runs.iterdir() if p.is_dir()]) if runs.is_dir() else 0
        tail = (proc.stdout or "")[-4000:]
        return DriverResult(
            iterations=iterations,
            driver="muse_exec",
            transcript=f"$ {cmd}\nexit={proc.returncode}\n--- stdout (tail) ---\n{tail}",
        )

    driver.spends_money = True  # type: ignore[attr-defined]
    return driver


# ------------------------------------------------------------------ harness
def _prepare_workspace(root: Path, ws: Path, test: str, script: str) -> None:
    if ws.exists():
        shutil.rmtree(ws)
    (ws / script).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / script, ws / script)
    for green in sorted((root / "examples").glob("*.green")):
        (ws / "examples").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(green, ws / "examples" / green.name)
    if not (ws / test).is_file():
        raise FileNotFoundError(f"test {test} not found in {root}")


def _test_hashes(ws: Path) -> dict[str, str]:
    return {p.relative_to(ws).as_posix(): _sha256(p) for p in sorted(ws.rglob("*.green"))}


def _write_transcript(path: Path, outcome: BugOutcome, driver_text: str, gate_msg: str, extra: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {outcome.bug} transcript",
        "",
        f"- driver: `{outcome.driver}`",
        f"- injection: `{outcome.injection}` Â· bug manifests before driver: `{outcome.bug_manifests}`",
        f"- iterations: {outcome.iterations}",
        f"- gate_pass: {outcome.gate_pass} Â· oracle_success: {outcome.oracle_success} Â· hash_unchanged: {outcome.hash_unchanged}",
        f"- fixed: **{outcome.fixed}**",
        "",
        "## Driver output",
        "",
        "```",
        driver_text.strip() or "(none)",
        "```",
        "",
        "## Final gate check",
        "",
        "```",
        gate_msg.strip() or "(gate printed nothing: exit 0)",
        "```",
        *([""] + extra if extra else []),
    ]
    if outcome.driver == "reference_patcher":
        lines += ["", "> Plumbing dry-run with a scripted patcher. NOT an AI agent and NOT a Muse Code result."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_loop_eval(
    bugs: list[str],
    driver: Driver,
    *,
    max_iters: int = 5,
    out_dir: Path,
    repo_root: Path | None = None,
    test: str = DEFAULT_TEST,
    sim_script: str = DEFAULT_SCRIPT,
    seed: int = 0,
) -> list[BugOutcome]:
    """Run the fix-rate protocol for `bugs` with `driver`; returns one BugOutcome per bug."""
    if getattr(driver, "spends_money", False):
        require_spend_guard(bugs, max_iters)

    from Kodiac_robotics.loop.gate import gate_check, gate_init
    from Kodiac_robotics.sim.runner import run_script

    root = repo_root or _repo_root()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outcomes: list[BugOutcome] = []

    previous_home = os.environ.get(GATE_HOME_ENV)
    os.environ[GATE_HOME_ENV] = str((out_dir / "gate_home").resolve())
    try:
        for bug in bugs:
            ws = (out_dir / "workspaces" / bug).resolve()
            transcript = out_dir / "transcripts" / f"{bug}.md"
            notes: list[str] = []
            _prepare_workspace(root, ws, test, sim_script)
            injection = inject_bug(ws / sim_script, bug, root / "examples" / "sim" / "bugs" / f"{bug}.patch")

            manifests: bool | None
            try:
                manifests = not run_script(ws / sim_script, seed, out_dir / "sim" / bug / "pre").oracle_success
            except Exception as exc:  # noqa: BLE001
                manifests = None
                notes.append(f"pre-check sim crashed: {type(exc).__name__}: {str(exc)[:200]}")

            gate_init(ws, ws / test, ws / sim_script, seed=seed, max_blocks=max_iters)
            hashes_before = _test_hashes(ws)

            driver_text, driver_name, iterations = "", getattr(driver, "driver_name", "driver"), 0
            try:
                res = driver(ws, bug)
                driver_text, driver_name, iterations = res.transcript, res.driver, res.iterations
            except (SpendGuardError, MuseDriverUnavailable):
                raise
            except Exception as exc:  # noqa: BLE001 - a crashing driver is a failed bug, not a crashed eval
                driver_text = f"driver raised {type(exc).__name__}: {str(exc)[:300]}"
                iterations = max_iters + 1

            hash_unchanged = _test_hashes(ws) == hashes_before
            try:
                code, gate_msg = gate_check(ws)
            except Exception as exc:  # noqa: BLE001
                code, gate_msg = 2, f"gate_check raised {type(exc).__name__}: {exc}"
            exhausted = (ws / ".Kodiac" / "gate_exhausted").exists()
            gate_pass = code == 0 and not exhausted and "GATE EXHAUSTED" not in gate_msg

            sim_backend, is_mock = "", None
            try:
                post = run_script(ws / sim_script, seed, out_dir / "sim" / bug / "post")
                oracle, sim_backend, is_mock = bool(post.oracle_success), str(post.backend), bool(post.is_mock)
            except Exception as exc:  # noqa: BLE001
                oracle = False
                notes.append(f"post-check sim crashed: {type(exc).__name__}: {str(exc)[:200]}")

            fixed = gate_pass and oracle and hash_unchanged and iterations <= max_iters
            outcome = BugOutcome(
                bug=bug, fixed=fixed, iterations=iterations, gate_pass=gate_pass, oracle_success=oracle,
                hash_unchanged=hash_unchanged, transcript_path=str(transcript), driver=driver_name,
                injection=injection, bug_manifests=manifests, sim_backend=sim_backend, is_mock=is_mock,
                note="; ".join(notes),
            )
            _write_transcript(transcript, outcome, driver_text, gate_msg, [f"- {n}" for n in notes])
            outcomes.append(outcome)
    finally:
        if previous_home is None:
            os.environ.pop(GATE_HOME_ENV, None)
        else:
            os.environ[GATE_HOME_ENV] = previous_home
    return outcomes


def build_report(outcomes: list[BugOutcome], *, max_iters: int) -> dict[str, Any]:
    """Aggregate JSON. Reference-patcher runs are labelled as plumbing dry-runs with no fix rate."""
    drivers = sorted({o.driver for o in outcomes})
    dry = drivers == ["reference_patcher"]
    report: dict[str, Any] = {
        "driver": drivers[0] if len(drivers) == 1 else drivers,
        "evidence_type": "plumbing_dry_run" if dry else "agent_run",
        "max_iters": max_iters,
        "sim_backend": sorted({o.sim_backend or "unknown" for o in outcomes}),
        "is_mock": sorted({o.is_mock for o in outcomes if o.is_mock is not None}),
        "outcomes": [o.model_dump() for o in outcomes],
    }
    if dry:
        report["agent_fix_rate"] = None
        report["note"] = DRY_RUN_NOTE
        report["explanation"] = (
            "A scripted function restored the pristine script for each bug to prove the harness plumbing "
            "(workspace copy, bug injection, gate pinning, hash check, transcripts). No AI agent ran."
        )
    else:
        report["agent_fix_rate"] = {"fixed": sum(o.fixed for o in outcomes), "n_bugs": len(outcomes)}
    return report


def _display_path(path: Path) -> str:
    """Repo/cwd-relative posix path when possible, so reports carry no machine-specific prefix."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Muse Code /goal fix-rate harness (F42)")
    parser.add_argument("--driver", choices=["reference_patcher", "muse_exec"], default="reference_patcher")
    parser.add_argument("--bugs", default=",".join(BUG_IDS))
    parser.add_argument("--max-iters", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=Path(".cache/loop_eval"))
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    bugs = [b.strip().upper() for b in args.bugs.split(",") if b.strip()]
    unknown = [b for b in bugs if b not in BUG_IDS]
    if unknown:
        print(f"unknown bug ids: {unknown}", file=sys.stderr)
        return 2
    driver: Driver = reference_patcher if args.driver == "reference_patcher" else muse_exec_driver(args.max_iters)
    try:
        outcomes = run_loop_eval(bugs, driver, max_iters=args.max_iters, out_dir=args.out_dir)
    except (SpendGuardError, MuseDriverUnavailable) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.report:
        published = args.report.parent / "transcripts"
        published.mkdir(parents=True, exist_ok=True)
        for o in outcomes:
            target = published / Path(o.transcript_path).name
            shutil.copyfile(o.transcript_path, target)
            o.transcript_path = _display_path(target)
    report = build_report(outcomes, max_iters=args.max_iters)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.report}")
    for o in outcomes:
        print(f"{o.bug}: fixed={o.fixed} gate_pass={o.gate_pass} oracle={o.oracle_success} hash_ok={o.hash_unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BugOutcome",
    "DriverResult",
    "InjectionError",
    "MuseDriverUnavailable",
    "SpendGuardError",
    "build_report",
    "inject_bug",
    "muse_exec_driver",
    "reference_patcher",
    "require_spend_guard",
    "run_loop_eval",
]
