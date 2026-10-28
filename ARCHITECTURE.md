# ARCHITECTURE.md: Kodiac System Architecture, Workflows & Final Output Design

> Built from `IDEA.md` (features F01–F60, invariants I1–I17) and `TOOLS_AND_REQUIREMENTS.md` (approved stack).
> Feature IDs `F##`, invariant IDs `I##`, and key-decision IDs `KD-##` are shared across all docs. A change to anything here goes
> through the council (`AGENTS.md` §5) and is logged as an ADR.

---

## 0. Architecture at a Glance

```
                         ┌──────────────────────────────── Kodiac_robotics (Python 3.12 package, CLI `Kodiac`) ─────────────────────────────────┐
  INPUTS                 │                                                                                                                          │   OUTPUTS
  ──────                 │  ┌────────────┐   ┌──────────────┐   ┌──────────────────────┐   ┌─────────────┐   ┌──────────────┐   ┌──────────────┐  │   ───────
  webcam demo + voice ──▶│  │ io         │──▶│ segment      │──▶│ geometry + predicates │──▶│ engine      │──▶│ blame / diff │──▶│ render       │  │──▶ Verdict Card PNG
  LeRobot repo/episode ─▶│  │ ingest,    │   │ Segmenter    │   │ scale tiers, 6 preds, │   │ step chain, │   │ t*, facts,   │   │ CLI text,    │  │──▶ blame line + diff
  local clip / upload ──▶│  │ transcode, │   │ (SAM 3.1:    │   │ smoothing, σ, gates   │   │ 3-valued    │   │ summary,     │   │ evidence,    │  │──▶ trace.jsonl + .rrd
  sim run (ManiSkill) ──▶│  │ windows    │   │ api|modal|   │   └──────────────────────┘   │ verdict,    │   │ hint, code   │   │ JSON, HTML   │  │──▶ exit code 0/1/2/3
                         │  └────────────┘   │ fixture)     │            ▲                  │ bisect      │   │ location     │   └──────────────┘  │──▶ verdicts.parquet
                         │        ▲          └──────────────┘            │                  │ scheduler   │   └──────────────┘                     │
                         │  ┌─────┴──────┐                     ┌─────────┴─────────┐        └─────────────┘          ▲                            │
                         │  │ compiler   │ .green + .lock ────▶│ judge (looks())   │◀── crops ─────────────────────────┘                            │
                         │  │ Voice→Spark│                     │ Spark 2-way →     │                                                              │
                         │  │ →DSL, lint,│                     │ Wonder escalate   │   loop/: MCP verify · gate · hooks   audit/: batch · digest   │
                         │  │ SAM check, │                     │ open-weights      │   proof/: judges · pool · train · stats · chart              │
                         │  │ self-test  │                     │ switch            │   app/: Gradio+FastAPI on Modal CPU                          │
                         │  └────────────┘                     └───────────────────┘   sim/: ManiSkill harness · span logger · seeded bugs        │
                         └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
       EXTERNAL: Meta Model API (sam-3.1 · muse-spark-1.3 · muse-wonder-1.0 · muse-voice-transcribe-1.0) · Muse Code (host agent) ·
                 Modal (CPU demo + GPU batch, scale-to-zero) · Baseten/Fireworks (Muse Spark Open) · HF Hub (datasets) · GitHub (repo, CI, Pages)
```

### 0.1 Design principles (non-negotiable)
1. **Measure, don't guess** (I6). Geometry from SAM 3.1 masks decides. VLMs answer appearance questions only, on crops.
2. **Abstain honestly** (I3). Three-valued logic from per-frame tri-states up to the verdict. `CAN'T TELL` always carries a reason code.
3. **Every printed number is traceable** (I15). Each number has a `trace_id` pointing to a frame, a mask, a metric, and a model call.
4. **One interface, many backends.** `Segmenter`, `VLMJudge`, `ASR`, and `Memory` are protocols. Backends are chosen by config:
   hosted, Modal, open-weights, or fixture replay.
5. **Deterministic and cached.** Seeded RNG. Every external call is cached by content hash, so re-runs are free and identical, and CI
   runs without network.
6. **Fast path for humans, full path for batch.** The live path uses bisect plus a dense window. Batch can afford dense full-clip tracking.
7. **Honesty by construction.** Outputs carry provenance badges: `[REAL]`, `[SIM]`, `[CACHED]`, `[OPEN-WEIGHTS]`. `[REPLAY]` marks recorded real API outputs replayed offline. The shipped-status table is generated from
   `docs/features.yaml` (created in P01), not hand-written.

---

## 1. Final Output Design: What Judges Actually See

> The architecture exists to produce **seven artifacts**. Each one is designed for a judging criterion (`HACKATHON.md` §9).

### 1.1 The unifying artifact: the **Kodiac Verdict Card** (unique output)

One standardized visual is rendered everywhere: CLI (`--card`), the hosted page, the README, video beats, and the X post. Repeated
exposure builds recognition.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  ● FAIL   stack_blocks.green · episode_000123 [SIM · ManiSkill3]         7.9 s · sam-3.1 │
│ ┌──────────────────────────────────────────────┐                                         │
│ │   evidence frame @ t* (frame 114, 0:03.8)    │  step 1 grasp    ✓ PASS   0:01.4        │
│ │   red SAM outline on red_block               │  step 2 place    ✗ FAIL   0:03.8        │
│ │   green outline on green_block               │  step 3 release  · not reached         │
│ │   arrow: offset 2.6 ± 0.4 cm                 │                                         │
│ └──────────────────────────────────────────────┘  blame: gripper released red_block      │
│  timeline ▕███ grasp ███▏▕██ place ██▲✗▏▕ release ▏   0.4 s before reaching green_block │
│            0s          ▲ t* = 0:03.8          10s     (xy offset 2.6 cm, frame 114)      │
│  "pick up the red block" · "put it on the green one" · "let go"      Kodiac · SAM 3.1 + Spark │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
- **Colour tokens:** PASS `#16A34A` · FAIL `#DC2626` · CAN'T TELL `#D97706` · neutral `#334155`. The SAM outline uses the verdict colour on the blamed object.
- **The timeline strip** (the "blame strip") has one bar per step, coloured by step verdict, with a ▲ marker at t*. It is the visual metaphor for `git blame`.
- **Badges** are mandatory: data source (`REAL · <dataset>` / `SIM · ManiSkill3` / `UPLOAD`), `CACHED` if from the replay store, and the model backend.
- Rendered by `render/card.py` (Pillow + supervision), 1600×900 PNG (16:9, so it can go straight into the video or onto X).

### 1.2 Terminal outputs (exact formats; snapshot-tested)

```text
$ Kodiac test --video demo.mp4
  ✓ transcript  3 instructions  (muse-voice-transcribe-1.0, 1.1 s)
  ✓ compiled    stack_blocks.green  (muse-spark-1.3, 2.3 s)
  ✓ objects     gripper→hand ✓  red_block ✓ 0.94  green_block ✓ 0.97  (sam-3.1)
  ✓ self-test   demo PASSES its own test (min margin +2.1σ)
  ⚠ W101        "gently" → MANUAL("contact force")   (not visible to a camera)
  wrote stack_blocks.green (4 lines) + stack_blocks.green.lock

$ Kodiac run stack_blocks.green lerobot://<repo>/123 --camera exterior_1
  step 1 grasp    PASS   0:01.4   lifted 4.2 ± 0.3 cm · moves_with ✓
  step 2 place    FAIL   0:03.8   moves_with T→F (released 2.6 ± 0.4 cm from green_block)
  step 3 release  —      not reached
  FAIL  ·  exit 1  ·  7.9 s  ·  card: runs/<id>/card.png  ·  trace: runs/<id>/trace.jsonl

$ Kodiac blame runs/<id>
  blame: gripper released red_block 0.4 ± 0.07 s before reaching green_block (xy offset 2.6 ± 0.4 cm at 0:03.8, frame 114 · SIM 30 fps)
  where: t* = 0:03.800 ± 1 frame · LeRobot index 58231 · step 2 "place" · moves_with T→F
  hint : release_time +0.4 s

$ Kodiac blame runs/<sim-id>          # simulation
  blame: ... (frame 114)   code: pick_place.py:42 -> gripper.open()   hint: move gripper.open() after arm.move_to(place)

$ Kodiac run stack_blocks.green occluded.mp4
  CAN'T TELL  ·  exit 2  ·  target occluded 46% at step 2 (green_block)  ·  card: …
```
*(All numbers above are illustrative. Frame numbers assume a 30 fps SIM clip; on DROID (15 fps) 0:03.8 = frame 57. Offline output from the fixture backend is headed `[REPLAY: recorded SAM 3.1 + Muse outputs, no key needed] · run with --live to call the Meta API`.)*

