# T08: Judge layer (`looks()` two-way crop judge, Wonder escalation, backends)
phase: P06 · owner: IMPL-8 (Sonnet 5.5 @ high) · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P06.S09 · ARCHITECTURE.md §8, KD-09 · IDEA F25–F27 (Strong tier)
depends_on: [] · blocks: [engine `looks()` wiring (ORCH), proof ablation R2–R4]
owns_paths: [src/Kodiac_robotics/judge/crops.py, src/Kodiac_robotics/judge/two_way.py, src/Kodiac_robotics/judge/client.py, src/Kodiac_robotics/judge/backends.py, src/Kodiac_robotics/judge/__init__.py, tests/judge/**, tests/fixtures/judge/**]
reads_only: [contracts/**, engine/**, render/overlay.py, config.py, cache.py, proof/judges/single_pass.py (style reference), segment/rle.py]
timebox: 120 min

## Mission
Where geometry cannot decide (e.g. "is the drawer flush?"), a VLM judges a crop with an outline, asked **twice with antonyms** so a biased "yes" cannot pass.
Disagreement escalates to Muse Wonder, otherwise `CAN'T TELL (appearance_unresolved)`. No API key exists: build to the real protocol with recorded fixtures; never present fixture answers as model output.

## Interface contract (FROZEN)
```python
# crops.py
def make_crop(frame_bgr: np.ndarray, mask_rle: str, rle_size: tuple[int,int], *, pad: float = 0.25, min_px: int = 512) -> bytes   # PNG, outline drawn, upscaled ≥512
# two_way.py   (implements contracts.core.VLMJudge via TwoWayJudge.ask_two_way)
class TwoWayJudge:
    def __init__(self, backend: "JudgeBackend", escalator: "JudgeBackend | None" = None, *, escalation_cap_s: float = 3.0, cache=None): ...
    def ask_two_way(self, crop_png: bytes, q_pos: str, q_neg: str) -> tuple[Tri, str]   # (Tri, reason); U + reason "appearance_unresolved" when unresolved
def antonym_questions(obj: str, state: str) -> tuple[str, str]     # ("Is the {obj} {state}?", "Is the {obj} {opposite}?") using an antonym table; never "not"
# backends.py / client.py
class JudgeAnswer(BaseModel): answer: Literal["yes","no","cant_tell"]; reason: str
class JudgeBackend(Protocol): name: str; model_id: str; is_fixture: bool; def ask(self, crop_png: bytes, question: str, system: str) -> JudgeAnswer
def get_backend(name: str | None = None) -> JudgeBackend     # env Kodiac_JUDGE_BACKEND ∈ meta|baseten-spark-open|modal-glimmer-vllm|llamacpp-glimmer|fixture ; default meta; no key → returns the fixture backend LABELLED is_fixture=True (never silently)
```
## Steps
1. Decision table (ARCH §8.3): (yes,no)→T · (no,yes)→F · otherwise escalate to `muse-wonder-1.0` with the same pair under a wall-clock cap (injectable clock for tests) → (yes,no)/(no,yes) decides, else U/`appearance_unresolved`. System prompt: "Answer only from the outlined region." Both questions asked in parallel (threads).
2. Backends: `meta` (OpenAI-compatible HTTP via httpx to the Meta API; key from `MODEL_API_KEY` env, **presence only**, never printed; request shape exactly as in `proof/judges/single_pass.py` / `compiler/spark_compile.py` for consistency), `baseten-spark-open`, `modal-glimmer-vllm`, `llamacpp-glimmer` (all OpenAI-compatible, base URL from env; Glimmer sampling temp 1.0 / top_p 0.95 / top_k 64), and a `fixture` backend replaying recorded answers keyed by `(crop sha256, question)` from `tests/fixtures/judge/*.json`, plus a deterministic synthetic recorder to build those fixtures (labelled).
3. Caching by `(backend, model, crop sha, question)` using `cache.cached_call`.
4. Wire contract: expose `judge_atom(atom: Atom, frame, mask) -> tuple[Tri, ReasonCode|None]` helper that the engine can call for `Atom(kind="looks")`; returns `(Tri.U, ReasonCode.APPEARANCE_UNRESOLVED)` when unresolved. **Do not edit engine/**: ORCH wires it.
5. Tests (all offline): antonym table coverage; decision table exhaustively (9 combos × escalation outcomes); escalation timeout → U; cache hit; the no-key path returns a fixture backend with `is_fixture=True` and the result string/reason carries `[FIXTURE]`; crop is ≥512 px, contains the outline pixels; an adversarial always-"yes" backend yields U/F-not-T (the two-way protocol defeats yes-bias).

## Definition of Done
- [ ] Tests pass; ruff clean on owned paths; no `TODO|NotImplemented`; full suite green. No network calls in tests.
- [ ] Committed `feat(p06/t08): …`.

## Report (filled by owner at DONE)
