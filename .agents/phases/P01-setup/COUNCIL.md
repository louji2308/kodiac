# COUNCIL: P01 Setup & Environment Verification
Inputs: BRIEF.md · REVIEW(P00) status: N/A · Hours to deadline: ~175.5

## R0/R1: D1 Architect
[2026-10-28T09:32:00Z · D1]

- **Phase goal as I understand it (≤3 lines):**
  Establish a compliant, reproducible engineering environment: scaffold `Kodiac-robotics` under Python 3.12 with `uv`, freeze Pydantic v2 core contracts with roundtrip tests and JSON Schema export, implement atomic SHA-256 caching and config, build `Kodiac doctor` and the ST1–ST13 smoke test suite with offline fixture fallbacks, and verify the SDM channel.

- **Evidence gathered:**
  - `python --version` → `Python 3.11.9` on host Windows machine; `uv python list` confirms `cpython-3.12.13-windows-x86_64-none` is available for automatic installation and pinning via `uv`.
  - `uv --version` → `uv 0.12.3 (507230998 2026-08-07 x86_64-pc-windows-msvc)` operational.
  - `ffmpeg -version` → `ffmpeg 8.1-full_build-www.gyan.dev` with `libx264`, `libx265`, `libsvtav1` present on system PATH.
  - `nvidia-smi` → command not found (no local GPU on host PATH). Architecture deduction: all GPU-intensive tasks (ManiSkill rendering, SAM 3.1 batch tracking) must run remotely on Modal or use synthetic fixture replays.
  - `opencode run --help` → command succeeded; full CLI interface verified (`-m`, `--dir`, `--format`). Confirms SDM Option A is functional.
  - `Get-Command muse` → not found on PATH. Muse Code hook testing must rely on programmatic SDK or manual/mock harness.
  - Environment keys check (`MODEL_API_KEY`, `HF_TOKEN`, `MODAL_TOKEN_ID`) → all unset (`False`). Architecture requirement: `Kodiac doctor` and ST1–ST13 smoke scripts must support graceful diagnostic reporting and synthetic fixture fallback without uncaught crashes.
  - `git log -1 --format="%cI %h %s"` → `2026-10-28T09:07:01+05:30 7341080` (commit date ≥ 2026-10-26, compliant with hackathon in-window build rule).

- **Proposed approach:**
  1. **Scaffold & Build Setup (S00–S04):** Initialize `pyproject.toml` targeting Python 3.12 with `uv`, declaring extras `[sim, proof, app, viz, mcp, lerobot, dev]` per `TOOLS_AND_REQUIREMENTS.md` §12. Package name `Kodiac-robotics`, module `src/Kodiac_robotics/`. CLI entrypoint `Kodiac = "Kodiac_robotics.cli:app"`.
  2. **Frozen Data Contracts (S05):** Implement `src/Kodiac_robotics/contracts/core.py` matching `ARCHITECTURE.md` §4 with Pydantic v2. Implement `schema_export.py` exporting to `docs/schemas/`. Implement unit test suite in `tests/unit/contracts/test_core.py` verifying roundtrip serialization, `Tri` and `Verdict` enum constraints, and `Expr.model_rebuild()` recursive resolution. Tag `contracts-v1`.
  3. **Config & Hash-Based Caching (S06):** Implement `src/Kodiac_robotics/config.py` using `pydantic-settings` (reads `.env`, safely masks secrets). Implement `src/Kodiac_robotics/cache.py` using SHA-256 over canonical JSON inputs and payload bytes with atomic file writes (`atomicwrites` or tempfile rename).
  4. **Code Quality & CI (S07):** Configure `ruff.toml` (lint + format), `pytest.ini` (markers: `slow`, `live`, `gpu`), and `.github/workflows/ci.yml` running unit tests in secret-free offline mode.
  5. **Diagnostic CLI `Kodiac doctor` (S08):** Implement rich diagnostic reporting checking Python version, ffmpeg, env-var presence (masked), network reachability to `api.meta.ai`, and Modal setup. Must exit 0 when core offline development environment is valid.
  6. **Smoke Test Suite ST1–ST13 (S09–S10):** Implement scripts in `scripts/smoke/st01_models.py` through `st13_sdm.py`. Each writes `artifacts/p01/smoke/stNN.json`. Provide `--mock` / fixture execution when credentials are not yet injected.
  7. **SDM Channel & Modal Infrastructure (S11–S12):** Deploy SDM dispatch script utilizing `opencode run` (Option A) and record ADR-0002. Scaffold `modal/hello_cpu.py` and `modal/hello_l4.py`.
  8. **Documentation & Traceability Skeletons (S14):** Generate `docs/features.yaml` (seeding F01–F60 as `planned`), `docs/VIDEO_NUMBERS.md`, `tests/fixtures/README.md`, and `experiments/README.md`.

- **Interface contracts:**
  - `src/Kodiac_robotics/contracts/core.py`:
    - Enums: `Tri(str, Enum) = T|F|U`, `Verdict(str, Enum) = PASS|FAIL|CANT_TELL`, `ReasonCode(str, Enum)`.
    - AST: `ObjectDecl`, `Param`, `Atom`, `Expr`, `Step`, `GreenTest`, `GreenLock`.
    - Media & Perception: `ClipRef`, `Clip`, `ObjMask`, `Track`, Protocols `Segmenter`, `VLMJudge`, `ASR`, `Memory`, `ScaleModel`.
    - Measurement & Blame: `Component`, `PredFrame`, `Event`, `StepResult`, `CodeLocation`, `Hint`, `FactTable`, `Blame`.
    - Engine & Loop: `RunResult`, `VerifyRequest`, `GateState`.
    - Storage & Proof: `VerdictRow`, `JudgeLabel`.
  - `src/Kodiac_robotics/config.py`:
    ```python
    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
        model_api_key: SecretStr | None = None
        model_api_base: str = "https://api.meta.ai/v1"
        sam_model_id: str = "sam-3.1"
        spark_model_id: str = "muse-spark-1.3"
        wonder_model_id: str = "muse-wonder-1.0"
        voice_model_id: str = "muse-voice-transcribe-1.0"
        cache_dir: Path = Path(".cache/Kodiac")
        offline_mode: bool = False
    ```
  - `src/Kodiac_robotics/cache.py`:
    ```python
    def cached_call(key_parts: dict[str, Any], fn: Callable[[], T], cache_dir: Path | None = None) -> T: ...
    def compute_cache_key(key_parts: dict[str, Any]) -> str: ...
    ```

- **Proposed task DAG:**
  ```
  ORCH (S00-S03, S13)
    │
    ├──► IMPL-1: T01-core-contracts-and-tooling (S04, S05, S06, S07)
    │      owns_paths:
    │        - pyproject.toml
    │        - src/Kodiac_robotics/contracts/
    │        - src/Kodiac_robotics/config.py
    │        - src/Kodiac_robotics/cache.py
    │        - tests/unit/contracts/
    │        - docs/schemas/
    │        - .github/workflows/
    │
    ├──► IMPL-2: T02-doctor-and-smoke-suite (S08, S09, S10)
    │      owns_paths:
    │        - src/Kodiac_robotics/cli/
    │        - scripts/smoke/
    │        - artifacts/p01/smoke/
    │        - tests/unit/cli/
    │
    └──► IMPL-3: T03-modal-sdm-and-docs (S11, S12, S14)
           owns_paths:
             - modal/
             - scripts/sdm/
             - docs/features.yaml
             - docs/VIDEO_NUMBERS.md
             - docs/DEMO_FILMING_GUIDE.md
             - tests/fixtures/README.md
             - experiments/README.md
    │
    ▼
  ORCH Integration & Gate (S15)
    owns_paths: .agents/STATE.md, .agents/DECISIONS.md, .agents/phases/P01-setup/GATE.md
  ```