**Frozen CLI surface:** `Kodiac run <test.green> (<clip-ref> | --sim <script.py> [--seed N]) [--camera K] [--mode fast|full] [--backend api|modal|fixture] [--json] [--card] [--salvage] [--local-glimmer]` · clip ref `lerobot://<org>/<name>/<episode_index>[/<camera_key>]` (needs the `[lerobot]` extra) · utilities: `gate`, `mcp`, `audit`, `doctor`, `loop`, `card`, `goal-run`. CLI code lives in `src/Kodiac_robotics/cli/` (one module per command).

### 1.3 The hosted page (wireframe)

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Kodiac: Robots can finally fail a test.                [GitHub] [How it works] [Video]│
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ [ Dataset ▾ curated LeRobot/DROID episodes ] [ Upload clip ] [ Record webcam ] [ Teach it ] │
│  episode: [123 ▾]   camera: [exterior_1 ▾]   test: [auto: compiled from task text ▾]     │
│  ☐ paint occluder (brush)                         [ ▶ GRADE ]     ⏱ 00:07.9               │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│  [ VERDICT CARD (1.1) ]                                                                    │
│  ┌ diff ──────────────────────────────┐  ┌ frames around t* ◀ ▶ ──────────────┐           │
│  │ - step 2: released on green (0.3cm)│  │  scrub frames 104…124 with outlines │           │
│  │ + step 2: released 2.6 cm left …   │  └─────────────────────────────────────┘           │
│  └────────────────────────────────────┘   [download trace.jsonl] [open in Rerun]          │
│  Badge row: REAL · DROID | sam-3.1 · muse-spark-1.3 | LIVE  (or ⚡ CACHED replay)           │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Which Meta model does what (table) · Limits we're honest about · Uploads auto-delete 24 h │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```
- **Zero login, zero keys.** Results in the cached replay store render instantly with a **⚡ CACHED** badge. The "Re-run live" button
  performs a real run with the timer.
- **Occlusion brush:** paint a rectangle on frame 0. It is applied to every frame before grading. This demonstrates `CAN'T TELL`
  without props (I10).
- **Webcam:** a ≤15 s `MediaRecorder` clip is uploaded as a file (not a stream). A covered lens gives `CAN'T TELL (view blocked)`.
- **Teach it live:** the judge records a ≤10 s demo with three spoken instructions → `Kodiac test` compiles the 4-line test on screen → records an attempt → verdict, with a timer on both steps. Compile failure → a friendly message + typed-instruction fallback (text-compile).

### 1.4 The Audit Card (opening shot) and the Proof Chart (headline)
- **Audit card:** 3 frozen episodes (verdict cards) + the line *"N episodes published as successful demonstrations checked · at least X%
  didn't do their task · hand-verified"* + the dataset names + a digest one-liner ("most failures: step 2 release, 68% [CI]").
- **Proof chart:** x = measured false-PASS rate (%, Wilson CI bars), y = downstream success (%, per-seed values + mean; episode-bootstrap CI within seed; Welch t across seeds for Δ). One labelled point per judge:
  single-pass Spark, Robometer-4B, TOPReward, Kodiac, Kodiac+salvage, Kodiac open-weights (where applicable), Oracle, Accept-all.
  A dashed dose-response curve (oracle + k% injected false PASSes). Subtitle: "Simulation · ManiSkill3 StackCube · 3 seeds · n=… eval
  episodes per seed". The title is the invariant sentence with the measured Y.

### 1.5 The Muse Code take
A single unedited screen recording: `/goal …` → Muse Code calls `Kodiac.verify` → FAIL blame shown → the agent edits `pick_place.py:42`
→ re-run → **the Stop hook refuses "done"** at least once (visible message) → PASS → `/goal` completes. Overlay label: "Simulation ·
unedited take". The N/10 batch result is shown as an end card, with a link to the transcripts.

### 1.6 README first screen (generated sections marked ⚙)
1. H1 Kodiac · H3 *Robots can finally fail a test.* · **live demo URL** · video link · `pip install Kodiac-robotics`.
2. Theme sentence (Push the Frontier, official phrasing). One-paragraph problem with citations.
3. The verdict card GIF.
4. Quickstart (60 s): `Kodiac run examples/stack_blocks.green examples/clips/fail_early_release.mp4` (works offline from fixtures).
5. ⚙ Results table (n, 95% CI) · ⚙ Shipped-status table · "Which Meta model does what" table · honest limits · build log · attributions.

### 1.7 How we reach the judges (touchpoint → criterion map)

| Touchpoint | Time a judge spends | Primary criterion | Design response |
|---|---|---|---|
| Video 0:00–0:05 | 5 s | Demo / Impact | Real "success" episode freezing at the blamed frame + red outline + audit line |
| Video 0:24–1:50 | 85 s | Meta Tooling / Tech Depth | Voice → test; SAM running backward to t*; Muse Code gate refusing "done" |
| Video 1:50–2:25 | 35 s | Impact / Tech Depth | Proof chart with n/CI, sim labelled |
| README first screen | 60 s | All | Live URL, quickstart, results, shipped table |
| Live page | 60–120 s | Demo ("holds up live") | Zero login, timer, cached + live, occlusion brush |
| Repo skim | 30–60 s | Tech Depth | Clean layout, tests, CI badge, build log, prereg |
| X post | 10 s | Most Viral bonus | Verdict card + 20 s clip |

---

## 2. Key Decisions (KD; each is an ADR seed for `.agents/DECISIONS.md`)

