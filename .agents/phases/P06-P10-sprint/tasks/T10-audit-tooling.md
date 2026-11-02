# T10: Dataset-audit tooling (run, review, digest, export, guarded publish)
phase: P08 · owner: IMPL-10 (Sonnet 5.5 @ high) · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P05.S11, P06.S14, P08.S08–S09 · ARCHITECTURE.md §5.6, KD-19 · IDEA F49–F52 · AGENTS §12.3
depends_on: [] · blocks: [ORCH CLI `audit` wiring]
owns_paths: [src/Kodiac_robotics/audit/**, tests/audit/**, tests/fixtures/audit/**]
reads_only: [contracts/** (VerdictRow), pipeline/run.py, compiler/text_compile.py, compiler/template_fallback.py, io/lerobot.py, render/card.py, tests/fixtures/**]
timebox: 120 min

## Mission
The audit opener ("we ran Kodiac over public robot datasets; N of the 'successful' demonstrations fail the physics test") needs (1) a batch runner, (2) a human-verification UI so only **hand-verified** flags are ever shown, (3) a deterministic Failure-Norm Digest, (4) a LeRobot-compatible verdict export, and (5) a publish command that is impossible to run without recorded human approval. No network, no keys: everything is exercised on fixture clips and **clearly labelled demonstration data**; the real datasets are never claimed audited.

## Interface contract (FROZEN)
```python
# audit/run.py
def audit_run(dataset: str, task_filter: str, camera: str, limit: int, *, episodes: Iterable[AuditEpisode], out_dir: Path, test_for_task: Callable[[str], Path], run_fn=...) -> pd.DataFrame   # VerdictRow-conformant; per-episode try/except; resumable; cache per (dataset, task) compile
class AuditEpisode(BaseModel): dataset: str; episode_index: int; camera: str; task: str; clip_path: str; is_fixture: bool
# audit/review.py     review queue (candidates.html static page + jsonl decisions); only FAIL candidates enter; `human_verified` only ever set by a reviewer decision file
def build_candidates_html(verdicts_parquet: Path, out_html: Path) -> None
def apply_reviews(verdicts_parquet: Path, reviews_jsonl: Path) -> pd.DataFrame
# audit/digest.py    deterministic: histogram of failure norms (step/predicate) + Wilson CI of X (lower bound) over *human-verified* flags only
def failure_norm_digest(df: pd.DataFrame) -> dict         # includes N, n_flagged, n_verified, X_lower_bound, sampling description, `is_demonstration_data: bool`
def narrate(digest: dict, wonder: Callable[[str],str] | None) -> tuple[str, Literal["muse-wonder","template"]]   # numbers validated against digest (reuse the validator approach of blame/validate.py: no new numbers)
# audit/export.py
def export_verdicts(df, out_dir: Path) -> Path             # Kodiac_verdicts.parquet (VerdictRow schema) + evidence dir manifest
# audit/publish.py
def publish(report_md: Path, *, approval_ticket: str | None, dry_run: bool = True) -> str   # refuses (raises PublishRefused) unless approval_ticket is a non-empty string AND dry_run is False AND file `.Kodiac/human_approval/<ticket>` exists; NEVER performs a network action in this repo (returns the text it would post). 
```
## Rules
- `human_verified=None` by default for every row; flags without a human decision never appear in the digest numerator or any summary. If there are no verified flags, `X_lower_bound` is `None` and the narration says so.
- Everything derived from `tests/fixtures/**` clips carries `is_demonstration_data=True` and the HTML banner "DEMONSTRATION DATA: fixture clips, not a real dataset audit".
- Text-compile of task strings must go through the existing `compiler.text_compile` (deterministic template fallback is badged `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK]`: propagate that badge into the verdict rows' notes).
- No outward actions (AGENTS §12.3): `publish` is guarded as specified; no `requests/httpx` calls anywhere in `audit/`.
## Definition of Done
- [x] Tests pass: audit_run resumability + per-episode failure isolation; review flow (only reviewer files set `human_verified`); digest determinism (byte-identical JSON twice) and the no-verified-flags case; narration validator rejects an invented number; export parquet validates against VerdictRow; publish refusal matrix (no ticket, dry_run, missing approval file) and the one allowed path returns text without any network import.
- [x] ruff clean; no `TODO|NotImplemented`; full suite green. Committed `feat(p08/t10): …`.

## Report (filled by owner at DONE)

**Micro-plan:** rows.py shared schema -> run.py batch runner -> review.py -> digest.py -> export.py -> publish.py -> tests.

**Built** (`src/Kodiac_robotics/audit/`): `run.py` (AuditEpisode, audit_run, text_compile_resolver, default_run_fn), `rows.py`, `review.py` (static HTML + `apply_reviews`), `digest.py` (Wilson, digest, narrate, validate_narration_numbers, render_report), `export.py`, `publish.py` (PublishRefused).
**Commits:** 2ab055b (runner), a462bee (review/digest/export/publish + tests).
**Tests:** `tests/audit` = 23 passed (8 runner, 15 review/digest/export/publish/no-network AST scan); ruff clean; no TODO/NotImplemented. Full suite: 698 passed, 1 failed: `tests/loop/test_mcp.py::test_integration_correct_script_passes` (sim/loop area owned by other tasks; fails in isolation too; not touched by audit/).
**Evidence:** fixture episodes `tests/fixtures/audit/episodes.json` (clips from tests/fixtures/clips); all outputs carry `is_demonstration_data=True` and the banner.

**Behaviours / deviations**
- Frozen signatures kept. Additions: `run_fn(test_path, clip_path, out_dir, is_fixture)`; `export_verdicts(..., evidence_root=None)`; `publish(..., approval_dir=...)`; `failure_norm_digest(df, sampling=None)`; `text_compile_resolver`.
- Rows = VerdictRow columns + `task, clip_path, is_fixture, is_demonstration_data, notes, error, review_decision, reviewer`. Export keeps VerdictRow columns + `is_demonstration_data`, `notes`.
- `t_star_s` here is the decisive-step decision time from `run`, not a blame onset (stated in row notes).
- Run errors -> CANT_TELL row with reason `run_error`; excluded from N; never cached (rerun retries).
- Digest: X_lower_bound = 95% Wilson lower bound of (human-confirmed FAIL / N checked); None if no verified flags. Narration numbers validated against digest; any violation or Wonder error -> template.
- publish refuses additionally on malformed ticket (path traversal), CI env, missing/empty report, and any report containing DEMONSTRATION DATA. Spec-literal: default dry_run=True refuses.
- Not built: Wonder persisted memory file (F50 "Full"); blame-onset t* (T01's blame not imported); audit card PNG.
- pandas + pyarrow are imported by audit/ and are installed in the venv but are NOT in pyproject dependencies/extras: ORCH should add them (e.g. to `proof` extra).

**3 embarrassment risks:** (1) fixture flags look like a real audit -> banner in HTML/notes/digest/report/manifest, publish refuses demo reports, no real dataset claimed. (2) Engine false positive observed: golden `correct_run.mp4` returns FAIL at step grasp via `pipeline.run` (existing engine behaviour, not audited here); hence nothing counts without a human `confirmed`; reviewers must reject such flags. (3) A forged reviews.jsonl could mark flags verified -> file is the only path and requires named reviewer, but is not cryptographically signed; disclose as human-process control.