- **Top risks (3):**
  1. *Risk:* Blocked cloud credentials (`MODEL_API_KEY`, Modal) halt smoke execution and prevent gate passage.
     *Mitigation:* Smoke tests implement dual-mode execution: live network check when keys exist, structured mock fixture validation (`{ok: false, status: "PENDING_KEY"}`) when missing, ensuring CI and exit gate verifications are non-blocking.
     *Tripwire:* If keys remain unavailable after 12 hours, lock stack facts via ADR-0003 using documented API contracts and continue P02 on synthetic fixtures.
  2. *Risk:* Pydantic v2 recursion errors during recursive `Expr` serialization and JSON schema generation.
     *Mitigation:* Call `Expr.model_rebuild()` immediately following model definitions and write an explicit test asserting `GreenTest.model_json_schema()` executes without recursion limit errors.
     *Tripwire:* Schema generation failure in S05 triggers immediate fallback to flat AST model (`CompileDraft`).
  3. *Risk:* Host lacks local Nvidia GPU, threatening simulation and rendering workflows in P02.
     *Mitigation:* Isolate local execution to CPU/headless software rendering and ensure ManiSkill3 / SAM 3.1 workflows are routed to Modal remote GPU functions.
     *Tripwire:* Local ManiSkill test failing on OpenGL context forces headless OSMesa or remote-only execution mode.

- **Improvement proposals:**
  - **IP-P01-D1-1: Contract Synthetic Fixture Generator:** Add `src/Kodiac_robotics/contracts/fixtures.py` producing minimal valid instances of `GreenTest`, `Clip`, `RunResult`, and `Blame`. Guarantees downstream phases (P02–P04) have standardized, schema-compliant test doubles without network overhead.
    - *Judge impact:* +Reliability, ensures zero mock drift across phases.
    - *Cost:* 0.5 h.
    - *Affects:* `src/Kodiac_robotics/contracts/`.
    - *Invariants:* Preserves all I1–I17.
  - **IP-P01-D1-2: Nonce & Timings Verification in RunResult:** Add Pydantic field validators on `RunResult` ensuring `timings_ms` contains `total_ms` and `nonce` is a valid 16-character hex string.
    - *Judge impact:* Reinforces I15 (traceability & honesty by construction).
    - *Cost:* 0.25 h.
    - *Affects:* `src/Kodiac_robotics/contracts/core.py`.

- **Confidence:** 94/100 because all underlying system dependencies (`uv`, `ffmpeg`, `opencode`) are verified on the machine, the contracts in `ARCHITECTURE.md` are completely specified, and the 3-way task partitioning has zero path collisions.

## R0/R1: D2 Judge Advocate
- **Phase goal as I understand it (≤3 lines):**
  Bootstrap Kodiac's compliant OSS repository, freeze core Pydantic data contracts (`Verdict`, `BlameReport`, `PredicateResult`) with round-trip serialization tests, build diagnostic CLI `Kodiac doctor`, and establish verifiable smoke tests ST1–ST13 against Meta/partner APIs. Ensure Day 1 meets the Indie Track winning bar with zero broken stubs, zero ungrounded claims, and rock-solid foundation for video, live demo, and downstream retraining proof.

- **Evidence gathered:**
  - `python --version` → `Python 3.11.9` on host; `uv python list` confirms `cpython-3.12.13` available via uv download. `pyproject.toml` specifies `requires-python = ">=3.12"`.
  - `ffmpeg -version` → `ffmpeg version 8.1-full_build` installed and functional (satisfies `>=6` requirement).
  - `opencode --version` → `1.18.20`; `opencode run --help` validates headless flags (`--model`, `--format json`, `-f`), confirming SDM Option A execution readiness.
  - `git log -n 2 --format=fuller` → First commit `11bf83d` authored `Wed Oct 28 09:04:56 2026 +0530`, strictly within hackathon build window (opened Oct 26 16:00 UTC), verifying Rule R1 compliance.
  - `git ls-files "Project Spec"` → Tracked duplicate spec directory exists in git index; public repo presentation requires removal during S00 scrub.
  - `HACKATHON.md §0, §9`: Rubric is Impact (30%), Meta AI Tooling (25%), Demo (25%), Technical Depth & Execution (20%). A first-round judge spends ~5 minutes; an ungrounded claim or broken quickstart drops Demo to ≤5.
  - `IDEA.md §0`: Invariants I1–I17 are binding. P01 must freeze I3 (`PASS / FAIL / CAN'T TELL`), I4 (`blame` t* + cause ±σ), I6 (6 exact predicates), and I16 (human demo to robot attempt effector aliasing).

- **Proposed approach:**
  1. *S00/S01 Compliance & Scrub:* Remove `Project Spec/` duplicate tracking, enforce `.gitignore` (secrets, raw video, heavy artifacts), verify `BUILD_LOG.md`, `ATTRIBUTIONS.md`, and clean `README.md`.
  2. *S02/S03 Scaffolding & ADR-0001:* Confirm agent runtime (Gemini 3.8 Flash for subagents per user directive) and record `ADR-0001`.
  3. *S04 Python Scaffold:* Initialize `pyproject.toml` with `uv` (`name = "Kodiac-robotics"`, CLI entrypoint `Kodiac`, optional extras `[sim]`, `[proof]`, `[app]`, `[dev]`, keeping core install torch-free for instant judge install).
  4. *S05 Frozen Contracts:* Implement `src/Kodiac_robotics/contracts/core.py` (Pydantic v2 models: `Verdict`, `ReasonCode`, `PredicateType`, `PredicateResult`, `BlameReport`, `DiffReport`, `RunResult`). Add schema exporter to `docs/schemas/` and round-trip tests. Tag `contracts-v1`.
  5. *S06 Configuration & Cache:* Implement `config.py` (Settings from env) and `cache.py` (content-hash sha256 cache) with unit tests.
  6. *S07 Tooling & CI:* Configure `ruff`, `pytest` (markers: slow, live, gpu), and `.github/workflows/ci.yml` (runs with zero network secrets).
  7. *S08 `Kodiac doctor`:* Rich diagnostic CLI command testing env vars (presence only), Python, ffmpeg, and API endpoints without leaking secrets.
  8. *S09/S10 Smoke Test Suite ST1–ST13:* Scripted tests in `scripts/smoke/st01_models.py` through `st13_sdm.py`. Record latency and stack facts into `ADR-0003`.
  9. *S11 SDM Channel:* Verify Option A (`opencode run` with DeepSeek V4.1 Flash) and fallback Option B; log `ADR-0002`.
  10. *S12 Modal Foundation:* Prepare `modal/hello_cpu.py` and secret definitions for deployment.
  11. *S13 Human Checklist:* Deliver `HUMAN_TODO.md` (claims, tokens, gated weights access, PyPI package reservation).
  12. *S14 Docs Skeletons:* Seed `docs/VIDEO_NUMBERS.md`, `docs/features.yaml` (F01–F60 matrix), `experiments/README.md`.
  13. *S15 Exit Gate:* Fill `GATE.md`, execute verifications, and tag `p01-done`.

- **Interface contracts:**
  Core Pydantic v2 models in `src/Kodiac_robotics/contracts/core.py`:
  - `Verdict(str, Enum)`: `PASS = "PASS"`, `FAIL = "FAIL"`, `CANT_TELL = "CAN'T TELL"` (JSON serializes as `"CANT_TELL"`).
  - `ReasonCode(str, Enum)`: `OCCLUSION = "E001_OCCLUSION"`, `OBJECT_NOT_FOUND = "E002_OBJECT_NOT_FOUND"`, `LOW_CONFIDENCE = "E003_LOW_CONFIDENCE"`, `CAMERA_BLUR = "E004_CAMERA_BLUR"`, `OUT_OF_FRAME = "E005_OUT_OF_FRAME"`.
  - `PredicateType(str, Enum)`: `on = "on"`, `inside = "inside"`, `near = "near"`, `lifted = "lifted"`, `moves_with = "moves_with"`, `dwell = "dwell"`.
  - `PredicateResult(BaseModel)`: `predicate: PredicateType`, `satisfied: bool`, `value: float`, `threshold: float`, `sigma: float`, `unit: str`, `confidence: float`, `details: dict[str, Any] = Field(default_factory=dict)`.
  - `BlameReport(BaseModel)`: `onset_frame: int`, `onset_time_s: float`, `broken_predicate: PredicateType`, `measured_value: float`, `threshold: float`, `sigma: float`, `unit: str`, `direction: str`, `summary: str`.
  - `DiffReport(BaseModel)`: `step_index: int`, `event: str`, `demo_timestamp_s: float`, `attempt_timestamp_s: float`, `delta_s: float`, `discrepancy: str`.
  - `RunResult(BaseModel)`: `verdict: Verdict`, `reason: Optional[ReasonCode] = None`, `blame: Optional[BlameReport] = None`, `diff: Optional[DiffReport] = None`, `predicates: list[PredicateResult] = Field(default_factory=list)`, `latency_ms: float`, `trace_id: str`.

