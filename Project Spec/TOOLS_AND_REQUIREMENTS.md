# TOOLS_AND_REQUIREMENTS.md: Approved Stack, Shortcuts, Accounts, Budgets

> **Binding for every agent.** Do not install, call, or depend on anything that is not approved in this file. A new tool goes
> to ORCH as an improvement proposal (`AGENTS.md` §5.4).
> Raw research with every source URL: `docs/research/03_tools_research.md` (compiled 2026-10-27).
> **Tags:** **V** = verified in official code or docs · **P** = partial (secondary sources or conflicting official sources) ·
> **U** = unverified: smoke-test it in P01 before relying on it.

---

## 0. Selection Policy (strict priority order)

| Priority | Class | Rule |
|---|---|---|
| **P1** | **Meta products + the hackathon's official partners** (Modal, Baseten, Fireworks) + **Meta open-source research releases** | Always first. Meta models must do load-bearing work (`IDEA.md` §7) |
| **P2** | **Completely free / open-source** (permissive licences) | Use when P1 has no equivalent |
| **P3** | **Free tiers** of services (exact limits stated) | Only when P1/P2 can't do it. Never depend on a free tier for the live demo's critical path |
| ✗ | **Paid third-party tools** | **Forbidden.** Anything that would charge real money → `HUMAN-DECISION-NEEDED` (`AGENTS.md` §12) |

**The "RevenueCat rule" (simplifiers).** Before writing a subsystem from scratch, look for an existing library, repo, or platform that
deletes the work or improves the result (the way RevenueCat replaces a hand-built paywall). §6 lists the approved shortcuts. Custom code
is reserved for **our novelty**: predicates, uncertainty, bisect scheduling, blame, diff, the `.green` language, and the done-gate.

---

## 1. Sponsors & Partners (what they give, how to claim)