| KD | Decision | Rationale | Alternatives rejected | Revisit if |
|----|----------|-----------|-----------------------|-----------|
| **KD-01** | **Geometry decides; VLM only for `looks()`** | I6; credibility; no VLM latency on geometric tasks | VLM-first judging (that's the baseline we beat) | Never (invariant) |
| **KD-02** | **Kleene 3-valued logic end to end**; `Verdict = PASS\|FAIL\|CANT_TELL`; exit codes 0/1/2 (3 = error) | I3; composable abstention | Probability scores (can't abstain cleanly) | Never |
| **KD-03** | **One `Segmenter` protocol, three backends:** `api` (hosted `sam-3.1`, live + real clips), `modal` (self-hosted SAM 3.1 weights, batch/sim bulk), `fixture` (recorded outputs, CI/offline) | Latency for live, cost for bulk, determinism for CI | Single backend | Hosted latency fails the budget → Modal warm H100 only during judging hours (human cost decision) |
| **KD-04** | **The IO layer owns time and format:** native-fps time base; H.264 `yuv420p` normalisation; client-side window cutting; packing keyframes into one MP4 | SAM API limits (no AV1, no window param, 50-frame billing minimum) | Server-side windows (don't exist) | API adds window params |
| **KD-05** | **Two-stage bisect on a monotone target** (6 coarse keyframes → halving to ≤50 frames → dense backward window). Static proxies at keyframes; sparse verification for PASS steps | Speed + frame-exactness; makes "git bisect" literally true | Full-clip dense tracking on the live path | P03 measurement shows a subsampled full-clip pass is faster **and** equally correct. Then the fast path may use it to *locate* the window, but the dense backward window and the bisect story stay |
| **KD-06** | **Scale model with Tiers A/B/C**, anisotropic σ, Monte-Carlo propagation, one calibrated σ-inflation λ (fitted on sim ground truth) | All thresholds are in cm; portability across cameras; honest CAN'T TELL on bad geometry | Pixel thresholds (not portable) | Tier B fails on real data → MapAnything metric depth (Tier A′) |
| **KD-07** | **`.green` = custom Lark grammar with bound provenance + `.green.lock` sidecar.** Spark chooses structure; the demo self-test chooses numbers | I2; YAML drops comments; LLM-chosen numbers are arbitrary | YAML; LLM thresholds | Never |
| **KD-08** | **Blame sentence is fact-bound:** Spark sees only the fact table (no pixels); validator (numbers, objects, licensed verbs, ≤30 words); template fallback | I6; privacy under open-weights mode | Free-form VLM explanation | Never |
| **KD-09** | **Single OpenAI-compatible judge client;** backend = `(base_url, model)` from config: Meta API, Baseten (Muse Spark Open), Modal vLLM / llama.cpp (Glimmer) | One code path; open-weights row for free | Per-vendor SDKs | — |
| **KD-10** | **Content-hash cache for every external call** (`sha256(model, params, input bytes)`) under `Kodiac_CACHE_DIR`; seeds everywhere | Cost, determinism, offline CI, instant replays | No cache | — |
| **KD-11** | **Done-gate fails closed and re-runs the test itself.** Muse Code `Stop` hook → `Kodiac gate`. Pins live **outside the workspace** (`~/.config/Kodiac/gates/<sha256(workspace)>.json`: test sha, config sha, script path, seed). On Stop the gate **re-runs** `Kodiac run <pinned test> --sim <pinned script> --seed <pinned seed> --mode full` and decides from that run only. The gate **never exits 3**: any error → exit 2. The MCP server is declared in `.mcp.json` (env passthrough), not as a plugin MCP (cleared env) | I7; anti-cheat (agent-writable files are never trusted) | Trusting `.Kodiac/last_verdict.json` | Re-run exceeds the hook timeout → HMAC-signed RunResult (`~/.config/Kodiac/gate.key`); Stop hook doesn't gate `/goal` completion → add a PreToolUse deny on `update_goal` |
| **KD-12** | **One sim harness: ManiSkill3 `StackCube-v1`** for both the `/goal` loop and the proof, with `sim_freq=120, control_freq=30` so frames = 30 fps and an overridden `max_episode_steps`. Robot-API wrapper with span logging. Fallback: Meta cookbook MuJoCo Panda | Shared work; the oracle matches our test; 30 fps claims honest | Two sims | ManiSkill rendering unavailable → MuJoCo fallback for the loop; the proof stays on ManiSkill in a Modal GPU image |
| **KD-13** | **Policy learns from state; judges see only rendered RGB** | Isolates label quality; cheap training | Image policies (slow; confounds) | — |
| **KD-14** | **Hosted demo = Modal CPU `asgi_app` + Gradio 6**; hosted Meta APIs do the heavy lifting. Curated allowlist pre-indexed (metadata + test pre-compiled); arbitrary IDs best-effort. Labelled cached replay | Cost (no warm GPU), reliability, honesty | HF Gradio Spaces (need PRO); a warm GPU pool | — |
| **KD-15** | **Digest numbers are deterministic** (histogram + Wilson CI); Muse Wonder clusters and narrates; memory = persisted JSON + `previous_response_id` | No hallucinated statistics; no memory API exists | Wonder computes the stats | A memory API appears |
| **KD-16** | **Distribution `Kodiac-robotics`, import `Kodiac_robotics`, CLI `Kodiac`**; extras `[sim] [proof] [app] [viz] [mcp] [dev]` | PyPI collision; a light base install | `Kodiac` | — |
| **KD-17** | **Observability = `trace.jsonl` (orjson) + optional Rerun `.rrd`**; every rendered number carries a `trace_id` | I15 | Logs only | — |
| **KD-18** | **Effector aliasing by role** (`gripper` → robot-gripper prompt set or hand prompt set; clip type auto-detected) | I2 + I16 with one test file | Separate tests per embodiment | — |
| **KD-19** | **Outward actions are human-gated in code:** `Kodiac audit publish` requires `--i-have-human-approval <ticket>` and refuses in CI | `AGENTS.md` §12 | Agent-initiated posting | Never |
| **KD-20** | **CAN'T TELL = "not accepted" in filtering/retraining**; coverage always reported | Prevents metric gaming (pre-registered) | Treating CAN'T TELL as PASS | Never |

---

## 3. Component Model

### 3.1 Packages and responsibilities

| Package (`src/Kodiac_robotics/…`) | Responsibility | Key public API | Features |
|---|---|---|---|
| `contracts/` | **Frozen Pydantic models and Protocols** (owned by ORCH) | §4 | all |
| `config.py` | Settings (env + `Kodiac.toml`): backends, model IDs, thresholds, cache dir | `Settings.load()` | all |
| `cache.py` | Content-hash cache (disk) | `cached_call(key_parts, fn)` | KD-10 |
| `io/` | Ingest (file / LeRobot / sim / webcam), time base, transcode, window cutting, keyframe packing, frame access | `open_clip(ref) -> Clip`, `cut_window(clip, f0, f1) -> Path`, `pack_frames(clip, idx) -> Path` | F01, F11 |
| `segment/` | `Segmenter` protocol + backends `api.py`, `modal_backend.py`, `fixture.py`; re-ID; mask decode | `segment_keyframes(...)`, `track(window, seeds, direction)` | F07, F12, F14 |
| `geometry/` | Anchors, scale model tiers A/B/C, ground-plane fit, rim ellipse, optional depth | `ScaleModel.fit(clip_masks) -> ScaleModel`, `to_table_frame(...)` | F15, F17 |
| `predicates/` | The six predicates + `looks` dispatch + MANUAL; per-frame `PredFrame` tri-states with margin/σ | `evaluate(expr, tracks, scale, t) -> PredFrame` | F16–F21 |
| `uncertainty/` | σ_px estimation, Monte-Carlo propagation, λ calibration, gates G1–G6 | `sigma_margin(...)`, `apply_gates(...)` | F22–F24 |
| `engine/` | Smoothing/hysteresis, step-chain evaluator, carried literals, verdict, **bisect scheduler**, verification windows, run orchestration | `run(test, clip, mode) -> RunResult` | F13, F22, F28 |
| `pipeline/` | `run.py` (full + fast orchestration, stored-track replay), `bisect.py` (two-stage fast path), `looks()` dispatch through the injected `VLMJudge` | `run(test, clip, mode, tracks=None) -> RunResult` | F13, F28 |
| `judge/` | Crop rendering, two-way protocol, escalation, OpenAI-compatible client, backends | `ask_two_way(crop, q_pos, q_neg) -> Tri` | F25–F27 |
| `compiler/` | ASR (Muse Voice), clause → steps (Spark), Lark grammar, printer, linter, lock, SAM existence check, self-test, text-compile, effector aliasing | `compile_demo(video) -> GreenTest`, `compile_text(task, frame)`, `parse(path)`, `print(test)` | F02–F10 |
| `blame/` | Transition finder, t* refinement, fact table, summary + validator, diff, hint, code location, salvage | `blame(run) -> Blame`, `diff(demo_events, attempt_events)` | F31–F37 |
| `render/` | Verdict card, evidence frames, CLI rendering, HTML report, Rerun logging | `card(run) -> PNG` | F29, F30 |
| `sim/` | ManiSkill harness, robot API wrapper + span logger, bug registry (B1–B10), oracle access | `run_script(script, seed) -> SimRun` | F41, F42, F35b |
| `loop/` | MCP server (`verify`), `gate` command, hook/MCP config templates, `/goal` recipe | `Kodiac mcp`, `Kodiac gate` | F38–F40 |
| `audit/` | Batch audit, sampling for hand-verification, labelling helper, digest (deterministic + Wonder), parquet export, (human-gated) publish | `Kodiac audit run|review|digest|export|publish` | F49–F52 |
| `proof/` | Judge registry (baselines + Kodiac arms), pool management, calibration, Modal training/eval orchestration, stats, chart | `Kodiac-proof …` (dev CLI) | F43–F48 |
| `app/` | Gradio UI + FastAPI routes, replay store, rate limiting, upload hygiene, Modal entrypoint | `build_ui()`, `modal deploy app/modal_app.py` | F53–F57 |
| `cli.py` | Typer CLI: `test`, `run`, `blame`, `diff` (+ `gate`, `mcp`, `serve`, `audit`, `card`) | — | I1 |

### 3.2 Dependency rule (enforced by import-linter or a simple test)
`contracts ← config/cache ← io ← segment ← geometry ← predicates/uncertainty ← engine (logic, smoothing, steps) ← judge · blame · render ← pipeline (run, bisect, looks dispatch via the injected VLMJudge) ← compiler ← cli/loop/audit/proof/app`.
Lower layers never import higher ones. `sim/` depends only on `contracts` and `io`. `proof/` may import anything.

---

## 4. Data Contracts (frozen at P01 dispatch; changes only via ORCH)

```python
# src/Kodiac_robotics/contracts/core.py  (sketch: field names AND types are binding; implement one field per line)
# Implementation notes (binding): GreenLock.model_rebuild() at module end; @model_validator: verdict == CANT_TELL ⇒ reasons != [];
# Atom.name: Literal["on","inside","near","lifted","moves_with","dwell"] | None; ObjMask gets rle_size: tuple[int, int];
# reserved object name `gripper` ⇒ role="effector" unless declared; `dwell` accepts rigid|articulated A.
from enum import Enum
from typing import Literal, Protocol
from pydantic import BaseModel

class Tri(str, Enum):            # per-frame / per-component
    T = "T"; F = "F"; U = "U"

class Verdict(str, Enum):        # user-facing: PASS / FAIL / CAN'T TELL
    PASS = "PASS"; FAIL = "FAIL"; CANT_TELL = "CANT_TELL"

class ReasonCode(str, Enum):     # every CANT_TELL carries ≥1
    NOT_VISIBLE = "not_visible"; OCCLUDED = "occluded"; BELOW_NOISE_FLOOR = "below_noise_floor"
    VIEW_BLOCKED = "view_blocked"; APPEARANCE_UNRESOLVED = "appearance_unresolved"; DEPTH_AMBIGUOUS = "depth_ambiguous"

# ---------- .green ----------
class Provenance(BaseModel):
    quote: str | None; t_start: float | None; t_end: float | None
    source: Literal["voice", "text", "compiler-default", "user-edit"]

class ObjectDecl(BaseModel):
    name: str; role: Literal["effector", "rigid", "container", "articulated", "surface"] = "rigid"
    prompt: str | None = None; aliases: list[str] = []; size_cm: float | None = None; height_cm: float | None = None

class Param(BaseModel):
    name: str; op: Literal["=", "<=", ">="]; value: float

class Atom(BaseModel):
    kind: Literal["pred", "looks", "manual"]
    name: str | None = None                  # on|inside|near|lifted|moves_with|dwell (kind=pred)
    args: list[str] = []; params: list[Param] = []
    looks_pos: str | None = None; looks_neg: str | None = None; manual_text: str | None = None

class Expr(BaseModel):                       # boolean tree
    op: Literal["and", "or", "not", "atom"]; children: list["Expr"] = []; atom: Atom | None = None

class Step(BaseModel):
    index: int; name: str; expr: Expr; provenance: Provenance; extra_provenance: list[Provenance] = []

class GreenTest(BaseModel):
    version: Literal["0.1"] = "0.1"; name: str; objects: list[ObjectDecl]; steps: list[Step]
    params: list[Param] = []; header_comment: str | None = None

class GreenLock(BaseModel):                  # <name>.green.lock (JSON)
    test_sha256: str; transcript: list[dict]; object_baselines: dict[str, dict]   # A0, k0, rim ellipse, scores
    demo_events: list["Event"]; geometry_tier: Literal["A", "B", "C"]; model_ids: dict[str, str]; created_at: str

# ---------- video & masks ----------
class ClipRef(BaseModel):
    uri: str                                 # file://… | lerobot://repo/episode[/camera] | sim://run_id | upload://id
    source_kind: Literal["real", "sim", "upload", "demo"]; dataset: str | None = None; episode_index: int | None = None
    camera: str | None = None

class Clip(BaseModel):
    ref: ClipRef; path_h264: str; fps: float; n_frames: int; width: int; height: int; sha256: str

class ObjMask(BaseModel):
    obj: str; frame: int; score: float; bbox_xyxy: tuple[float, float, float, float]
    rle: str                                  # COCO RLE of the full-frame mask
    area_px: int

class Track(BaseModel):
    obj: str; frames: dict[int, ObjMask]; backend: Literal["api", "modal", "fixture"]; direction: str; trace_id: str

class Segmenter(Protocol):
    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]: ...
    def track(self, clip: Clip, f0: int, f1: int, seeds: dict[str, ObjMask],
              direction: Literal["forward", "backward", "both"]) -> dict[str, Track]: ...

class VLMJudge(Protocol):
    def ask_two_way(self, crop_png: bytes, q_pos: str, q_neg: str) -> tuple[Tri, str]: ...

class ASR(Protocol):
    def transcribe(self, wav_path: str) -> list[dict]: ...      # [{startMs, endMs, transcript}]

class Memory(Protocol):
    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...

class ScaleModel(Protocol):
    tier: Literal["A", "B", "C"]
    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]: ...   # X, D, h (cm), sigma

# ---------- measurement ----------
class Component(BaseModel):
    name: str                                 # e.g. "on.align_xy"
    value: float; threshold: float; margin: float; sigma: float; unit: Literal["cm", "s", "ratio", "cm/s"]; tri: Tri
    reason: ReasonCode | None = None

class PredFrame(BaseModel):
    frame: int; atom_key: str; tri: Tri; components: list[Component]; trace_id: str

class Event(BaseModel):                       # for diff + digest
    step: int; step_name: str
    kind: Literal["achieved", "failed", "grasped", "lifted", "contacted", "released", "entered", "settled", "broke", "order_violation"]
    predicate: str | None; args: list[str]; t_s: float; frame: int; fps: float
    measurements: dict[str, tuple[float, float]]   # name -> (value, sigma)
    source: Literal["demo", "attempt"]; verdict: Verdict | None = None

class StepResult(BaseModel):
    index: int; name: str; verdict: Verdict | None; t_s: float | None; frame: int | None   # None = not evaluated
    decisive: list[Component]; reasons: list[ReasonCode] = []; evidence: list[str] = []

# ---------- blame ----------
class CodeLocation(BaseModel):
    file: str; line: int; code: str; span_id: int

class Hint(BaseModel):
    variable: str; delta: float | list[float] | None; unit: str | None; move: str | None = None; basis: str

class FactTable(BaseModel):
    t_star_s: float; frame: int; fps: float; sigma_frames: float
    step_index: int; step_name: str; literal: str; transition: Literal["T->F", "never_T", "order", "unmet"]
    facts: dict[str, dict]                    # name -> {value, sigma, unit, ref?, dir?}
    dataset_index: int | None = None; action_chunk: int | None = None; code_location: CodeLocation | None = None
    evidence: list[str]; trace_ids: list[str]

class Blame(BaseModel):
    facts: FactTable; summary: str; summary_source: Literal["muse-spark", "template"]; hint: Hint | None
    warnings: list[str] = []                  # transient breaks, low-confidence tracking

# ---------- run ----------
class RunResult(BaseModel):
    run_id: str; test_name: str; test_sha256: str; config_sha256: str; clip: ClipRef
    verdict: Verdict; exit_code: Literal[0, 1, 2, 3]; steps: list[StepResult]; reasons: list[ReasonCode]
    blame: Blame | None; diff_text: str | None; events: list[Event]; manual_checks: list[str]
    timings_ms: dict[str, int]; backends: dict[str, str]; badges: list[str]   # REAL/SIM/UPLOAD/CACHED/OPEN-WEIGHTS
    nonce: str  # 16-character hex string (^[0-9a-f]{16}$)
    is_fixture: bool = False  # True if generated via fixture / mock mode without live model inference
    card_path: str | None; trace_path: str; created_at: str

# ---------- loop ----------
class VerifyRequest(BaseModel):              # MCP Kodiac.verify input
    test: str; sim_script: str | None = None; seed: int = 0; clip: str | None = None
    mode: Literal["fast", "full"] = "full"; fresh: bool = True

# VerifyResponse = RunResult (JSON) + "hint" + "evidence" paths

class GateState(BaseModel):                  # .Kodiac/gate_state.json
    pinned_test_sha256: str; pinned_config_sha256: str; blocks: int; max_blocks: int; last_nonce: str | None

# ---------- audit / proof ----------
class VerdictRow(BaseModel):                 # Kodiac_verdicts.parquet
    dataset: str; episode_index: int; camera: str; verdict: Verdict; t_star_s: float | None; frame: int | None
    step: str | None; predicate: str | None; margin: float | None; sigma: float | None
    reasons: list[str]; evidence_uri: str | None; model_ids: str; Kodiac_version: str; human_verified: bool | None

class JudgeLabel(BaseModel):                 # proof pool labels
    judge: str; episode_id: str; accept: bool; score: float | None; verdict: Verdict | None
    latency_ms: int; cost_usd: float; calibration_threshold: float | None
```

### 4.1 Trace record (`trace.jsonl`, one JSON per line)
```json
{"trace_id":"tr_01J…","run_id":"run_…","ts":"…","kind":"sam.track|sam.segment|pred.frame|gate|judge.ask|judge.escalate|blame.tstar|summary|cache.hit",
 "inputs":{"frames":[64,113],"objects":["red_block"],"direction":"backward","prompt_frame":113},
 "outputs":{"n_masks":100,"mean_score":0.91},"model":"sam-3.1","backend":"api","latency_ms":3120,"cost_usd":0.01,"cache_key":"sha256:…"}
```

### 4.2 File & artifact layout per run
```
runs/<run_id>/result.json   (RunResult)       runs/<run_id>/trace.jsonl       runs/<run_id>/card.png
runs/<run_id>/evidence/f0114_overlay.png …   runs/<run_id>/diff.txt          runs/<run_id>/run.rrd (optional)
.Kodiac/last_verdict.json  (symlink/copy of the latest RunResult, read by the gate)
```

---

## 5. Workflows

### 5.1 `Kodiac test` (compile from a demo): F01–F10

```
demo.mp4 ──► io.open_clip ──► audio.wav ──► Muse Voice (ENDPOINTING) ──► turns[{startMs,endMs,text}]
                    │                                                         │
                    │                                    clauses (≤ 5; one per turn; Spark may split a turn)
                    ▼                                                         ▼
          keyframes (2–3) ──► SAM 3.1 segment_frames(prompts per object) ◄── Muse Spark 1.3 structured output:
                    │            (existence + ambiguity + A0/k0 + rim)        GreenTest skeleton {objects, steps, exprs}
                    ▼                                                         │   (no numbers: placeholders)
          effector alias: detect human clip → gripper := hand                 ▼
                    └──────────────► linter (E00x/W10x, MANUAL rules) ◄──── printer/parser round-trip
                                               │
                                               ▼
                        demo self-test: engine.run(test_with_default_params, demo, mode=full)
                          → measured demo events → thresholds from slack table (e.g. min_cm = ⌊0.5·lift⌋; align_xy = max(1.5, 3σ))
                          → re-run: demo must PASS with margin ≥ 2σ (else E005/W103)
                                               │
                                               ▼
                          write <name>.green (canonical 4 lines) + <name>.green.lock (+ demo events for diff)
```
**Text-compile (F09):** same pipeline, with `turns` replaced by the task string and the demo replaced by the first frame (existence check
Text-compiled tests store `expected_events` synthesized from the step thresholds (e.g. `- step 2: on(red_block, green_block) align_xy ≤ 1.5 cm`), so `diff` still works: it renders spec-vs-attempt under the header `--- test spec` when no demo lock exists.
only; no self-test). Thresholds come from the defaults table, or from the oracle-matched table for proof tasks.

### 5.2 `Kodiac run`, live fast path: F11–F14, F22–F30 (target p50 < 10 s, p95 < 12 s)

```
t=0   ingest: resolve ClipRef (curated → pre-fetched H.264; upload → transcode) .................... ≤1.0 s
      ┌────────────────────────── Stage 1: coarse (parallel) ─────────────────────────┐
      │ K = max(6, ⌈dur/2.5s⌉) keyframes → pack into one MP4 → SAM 3.1 text prompts   │ ≤2.0 s
      │ → static proxies per step at each keyframe: on/inside/near/lifted (static),   │
      │   grasp_proxy = lifted ∧ contact, release_proxy = ¬contact ∧ (on ∨ inside ∨ rest)
      │ → progress(f_j) (prefix-max, monotone) → first failing step k+1               │
      │ → bracket [f_a, f_b] on the monotone target F_L(t) = "L false from t onward"  │
      └───────────────────────────────────────────────────────────────────────────────┘
      Stage 1.5: while f_b − f_a > 50: probe f_m (SAM image mode, 1 frame) → halve ........... ≤0.6 s
      Stage 2: cut [f_a−3, f_b+3] (≥50 frames) → SAM 3.1 track, seeds = boxes on the LAST frame,
               direction = backward (optionally forward from f_a; IoU(fwd,bwd) < 0.7 → σ inflated)  3–5 s
      PASS path: sparse verification windows (≤10 fps) around each step's achievement keyframe for temporal predicates
      predicates + Monte-Carlo σ + gates + 3-valued step chain → verdict ........................... ≤0.2 s
      looks() checks only: Spark two-way on crops (parallel); conflict → Wonder (≤3 s cap) ........... ≤1.5 s (+3 s rare)
      blame (if FAIL): t* changepoint + fact table → Spark summary (1.5 s timeout → template) ‖ render card   ≤1.5 s
t≈7–11 s  RunResult + card + trace
```
**Guards:** G-alias (flicker/regrasp → union bracket) · G-miss (prerequisite already false at window start → extend back by 50 frames,
≤2×) · G-budget (unbracketable → full path, flag `slow_path`) · G-pass (all steps pass at keyframes → verification windows only).

### 5.3 `Kodiac run`, full path (batch, audits, proof)
Dense SAM 3.1 tracking of the whole clip at native fps (self-hosted on Modal for bulk; `start_frame_index`/`max_frame_num_to_track` for
exact windows) → all predicates per frame → the same evaluator. Used to **validate the fast path** (agreement test in P06: fast vs. full
verdict and t* on ≥100 clips; required agreement ≥95% verdict, t* within ±2 frames on ≥90%).

### 5.4 `Kodiac blame` / `Kodiac diff`: F31–F37

```
RunResult(FAIL) → transition finder (carried literals):
   class 1 broken prerequisite: t*_L = onset of L's final False run before C_{k+1} ever holds; L* = argmin t*_L
   class 2 unmet condition:     t* = argmax softscore(C_{k+1}); cause = most negative m/σ component
   class 3 order violation:     t* = the out-of-order event
   (transient breaks → warnings)
→ refine t* in the dense window: moves_with → detach-onset rule; threshold components → 2-segment piecewise-linear breakpoint; σ_t* by bootstrap
→ FactTable (+ dataset index / action chunk / CodeLocation from the span log in sim)
→ Muse Spark summary from the FactTable only → validator → (retry once) → template fallback
→ Hint: the single variable change that flips the blamed margin to ≥ +σ (uses the demo event as reference)
→ diff: demo_events (from .green.lock) vs attempt events → LCS on (step, kind, predicate) → unified-diff text with measurements
```

### 5.5 Muse Code `/goal` loop with the done-gate: F38–F42

```
Developer: /goal Fix pick_place.py so the robot stacks red on green. Done ONLY when Kodiac run prints PASS.
   │
   ▼
Muse Code ──(MCP tool call)──► Kodiac.verify {test: stack_blocks.green, sim_script: pick_place.py, seed: 7}
   │                              └─► sim.run_script (ManiSkill StackCube, 30 Hz render, span log) → video
   │                              └─► engine.run(mode=full) → RunResult + blame(code: pick_place.py:42 -> gripper.open()) + hint
   │                              └─► writes .Kodiac/last_verdict.json (nonce N1)
   ◄── FAIL + blame + diff + hint
   edits pick_place.py:42 (moves gripper.open() after arm.move_to(place))
   calls verify again → PASS (nonce N2) → tries to stop
   │
   ▼
Stop hook ─► Kodiac gate --max-blocks 8          (no `gate --init` state → exit 0: never blocks unrelated sessions)
   if blocks ≥ max: print "GATE EXHAUSTED: goal NOT verified", write .Kodiac/gate_exhausted, exit 0 (recipe treats it as failure)
   re-run pinned sim + test → PASS iff verdict == PASS ∧ test sha == pin ∧ config sha == pin ∧ source_kind == "sim" ∧ script sha == sha256(current script)
   PASS → exit 0 → /goal completes     else → blocks += 1; exit 2, stderr = blame + diff + hint → Muse Code keeps working     any internal error → exit 2 "GATE ERROR: …" (fail closed)
```
- **Pinning:** `Kodiac gate --init` writes the pins outside the workspace. Editing `stack_blocks.green`, the thresholds, or the pin file inside the repo has no effect; a changed test → `test modified`.
- **Freshness by construction:** the gate never trusts a cached verdict; it grades the current script itself (< 60 s, hook timeout 600 s).
- **Loop safety:** `blocks` counter in `.Kodiac/gate_state.json`; at `max_blocks` the stop is allowed with `GATE EXHAUSTED: goal NOT verified`. Gate templates are installed into `examples/sim/` only.
- **Fix-rate eval (F42):** `Kodiac-proof loop-eval --bugs B1..B10 --max-iters 5` runs `muse exec` headless per bug, logs transcripts, and checks gate PASS ∧ oracle success ∧ hash unchanged.

### 5.6 Dataset audit: F49–F52

```
audit run --dataset <repo> --task-filter "pick|place|put|stack" --camera <key> --limit N
   → per task string: text-compile .green (cached per dataset+task)
   → batch full-path runs (Modal SAM bulk) → VerdictRow per episode
audit review → candidate flags (FAIL with margin ≥ 2σ) → local HTML/Rerun review UI → HUMAN marks confirmed / rejected / unsure
audit digest → deterministic histogram (step × component × cause) + Wilson CI → Muse Wonder narration (+ memory file)
audit export → Kodiac_verdicts.parquet (+ evidence PNGs) → audit card PNG
audit publish → HUMAN-GATED (KD-19): HF discussion + PR with the parquet (one consolidated, polite report)
```

### 5.7 Proof experiment pipeline: F43–F48

```
[pre-register: experiments/PREREGISTRATION.md committed + tagged BEFORE any judge label is revealed]
demos: ManiSkill motion-planning expert, 20–50 clean episodes → π0 (weak state-based DP/ACT; target oracle success 30–60%)
pool:  ~70% π0 self-practice rollouts + ~30% perturbed-expert near-misses (early open, xy offset U(1,6) cm, low lift, short dwell, regrasp)
       → total ≈ 600–1,000 episodes rendered at 30 Hz; saved with state, oracle success, perturbation onset (ground truth for blame)
       → split: calibration (≈200) | training pool (rest)
judges (registry; same pool, same videos):
       single-pass Spark (2 fps) · Robometer-4B · TOPReward · Kodiac (cloud) · Kodiac (open-weights, if applicable)
       · Kodiac + prefix salvage · Oracle · Accept-all · size-matched random oracle-success · Oracle + k% injected false-PASS (k=5,10,20,30)
       → thresholds for score judges tuned on the calibration split (max balanced accuracy)
train: the same policy + the same hyperparameters + FIXED gradient steps, per judge's accepted set × 3 seeds (Modal L4, parallel)
eval:  ≥200 oracle-scored episodes per seed, fixed eval seeds (GPU-parallel envs)
stats: per-seed success + mean, episode-bootstrap CI within seed, Welch t across seeds for Δ (hierarchical bootstrap secondary); Wilson CIs for false-PASS / false-REJECT / coverage; episode-bootstrap CIs for BA / contamination / AUROC; Holm-corrected McNemar vs Kodiac; all on the training split
chart: §1.4                        real-footage benchmark (no retraining): RoboRewardBench test + own blind-labelled DROID slice (+ FailBench subsets if released)
```

### 5.8 Hosted demo request: F53–F57

```
Browser ─► Modal CPU container (FastAPI + Gradio; concurrency 20; min_containers=1 during Nov 4–16)
   ├─ GET /                  → UI; curated list from replay store (Modal Volume): instant CACHED cards
   ├─ POST /grade {ref|upload|webcam, test?, occluder_rects?}
   │     rate limit (per-IP token bucket) → size/length caps (20 s / 50 MB) → transcode
   │     → test: curated → precompiled .green; upload → user choice of example tests or text-compile from a typed instruction
   │     → engine.run(fast) → hosted sam-3.1 / muse-spark-1.3 (cache first) → RunResult + card
   │     → response streamed in stages (timer runs client-side from click to verdict)
   └─ uploads deleted after 24 h (scheduled Modal function); spend counter; health endpoint for the uptime monitor
```

---

## 6. The `.green` Language (normative)

### 6.1 Grammar (Lark-style EBNF)
```ebnf
file        : comment* objects_line params_line? ("steps:" NL)? step+
objects_line: "objects:" "[" object ("," object)* "]" NL
object      : IDENT ("(" obj_attr ("," obj_attr)* ")")?
obj_attr    : "role" "=" ROLE | "prompt" "=" STRING | "alias" "=" "[" STRING ("," STRING)* "]" | "size_cm" "=" NUMBER | "height_cm" "=" NUMBER
ROLE        : "effector" | "rigid" | "container" | "articulated" | "surface"
params_line : "params:" param ("," param)* NL
step        : INT "." IDENT ":" expr provenance? NL
expr        : and_expr ("or" and_expr)*
and_expr    : not_expr ("and" not_expr)*
not_expr    : "not" not_expr | atom
atom        : predicate | looks | manual | "(" expr ")"
predicate   : PRED "(" IDENT ("," IDENT)? ("," param)* ")"
PRED        : "on" | "inside" | "near" | "lifted" | "moves_with" | "dwell"
param       : PNAME CMP NUMBER            CMP: "=" | "<=" | ">="
looks       : "looks" "(" IDENT "," STRING ("|" STRING)? ")"
manual      : "MANUAL" "(" STRING ")"
provenance  : "#" QUOTED? ("[" TIME ("–"|"-") TIME "]")? FREE_TEXT?
TIME        : (INT ":")? INT "." DIGIT
```
The source spec's example (with `steps:` and indented steps) **must parse verbatim** (golden test). The canonical printer emits 4 lines.

### 6.2 Predicate signatures & parameter directions
| Predicate | Args | Params (direction, default, unit) |
|---|---|---|
| `on` | (rigid A, rigid\|surface\|container B) | `align_xy_cm` (≤, 1.5, cm) · `gap_cm` (≤, 1.0, cm) · `depth_tol` (≤, 0.12, ratio) |
| `inside` | (rigid A, container B) | `rim_margin_cm` (≥, 0.5, cm) · `depth_tol` (≤, 0.15, ratio) |
| `near` | (any A, any B) | `max_cm` (≤, 5.0, cm) |
| `lifted` | (rigid A) | `min_cm` (≥, 2.0, cm) |
| `moves_with` | (effector\|rigid E, rigid A) | `slip_cm` (≤, 1.0, cm) · `window_s` (=, 0.33, s) |
| `dwell` | (rigid A [, any B]) | `for_s` (≥, 0.5, s) · `max_speed_cm_s` (≤, 1.0, cm/s) |
| `looks` | (any X, "state" \| "opposite") | — (two-way crop judge; the compiler generates the opposite if omitted) |
| `MANUAL` | ("requirement") | — (never evaluated; listed in the report; never blocks the gate) |

### 6.3 Diagnostics
E001 object not found · E002 ambiguous object · E003 type error · E004 comparator against direction · E005 demo fails its own test ·
W101 non-visual → MANUAL · W102 step without provenance · W103 demo margin < 2σ · W104 depth-critical check under Tier C · W105 `or` used.

---

## 7. Measurement Engine (normative summary; full derivations in `docs/research/01_project_analysis.md` §3)

### 7.1 Per-frame measurements
Mask `M_o,t`, area `a`, bbox, centroid, **bottom anchor β** (median column of the lowest 5% of mask rows), top anchor, track score `s`.
Expected unoccluded area `â` (scale-corrected from the last untouched frame) → occlusion fraction `occ = clip(1 − a/â, 0, 1)`.

### 7.2 Scale model (KD-06)
- **Size priors** `W_o` (cm) from `.green` attributes, then a priors table, then a compile-time question. Each carries a σ_W of 3% / 10% / 20%.
- Per-object scale `k_o,t = (ℓ_o,0 / W_o) · (ℓ_o,t / ℓ_o,0)` (px/cm); depth `z = f / k`.
- **Tier A:** known K, [R|t] (sim exact) → back-project onto the support plane.
- **Tier B (default):** ground-plane fit from ≥2 resting objects: `v_i − v_h = k_i · H̃` → `(v_h, H̃)`; f from the HFOV prior (70° ± 10°) → height `h = cos θ · (H̃ − (v − v_h)/k)`, lateral `X = (u − c_x)/k`, forward D from z.
- **Tier C:** single reference; σ inflated so depth-critical components fall to CAN'T TELL honestly.
- Anisotropy: depth-axis σ ≫ lateral σ. This shows up in the gates, not as false precision.

### 7.3 Predicates (component margins; positive = satisfied)
- `on`: `m_xy = align_xy − ‖ΔXY‖`; `m_z = gap − |h_A,bottom − H_B|`; `m_ρ = τ_ρ − |√ρ_A − 1|` with `ρ_A = (ℓ_A,t/ℓ_A,0)²·(z_B⁺/z_A,0)²` (catches hovering in front).
- `inside`: in-rim distance `m_1`; occlusion order (front_occluder vs behind_rim); depth consistency `m_3`; rim-crossing memory c4; object permanence.
- `near`: `m = max_cm − √(d_lat² + d_depth²)`.
- `lifted`: `m = (h_A,t − h_A,0) − min_cm` (relative to rest; k from the unoccluded width).
- `moves_with`: attach/detach state machine on `ρ_rel = ‖Δ_A − Δ_E‖` over `window_s`, with `n_on = max(2, round(0.1·fps))` confirmations; detach onset = `1 + max{t ≤ t_confirm : R(t) ≤ σ_R}`. Optional aperture event licenses the word "opened".
- `dwell`: run-length of (speed ≤ max_speed ∧ relation) ≥ `for_s`.

### 7.4 Uncertainty & gates (F23–F24)
- `σ_px = max(0.5, 1.4826·MAD(Δ²x)/√6)` on static segments (Savitzky–Golay residual when moving).
- Monte-Carlo with S = 256 over pixel noise, W, f, κ → `σ_m`. Calibrated inflation λ (fitted on sim GT so |m_true − m_est| ≤ σ ≈ 68%).
- **Gates:** G1 not visible (s < 0.5) · G2 occluded > 40% by effector/unknown (excluding container→contents and the carried object) ·
  G3 `|m| < σ_m` · G4 view blocked (luminance < 15/255, low Laplacian variance, > 60% uniform) · G5 appearance unresolved · G6 depth ambiguous (Tier C, σ > 0.5·threshold).

### 7.5 Logic, steps, verdict
- Kleene: `¬U=U, T∧U=U, F∧U=F, T∨U=T`. Smoothing: Hampel(7) → Savitzky–Golay(≈0.2 s) → Schmitt trigger (n_on); U frames neither confirm nor reset.
- Achievement `a_k = min{t > a_{k−1} : C_k = T for n_on frames}`. **Carried literals** persist from `a_k` until the onset of the ¬L run that begins `C_j`'s achieving run (j = first later step containing ¬L), else until `a_{k+1}`. `Inv_{k+1}` excludes every literal whose negation appears in `C_{k+1}`. (Unit test: correct release + 0.2 s dwell → class 2 `dwell`, not class 1.) Steps after the first non-PASS step are not evaluated (printed "—"; `StepResult.verdict = None`).
- Step PASS iff a sustained T run exists. FAIL iff F on every decided frame and no U run ≥ n_on could hide a T run (state conditions may FAIL on a settled end state). Else CAN'T TELL.
- **Overall verdict = the first non-PASS step's verdict.** MANUAL never changes it (`PASS (1 MANUAL check not verified)`).

---

## 8. Judge Layer (`looks()` only): F25–F27

1. **Crop:** take the decisive frame (achievement / t* / settled end), crop the object mask bbox with 25% padding, draw the outline (supervision), upscale to ≥512 px.
2. **Two-way protocol:** ask `Q⁺ = "Is the {obj} {state}?"` and `Q⁻ = "Is the {obj} {opposite}?"` (antonym state, never "not"). Schema `{answer: yes|no|cant_tell, reason}`. Ask both in parallel. Use the system prompt "Answer only from the outlined region."
3. **Decision:** (yes,no) → T · (no,yes) → F · otherwise → escalate to `muse-wonder-1.0` with the same pair (live cap 3 s) → (yes,no)/(no,yes) decides, otherwise U with `appearance_unresolved`.
4. **Backends (KD-09):** `meta` (default), `baseten-spark-open`, `modal-glimmer-vllm`, `llamacpp-glimmer`. Selected by `Kodiac_JUDGE_*`. Glimmer sampling: temp 1.0 / top_p 0.95 / top_k 64. Results cached by `(backend, model, crop sha, question)`.
5. **Single-pass baseline** (proof only): `muse-spark-1.3` on the whole clip (`input_video`, or ≤50 frames at 2 fps as images), yes/no schema.
6. **Appearance benchmark** (`experiments/appearance/`, ≥60 labelled `looks()` clips: sim drawer flush vs. ajar + real DROID drawer episodes) is where the two-way judge, Wonder escalation, the open-weights row and ablation rungs R2–R4 are measured. On geometry-only tasks the VLM layer is a no-op by design, and we say so.

---

## 9. Blame & Diff Details: F31–F37

- **Fact table** (§4 `FactTable`): the **only** input to the summary. Facts include `xy_offset_cm`, `dt_before_reference_s` (defined as `t_ref − t*`,
  with `t_ref` = the effector's closest xy approach to the target after t*; omitted if there is none), `lift_cm`, `slip_cm`, `aperture_open_event`, `occlusion`.
- **Summary validator:** a regex over numbers+units must match fact values (1-decimal rounding); object names ∈ objects; verbs licensed ("opened" needs an aperture event or a sim span); one sentence ≤ 30 words. Retry once, then the template:
  `blame: {E} released {A} {dt} ± {σdt} s before reaching {B} (xy offset {d} ± {σd} cm at {mm:ss.s}, frame {f})`. The sentence must contain ≥1 `value ± σ` pair copied from the fact table.
- **Blame disambiguation for `moves_with` T→F:** if the release span precedes the `move_to(place)` span → blame the release line (hint: order); elif xy_offset ≤ align_xy ∧ gap_z > gap_cm → blame `move_to(place)` (hint: z).
- **Diff:** demo events come from `.green.lock`; alignment is Myers LCS on `(step, kind, predicate)`; matched + within 2σ → context line; otherwise `-`/`+`. Directions are labelled `camera-left` unless Tier A.
- **Code location (sim):** the span logger records `{span, file, line, func, code, class, step_start, step_end}` per robot-API call. Blamed span = the latest span with `step_start ≤ frame(t*) + 3` whose actuation class matches the broken component (table in `01_project_analysis.md` §3.11).
- **Prefix salvage:** `cut = t* − 0.5 s` (keep only if ≥ 1.0 s); for chunked policies, sample only starts with `s + H_a ≤ cut`.

---

## 10. Simulation Harness & Seeded Bugs: F41–F42

```python
# examples/sim/pick_place.py  (the program Muse Code edits; ~25 lines, readable)
from Kodiac_robotics.sim.robot import Robot          # wrapper over ManiSkill StackCube motion planner, span-logged
def run(robot: Robot) -> None:
    robot.arm.move_to("above", "red_block")
    robot.arm.move_to("grasp", "red_block")
    robot.gripper.close()
    robot.arm.lift(0.10)
    robot.arm.move_to("above", "green_block")
    robot.arm.move_to("place", "green_block")            # B2: offset target · B10: place z too high
    robot.gripper.open()                                 # B1 hero: open() moved before arm.move_to("above","green_block")
    robot.wait(0.5)                                      # B4: removed
    robot.arm.retract()
```
- `sim/robot.py`: every call is wrapped by `@span(cls="gripper_release")` etc.; the caller's file/line comes from `inspect`.
- Env config: `StackCube-v1`, `sim_freq=120, control_freq=30` (30-fps frames), `max_episode_steps` = 2× measured expert length, expert episodes converted to the policy control mode with `replay_trajectory`, a fixed render camera at 512×512, `render_mode="rgb_array"`, seeds fixed.
- `sim/bugs.py`: registry B1–B10 as unified-diff patches against `pick_place.py`, each with the expected blame class (used for eval and regression tests).
- Oracle access (`env.evaluate()["success"]`) is used **only** by the proof/eval code, never by the judge path (KD-13 / objection 1).

---

## 11. Deployment Topology

```
 Developer machine / agent sandbox                      Meta Model API (api.meta.ai)              Modal (sponsor credits)
 ┌──────────────────────────────┐   HTTPS (cached)     ┌──────────────────────────┐   ┌────────────────────────────────────────┐
 │ Kodiac CLI               │ ───────────────────▶ │ sam-3.1 · muse-spark-1.3 │   │ Kodiac-demo   CPU asgi (min=1 Nov4-16) │
 │ Muse Code + .mcp.json + hooks│                      │ muse-wonder-1.0 · voice  │◀──│ Kodiac-sam31  L4 batch, scale-to-zero  │
 │ ManiSkill (local GPU) or ────┼──── modal run ─────▶ └──────────────────────────┘   │ Kodiac-proof  L4 train/eval (parallel) │
 │   Modal GPU image            │                                                     │ Kodiac-glimmer H100 vLLM / L4 llama.cpp│
 └──────────────────────────────┘                      Baseten / Fireworks            │ Volumes: hf-cache · gl-cache · gl-replays  │
 GitHub: repo (public at submission) · Actions CI      ┌──────────────────────────┐   │          gl-pool (sim videos) · gl-uploads │
 (no GPU; fixture replay) · Pages (static mirror)      │ Muse Spark Open (judge)  │   └────────────────────────────────────────┘
 HF Hub: datasets (read) · verdict PRs (human-gated)   └──────────────────────────┘
```

---

## 12. Reliability, Fallbacks & Error Handling

| Dependency | Failure | Detection | Fallback (preserves invariants) |
|---|---|---|---|
| Hosted SAM 3.1 | Slow (> budget), 429, 5xx | Timing in trace; HTTP status | Retry with backoff (2/4/8 s) → Modal SAM backend → cached replay (labelled) |
| Muse Spark | Timeout / invalid JSON | Pydantic parse failure | One retry → template summary; `looks()` → CAN'T TELL `appearance_unresolved` |
| Muse Wonder | Timeout | 3 s cap (live) | CAN'T TELL `appearance_unresolved` (live); full escalation in batch |
| Muse Voice | Wrong turn count | ≠ expected clauses | Spark clause-splitting on the transcript text; MMS_FA alignment; manual edit |
| Muse Code hooks | Gate not invoked | Recorded test in P07 | Wrapper script `Kodiac goal-run` that the recipe must call; the done check is still enforced |
| ManiSkill render | No Vulkan locally | Smoke test ST9 | Modal GPU image; MuJoCo cookbook fallback for the loop |
| Glimmer serving | vLLM image fails | Smoke test | llama.cpp GGUF on L4 → Muse Spark Open on Baseten (the open-weights row survives) |
| Baselines | Install/VRAM failure | P02/P08 spike | Keep one reward model; label the row "not run" honestly |
| Hosted app | Container down | Uptime monitor | Static GitHub Pages mirror of cached replays + CLI quickstart |
| Budget | Credits exhausted | Daily spend check | Cache-only mode for the demo (labelled); stop batch jobs; human decision |

All errors return exit code 3 (**exception: `Kodiac gate` never exits 3; it fails closed with exit 2**) with a typed `KodiacError(code, message, hint)`. No stack traces in user output (`--debug` shows them).

---

## 13. Performance & Cost Budgets

| Path | Budget | Measured in |
|---|---|---|
| Live fast path (≤15 s clip, curated) | **p50 < 10 s, p95 < 12 s** end-to-end (claim only if measured, n ≥ 30) | P06, P09 |
| Full path (batch) | ≤ 3× clip duration on Modal L4 | P04 |
| `Kodiac test` (11 s demo) | < 15 s | P05 |
| `/goal` iteration (sim run + verify) | < 60 s | P07 |
| Cost per graded clip (hosted) | ≈ $0.05–0.09 (n_concepts × $0.01 coarse + window + verification + crops) | P06 |
| Proof compute | ≤ 50 GPU-h (Modal L4; 36–39 training runs) | P08 |

---

## 14. Security, Privacy, Compliance
- Keys only from env/secret stores; never logged (structlog redaction processor); pre-commit secret scan.
- Uploads: 24 h retention, visible notice, no training use, deleted by a scheduled function. **Real/private footage never goes to the contributor tier.**
- `--local-glimmer` / private mode: self-hosted SAM + open-weights judge for any pixel-bearing call; text-only calls allowed unless `--offline`.
- Dataset licences recorded in `ATTRIBUTIONS.md`; no weights redistributed.
- **New-work compliance:** first commit ≥ Oct 26; `BUILD_LOG.md` dated entries; `docs/private/` gitignored.
- **Public repo = filtered mirror.** The working repo stays private. `scripts/make_public_mirror.sh` builds the public repo with `git filter-repo` (excluding `HACKATHON.md`, `docs/research/`, `docs/private/`, `.agents/`, `HUMAN_TODO.md`), then `scripts/lint_public.py --history` checks files, full history and commit messages against `docs/private/lineage_terms.txt`. Publishing = 👤 approval.

---

## 15. Testing Strategy

| Layer | What | Tooling |
|---|---|---|
| Unit | Geometry, each predicate, the σ estimator, gates, Kleene logic, step chain, carried literals, bisect monotone target, LCS diff, summary validator | pytest + **hypothesis** (properties: symmetry of `near`, monotonic margins, abstention when σ → ∞) |
| Golden | The source spec `.green` parses verbatim; printer round-trip; CLI outputs; verdict JSON; diff text | **syrupy** snapshots |
| Fixture replay | Recorded SAM `output_text` + Spark/Wonder responses replayed through `meta-sam-parser` → full runs with no network | `Kodiac_SAM_BACKEND=fixture` |
| Sim ground truth | Predicates vs. ManiSkill privileged state on ≥50 episodes; blame t* vs. perturbation onset; λ fitted on the calibration-fit half, validated on the calibration-validate half; `artifacts/p04/sigma_calibration.png` (predicted vs. true margin, 1σ coverage) for the README | `@pytest.mark.slow` (GPU) |
| Fast vs. full agreement | ≥100 clips: verdict agreement ≥95%; t* ±2 frames ≥90% | P06 gate |
| E2E | `Kodiac test → run → blame → diff` on examples; MCP verify + gate refuse/allow | CI (fixtures) + GATE (live) |
| Live smoke | Hosted page: curated clip p95, upload, occlusion brush, webcam | P09/P10 scripted checks (Playwright) |

---

## 16. Meta Model → Feature → "Breaks Without" (I14 acceptance)

| Model | Features | Removing it breaks |
|---|---|---|
| SAM 3.1 | F07, F12–F24, F29, F32 | All measurement; blame t*; `test` type-check |
| Muse Spark 1.3 | F03, F09, F25, F33, F44 (baseline) | `test` compiler; `looks()`; the blame sentence (template remains) |
| Muse Voice Transcribe 1.0 | F02, F05 | Provenance spans and step windows from speech |
| Muse Wonder 1.0 | F26, F50 | Hard-case resolution; digest narration |
| Muse Code | F38–F42 | The loop and the done-gate (I7) |
| Muse Glimmer 30B / Muse Spark Open | F27, benchmark row | Open-weights/private mode |

---

## 17. Traceability: Feature → Module → Phase

| Features | Module(s) | Phase (IMPLEMENTATION_PLAN) |
|---|---|---|
| Contracts, config, cache, CLI skeleton, CI | `contracts/ config.py cache.py cli.py` | P01 |
| F41–F42 (harness, bugs), pool generation, dataset loaders, fixtures, hero-clip search | `sim/ io/ proof/pool` | P02 |
| F11–F12, F14 (segmentation, tracking, windows), fixture backend | `io/ segment/` | P03 |
| F15–F24, F28–F30 (scale, predicates, σ, gates, verdict, evidence, trace) | `geometry/ predicates/ uncertainty/ engine/ render/` | P04 |
| F01–F10 (`test` compiler) | `compiler/` | P05 |
| F13 (bisect fast path), F25–F27 (judge), F31–F37 (blame, diff) | `engine/bisect blame/ judge/` | P06 |
| F38–F40, F42 eval | `loop/ sim/` | P07 |
| F43–F52 (proof, audit) | `proof/ audit/` | P08 |
| F53–F58 (app, packaging) | `app/` + packaging | P09 |
| F59–F60 + final verification | `docs/ README` | P10 |


*Review round 1 (R1/R2) applied 2026-10-28: see `docs/research/07_fix_ruling.md`.*