- **Proposed task DAG:**
  - `T01-core-contracts` (IMPL-1): S04, S05, S06, S07. `owns_paths`: `pyproject.toml`, `src/Kodiac_robotics/contracts/`, `src/Kodiac_robotics/config.py`, `src/Kodiac_robotics/cache.py`, `tests/unit/`, `.github/workflows/ci.yml`, `docs/schemas/`.
  - `T02-doctor-and-smoke` (IMPL-2): S08, S09, S10. `owns_paths`: `src/Kodiac_robotics/cli.py`, `scripts/smoke/`, `artifacts/p01/`. (Depends on T01).
  - `T03-infra-sdm-docs` (IMPL-3): S11, S12, S14. `owns_paths`: `modal/`, `scripts/sdm/`, `docs/VIDEO_NUMBERS.md`, `docs/features.yaml`, `experiments/README.md`. (Parallel with T02).
  - `ORCH`: S00, S01, S02, S03, S13, S15, Gate verification & Tagging.

- **Judge-impact table:**
  | Criterion (Weight) | What Judge Checks (HACKATHON.md §9) | Phase P01 Concrete Delivery | Score Impact |
  |---|---|---|---|
  | **Impact (30%)** | Real-world pain in robot training; clean packaging; can a researcher install & run it next week? | Clean `pyproject.toml` (`pip install Kodiac-robotics`), zero-torch core CLI, `features.yaml` matrix F01–F60 tracking shipped capabilities. | **8.5 / 10** (eliminates broken-install friction). |
  | **Use of Meta AI Tooling (25%)** | Load-bearing, unexpected Meta model capabilities (backward SAM time machine, Spark compiler, Wonder adjudicator). | Smoke tests ST1–ST7 verifying SAM 3.1 backward propagation, Spark structured JSON output, Wonder crop adjudication, and Muse Code Stop-hook done-gate interface. | **9.0 / 10** (solidifies genuine multi-model platform depth). |
  | **Demo (25%)** | Reliable, crash-proof execution; honest diagnostics; fast live path (<12s budget). | `Kodiac doctor` CLI with Rich terminal output, hash-based deterministic caching (`cache.py`), Modal CPU deployment foundation. | **8.5 / 10** (prevents demo-day crashes and silent 500s). |
  | **Technical Depth & Execution (20%)** | Sound engineering, strict data contracts, round-trip tests, honest bounds (±σ), zero faked numbers. | Frozen Pydantic v2 contracts enforcing ±σ error bars, 3-state verdict (`PASS / FAIL / CAN'T TELL`), JSON Schema export, CI suite. | **9.5 / 10** (uncompromising software rigor). |

- **Demo/video artifacts this phase must produce:**
  - `artifacts/p01/doctor_terminal.txt`: ANSI capture of `Kodiac doctor` diagnostic run (usable for README and video B-roll).
  - `docs/schemas/core_contracts.json`: Exported JSON Schemas for `RunResult` and `BlameReport` demonstrating typed rigor.
  - `artifacts/p01/smoke/stNN.json`: Structured results of ST1–ST13 with latency and memory footprints.
  - `docs/features.yaml`: Seeded status matrix of F01–F60 for the README Shipped Table.

- **Top risks (3):**
  1. *Risk:* Pending external API keys (Meta / Modal) stall smoke testing and block phase sign-off.  
     *Mitigation:* Implement synthetic fixture replay mode (`Kodiac_SAM_BACKEND=fixture`) in smoke scripts so client decoding and contract parsing are 100% verified locally.  
     *Tripwire:* External keys missing > 2 hours into execution.
  2. *Risk:* Host Python 3.11 defaults conflict with package requirement `>=3.12`.  
     *Mitigation:* Explicitly provision and bind Python 3.12 via `uv venv --python 3.12`.  
     *Tripwire:* `uv run python --version` output is `< 3.12`.
  3. *Risk:* Redundant spec copies in `Project Spec/` leak unpolished artifacts into public repository.  
     *Mitigation:* ORCH executes git untracking and removal of `Project Spec/` during S00 scrub.  
     *Tripwire:* `git ls-files "Project Spec"` returns non-empty.

- **Improvement proposals:**
  - `IP-P01-D2-1: Public-Surface Polish & Scrub (S00 Enforcement)`  
    *Change:* Untrack and remove duplicate `Project Spec/` directory from git; verify root layout is clean and compliant.  
    *Evidence:* `git ls-files "Project Spec"` shows redundant tracked files.  
    *Judge Impact:* +0.5 on Technical Depth & Execution (clean repository hygiene). Cost: 0.25 h. Risk: None. Invariants: Protected.
  - `IP-P01-D2-2: Standardized Doctor Rich Table for Video B-Roll`  
    *Change:* Style `Kodiac doctor` with a polished Rich table (component, status icon, latency, masked secrets) designed for README quickstart screenshots and video Beat 4.  
    *Evidence:* `HACKATHON.md §9.2`: J3 (DevRel) inspects install experience; visual proof establishes instant credibility.  
    *Judge Impact:* +0.5 on Demo. Cost: 0.5 h. Risk: None. Invariants: Protected.

- **Confidence:** 95/100 because the tooling environment is verified (Python 3.12 via uv, ffmpeg 8.1, opencode 1.18.20), data contracts strictly match `ARCHITECTURE.md §4`, and the evaluation plan directly optimizes for the 4 hackathon rubric criteria.

## R0/R1: D3 Red Team
[2026-10-28T09:30:00Z · D3]

- **Phase goal as I understand it (≤3 lines):**
  P01 establishes an unshakeable, fully audited repository and CI environment, freezes core data contracts with zero runtime stubs, builds `Kodiac doctor`, and constructs a non-blocking smoke test suite ST1–ST13 with mock fixture fallbacks so downstream development proceeds deterministically even while external API keys, tokens, and gated weights remain pending.

- **Evidence gathered:**
  - `python --version` → Python 3.11.9 present; `uv python list` confirms `cpython-3.12.13` is available for automatic download. Must enforce Python 3.12 via `uv venv --python 3.12`.
  - `nvidia-smi` → Command not found. Local Windows host has NO accessible CUDA GPU. All heavy ML/sim/CUDA workloads (ManiSkill rendering, SAM 3.1 weights, CoTracker3, Glimmer) MUST run remotely on Modal.
  - `ffmpeg -version` → ffmpeg 8.1 with libx264/libx265 is installed and functional.
  - `modal --version` → Command not found. Modal CLI not installed in base environment.
  - `opencode --version` → 1.18.20 is installed; `opencode run --help` confirms `-m, --model provider/model` supports headless CLI execution for SDM Option A.
  - `muse --version` → Command not found. Muse CLI is absent.
  - `Get-ChildItem env:MODEL_API_KEY, env:HF_TOKEN, env:MODAL_TOKEN_ID, env:BASETEN_API_KEY` → None of the 4 required sponsor credentials are set.
  - `git status` → Working tree has uncommitted scaffolding files; clean scrub and commit required.