| Org | Role | Gives | How to claim | Use in Kodiac | Tag |
|---|---|---|---|---|---|
| **Meta** | Host | **$150 Meta Model API credits per participant** (Muse Spark, Muse Wonder, Muse Image, Muse Voice Transcribe, SAM 3.1); open weights (Muse Glimmer, Muse Spark Open); Muse Code | Credit form in the CV participant guide; **card pre-auth required**; claim by **Wed Nov 4, 9 PM ET**; **set a spend limit** (alerts don't stop billing) | Everything in §2.1 | V ($150) / P (mechanics) |
| **Modal** | Compute partner | **$100 credits** (reportedly the first 1,000 participants) + Starter plan ≈ $30/month (P) | Credit form in Discord `#resources` | Batch SAM 3.1, baselines, policy training, Glimmer serving, **hosted demo (CPU)** | V (amount) / P (cap) |
| **Baseten** | Inference partner | **$100 + 2M TPM** for Meta open-weight models (≤2,000 participants, use-case review) | Credit form in Discord; model string reportedly **`meta-models/muse-spark-open-1026`** (verify in the dashboard) | Open-weights judge row via **Muse Spark Open** (video by URL) | V (amount) / P (model ID) |
| **Fireworks AI** | Inference partner | **$25** (shortlisted teams only) + workshop (Fri Oct 30, 16:00 UTC) | Email notification | Backup open-weights inference (text + images) | P |
| **Cerebral Valley** | Operator | Platform, Discord, submission | — | Submission, office hours | — |

> **Day-1 human action:** claim all four credit sources **today**. They are first-come and "not guaranteed".

---

## 2. P1: Meta + Partner Stack

### 2.1 Meta Model API (one key: `MODEL_API_KEY`; OpenAI-compatible at `https://api.meta.ai/v1`)

| Product | Model ID | Our job for it | Interface | Price | Limits & gotchas | Tag |
|---|---|---|---|---|---|---|
| **SAM 3.1 (hosted)** | `sam-3.1` (the docs also show `sam-3-1`, so confirm via `GET /v1/models` and keep IDs in config) | Object type-check; keyframe concept segmentation; **dense backward window**; live demo | `POST /v1/responses` (OpenAI SDK `client.responses.create`). Video via the Files API (`purpose="user_data"`), **streaming**. Prompts: a noun phrase **or** box/point object prompts (never both). `metadata.propagation_direction = both\|forward\|backward` (backward needs a prompt on a frame > 0). Decode with **`meta-sam-parser`** | **$0.20 / 1k video frames** (≥50 frames billed per request); $2.50 / 1k images | ≤15,000 frames/request; **≤16 objects/frame**; **MP4/MOV H.264/H.265/MPEG-4 only** (transcode AV1/VP9); **no server-side window**, so cut clips client-side; 3,000 RPM; latency unpublished, **measure in P01** | V |
| **Muse Spark 1.3** | `muse-spark-1.3` (Standard); `muse-spark-1.3-contributor` (cheap, **trains on your data**) | `.green` compiler (structured output); two-way crop judge; fact-bound blame sentence; single-pass baseline | Chat Completions / Responses; `response_format=json_schema` or `beta.chat.completions.parse(PydanticModel)`; images in **user** messages only; `input_video` parts | $1.25 in / $4.25 out / $0.15 cached per 1M; contributor $0.10 / $0.20 | 1M context; ~50 images/request; 3,000 RPM / 4M TPM (contributor 150 RPM); hosted video sampling **U**. **Contributor tier is for sim-only data, never real/private footage** | V |
| **Muse Wonder 1.0** | `muse-wonder-1.0` | Hard-case crop adjudication; failure-norm digest narration over a dataset | Same API; `previous_response_id` for server-side chaining | $4 in / $20 out / $0.20 cached per 1M | 1M context. **No "Active Memory" API found**: build memory as a persisted JSON file + long-context call. Live path capped at 3 s | V (model) / U (memory API) |
| **Muse Voice Transcribe 1.0** | `muse-voice-transcribe-1.0` | Spoken instructions → step windows + provenance | **Not OpenAI-compatible.** One-shot `POST https://api.meta.ai/v1/asr/transcribe` (multipart: JSON `request` + `audio`). WAV mono s16 at 24 kHz or 16 kHz | $0.18 / audio hour | **Turn-level timestamps only** (no word timing, no confidence). Use `ENDPOINTING` mode with pauses between instructions; ≤10 min / 32 MB | V |
| **Muse Image 1.0** | `muse-image-1.0` | **Not used** (optional title art only; never claimed as load-bearing) | — | $0.01 / image | — | V |
| **Meta Model API Cookbook** | `github.com/meta-models/meta-model-cookbook` (MIT) | **Copy-paste clients:** `07_sam/01_api_basics/python/sam_api.py`, `06_muse_voice/01_voice_api_fundamentals/utils.py`, structured output, vision input, error handling/backoff, **`14_muse_robotics`** (MuJoCo Panda + SAM + Spark + Voice), **`04_muse_code/07_goal_tracking`** | — | Free | Read first; vendor with attribution | V |

### 2.2 Muse Code (agentic coding product; hosts our plugin)

| Item | Detail | Tag |
|---|---|---|
| CLI | `muse`; `muse exec` (headless one prompt); install per dev.meta.ai docs (check the official install command in P01) | V (CLI) / P (installer) |
| `/goal` | Pins a durable objective; a completion audit gates `update_goal`. Recipe tip: **"name the oracle in the objective"** | V |
| Hooks | 17 events. **`Stop` can block** (exit 2 with stderr text, or `{"decision":"block","reason":…}`) and the model keeps working with the reason as its instruction. `PreToolUse` can deny. Project config **`.muse/hooks.json`** (the workspace must be trusted; `--trust-workspace` for `muse exec`). Default timeout 600 s; payloads > 256 KiB are skipped | V |
| MCP | Project **`.mcp.json`** or `settings.json` `mcpServers` (stdio / streamable-http, **with `env` + `${VAR}`**) | V |
| Plugins | `.muse-plugin/plugin.json`; also reads `.claude-plugin/plugin.json` unchanged. **Plugin hooks and plugin MCP servers get a CLEARED environment (no provider keys)**, so declare our MCP server in `.mcp.json` and have the gate read files, not env vars | V |
| Programmatic | `@muse-code/sdk` (npm, Node 20+, Developer Preview); "Deterministic Replay in CI" cookbook recipe | V |
| **Cost** | **No free tier found** (third parties report $5–$200/month plans or per-token billing). Whether hackathon credits apply is **U**. **Ask in `#office-hours` on day 1.** It is a P1 product central to invariant I7, so if a plan is needed → `HUMAN-DECISION-NEEDED` with the smallest plan and a spend cap | P / U |

### 2.3 Meta open weights & OSS

| Asset | Where | Our use | Requirements | Licence | Tag |
|---|---|---|---|---|---|
| **SAM 3.1 weights** | HF `facebook/sam3.1` (**gated**: request access now), repo `facebookresearch/sam3` | Bulk tracking on Modal (sim pool, audits); exact windows via `start_frame_index` + `max_frame_num_to_track`; backward propagation | Python ≥3.12, torch 2.10 (cu128), CUDA ≥12.6; **`use_fa3=False` on non-Hopper GPUs** (L4/A10G/A100) | SAM License | V |
| **Muse Glimmer 30B** | HF `meta-models/Muse-Glimmer-30B` (bf16, ~60 GB → **budget 72 GB VRAM**) and `…-GGUF` (Q4 ≈ 17–20 GB) | Open-weights crop judge row / private mode | vLLM only via Docker `vllm/vllm-openai:muse-glimmer` (status "unverified end to end"; image input unattested on vLLM); llama.cpp GGUF (vision verified on Apple Metal only); Transformers ≥5.15 "tested". **Don't run greedy** (temp 1.0, top_p 0.95, top_k 64) | Apache-2.0 (P: per Meta's X post; check the model card) | V / P |
| **Muse Spark Open** | HF `meta-models/Muse-Spark-Open-816B-A42B` (can't self-host on our budget) → **hosted on Baseten / Fireworks / Modal** | **Most robust open-weights judge row** (no GPU ops) | Baseten: `https://inference.baseten.co/v1`, image/**video**/audio by URL (video ≤200 MB, ≤96 sampled frames). Fireworks: `accounts/fireworks/models/muse-spark-open` (text + images; `reasoning_effort` required, not `none`) | Muse Model License | V |
| **CoTracker3** | `torch.hub.load("facebookresearch/co-tracker","cotracker3_offline")` | Optional robust point tracks for `moves_with` | GPU recommended | see repo | V |
| **MapAnything** | `facebook/map-anything-apache` (Apache-2.0) | Optional metric monocular depth (Tier A′ scale on real footage) | GPU | Apache-2.0 | V |
| **VGGT-1B** | `facebook/VGGT-1B` (non-commercial) / `-Commercial` (gated) | Alternative depth/camera estimation | GPU | NC / gated | V |
| **torchcodec** 0.17 | PyPI | Frame-accurate decoding to tensors | — | BSD | V |
| **MMS forced aligner** | `torchaudio.pipelines.MMS_FA` (torchaudio 2.11) | Optional word-level timing for step windows | — | NC weights (fine for a hackathon) | V |
| **SAM 2.1** | `pip install sam2` (Apache-2.0) | Fallback tracker (box-seeded from SAM 3.1 image mode) | GPU | Apache-2.0 | V |
| ✗ Llama API | — | **Retired 2026-07-06. Do not use `llama-api-client`.** | — | — | CONTRADICTED |

### 2.4 Partner compute & inference

| Partner | Use | Config | Cost guard | Tag |
|---|---|---|---|---|
| **Modal** (`modal` 1.6.2) | (a) **Hosted demo: CPU** `@modal.asgi_app` with `min_containers=1` **only Nov 4–16**; (b) batch GPU functions (SAM 3.1, Robometer/TOPReward, policy training, Glimmer) that **scale to zero**; (c) Volumes for HF cache + cached replays | Secrets: `meta-model-api` (`MODEL_API_KEY`), `huggingface` (`HF_TOKEN`). GPU per-hour (P): T4 0.59 · L4 0.80 · A10 1.10 · A100-40 2.10 · A100-80 2.50 · H100 3.95 USD | **Never keep a GPU warm** (a 130 h L4 ≈ $104; an H100 ≈ $514). `scaledown_window ≤ 300 s`. Daily spend check | V (API) / P (prices) |
| **Baseten** | Muse Spark Open judge row (video by URL) | `BASETEN_API_KEY`; model string from the credit email | Stop at $90 used | V / P |
| **Fireworks** | Backup open-weights row | `FIREWORKS_API_KEY` | Only if credits are granted | P |

---

### 2.5 Agent runtimes & the Senior Decision Maker channel (required by `AGENTS.md` §6, §16)
| Runtime / model | Role | Cost class | Rule | Tag |
|---|---|---|---|---|
| ORCH runtime (recorded in ADR-0001) | Orchestrator + subagents | The user's existing plan; no new spend | — | V |
| **Antigravity + Gemini 4 Argon** | SDM option B | The user's own access / free quota (verify in P01, ST13) | Use within existing quota only; exhausted → option C/D | U |
| **OpenCode** (MIT, free OSS) **+ DeepSeek V4.1 Flash** | SDM option A | OpenCode free; the model provider is usually pay-per-token | Use the user's existing account/credits. Any new spend → `HUMAN-DECISION-NEEDED` with a hard cap (≤ $5 total; ~8 rulings × ~20k tokens). Never enable auto top-up | U |
| Muse Code | `/goal` host (I7); optional runtime | See §2.2 | — | P/U |

---

## 3. P2: Free & Open-Source Stack (pinned; verified on PyPI 2026-10-27; re-pin after P01 smoke tests)

| Package (version) | Role | Licence |
|---|---|---|
| **openai** 3.40.0 | Single client for Meta API, Baseten, Fireworks, vLLM, llama.cpp (**pass the key explicitly**; it doesn't read `MODEL_API_KEY`) | Apache-2.0 |
| **meta-sam-parser** 0.1.0 | Decode SAM output to masks (raster/RLE/SVG); `build_object_prompt` | SAM License (Meta) |
| **lerobot** 0.6.1 (`[robometer,topreward]`) | LeRobotDataset v3 loading/streaming; **Robometer-4B + TOPReward baselines** (`lerobot.rewards`); ACT/Diffusion training CLI | Apache-2.0 |
| **mani-skill** 3.0.1 (+SAPIEN, mplib 0.1.1) | `StackCube-v1` sim with success oracle; Panda motion-planning expert solutions; ACT/DP baselines; `--save-video`; GPU-parallel envs | Apache-2.0 |
| **mujoco** 3.17.0 | Fallback sim (Meta cookbook `14_muse_robotics` Panda) with `MUJOCO_GL=egl` | Apache-2.0 |
| **mcp** 2.3.0 (or **fastmcp** 4.1.4) | `Kodiac.verify` MCP server. **v2 renamed `FastMCP` → `MCPServer`** (`from mcp.server.mcpserver import MCPServer`) | MIT / Apache-2.0 |
| **typer** 0.27.3 + **rich** 15.0 | CLI; coloured unified diff (`rich.syntax.Syntax(..., "diff")`), tables, progress | MIT |
| **pydantic** 2.14 + **lark** 1.3.1 | Contracts + `.green` grammar (provenance-binding parser) | MIT |
| **av** 19.0.2 (PyAV), **imageio-ffmpeg** 0.6, **opencv-python** 5.0 | Decode, trim, H.264 transcode, contours, `fitEllipse` | BSD/Apache |
| **supervision** 0.31.2 | Mask/box/halo annotators for evidence frames and crops | MIT |
| **shapely** 2.2, **scikit-image** 0.26, **scipy**, **numpy** | Polygons, regionprops, distance transforms, Savitzky–Golay | BSD |
| **filterpy** 2.0 | Kalman smoothing of centroids/bboxes (σ estimation) | MIT |
| **rerun-sdk** 0.40 (+ `gradio_rerun` 0.39) | Frame-by-frame trace viewer: masks + predicate scalars on a timeline; embeddable in Gradio | MIT/Apache |
| **orjson** + **structlog** | Fast `trace.jsonl` writing | Apache/MIT |
| **gradio** 6.30 / **fastapi** 0.162 / **uvicorn** 0.54 | Hosted demo UI/API (served on Modal) | Apache/MIT |
| **huggingface_hub** 2.3.0 / **datasets** 5.1.0 | Verdict export; `create_discussion`; `upload_file(create_pr=True)` (outward → human approval) | Apache-2.0 |
| **polars** / **pyarrow** | `Kodiac_verdicts.parquet` | MIT/Apache |
| **matplotlib** 3.11 / **plotly** 7.1 | Proof chart (static + interactive) | BSD/MIT |
| **statsmodels** / **scipy.stats** | Wilson intervals, McNemar, bootstrap | BSD |
| **uv** 0.13.6, **ruff** 0.17.3, **pytest** 9.1 (+xdist, timeout), **syrupy** 6.1, **hypothesis**, **pre-commit** 4.7 | Tooling; snapshot tests of `.green`/verdict/diff; property tests on predicates | MIT/MPL |
| **Kokoro** 0.9.4 (Kokoro-82M) | Free local TTS voiceover if the human doesn't record their own voice | Apache-2.0 |
| **OBS Studio**, **Kdenlive**, **ffmpeg**, **VHS** (charmbracelet Go binary), **asciinema** | Screen/webcam capture, editing, reproducible terminal takes | GPL/MIT |
| **GitHub Actions** (public repo) | CI: free and unlimited on standard runners for public repos (no GPU) | — |
| **GitHub Pages** | Optional static landing page + mirrored cached replays | Free |
| **Pillow** | Verdict-card composition (`render/card.py`) | HPND |
| **import-linter** (or a pytest import test) | Enforces the layer rule (`ARCHITECTURE.md` §3.2) | BSD-2 |
| **Playwright** (pre-installed Chromium) | Hosted-app E2E tests (P09) | Apache-2.0 |
| **detect-secrets** / **gitleaks** | Pre-commit + history secret scans | Apache/MIT |
| **Manim CE** (or Plotly frame export) | Proof-chart animation (P08) | MIT |
| **MCP Inspector** (`@modelcontextprotocol/inspector`, Node) | Manual MCP testing (P07) | MIT |
| **git filter-repo** | Builds the filtered public mirror (P10) | MIT |
| **ruptures** | `t*` changepoint detection (PELT/Binseg) | BSD-2 |
| **vcrpy / pytest-recording** | Fixture recording for Spark/Wonder/Voice HTTP calls | MIT |
| **tenacity** | Retries/backoff | Apache-2.0 |

**Rule:** transitive dependencies of approved packages are approved. Any package imported *directly* must be listed in this file.

**Datasets (licences checked in P02):** `lerobot/droid_1.0.1` & `lerobot/droid_100` (CC-BY; **15 fps, 320×180, AV1**; most failures lack
instructions) · `nvidia/Cosmos3-DROID` (success/failure split) · RoboRewardBench (`teetone/RoboReward`, CC-BY-4.0; 2,831 human-verified
test labels) · FailBench subsets (release status **U**) · RoboFAC (`MINT-SJTU/RoboFAC-dataset`) · LIBERO via LeRobot ports · BotFails.

**Avoid:** `decord` (stale since 2021) · `from mcp.server.fastmcp import FastMCP` (gone in mcp 2.x) · `llama-api-client` (retired).

---

## 4. P3: Free Tiers (exact limits; never on the critical path)

| Service | Free limit | Use? |
|---|---|---|
| Modal Starter | ≈ $30/month credits, 10 concurrent GPUs, 100 containers (P) | Yes, on top of the $100 |
| HF ZeroGPU | 5 GPU-min/day (free), ≤2 ZeroGPU Spaces (P) | Optional mirror only |
| HF Spaces `cpu-basic` | **Gradio/Docker Spaces now need PRO (HTTP 402 on free)**; Static Spaces free | **Static only** |
| Cloudflare Pages | 500 builds/month; Functions on Workers Free (100k req/day) | Optional static front end |
| HF Inference Providers | ≈ $0.10/month (P) | No (negligible) |

---

## 5. Rejected / Paid Items & Their Substitutes

| Item | Why rejected | Substitute |
|---|---|---|
| HF PRO (for Gradio Spaces) | Paid | Modal CPU endpoint (sponsor credits) + static Pages |
| GPU warm pool for the whole judging window | ≈ $100–500 | CPU endpoint calling hosted SAM 3.1 + Spark; GPUs scale to zero |
| W&B / paid experiment tracking | Paid | CSV/JSON logs + TensorBoard + `experiments/results/*.json` |
| Paid TTS / editing suites | Paid | Own voice, or Kokoro; Kdenlive; VHS |
| Together AI hosting of Glimmer | Not a sponsor, paid | Modal / Baseten / llama.cpp |
| Muse Code paid plan | Possibly required (P1 product) | **Human decision:** smallest plan with a cap, or credits if they apply |

---

## 6. Simplifiers: the "RevenueCat Moves" (per subsystem)

> Format: **Shortcut** → what it replaces → hours saved (estimate). These are pre-approved. Prefer them over custom code.

| # | Subsystem | Shortcut (approved) | Replaces | Saves |
|---|---|---|---|---|
| S1 | **Meta API clients** | **Meta Model API Cookbook**: `sam_api.py` (streaming adapter + parser), Voice `transcribe_recording`, structured-output + vision notebooks, `09_error_handling` backoff | Hand-written SAM stream parsing, multipart ASR, retry glue | 4–6 h |
| S2 | **Mask wire format** | **`meta-sam-parser`** (`parse_responses_stream`, `decode_mask_to_raster`, `build_object_prompt`) | A custom base85/box-local mask decoder | 2–3 h |
| S3 | **Sim task + oracle + expert** | **ManiSkill3 `StackCube-v1`**: red cube on green; `evaluate()` = `on ∧ static ∧ ¬grasped` (literally our test); `solutions/stack_cube.py` motion-planning expert with explicit `close_gripper()`/`open_gripper()` lines (reference for our `pick_place.py` bug sites); `--save-video`; GPU-parallel | Building a sim task, an oracle, an expert, and a recorder | 10–15 h |
| S4 | **Policy training for the proof** | **ManiSkill's own Diffusion Policy / ACT baselines** (state-based; train on its `.h5` demos; evaluate in the same env with the same metric) | A training loop, dataset conversion, an eval harness | 6–10 h |
| S5 | **Baseline judges** | **LeRobot v0.6 `lerobot.rewards`**: `make_reward_model_config("robometer", pretrained_path="lerobot/Robometer-4B")` and `("topreward", vlm_name="Qwen/Qwen3-VL-8B-Instruct")` | Reimplementing two papers | 6–8 h |
| S6 | **Dataset IO** | **`LeRobotDataset(repo, episodes=[i], return_uint8=True)`** / streaming dataset | Parsing v3 multi-episode MP4 shards | 2–3 h |
| S7 | **Agent loop** | **Muse Code `/goal` + completion audit + Stop hook**. We only provide the oracle (`Kodiac gate`) | Writing an agent loop, retries, a judge | 8+ h |
| S8 | **MCP server** | **`mcp` 2.x `MCPServer`** (or `fastmcp` 4) | A JSON-RPC server | 2 h |
| S9 | **Evidence visuals** | **`supervision`** annotators (mask outline, halo, label) | Custom drawing code | 2 h |
| S10 | **Trace viewer** | **Rerun** (`rr.log` images + `SegmentationImage` + scalars on a timeline; `.rrd` per run; `gradio_rerun` embed) | Building a frame scrubber UI | 5–8 h |
| S11 | **Hosted demo** | **Modal `@asgi_app` + Gradio 6** (`gr.Video(sources=["webcam","upload"])`); Modal Volume for the cached replays | Server ops, GPU serving, storage | 4–6 h |
| S12 | **Structured LLM output** | **`beta.chat.completions.parse(response_format=PydanticModel)`** | Prompt parsing + JSON repair | 2 h |
| S13 | **Open-weights switch** | **One OpenAI-compatible client**: `base_url` + `model` from config covers the Meta API, Modal vLLM, Baseten, Fireworks, llama.cpp | Five SDK integrations | 3–4 h |
| S14 | **Publishing verdicts** | **`huggingface_hub`** `upload_file(create_pr=True)` + `create_discussion` (human-gated) | Manual issue writing, custom export | 2 h |
| S15 | **CI without API costs** | **Recorded SAM `output_text` fixtures** replayed through `meta-sam-parser`; **syrupy** snapshots; Muse Code "Deterministic Replay in CI" recipe | Flaky, costly online tests | 3 h |
| S16 | **Terminal shots for the video** | **VHS `.tape` files** | Manual re-takes | 2–4 h |
| S17 | **Word timing (optional)** | **torchaudio `MMS_FA`** (Meta) / WhisperX fallback | Custom alignment | 2 h |
| S18 | **Metric depth (optional)** | **MapAnything** (Meta, Apache) | Building depth estimation | 4+ h |
| S19 | **Reference robotics integration** | **Cookbook `14_muse_robotics`**: MuJoCo Panda pick-and-place with phase callbacks, a success oracle, 30 fps video, and existing SAM/Spark/Voice calls | A fallback sim + integration examples | 4–6 h |
| S20 | **`t*` changepoint** | **ruptures** PELT/Binseg on the blamed margin series | Hand-rolled breakpoint search | 2–3 h |
| S21 | **HTTP fixtures** | **vcrpy / pytest-recording** for Spark/Wonder/Voice (SAM stays on `meta-sam-parser` fixtures) | A custom recorder | 2 h |
| S22 | **Retries** | **tenacity** | Hand-written retry loops | 1 h |
| S23 | **Human labelling + audit review** | **Label Studio** (local, Apache-2.0) or **FiftyOne** (Apache-2.0) | A custom labelling/review HTML | 3–5 h |
| S24 | **Trustworthy prereg timestamp** | Push the `prereg-v0/v1` tags at once + **OpenTimestamps** `ots stamp` (free) | "Trust our commit date" | 15 min |
| S25 | **Uptime alerts** | **UptimeRobot free tier** (P3: 5-min checks) next to the GitHub cron | Late outage discovery | 15 min |
| S26 | **README/X GIFs** | **`agg`** (asciinema GIF) + ffmpeg palettegen | Manual screen-to-GIF | 1 h |
| S27 | **Public mirror** | **git filter-repo** on a fresh clone + `lint_public.py --history` | Manual history surgery (removes a disqualification risk) | 1–2 h |

---

## 7. System Requirements

| Environment | Spec | Notes |
|---|---|---|
| **Core CLI** (`Kodiac-robotics`) | Python **3.12**, ffmpeg ≥6, CPU only | The core calls hosted APIs; **no torch dependency in the core install** |
| **GPU jobs (Modal images)** | CUDA 12.8 base, torch 2.10 (cu128) for `sam3`; L4/A10G for SAM bulk + baselines + training; A100-80/H100 only for Glimmer bf16 (scale to zero) | `use_fa3=False` except on H100 |
| **Sim** | `mani-skill` 3.0.1 needs **Vulkan / a GPU for rendering**: run in a Modal GPU image if the local machine lacks it. MuJoCo fallback renders headless with `MUJOCO_GL=egl`/`osmesa` | Verify in P01 (`python -m mani_skill.examples.demo_random_action -e StackCube-v1 --render-mode rgb_array`) |
| **Dev machine** | Linux/macOS, git, `gh`, `uv`, Node 20+ (only if using `@muse-code/sdk`) | — |
| **Packaging extras** | `[sim]` mani-skill/mujoco · `[proof]` lerobot[robometer,topreward] · `[app]` gradio/fastapi/modal · `[viz]` rerun · `[dev]` tooling | Keeps the base install light (fast `pip install` for judges) |

---

## 8. Accounts & Keys (names only; never commit values)

**Accounts (human creates):** Cerebral Valley · Discord · dev.meta.ai (team, billing card, **spend limit $150**, credit claim) · Muse Code
sign-in · Hugging Face (request access to `facebook/sam3.1`; write token) · Modal (credit form) · Baseten (credit form) · Fireworks (if
shortlisted) · GitHub (public repo) · PyPI (**reserve `Kodiac-robotics` on day 1**, trusted publishing) · X (Most Viral post).

| Env var | Used by | Where stored |
|---|---|---|
| `MODEL_API_KEY` | Meta API: SAM 3.1, Spark, Wonder, Voice | `.env` (gitignored), Modal Secret `meta-model-api`, `~/.config/Kodiac/.env` for hooks |
| `HF_TOKEN` | Gated SAM weights, dataset loading, (human-approved) PRs/discussions | `.env`, Modal Secret `huggingface` |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Deploys (CI optional) | `~/.modal.toml` / GitHub secret |
| `BASETEN_API_KEY`, `FIREWORKS_API_KEY` | Open-weights rows | `.env` |
| `Kodiac_SAM_BACKEND` = `api` \| `modal` \| `fixture` | Segmenter backend selection | config |
| `Kodiac_JUDGE_BASE_URL`, `Kodiac_JUDGE_MODEL`, `Kodiac_JUDGE_KEY` | Open-weights switch | config/.env |
| `Kodiac_CACHE_DIR` (default `.cache/Kodiac`), `Kodiac_ENV_FILE` | Content-hash cache; hooks' cleared env | config |
| `MUJOCO_GL=egl` | Headless MuJoCo | shell |

Agents check **presence only** (`test -n "$MODEL_API_KEY"`) and **never print values**.

---

## 9. Budget Plan & Spend Guards

| Budget | Amount | Allocation (estimate) | Guard |
|---|---|---|---|
| **Meta Model API** | $150 | Engine dev ≈ $10 · `test` ≈ $1 · blame ≈ $3 · Muse Code loop ≈ $10–30 (if billed per token) · proof ≈ $31 · audit ≈ $15 · live app ≈ $9 · **reserve ≥ $40 for judging Nov 5–16** | dev.meta.ai spend limit = $150; server-side rate limiter; cache by content hash; contributor tier for **sim-only** bulk |
| **Modal** | $100 (+ ≈ $30/month Starter) | SAM bulk ≈ $8 · baselines ≈ $2 · Glimmer ≈ $8 · training ≈ $10–31 (36–39 runs) · audit ≈ $3 · CPU demo ≈ $11–22 (Nov 4–16) | Scale to zero; `min_containers=1` only on the demo, only Nov 4–16; alarm at $70 |
| **Baseten** | $100 | Muse Spark Open judge row | Stop at $90 |
| **Fireworks** | $25 (if granted) | Backup | — |
| **Real money** | **$0** | — | Anything else → `HUMAN-DECISION-NEEDED` |

Per-clip cost model (hosted path): coarse pass (6-frame MP4, billed 50 frames) $0.01 + window (50 frames) $0.01 + ≈4 Spark crop calls
≈ $0.0075 → **≈ $0.05–0.09 per clip**. Measure the image-token cost with `POST /v1/responses/input_tokens`.

---

## 10. Top Gotchas (read before coding)

1. `pip install Kodiac` installs a **horticulture package**. Ours is **`Kodiac-robotics`** (import `Kodiac_robotics`, CLI `Kodiac`).
2. The SAM API rejects **AV1/VP9/WebM**: transcode to H.264 `yuv420p`. DROID/LeRobot v3 videos are usually AV1.
3. The SAM API bills **≥50 frames per request** and has **no window parameter**, so cut windows client-side. Batch keyframes into one MP4.
4. SAM `backward` needs the prompt on a frame **after 0**. Seed on the window's last frame.
5. **≤16 objects per frame** on the hosted SAM.
6. Muse Voice gives **turn-level** timestamps only, so pause between instructions (`ENDPOINTING`).
7. Muse Code plugin hooks get a **cleared environment**: the gate reads `.Kodiac/last_verdict.json` and loads keys from `~/.config/Kodiac/.env`.
8. The done-gate must **not** auto-pass when `stop_hook_active` is true. Use an attempt counter (`--max-blocks`).
9. `mcp` 2.x: `MCPServer`, not `FastMCP`.
10. `use_fa3=False` for SAM 3.1 weights on L4/A10G/A100.
11. Glimmer: no greedy decoding; bf16 needs 72 GB VRAM; prefer GGUF on an L4 or Muse Spark Open on Baseten.
12. `muse-spark-1.3-contributor` **trains on your data**: sim-only.
13. ManiSkill `run.py --only-count-success` **discards failures**. Never use it for practice data.
14. StackCube's oracle tolerance (≈3.3 cm xy) ≠ the hero test (1.5 cm). The proof uses `stackcube.green` matched to the oracle.
15. The OpenAI SDK does **not** read `MODEL_API_KEY` automatically. Pass `api_key=` explicitly.
16. Images must be in **user** messages for Muse Spark (system/developer images → 400).
17. HF Gradio Spaces now need PRO. Host on Modal.

---

## 11. Day-1 Smoke Tests (P01 exit gate; each ≤10 min; record results in `.agents/DECISIONS.md`)

| # | Test | Pass criterion |
|---|---|---|
| ST1 | `GET https://api.meta.ai/v1/models` | Lists `sam-3.1` (or `sam-3-1`), `muse-spark-1.3`, `muse-wonder-1.0` |
| ST2 | SAM 3.1 hosted: 50-frame H.264 clip, text prompt "red cube", forward; **plus a 6-frame packed MP4**; plus a test of ≥2 noun phrases in one request | Masks decoded with `meta-sam-parser`; **latency recorded** for each; cost per clip model confirmed |
| ST3 | SAM 3.1 hosted: same clip, box prompt on the last frame, `backward` | Masks on earlier frames; latency recorded |
| ST4 | Muse Spark 1.3: image crop + Pydantic `parse` | Valid `{answer, reason}`; latency recorded |
| ST4b | Muse Spark 1.3: `parse(GreenTest skeleton)` with recursive `Expr` | Valid; else fall back to a flat `CompileDraft` schema (record which) |
| ST5 | Muse Wonder 1.0: same | Valid; latency recorded |
| ST6 | Muse Voice: 10 s WAV with 3 paused instructions, `ENDPOINTING` | 3 turns with `startMs/endMs` |
| ST7 | Muse Code: `.mcp.json` echo tool + `.muse/hooks.json` Stop hook that exits 2 once | The agent continues after the block; tool callable. Also record: (i) do exit 1/3 block? (expected: no); (ii) can `update_goal`(complete) happen while the Stop hook blocks?; (iii) is `/goal` available under `muse exec` (else use `@muse-code/sdk goal/set`) |
| ST8 | Modal: deploy a hello CPU `asgi_app` + an L4 function | Both respond; cold start recorded |
| ST9 | ManiSkill `StackCube-v1` render + `evaluate()` + motion-planning expert, 1 episode with `--save-video` | MP4 + success flag (locally or in a Modal GPU image) |
| ST10 | LeRobot: load `lerobot/droid_100` episode 0 → H.264 export | Plays; fps/resolution recorded |
| ST11 | `facebook/sam3.1` gated access granted? | Yes, or a request is pending (fallback: hosted API only) |
| ST12 | Baseten/Fireworks credits granted? Muse Code billing covered by credits? | Recorded (they drive the scope of F27) |
| ST13 | SDM channel: OpenCode `run` with DeepSeek, or the Antigravity/Gemini route (`AGENTS.md` §6.2) | A ruling round-trips |

---

## 12. Minimal `pyproject.toml` Sketch

```toml
[project]
name = "Kodiac-robotics"
requires-python = ">=3.12"
dependencies = [
  "openai>=3.40", "meta-sam-parser==0.1.0", "pydantic>=2.14", "lark>=1.3", "typer>=0.27", "rich>=15",
  "numpy", "scipy", "opencv-python-headless>=5.0", "av>=19", "shapely>=2.2", "supervision>=0.31",
  "orjson", "structlog", "requests", "ruamel.yaml", "polars", "pyarrow", "pillow", "tenacity", "ruptures",
]
[project.optional-dependencies]
sim   = ["mani-skill==3.0.1", "mujoco==3.17.0"]
proof = ["lerobot[robometer,topreward]==0.6.1", "statsmodels", "matplotlib>=3.11", "plotly>=7.1"]
app   = ["gradio==6.30.0", "fastapi>=0.162", "uvicorn>=0.54", "modal>=1.6.2"]
viz   = ["rerun-sdk>=0.40", "gradio_rerun>=0.39"]
mcp   = ["mcp>=2.3,<3"]
lerobot = ["lerobot==0.6.1", "huggingface_hub>=2.3"]   # needed for lerobot:// refs (pulls torch); the core install stays torch-free
dev   = ["pytest>=9.1", "pytest-xdist", "pytest-timeout", "syrupy>=6.1", "hypothesis", "ruff>=0.17", "pre-commit>=4.7"]
[project.scripts]
Kodiac = "Kodiac_robotics.cli:app"
```

Full snippets (SAM backward window, Modal SAM batch, two-way judge, Voice, LeRobot export, MCP + hooks, Modal demo, LeRobot rewards,
ManiSkill, HF publishing): `docs/research/03_tools_research.md` §7.


*Review round 1 (R1/R2) applied 2026-10-28: see `docs/research/07_fix_ruling.md`.*