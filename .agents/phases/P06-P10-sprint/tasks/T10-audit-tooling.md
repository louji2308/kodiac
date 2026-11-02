# T10: Dataset-audit tooling (run, review, digest, export, guarded publish)
phase: P08 · owner: IMPL-10 (Sonnet 5.5 @ high) · status: TODO
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
- [ ] Tests pass: audit_run resumability + per-episode failure isolation; review flow (only reviewer files set `human_verified`); digest determinism (byte-identical JSON twice) and the no-verified-flags case; narration validator rejects an invented number; export parquet validates against VerdictRow; publish refusal matrix (no ticket, dry_run, missing approval file) and the one allowed path returns text without any network import.
- [ ] ruff clean; no `TODO|NotImplemented`; full suite green. Committed `feat(p08/t10): …`.

## Report (filled by owner at DONE)