- **Proposed approach:**
  1. **S00–S03 (Scrub & Scaffolding):** Clean lineage check, initialize clean repo state, record ADR-0001 (Antigravity/OpenCode runtime).
  2. **S04–S07 (Core Contracts & CI):** Initialize `pyproject.toml` targeting Python 3.12. Implement `src/Kodiac_robotics/contracts/core.py` (Pydantic v2) with 100% round-trip unit tests. Setup hash-based `cache.py` and configuration. Configure CI without secrets requirement.
  3. **S08 (Kodiac Doctor):** Implement `Kodiac doctor` with graceful diagnostics that exit 0 for offline core capabilities and clearly flag missing sponsor keys without crashing or printing secret values.
  4. **S09–S10 (Smoke Test Suite ST1–ST13):** Build smoke tests with dual execution modes: live (when keys exist) and mock/dry-run (validating payload schemas and serialization offline). If keys are absent, generate valid `artifacts/p01/smoke/stNN.json` marked `status: pending_key` so the exit gate is non-blocking.
  5. **S11 (SDM Channel):** Verify Option A (`opencode run` + DeepSeek V4.1 Flash) and Option B (Antigravity + Gemini 4 Argon), logging ADR-0002.
  6. **S12 (Modal Setup):** Prepare Modal serverless definitions (`modal/`) with dry-run/CPU fallbacks.
  7. **S13–S15 (Human Checklist & Gate):** Provide `HUMAN_TODO.md`, populate doc skeletons, and tag `contracts-v1` and `p01-done`.

- **Interface contracts:**
  - `Verdict`: Enum `PASS`, `FAIL`, `CANT_TELL` (I2 inviolable).
  - `Measurement`: `metric: str`, `value: float`, `unit: str`, `sigma: float`, `onset_frame: Optional[int]`.
  - `PhysicalCause`: `predicate: str`, `measured_diff: float`, `threshold: float`, `confidence: float`, `evidence_frames: List[int]`.
  - `BlameResult`: `verdict: Verdict`, `onset_frame: Optional[int]`, `physical_cause: Optional[PhysicalCause]`, `claim: str`.
  - `DoctorReport`: `python_ok: bool`, `ffmpeg_ok: bool`, `keys_present: Dict[str, bool]`, `gpu_available: bool`, `modal_ok: bool`.
  - `SmokeTestResult`: `test_id: str`, `ok: bool`, `status: Literal["ok", "failed", "pending_key", "skipped"]`, `latency_ms: Optional[float]`, `notes: str`, `evidence_path: Optional[str]`.

- **Proposed task DAG:**
  - `T1` (S00–S07): Contracts, Scaffold, Cache & CI (`pyproject.toml`, `src/Kodiac_robotics/{contracts,config.py,cache.py}`, `tests/unit/`, `.github/workflows/`)
  - `T2` (S08–S10): `Kodiac doctor` CLI & Smoke Test Suite ST1–ST13 (`src/Kodiac_robotics/cli.py`, `scripts/smoke/`, `artifacts/p01/smoke/`)
  - `T3` (S11–S14): SDM Channel, Modal Foundation & Doc Skeletons (`scripts/sdm/`, `modal/`, `docs/`)
  - *DAG execution:* T1 runs first to freeze contracts. T2 and T3 execute in parallel once `contracts/core.py` is staged.

- **Top risks (3):**
  - **Risk 1: Dependency Deadlock on Human Keys.** Implementers block waiting for `MODEL_API_KEY` or `MODAL_TOKEN_ID` to run ST1–ST13.
    - *Mitigation:* Require `--mock`/`--dry-run` fallback in all smoke tests; record `status: pending_key` in artifact JSON without blocking CI.
    - *Tripwire:* Any task card stalled >20 min waiting for external network credentials.
    - *Fallback:* Generate synthetic OpenCV video fixtures and validate request/response parsing offline.
  - **Risk 2: Windows OS Incompatibilities & Missing CUDA.** Host lacks NVIDIA GPU/drivers; local CUDA torch or C-extensions will fail to install or compile.
    - *Mitigation:* Keep local `pyproject.toml` lightweight (pure-Python, Pydantic, Click/Typer, OpenCV, Rich). Designate all heavy CUDA/ManiSkill tasks for Modal containers.
    - *Tripwire:* Any build failure or stall during `uv pip install` attempting to compile C++ or CUDA extensions locally.
    - *Fallback:* Isolate GPU dependencies into an optional extra `[project.optional-dependencies] gpu` and run them strictly in Modal containers.
  - **Risk 3: Unmonitored API Quota Consumption.** Uncached requests during test iteration drain the $150 Meta API credit pool.
    - *Mitigation:* Wrap all API calls in `cache.py` hash-based persistent disk cache before running smoke tests.
    - *Tripwire:* Uncached requests to `api.meta.ai` detected in test scripts.
    - *Fallback:* Hard local rate-limiting and mock mode enforced in test harness.

- **Improvement proposals:**
  - `IP-P01-D3-1`: **Mock/Dry-Run Support in Smoke Suite (ST1–ST13).**
    - *Change:* Mandate `--mock` and auto-mock fallback on missing env vars in all ST1–ST13 scripts, producing `status: pending_key` JSON outputs.
    - *Evidence:* Zero sponsor keys currently exist in the environment; blocking the gate on missing keys halts P01.
    - *Judge impact:* +0 direct; prevents workflow stall and ensures reliable reproduction in keyless environments.
    - *Cost:* 0.5 hours. Risk: Low. Invariant impact: None.
  - `IP-P01-D3-2`: **Windows Host Isolation & Modal GPU Partitioning.**
    - *Change:* Exclude heavy CUDA PyTorch from local core dependencies in `pyproject.toml`; declare all GPU-bound tasks as Modal-only.
    - *Evidence:* Local host has no GPU (`nvidia-smi` missing); local build of ManiSkill/CUDA wheels on Windows is error-prone.
    - *Judge impact:* Guarantees clean cross-platform installation for judges.
    - *Cost:* 0.25 hours. Risk: Low. Invariant impact: None.

- **Confidence:** **85/100.** High certainty in local tools (Python 3.12 via `uv`, `ffmpeg`, `opencode`); primary risk is external credential latency, which is neutralized by our mock-fallback architecture.

- **Pre-mortem:**
  *"It is the morning of judging and P01's output broke the demo."*
  1. *Contract Incompatibility Drift:* Contracts frozen in P01 lacked necessary fields for multi-step reasoning or uncertainty boundaries, forcing uncoordinated breaking changes in P04/P05.
  2. *Keyless Crash on Evaluation:* A judge running `Kodiac doctor` on a clean laptop encounters an unhandled traceback instead of a clean, structured diagnostic report.
  3. *Unbudgeted Modal Spend:* A background test container spun up during setup was left running without a scaledown window, burning the $100 compute credit prematurely.

- **Schedule math:**
  - Total time remaining to internal submission: **175.5 hours**.
  - P01 allocated schedule budget: ~5.0 hours maximum realistic wall-clock time (1.5 h Council/Ruling, 2.5 h Implementation, 1.0 h Gate).
  - Buffer margin: 170.5 hours preserved for P02–P10.

- **Kill criteria:**
  1. If any task attempts to compile local CUDA C-extensions on Windows and exceeds 30 minutes, KILL the local task immediately and redirect to Modal.
  2. If Phase P01 exit gate is blocked by missing human credentials for >1 hour, KILL the live key requirement for P01 gate and validate via mock/dry-run artifacts.
  3. If un-cached API spend exceeds $2.00 during test development, KILL the test run and enforce the `cache.py` wrapper.

## R2: Stress tests
### D1 → D2, D3
[2026-10-28T09:35:00Z · D1]

#### 1. Interface Collision & Invariant Scan (attacking D2 & D3 contract models)
- **Attack (Tools: Interface Collision, Invariant Scan I1, I4, I6):** Both D2 and D3 propose ad-hoc, simplified data contracts (`BlameReport`, `PredicateResult`, `DiffReport` in D2; `Measurement`, `PhysicalCause`, `BlameResult` in D3) rather than the canonical contracts specified in `ARCHITECTURE.md §4`. In particular, D2 drops `FactTable` (which stores the onset frame, component metrics with ±σ, and code location required by I4), and D3 drops `Expr` recursive AST, `Track`, `Event`, and `ClipRef`.
- **Failure Scenario:** If IMPL-1 builds D2's or D3's ad-hoc models, contracts will diverge from `ARCHITECTURE.md §4`. When Phase P04 (Measurement Engine) and Phase P06 (`blame` + `diff`) start, the engine will fail to deserialize event diffs, step chains, or code locations, causing breaking contract rewrites and invalidating `contracts-v1`.
- **Proposed Fix:** Strict convergence on `src/Kodiac_robotics/contracts/core.py` as defined in `ARCHITECTURE.md §4` verbatim. Any field extensions must be added to the canonical models (`Blame`, `FactTable`, `StepResult`, `RunResult`), not substituted with new uncoordinated classes.

#### 2. Live-Demo Fragility & Invariant I3 Compliance (attacking D2's Verdict & ReasonCode)
- **Attack (Tools: Live-Demo Fragility, Invariant Scan I3, Honesty Audit):** D2 sets `Verdict.CANT_TELL = "CAN'T TELL"` and uses prefixed error codes like `E001_OCCLUSION`. `IDEA.md §0` (Invariant I3) explicitly dictates: *"The verdict enum has exactly 3 values. User text says CAN'T TELL (never 'UNKNOWN'). JSON CANT_TELL, exit code 2. Every CAN'T TELL carries a reason code."* Furthermore, `ARCHITECTURE.md §4` defines `ReasonCode` with lowercase values: `not_visible`, `occluded`, `below_noise_floor`, `view_blocked`, `appearance_unresolved`, `depth_ambiguous`.
- **Failure Scenario:** Setting enum value to `"CAN'T TELL"` causes raw JSON serialization to emit `"CAN'T TELL"` instead of `"CANT_TELL"`, breaking downstream schema validation, CLI exit parsing, and web UI integration. In addition, arbitrary error codes (`E001_OCCLUSION`) fail compatibility checks against `ARCHITECTURE.md`.
- **Proposed Fix:** Define `Verdict(str, Enum)` with values `PASS = "PASS"`, `FAIL = "FAIL"`, `CANT_TELL = "CANT_TELL"`. Implement a `.display_text` property or `__str__` returning `"CAN'T TELL"` for CLI/human presentation. Retain the exact 6 lowercase `ReasonCode` enum members from `ARCHITECTURE.md §4`.

#### 3. Schedule Math & DAG Serialization Bottleneck (attacking D2 & D3 task execution)
- **Attack (Tools: Schedule Math, Simplest Alternative):** D2 states T02 "Depends on T01", and D3 states "T1 runs first... T2 and T3 execute in parallel once contracts/core.py is staged." This creates a sequential dependency that forces IMPL-2 and IMPL-3 to idle for 1.5–2 hours while IMPL-1 finishes scaffolding, contracts, caching, and CI.
- **Failure Scenario:** With a 5-hour phase target, stalling 2 out of 3 implementers reduces DAG throughput by 50%, burning unnecessary wall-clock time and risking deadline slip.
- **Proposed Fix:** Decouple T01, T02, and T03 for full Day-1 parallelism. `Kodiac doctor` (IMPL-2) only checks system Python, ffmpeg on PATH, and env-var presence; it does NOT need `contracts/core.py` to be completed first. Smoke tests ST1–ST13 (IMPL-2) and Modal/Doc skeletons (IMPL-3) can be scaffolded immediately using standard library and requests. Integration occurs during S15.

#### 4. Pre-Mortem & Cost/Quota Check (attacking D3's smoke test specification)
- **Attack (Tools: Pre-Mortem, Cost/Quota Check):** D3 emphasizes `--mock` fallbacks for missing keys but omits strict requirements on latency measurement and client-side window cutting for live smoke tests ST2/ST3.
- **Failure Scenario:** When live keys are supplied, developers run un-windowed 300-frame video clips through the hosted SAM API, draining the $150 credit pool ($0.20 / 1k frames) and exceeding the <12s p95 latency budget without triggering any alerts until P03.
- **Proposed Fix:** In `scripts/smoke/st02_models.py` and `st03_models.py`, mandate that the test harness: (1) enforces client-side windowing (exactly 6-frame pack or 50-frame clip) before transmission, (2) records request latency in `artifacts/p01/smoke/stNN.json`, and (3) triggers a hard tripwire warning if 50-frame hosted SAM latency exceeds 5.0 seconds.
### D2 → D1, D3
[2026-10-28T09:36:00Z · D2]

#### 1. Interface Collision & Invariant Scan (attacking D3's ad-hoc contract models)
- **Attack (Tools: Interface Collision, Invariant Scan I4, I6):** D3 proposes ad-hoc, untyped contract models (`Measurement(metric, value, unit, sigma)`, `PhysicalCause(predicate: str, measured_diff)`, `BlameResult(verdict, onset_frame, physical_cause, claim)`). This introduces severe interface collision against `ARCHITECTURE.md §4` and dilutes Concept Invariants I4 and I6. Invariant I4 demands exact onset frame `t*` with measured physical cause (numbers with ±σ), and I6 restricts the vocabulary to exactly 6 predicates. Allowing unvalidated `predicate: str` allows arbitrary hallucinated predicates into the engine.
- **Failure Scenario:** Downstream phases (P04 Measurement Engine, P06 Blame & Diff) will inherit loosely typed data models that fail schema export and cannot interface with the `.green` AST, breaking contract guarantees and invalidating `contracts-v1`.
- **Proposed Fix:** Reject D3's ad-hoc models in favor of canonical `ARCHITECTURE.md §4` definitions: `Verdict(str, Enum)` with values `PASS`, `FAIL`, `CANT_TELL`; exact `ReasonCode` enum members; `FactTable`; and `Blame`. D1's call for strict `ARCHITECTURE.md §4` fidelity is correct and must be the converged decision.

#### 2. Live-Demo Fragility & Judge Simulation (attacking D1's `Kodiac doctor` UX)
- **Attack (Tools: Live-Demo Fragility, Judge Simulation J3 DevRel / J4 Product):** D1 states `Kodiac doctor` must "exit 0 when core offline development environment is valid", but leaves the fresh-clone developer UX completely unspecified. If J3 DevRel clones the repo, installs it via `pip install Kodiac-robotics`, and runs `Kodiac doctor` without having `.env` set up, an unhandled traceback or ambiguous exit will instantly cost us 2 points on Demo (HACKATHON.md §9.2). Conversely, exiting 0 without clean visual segmentation leaves judges confused about what works offline vs. online.
- **Failure Scenario:** A judge evaluating the submission runs `Kodiac doctor`, sees red errors or unmasked credential warnings, assumes the package is broken on Windows/Mac, and docks our Demo score to ≤5.
- **Proposed Fix:** Adopt `IP-P01-D2-2`. Mandate a Rich-styled two-table layout: Table 1 ("Core Engine - Offline", checking Python >=3.12, ffmpeg, cache directory, exit 0) and Table 2 ("Cloud Services & Sponsors - Online", checking presence-only of `MODEL_API_KEY`, Modal, etc., with clean instructions to run `--mock` or provide keys). Exit 0 whenever Core Engine passes.

#### 3. Honesty Audit & Pre-Mortem (attacking D1 & D3 on synthetic smoke test artifacts)
- **Attack (Tools: Honesty Audit Law 1, Pre-Mortem):** D3 proposes `IP-P01-D3-1` (Mock/Dry-Run Support in Smoke Suite) and D1 proposes fixture fallbacks. While necessary to prevent blocking the gate, neither D1 nor D3 establishes strict boundaries against fabricated benchmark numbers. If smoke scripts run offline and output `artifacts/p01/smoke/stNN.json` with synthetic latency figures (e.g. dummy 850 ms) that get logged into `ADR-0003 · stack facts`, this directly violates Law 1 ("Never fake anything") and triggers an instant disqualifying kill-shot (HACKATHON.md §9.7: "Any unlabeled mock or cached output").
- **Failure Scenario:** A Meta judge or reviewer inspecting `ADR-0003` discovers that the reported SAM 3.1 latency was generated from a local dummy OpenCV loop rather than `api.meta.ai`. Credibility is permanently destroyed.
- **Proposed Fix:** Every smoke test artifact generated without verified network credentials must explicitly set `is_fixture: true`, `live_verified: false`, `latency_ms: null`, and `status: "PENDING_KEY"`. Measured latency numbers are forbidden unless verified against live API responses. `GATE.md` must honestly disclose all deferred live verifications.

#### 4. Judge Simulation & Public Surface Polish (attacking D1 & D3 on repository hygiene)
- **Attack (Tools: Judge Simulation J3, Simplest Alternative):** Neither D1 nor D3 noted in R0 recon that the repo currently tracks duplicate specification documents inside `Project Spec/` (`ARCHITECTURE.md`, `DESIGN.md`, `HACKATHON.md`, etc.). Furthermore, an untracked root `DESIGN.md` exists. Leaving raw draft duplicates in git index degrades the repository's professional open-source appearance when judges review the code.
- **Failure Scenario:** Judges opening our public GitHub repository on Nov 5 see cluttered, redundant root directories and question our software craft.
- **Proposed Fix:** Adopt `IP-P01-D2-1`. ORCH must explicitly run `git rm -r --cached "Project Spec/"`, remove the directory, and ensure the repo surface strictly reflects professional OSS standards (`README.md`, `pyproject.toml`, `src/`, `tests/`, `docs/`, `LICENSE`, `ATTRIBUTIONS.md`).

#### 5. Schedule Math & Complexity Trap on Recursive AST vs. P02 Launch (attacking D1)
- **Attack (Tools: Schedule Math, Simplest Alternative):** D1 plans full recursive AST implementation (`Expr`, `Atom`, `GreenTest`) in S05, but notes risk of Pydantic recursion errors during JSON Schema export. If IMPL-1 gets bogged down debugging recursive validators for 3+ hours, P01 overruns its schedule. Crucially, this delays P02, which must launch the background simulation pool generation on Modal immediately to protect the headline retraining experiment (Invariant I8).
- **Failure Scenario:** Phase P01 runs 4 hours late, delaying the pre-registration tag `prereg-v0` and background pool generation, which consumes critical GPU compute buffer before the Nov 2 go/no-go deadline.
- **Proposed Fix:** Timebox recursive schema export to 30 minutes in S05. If Pydantic v2 recursion halts schema export, immediately fall back to the flat `CompileDraft` AST representation documented in `TOOLS_AND_REQUIREMENTS.md §11 ST4b`. Prioritize freezing data interchange models (`Verdict`, `FactTable`, `Blame`, `RunResult`) so downstream work proceeds without friction.
### D3 → D1, D2
[2026-10-28T09:34:00Z · D3]

#### 1. Interface Collision & Contract Invariant Attack (D2 vs. ARCHITECTURE.md §4 & D1)
- **Tool:** *Interface collision / Invariant scan*
- **Failure Scenario:** D2 proposes an ad-hoc set of simplified contract models (`BlameReport`, `DiffReport`, `PredicateResult`, and a stripped-down `RunResult`) that completely contradict the canonical specification in `ARCHITECTURE.md §4` (which defines `Blame`, `FactTable`, `Component`, `StepResult`, and `RunResult` containing `run_id`, `test_sha256`, `exit_code`, `events`, `timings_ms`, `nonce`). If implementers build D2's ad-hoc models, every downstream phase (P02 sim harness, P04 `Kodiac run`, P06 `blame`/`diff`, P07 Muse Code gate) will fail at the integration boundary, requiring a catastrophic contract rewrite mid-hackathon.
- **Proposed Consensus Fix:** Formally **REJECT** D2's simplified models. Adopt D1's strict implementation of `ARCHITECTURE.md §4` contracts in `src/Kodiac_robotics/contracts/core.py`. Tagging `contracts-v1` must only occur against the true canonical schemas.

#### 2. Schedule Math Attack on Credential Deadlock (D1's 12-Hour Tripwire)
- **Tool:** *Schedule math / Pre-mortem*
- **Failure Scenario:** D1 sets a tripwire: *"If keys remain unavailable after 12 hours, lock stack facts via ADR-0003..."*. Our entire realistic wall-clock budget for Phase P01 is 5.0 hours (schedule window is 13 h). Waiting 12 hours for human keys burns 92% of P01's window, idles implementers, and delays Phase P02 dispatch by half a day.
- **Proposed Consensus Fix:** Slash the credential timeout from 12 hours to **1.0 hour**. If sponsor keys (`MODEL_API_KEY`, `MODAL_TOKEN_ID`) are absent 1 hour post-dispatch, ST1–ST13 must automatically fall back to `--mock` / fixture execution, emit structured JSON artifacts with `status="pending_key"`, record stack facts in ADR-0003 as `PENDING_HUMAN_CREDENTIALS`, and exit P01 gate cleanly. Live API confirmation shifts to P02 S00 without blocking P01.

#### 3. Task DAG Execution Collision & Packaging Race (D1 & D2 DAGs)
- **Tool:** *Interface collision / Reversibility*
- **Failure Scenario:** Both D1 and D2 present task DAGs where T01 (contracts, pyproject.toml, packaging), T02 (doctor CLI, smoke tests), and T03 (SDM scripts, modal, docs) are dispatched concurrently from ORCH. But T02 (`cli.py`, `scripts/smoke/`) and T03 (`scripts/sdm/`) import `Kodiac_robotics.contracts` and depend on `uv sync` completing `pyproject.toml`. If T02 and T03 execute concurrently with T01, they will crash with `ModuleNotFoundError: No module named 'Kodiac_robotics'` or encounter broken partial imports while T01 is in mid-write.
- **Proposed Consensus Fix:** Enforce a strict **two-stage gated DAG**:
  - **Stage 1 (Sequential):** IMPL-1 executes T01 (S00–S07: `pyproject.toml`, `contracts/core.py`, `config.py`, `cache.py`, CI). Merged and verified via `uv sync`.
  - **Stage 2 (Parallel):** Once contracts and package are installed, launch IMPL-2 (T02: `Kodiac doctor` + ST1–ST13) and IMPL-3 (T03: SDM channel + Modal + doc skeletons) in parallel.

#### 4. Scope Creep & Simplest Alternative Test (D2's B-Roll Table vs. D1's AST recursion)
- **Tool:** *Simplest-alternative test / Honesty audit*
- **Failure Scenario:** D2 proposes IP-P01-D2-2 (spending 0.5 h on custom Rich table styling for video B-roll). Phase P01 is about establishing zero-stub infrastructure certainty; polishing video B-roll in P01 before CLI core commands even run is premature optimization. Concurrently, D1's recursion modeling on `Expr.model_rebuild()` risks schema export failures.
- **Proposed Consensus Fix:** Strip IP-P01-D2-2 down to standard clean Rich table formatting without bespoke video decorations (video polish belongs in Phase P10). For D1's contracts, mandate flat atom evaluation with immediate `model_rebuild()` validation in S05 unit tests to prevent recursion runtime failures.

#### 5. Cost & Quota Guard on Smoke Execution (Modal L4 & Meta SAM 3.1)
- **Tool:** *Cost and quota check / Live-demo fragility*
- **Failure Scenario:** Running ST1–ST13 live without hard parameter constraints could drain credits: SAM 3.1 charges $0.20/1k frames, and a live Modal GPU container left unscaled burns $0.80–$2.10/hour. If a smoke test runs against an unclipped video or leaves a Modal L4 container warm, credits are wasted before Phase P03 perception work starts.
- **Proposed Consensus Fix:** Impose hard guards in smoke test definitions:
  - Video clips in `tests/fixtures/` strictly capped at ≤50 frames (the minimum billing threshold).
  - Modal app definitions (`modal/hello_l4.py`) must hardcode `scaledown_window=0` and be explicitly deleted immediately after ST8 completes.
  - Wrap all API network calls through `cache.py` with sha256 input hashing enabled by default.

## R3: Converged plan
[2026-10-28T09:38:00Z · D1 (Single Writer)]

### 1. Ordered Steps
- **Stage 0: Repository Compliance & Scrub (S00–S03 · ORCH):**
  - **S00:** Execute public-surface scrub; run `git rm -r --cached "Project Spec/"` and clean root `DESIGN.md` duplicates (adopting IP-P01-D2-1). Verify lineage terms return zero hits.
  - **S01:** Initialize git repository, configure `.gitignore` (ignoring `.env`, `.cache/`, large media), add Apache-2.0 `LICENSE`, `BUILD_LOG.md` (recording build window opening), `ATTRIBUTIONS.md`, and clean `README.md`. Verify commit timestamp ≥ 2026-10-26.
  - **S02:** Confirm agent scaffolding (`STATE.md`, `DECISIONS.md`, `BACKLOG.md`, `LESSONS.md`, `prompts/`, phase artifacts).
  - **S03:** Record `ADR-0001` (Antigravity orchestrator, Gemini 3.8 Flash subagents via `Model: 'inherit'`, OpenCode SDM channel).

- **Stage 1: Core Contracts, Scaffolding & Tooling (S04–S07 · IMPL-1):**
  - **S04:** Initialize `pyproject.toml` with `uv` (`Kodiac-robotics`, Python `>=3.12`), extras `[sim, proof, app, viz, mcp, lerobot, dev]`. Enforce pure-Python, torch-free local core for instant judge installation (IP-P01-D3-2).
  - **S05:** Implement `src/Kodiac_robotics/contracts/core.py` strictly matching `ARCHITECTURE.md §4` verbatim (Pydantic v2). Implement `contracts/fixtures.py` providing canonical synthetic test instances (IP-P01-D1-1). Add field validation for `timings_ms` and 16-hex `nonce` on `RunResult` (IP-P01-D1-2). Implement JSON Schema export in `contracts/schema_export.py` to `docs/schemas/`. Add roundtrip unit tests in `tests/unit/contracts/test_core.py`. Tag `contracts-v1`.
  - **S06:** Implement `src/Kodiac_robotics/config.py` (Pydantic Settings from `.env`, masked secrets) and `src/Kodiac_robotics/cache.py` (atomic SHA-256 content-hashed disk cache).
  - **S07:** Configure `ruff` (lint + format), `pytest` (markers: `slow`, `live`, `gpu`), and `.github/workflows/ci.yml` (strictly zero-secret execution).

- **Stage 2: Parallel Verification & Diagnostic Tooling (S08–S14 · IMPL-2 ∥ IMPL-3):**
  - **S08 (IMPL-2):** Implement `Kodiac doctor` with a clean two-table Rich layout (IP-P01-D2-2). Table 1 ("Core Engine - Offline") validates Python ≥3.12, ffmpeg, cache directory, and core imports (exiting 0 if healthy). Table 2 ("Cloud Services & Sponsors - Online") validates presence-only of keys (`MODEL_API_KEY`, `MODAL_TOKEN_ID`, `HF_TOKEN`, `BASETEN_API_KEY`) and GPU availability without crashing or leaking secrets.
  - **S09–S10 (IMPL-2):** Implement smoke test suite ST1–ST13 in `scripts/smoke/st01_models.py` through `st13_sdm.py`. Implement honest dual-mode execution (IP-P01-D3-1): live API calls when credentials exist; mock fixture execution with `is_fixture: true, live_verified: false, latency_ms: null, status: "PENDING_KEY"` when keys are absent. Enforce ≤50-frame clip windowing on ST2/ST3 and record results into `artifacts/p01/smoke/stNN.json` and `ADR-0003`.
  - **S11 (IMPL-3):** Deploy SDM test harness using `opencode run -m deepseek/deepseek-chat` (Option A) and Antigravity Gemini 4 Argon fallback (Option B). Record `ADR-0002`.
  - **S12 (IMPL-3):** Scaffold `modal/hello_cpu.py` and `modal/hello_l4.py` with hardcoded `scaledown_window=0`. Delete hello apps immediately after ST8.
  - **S13 (ORCH):** Present `HUMAN_TODO.md` checklist to human (Meta/Modal credits, PyPI reservation, `facebook/sam3.1` access, I16 confirmation).
  - **S14 (IMPL-3):** Seed `docs/features.yaml` (F01–F60 matrix), `docs/VIDEO_NUMBERS.md`, `tests/fixtures/README.md`, and `experiments/README.md`.

- **Stage 3: Integration, Gate Verification & Tagging (S15 · ORCH):**
  - Merge task branches, verify green CI locally (`uv run ruff check .` and `uv run pytest tests/ -q`), verify `Kodiac doctor` exits 0, confirm ST1–ST13 artifacts exist, generate `GATE.md`, push, and tag `p01-done`.

---

### 2. Task DAG (Two-Stage Gated Execution)

```
[Stage 0: ORCH] S00, S01, S02, S03
       │
       ▼
[Stage 1: IMPL-1] T01-core-contracts-and-tooling (S04, S05, S06, S07)
       │  owns_paths:
       │    - pyproject.toml
       │    - src/Kodiac_robotics/contracts/
       │    - src/Kodiac_robotics/config.py
       │    - src/Kodiac_robotics/cache.py
       │    - tests/unit/contracts/
       │    - docs/schemas/
       │    - .github/workflows/ci.yml
       │
       ├─── uv sync & contracts-v1 staged ───┐
       │                                      │
       ▼                                      ▼
[Stage 2A: IMPL-2] T02-doctor-and-smoke     [Stage 2B: IMPL-3] T03-modal-sdm-and-docs
(S08, S09, S10)                            (S11, S12, S14)
  owns_paths:                                owns_paths:
    - src/Kodiac_robotics/cli/                 - modal/
    - scripts/smoke/                           - scripts/sdm/
    - artifacts/p01/smoke/                     - docs/features.yaml
    - tests/unit/cli/                          - docs/VIDEO_NUMBERS.md
                                               - docs/DEMO_FILMING_GUIDE.md
                                               - tests/fixtures/README.md
                                               - experiments/README.md
       │                                      │
       └──────────────────┬───────────────────┘
                          │
                          ▼
[Stage 3: ORCH] S13 (HUMAN_TODO), S15 (Integration, Gate & Tag)
  owns_paths:
    - .agents/STATE.md
    - .agents/DECISIONS.md
    - HUMAN_TODO.md
    - .agents/phases/P01-setup/GATE.md
```

---

### 3. Frozen Interface Contracts
Strictly conforming to `ARCHITECTURE.md §4` in `src/Kodiac_robotics/contracts/core.py`:
- **Enums:**
  - `Tri(str, Enum)`: `T = "T"`, `F = "F"`, `U = "U"`
  - `Verdict(str, Enum)`: `PASS = "PASS"`, `FAIL = "FAIL"`, `CANT_TELL = "CANT_TELL"` (display string `"CAN'T TELL"`)
  - `ReasonCode(str, Enum)`: `NOT_VISIBLE = "not_visible"`, `OCCLUDED = "occluded"`, `BELOW_NOISE_FLOOR = "below_noise_floor"`, `VIEW_BLOCKED = "view_blocked"`, `APPEARANCE_UNRESOLVED = "appearance_unresolved"`, `DEPTH_AMBIGUOUS = "depth_ambiguous"`
- **DSL & Specification (.green):**
  - `Provenance(quote, t_start, t_end, source)`
  - `ObjectDecl(name, role, prompt, aliases, size_cm, height_cm)`
  - `Param(name, op, value)`
  - `Atom(kind, name, args, params, looks_pos, looks_neg, manual_text)`
  - `Expr(op, children, atom)` (with `Expr.model_rebuild()`)
  - `Step(index, name, expr, provenance, extra_provenance)`
  - `GreenTest(version, name, objects, steps, params, header_comment)`
  - `GreenLock(test_sha256, transcript, object_baselines, demo_events, geometry_tier, model_ids, created_at)`
- **Video & Perception:**
  - `ClipRef(uri, source_kind, dataset, episode_index, camera)`
  - `Clip(ref, path_h264, fps, n_frames, width, height, sha256)`
  - `ObjMask(obj, frame, score, bbox_xyxy, rle, area_px)`
  - `Track(obj, frames, backend, direction, trace_id)`
  - Protocols: `Segmenter`, `VLMJudge`, `ASR`, `Memory`, `ScaleModel`
- **Measurement & Evaluation:**
  - `Component(name, value, threshold, margin, sigma, unit, tri, reason)`
  - `PredFrame(frame, atom_key, tri, components, trace_id)`
  - `Event(step, step_name, kind, predicate, args, t_s, frame, fps, measurements, source, verdict)`
  - `StepResult(index, name, verdict, t_s, frame, decisive, reasons, evidence)`
- **Blame & Attribution:**
  - `CodeLocation(file, line, code, span_id)`
  - `Hint(variable, delta, unit, move, basis)`
  - `FactTable(t_star_s, frame, fps, sigma_frames, step_index, step_name, literal, transition, facts, dataset_index, action_chunk, code_location, evidence, trace_ids)`
  - `Blame(facts, summary, summary_source, hint, warnings)`
- **Execution & Storage:**
  - `RunResult(run_id, test_name, test_sha256, config_sha256, clip, verdict, exit_code, steps, reasons, blame, diff_text, events, manual_checks, timings_ms, backends, badges, nonce, card_path, trace_path, created_at)`
  - `VerifyRequest`, `GateState`, `VerdictRow`, `JudgeLabel`

---

### 4. Tripwires & Kill Criteria
1. **Human Credential Tripwire (1.0 Hour SLA):** If sponsor credentials (`MODEL_API_KEY`, `MODAL_TOKEN_ID`) are absent 1.0 hour post-dispatch, switch ST1–ST13 to `--mock` fixture generation (`status: "PENDING_KEY"`, `latency_ms: null`), record `PENDING_HUMAN_CREDENTIALS` in `ADR-0003`, and pass the gate. Do not idle implementers.
2. **Hosted SAM Latency Tripwire:** If 50-frame hosted SAM 3.1 latency exceeds 5.0 seconds in ST2/ST3, the P03 council must immediately trigger evaluation of Modal-hosted open weights for the fast path.
3. **AST Recursion Timebox:** Timebox recursive `Expr` schema export to 30 minutes in S05. If Pydantic v2 recursion halts schema export, immediately fall back to flat `CompileDraft` AST.
4. **Modal Compute Kill Criterion:** All Modal testing must hardcode `scaledown_window=0`. Hello containers must be deleted immediately after ST8. Un-cached API spend during test development exceeding $2.00 triggers immediate test abort.
5. **Windows CUDA Isolation:** Pure-Python local core. Any local task attempting to build or compile CUDA extensions on Windows exceeding 15 minutes is killed immediately; execution shifts to Modal.

---

### 5. Improvement Proposals (IPs) Table

| IP | Proposal Summary | D1 | D2 | D3 | Escalate to SDM? |
|---|---|:---:|:---:|:---:|:---:|
| **IP-P01-D1-1** | Contract Synthetic Fixture Generator (`contracts/fixtures.py`) | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |
| **IP-P01-D1-2** | Strict Nonce (16-hex) & Timings Validation on `RunResult` | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |
| **IP-P01-D2-1** | Public-Surface Scrub: Untrack and remove `Project Spec/` duplicate | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |
| **IP-P01-D2-2** | Two-Table Rich `Kodiac doctor` UX (offline core vs. online sponsors) | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |
| **IP-P01-D3-1** | Honest Dual-Mode Smoke Suite (`is_fixture: true`, `latency_ms: null`) | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |
| **IP-P01-D3-2** | Windows Host Isolation & Modal GPU Partitioning (pure-Python core) | **APPROVE** | **APPROVE** | **APPROVE** | No (`COUNCIL-LOCAL`) |

*All 6 proposals are approved unanimously by the Council and represent local implementation discipline; per `AGENTS.md §5.4`, Phase P01 requires formal SDM ratification per `IMPLEMENTATION_PLAN.md §0`.*

---

### 6. Open Disagreements
None. D1, D2, and D3 reached complete consensus on the two-stage DAG, canonical contracts, honest mock smoke testing, and doctor UX.

---

### R3 Vote: D2 Judge Advocate
[2026-10-28T09:40:00Z · D2]

#### Votes on Improvement Proposals:
1. **IP-P01-D1-1 (Contract Synthetic Fixtures):** `APPROVE` · Standardizes test doubles across phases, eliminating mock drift and protecting Law 1.
2. **IP-P01-D1-2 (Strict Nonce & Timings on RunResult):** `APPROVE` · Enforces Invariant I15 (traceability and honesty by construction) at the contract boundary.
3. **IP-P01-D2-1 (Public-Surface Scrub of `Project Spec/`):** `APPROVE` · Ensures pristine, professional open-source presentation for hackathon judges (J3/J4).
4. **IP-P01-D2-2 (Two-Table Rich `Kodiac doctor` UX):** `APPROVE` · Guarantees exit 0 and clear onboarding on fresh clones, eliminating fatal demo deductions.
5. **IP-P01-D3-1 (Honest Dual-Mode Smoke Suite):** `APPROVE` · Prevents credential deadlock while strictly prohibiting fabricated latency benchmarks in `ADR-0003`.
6. **IP-P01-D3-2 (Windows Isolation & Pure-Python Core):** `APPROVE` · Ensures fast, effortless `pip install Kodiac-robotics` on any judge's machine without CUDA wheel compile issues.

#### Sign-off & Objections:
- **Sign-off:** Full unconditional sign-off. D1's converged plan comprehensively incorporates all D2 stress-test requirements: strict canonical contracts (`ARCHITECTURE.md §4`), two-table Rich doctor output, anti-fabrication smoke testing safeguards, S00 public surface scrub, and two-stage DAG execution with 1.0-hour credential SLA.
- **Remaining Objections:** None.
- **Final Confidence Score:** **98/100.** The plan is robust, strictly compliant with hackathon rubrics, and engineered for high-velocity execution.

---

### R3 Vote: D3 Red Team
[2026-10-28T09:40:00Z · D3]

- **Votes on Improvement Proposals:**
  - `IP-P01-D1-1` (Contract Synthetic Fixtures): **APPROVE** · Essential for decoupling downstream tests from network and preventing mock drift.
  - `IP-P01-D1-2` (Strict Nonce & Timings on `RunResult`): **APPROVE** · Enforces Invariant I15 auditability by construction without adding runtime overhead.
  - `IP-P01-D2-1` (Public-Surface Scrub `Project Spec/`): **APPROVE** · Eliminates duplicate tracking and guarantees clean repository hygiene.
  - `IP-P01-D2-2` (Two-Table Rich `Kodiac doctor` UX): **APPROVE** · Decouples offline core readiness from pending external sponsor credentials.
  - `IP-P01-D3-1` (Honest Dual-Mode Smoke Suite): **APPROVE** · Neutralizes credential deadlock and enforces strict honesty (`is_fixture: true`).
  - `IP-P01-D3-2` (Windows Host Isolation & Modal GPU Partitioning): **APPROVE** · Protects local development from Windows CUDA build failures.

- **Objections & Sign-Off:**
  No remaining objections. D1 fully incorporated all Red Team stress-test requirements: the two-stage sequential-then-parallel DAG prevents packaging race conditions, the 1.0-hour credential tripwire prevents pipeline stalls, and canonical contracts match `ARCHITECTURE.md §4` verbatim.

- **Final Confidence Score:** **95/100** · High execution certainty with zero identified interface or schedule traps. Ready for SDM packet generation.
