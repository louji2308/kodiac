# IDEA.md: Kodiac
## Tests, `git bisect`, and `git blame` for Robots
### *"Robots can finally fail a test."*

```
Concept version : v3.1   (v3.0 = the original master spec; v3.1 = this doc set: claims corrected, gaps fixed. See §14 Changelog)
Event / track   : Meta Global AI Developer Hackathon · Indie Developer track · Theme: "Push the Frontier"
Distribution    : pip install Kodiac-robotics   →   CLI command: Kodiac    (the name "Kodiac" is taken on PyPI)
Status          : DESIGN. Every number in this file is a TARGET or an ILLUSTRATION until measured (see §12)
```

> **One sentence.** Show Kodiac a task once, and Meta's models turn it into a readable, executable test. Kodiac then grades
> every robot video against that test frame by frame, and points to the **exact moment** and the **measured physical cause** of
> every failure. Same robot, same practice data, only the judge changed: **+Y points of success.**

> **Theme fit (official wording):** Kodiac gives robots, and the pipelines that train them, a new capability: knowing *whether*
> a task really succeeded, *exactly when* it went wrong, and *why*. It *"unlocks a better way to understand and control a physical system."*

---

## 0. Concept Invariants (canonical; never change without explicit human approval)

These are the load-bearing walls. An agent may implement an invariant more cheaply. It may **never** rename, remove, or dilute one.
Each invariant has an acceptance check that reviewers run.

| ID | Invariant | Why it carries weight | Acceptance check |
|----|-----------|----------------------|------------------|
| **I1** | **Three verbs:** `Kodiac test` · `Kodiac run` · `Kodiac blame` / `Kodiac diff` | The whole metaphor ("tests, `git bisect`, `git blame` for robots") maps onto habits every engineer and judge already has | `Kodiac --help` lists `test`, `run`, `blame`, `diff`. Utilities (`gate`, `mcp`, `serve`, `audit`) are never marketed as verbs |
| **I2** | **"Show it once."** One human demo + three short spoken instructions compile into a human-readable `.green` test. **Every check links to the sentence that produced it** | This is the new capability: specification by demonstration, with no reward engineering and no labelling | Every compiled step carries a provenance quote and a `[m:ss.s–m:ss.s]` span |
| **I3** | **Verdicts: `PASS` / `FAIL` / `CAN'T TELL`.** Kodiac doesn't guess when it can't see. If the camera can't see it, it says `CAN'T TELL` with a reason | Attacks the documented weakness of video judges (leaning "success" under ambiguity) | The verdict enum has exactly 3 values. User text says `CAN'T TELL` (never "UNKNOWN"). JSON `CANT_TELL`, exit code 2. Every CAN'T TELL carries a reason code |
| **I4** | **`blame` = exact onset frame `t*` + measured physical cause** (numbers in cm/s with ±σ, not adjectives) | The hero. The `git blame` moment no whole-clip score gives | `blame` output always has `t*` in seconds, the frame index at native fps, the broken predicate component, and ≥1 measured number with σ |
| **I5** | **Event-level `diff`** of demo vs. attempt, rendered like `git diff` | Makes the cause legible at a glance and completes the git metaphor | `Kodiac diff` prints unified-diff lines: step, event, measurement, timestamp |
| **I6** | **Measured, not guessed.** SAM 3.1 masks drive six measured predicates. The VLM judges **appearance only**, on zoomed crops. The one-sentence summary may contain **only measured numbers** | Credibility: every claim traces to a measurement | Exactly 6 predicate names in the grammar. The summary validator rejects any number or object not in the fact table |
| **I7** | **Closing the loop:** a Muse Code plugin (MCP tool `Kodiac.verify`) plus a **done-gate that blocks `/goal` from completing until `Kodiac run` returns PASS** | Turns Kodiac from an evaluator into a development tool | A recorded attempt to finish `/goal` while FAIL is refused. A `.green` hash change is refused |
| **I8** | **Headline proof: "Same robot, same practice data, only the judge changed: +Y points of success."** A controlled retraining experiment where only the episode judge varies | Converts "nice tool" into measured downstream impact | Pre-registered protocol committed **before** runs. Y is filled only from measured results with a 95% CI |
| **I9** | **Opening shot: real public episodes** that were published as successful demonstrations freeze at the `blame` frame with a red SAM outline. "Hand-verified" | Proves the problem exists in data people use today | Every flagged episode shown is human-verified. N and X are computed, not estimated |
| **I10** | **Live hosted demo:** a judge pastes a dataset ID or uploads a clip and gets the verdict + diff + blame with an on-screen timer. Cover the camera and get `CAN'T TELL`. A clearly labelled **"Instant Cached Replay"** | Shows the claims hold up live and unscripted | Timer visible. Cached results visibly badged. An occluded input yields CAN'T TELL with a reason |
| **I11** | **3-minute video, 8-concept cap, banned-word list** | Judges remember about 8 things | The voiceover passes the concept-ledger count (≤ 8) and the banned-word lint (§10.3) |
| **I12** | **Name / title / tagline:** Kodiac · "Tests, `git bisect`, and `git blame` for Robots" · ***"Robots can finally fail a test."*** | Brand memory | The tagline is the last spoken line of the video and the README's H3 |
| **I13** | **100% software.** No robot arm, glasses, or hardware needed to judge or reproduce. Real footage comes from public datasets. Simulation is labelled | Indie feasibility; anyone can reproduce | No step requires hardware beyond an optional webcam and microphone |
| **I14** | **Meta stack is load-bearing.** Each Meta model has one distinct job, and removing it breaks a named feature (§7) | 25% of the score: "Use of Meta AI tooling" | `ARCHITECTURE.md` lists, per model, the feature that breaks without it |
| **I15** | **Honesty affordances:** hand-verified flags, labelled simulation, one unedited `/goal` take, labelled cached replay, shipped-status table, pre-registered experiment, n + 95% CI on every metric | Judges discount staged demos. These labels are part of the concept, not polish | Each appears as a visible label or artifact in the submission |
| **I16** | **The same test grades a human demonstration and a robot attempt** (effector aliasing `gripper ↔ hand`). Closing line (v3.1 wording): ***"The same test checks the demonstrations robots learn from."*** | Extends value from robot policies to the *demonstration data* robots learn from | At least one human-hand demonstration is graded by the same `.green` file that grades robot attempts |
| **I17** | **Six predicates, exact names:** `on`, `inside`, `near`, `lifted`, `moves_with`, `dwell` | A small closed vocabulary keeps tests readable, lintable, and compilable from speech | The grammar enumerates exactly these. Appearance uses `looks(...)`; non-visual uses `MANUAL(...)`. Neither is a predicate |

> **⚠ Human confirmation requested (v3.1 change to I16's closing line):** the original line *"The same test can check the person who
> teaches the robot"* reads as AI grading human workers. That is close to the hackathon's banned "job screener / personality analyzer"
> categories (see `HACKATHON.md` §2 R2). The capability is unchanged; only the framing moved from *people* to *data*.

---

## 1. The Pitch

**30-second version.**
> Code has tests and `git blame`. Robots have someone scrubbing through video. Robot learning runs on people watching footage to decide
> which attempts *really* succeeded, and when they get it wrong, failed attempts saved as "success" poison the training data.
> Kodiac lets you **show a task once**: your demo and three spoken instructions become a 4-line test. Then it grades every robot
> video frame by frame with Meta's SAM 3.1 as a measuring instrument, says **PASS, FAIL, or CAN'T TELL**, and on failure points
> to the **exact frame** and the **physical cause**: "released 0.4 s early, 2.6 cm left of the target." Plug it into Muse Code and
> the agent fixes the robot program until the test passes. Swap it in as the judge for robot self-practice and we measure how much better the robot
> learns from the same data. **Robots can finally fail a test.**

**Who it's for (named beneficiaries).**
1. **Robot-learning engineers** who filter self-practice rollouts or evaluate policies and currently scrub video by hand.
2. **Dataset curators and maintainers** (Hugging Face LeRobot hub, DROID-style collections) whose "successful demonstrations" contain silent failures.
3. **Developers writing robot control code with coding agents** (Muse Code users), who need a physical-world oracle to say "done".

---

### 1.1 The five things to remember
1. **Show it once → a test.** One demo + three spoken instructions become a 4-line, readable test (F02–F08).
2. **Measured, honest verdicts.** PASS / FAIL / CAN'T TELL from SAM 3.1 measurements with ± error bars; it abstains when it can't see (F16–F24, F28).
3. **`blame` + `diff`.** The exact frame it went wrong and the measured cause, plus a demo-vs-attempt diff (F31–F34). ← the hero
4. **A coding agent that can't say "done" early.** The Muse Code done-gate (F38–F40).
5. **Proof.** Only the judge changed → +Y points (F43, simulation), real public datasets audited by hand (F49), and measured review time saved (P-7).

---

## 2. The Problem (claims in safe, sourced wording)

> Every sentence here was checked by the claims researcher (`docs/research/04_related_work.md` §A). Use **only** these wordings in public.

1. **Robot evaluation runs on human labor.** *"Evaluating one generalist policy (OpenVLA) took 2,500+ real-robot rollouts and 100+ hours of
   human labor to reset, run and score."* (AutoEval, CoRL 2025.) Contributors who film chores for robot training are a fast-growing
   source of data: *"In 2026 DoorDash started paying couriers to film household chores for AI and robotics training (the Tasks app,
   piloted in select U.S. markets)."* As more robot training data comes from crowdsourced video, the question becomes: **which of these demonstrations actually completed the task?**
2. **Automated video judges are not reliable enough.** *"On FailBench (Sep 2026; 2,197 attempts, 14 sources), the best of 13 VLM judges
   reached 0.77 mean balanced accuracy, and none exceeded 0.60 on contact-heavy assembly. The authors observed judges leaning toward
   'success' when evidence was ambiguous."*
3. **Even good scores don't say where or why.** *"Reward models give a success score or progress curve. They don't say which physical
   relation broke, by how much, or whether the camera could even see it."* Engineers still scrub footage to find a half-second slip.
4. **Wrong labels teach robots the wrong thing.** A failed attempt saved as "success" becomes poison in behavior cloning. Prior work
   observes false successes in robot-labelled episodes (silent-failure observability study, 2026). Learning-from-mixed-quality work
   warns that naive filtering needs low label noise (PU-learning BC, CoRL 2023).

**Never say (CONTRADICTED or UNVERIFIED):** "directly implements Robot Utility Models" · "all 13 judges lean toward success" · "opened to
8M couriers" · "reward models only score whole clips" · "two-way questioning cancels positivity bias" · "DROID ground-truth human labels"
· "labelled 'success'" for LeRobot community datasets (most have no success field; say "published as successful demonstrations").

---

## 3. The Solution at a Glance

```
   ┌───────────── SHOW IT ONCE ─────────────┐      ┌────────────── GRADE EVERY ATTEMPT ──────────────┐     ┌──────── EXPLAIN & FIX ────────┐
   │ webcam demo + 3 spoken instructions     │      │ robot video (real dataset / sim / upload)        │     │ blame: t* + measured cause    │
   │   Muse Voice Transcribe → step windows  │      │   2-stage bisect → 50-frame dense window          │     │ diff: demo vs attempt events  │
   │   Muse Spark 1.3 → 4-line .green test   │ ───▶ │   SAM 3.1 masks → 6 measured predicates ± σ       │ ──▶ │ hint: one-variable correction │
   │   SAM 3.1 → objects exist? baselines    │      │   appearance? → Spark crops, 2 ways → Wonder      │     │ Muse Code /goal + done-gate   │
   │   linter → MANUAL for non-visual checks │      │   PASS / FAIL / CAN'T TELL + evidence + trace     │     │ → patch → re-run → PASS       │
   └─────────────────────────────────────────┘      └──────────────────────────────────────────────────┘     └───────────────────────────────┘
                                                            │
                                     ┌──────────────────────┴───────────────────────┐
                                     ▼                                              ▼
                       PROOF: only the judge changed → +Y         AUDIT: public datasets → hand-verified flags,
                       (retrain on accepted practice data)        failure-norm digest (Muse Wonder), verdict export
```

---

## 4. Feature Catalog (every feature, in detail)

Legend: ⭐ = headline feature shown in the video · 🧪 = proof feature · 🛡 = honesty/robustness feature · `F##` = feature ID (shared with
`ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`) · **Tier** = MVP / Strong / Full (see §11).

### 4.1 Verb 1: `Kodiac test`, "Show It Once" ⭐

An expert performs the task once in front of a webcam while speaking three short instructions, for example *"pick up the red block · put
it on the green one · let go."* Kodiac compiles that into a test.

| ID | Feature | What it does (user-facing) | How it works | Meta model | Tier |
|----|---------|----------------------------|--------------|-----------|------|
| F01 | **Demo capture** | `Kodiac test --webcam` records ≤20 s of video and audio. `--video demo.mp4` is also accepted | OpenCV/ffmpeg capture; audio extracted to mono 16-bit WAV at 24 kHz | — | MVP |
| F02 | **Speech → step windows** | Shows the transcript split into instructions, each with its time span | **Muse Voice Transcribe 1.0** in `ENDPOINTING` mode (one pause = one turn = one step window; it gives turn-level timestamps only). Optional Meta MMS forced alignment for word timing | Muse Voice Transcribe | MVP |
| F03 | **Spec compiler** | Prints a readable `.green` test live | **Muse Spark 1.3** structured output (JSON schema → Pydantic `GreenTest`). Spark chooses the **structure**. Thresholds come from the demo's own measurements (F08), not from the LLM | Muse Spark 1.3 | MVP |
| F04 | **`.green` language + lock file** | A 4-line, human-editable test plus a machine `.green.lock` (baselines, transcript, model versions, hashes) | Custom grammar (Lark) that **binds** the `# "quote" [t0–t1]` provenance to its step (YAML would drop comments). Round-trip parse ↔ print | — | MVP |
| F05 | **Per-step provenance** | Every check shows the sentence that produced it and its time span. Click to jump to that moment | Provenance `{quote, t_start, t_end, source}`, where `source ∈ voice / text / compiler-default / user-edit` | (Voice output) | MVP |
| F06 | **Compile-time spec linter** | Non-visual requirements ("don't slam it", torque, force, weight) become `MANUAL(...)` instead of being faked. Also catches type errors, wrong comparator direction, and missing provenance | Rule table + keyword ontology. Diagnostic codes E001–E005, W101–W105 | (Spark proposes, rules decide) | MVP |
| F07 | **Object type-check** | "Object `green_block` not found in demo → test does not compile." Records each object's baseline scale and, for containers, the rim ellipse | **SAM 3.1** text-prompted concept segmentation on 2–3 demo keyframes. Ambiguity (≥2 instances) → E002 | SAM 3.1 | MVP |
| F08 | **Demo self-test** | The demo must PASS its own test with margin ≥ 2σ. Thresholds derive from what the expert actually did (demo lift 4.2 cm → `min_cm=2.0`) | Runs the `run` engine on the demo; suggests edits (E005/W103) | SAM 3.1 | MVP |
| F09 | **Text-compile mode** | `Kodiac test --from-text "put the red cube on the green cube" --first-frame ep.mp4` compiles a test from a dataset's task string, with no voice demo | Spark compile + SAM existence check on the first frame. Provenance = the task string | Muse Spark 1.3, SAM 3.1 | MVP (needed for the audit, the DROID slice, and the hosted app) |
| F10 | **Effector aliasing** | `gripper` means the robot gripper in robot clips and the hand in human clips. One test grades both | Role-based prompt sets; clip type auto-detected by the higher SAM score | SAM 3.1 | MVP (required by I2 and I16) |

**Example output (illustrative):**
```text
# stack_blocks.green — compiled from 11 s webcam demo
objects: [gripper, red_block(size_cm=4), green_block(size_cm=4)]
1. grasp:   moves_with(gripper, red_block) and lifted(red_block, min_cm=2.0)               # "pick up the red block" [0:01.2–0:04.0]
2. place:   on(red_block, green_block, align_xy_cm<=1.5)                                   # "put it on the green one" [0:04.1–0:07.5]
3. release: not moves_with(gripper, red_block) and dwell(red_block, green_block, for_s=0.5) # "let go" [0:07.6–0:10.4] (+dwell: compiler default)
```

### 4.2 Verb 2: `Kodiac run`, "Grade Every Attempt, Frame by Frame" ⭐

| ID | Feature | What it does | How it works | Meta model | Tier |
|----|---------|--------------|--------------|-----------|------|
| F11 | **Universal ingest, fps-agnostic time** | Accepts MP4/MOV/WebM, a LeRobot `repo_id/episode/camera`, or a sim run. Reports time in seconds and frames at the **native** fps (30 webcam, 15 DROID, sim per config) | PyAV/torchcodec decode. LeRobot v3 episode resolution. Transcode to H.264 `yuv420p` (the SAM API rejects AV1/VP9) | — | MVP |
| F12 | **Object tracking with stable IDs** | Multi-object masks per frame with persistent IDs | **SAM 3.1 Object Multiplex**: hosted API (`sam-3.1`) for live and real clips; self-hosted open weights on Modal for bulk | SAM 3.1 | MVP |
| F13 | **Two-stage `git bisect` fast path** ⭐ | Grades a 15 s clip live in seconds without tracking every frame | **Stage 1:** 6 coarse keyframes (static proxies of each step) bracket the broken transition. **Stage 1.5:** binary halving on a *monotone* target until the bracket ≤ 50 frames (this makes "bisect" literally true). **Stage 2:** dense SAM 3.1 tracking only in that window | SAM 3.1 | MVP |
| F14 | **Dense backward window** ⭐ | Frame-exact onset `t*` | SAM 3.1 seeded on the window's **last** frame, `propagation_direction=backward` (native in API and weights). The window is cut client-side (≥50 frames per request is the billing minimum) | SAM 3.1 | MVP |
| F15 | **Scale model (px → cm)** | Every number in cm with ±σ, portable across cameras | Tier A: calibrated (sim/known intrinsics). Tier B: ground-plane self-calibration from resting objects + size priors (default for webcams). Tier C: single reference (σ inflated → honest CAN'T TELL). Optional metric depth from Meta **MapAnything** | (Meta OSS optional) | MVP |
| F16 | **`on(A,B)`** + 2.5D depth check | "red_block on green_block (offset 0.3 ± 0.4 cm)" | xy offset + vertical gap + **scale-ratio consistency** (catches A hovering in front of B) | SAM 3.1 | MVP |
| F17 | **`inside(A,B)`** + 2.5D rim-occlusion | Catches an apple held *in front of* a bowl | Rim-ellipse fit, occlusion order ("who hides whom"), scale ratio A(t)/A(0), rim-crossing memory, object permanence | SAM 3.1 | MVP-lite / Strong-full |
| F18 | **`near(A,B)`** | "gripper within 0.8 cm of drawer" | Boundary distance (distance transform) + depth extent | SAM 3.1 | MVP |
| F19 | **`lifted(A)`** | "red_block lifted 4.2 cm" | Ground-plane height of the bottom anchor, so moving *away from the camera* is not mistaken for lifting | SAM 3.1 | MVP |
| F20 | **`moves_with(E,A)`** | "red_block moves with gripper (slip 0.2 cm)" | Attach/detach **state machine** on relative displacement, with hysteresis. Optional Meta **CoTracker3** point tracks for robustness | SAM 3.1 (+CoTracker3) | MVP |
| F21 | **`dwell(A[,B])`** | "red_block stayed on green_block 0.9 s" | Run-length of stillness ∧ relation | SAM 3.1 | MVP |
| F22 | **Smoothing & hysteresis** 🛡 | Stable timelines; no flicker events | Hampel → Savitzky–Golay → tri-state Schmitt trigger | — | MVP |
| F23 | **±σ uncertainty + margin gate** 🛡 | Every margin printed `value ± σ`. If `|margin| < σ` → `CAN'T TELL` | Jitter σ_px from mask/bbox second differences → Monte-Carlo propagation through the scale model. One σ-inflation factor λ is calibrated on sim ground truth | — | MVP |
| F24 | **Occlusion & view gates** 🛡 ⭐ | `CAN'T TELL (target occluded 46% at step 2)`; a covered lens gives `CAN'T TELL (view blocked)` | Visible vs. expected area (scale-corrected). Luminance/blur/uniformity check. Exclusions: container→contents, carried object | SAM 3.1 | MVP |
| F25 | **Two-way contrastive crop judge** | Appearance-only checks (`looks(lid, "closed flush" \| "open or ajar")`) asked as **two opposite states** on zoomed, mask-outlined crops | **Muse Spark 1.3**, structured `{yes\|no\|cant_tell, reason}`. Antonym phrasing (never "NOT closed?": VLMs mishandle negation). Agreement → decided; conflict → escalate | Muse Spark 1.3 | Strong |
| F26 | **Hard-case escalation** | Contested crops get a stronger look; still contested → `CAN'T TELL (appearance unresolved)` | **Muse Wonder 1.0**. Live path capped at 3 s | Muse Wonder | Strong |
| F27 | **Open-weights / private mode** (`--local-glimmer`) | Same pipeline with no pixels leaving infrastructure you control | OpenAI-compatible base-URL switch to **Muse Glimmer 30B** (Modal vLLM / Baseten / llama.cpp GGUF) or **Muse Spark Open** on partner inference. Self-hosted SAM 3.1 | Muse Glimmer 30B / Muse Spark Open | Strong (measured row) / Full (end-to-end privacy) |
| F28 | **Verdict + reason codes + exit codes** | `PASS` (exit 0) / `FAIL` (1) / `CAN'T TELL` (2) / error (3), for CI and the done-gate | Kleene 3-valued logic; the overall verdict = the first non-PASS step | — | MVP |
| F29 | **Evidence frames** | PNGs with the red SAM outline, the measured numbers, and the timestamp burned in | `supervision` annotators | SAM 3.1 | MVP |
| F30 | **`trace.jsonl` + provenance viewer** 🛡 | Every printed number is traceable to its frame, mask, metric, and model call. Visual timeline viewer | Append-only JSONL. **Rerun** `.rrd` recording (masks + predicate scalars on a timeline). HTML report | — | MVP (JSONL) / Strong (viewer) |

**Example output (illustrative):**
```text
$ Kodiac run stack_blocks.green lerobot://<dataset>/episode_000123
  step 1 grasp    PASS   0:01.4   lifted 4.2 ± 0.3 cm · moves_with ✓
  step 2 place    FAIL   0:03.8   moves_with T→F (released 2.6 ± 0.4 cm from green_block)
  step 3 release  —      (not reached)
FAIL · blame: gripper released red_block 0.4 ± 0.07 s before reaching green_block (xy offset 2.6 ± 0.4 cm at 0:03.8, frame 114 · SIM 30 fps)
evidence: runs/…/f114_overlay.png · trace: runs/…/trace.jsonl · 7.9 s
```

### 4.3 Verb 3: `Kodiac blame` and `Kodiac diff`, "The Exact Moment and the Physical Cause" ⭐ (the hero)

| ID | Feature | What it does | How it works | Meta model | Tier |
|----|---------|--------------|--------------|-----------|------|
| F31 | **Step-chain transition finder** | Names the failed step **and** the prerequisite that broke first ("`moves_with` went True→False before `on` became True") | **Carried literals:** a step's positive literals must persist until a later step negates them. Four failure classes: broken prerequisite, unmet condition, order violation, transient break (warning only) | — | MVP |
| F32 | **Exact `t*` by backward refinement** ⭐ | `t* = 0:03.8 · frame 114 (±1 frame)` | Changepoint on the blamed literal's margin series inside the dense backward window. `σ_t*` by bootstrap | SAM 3.1 | MVP |
| F33 | **One-sentence summary bound to measurements** 🛡 | One plain sentence. Every number in it exists in the fact table | **Muse Spark 1.3** gets the fact table only (no pixels). A validator checks numbers, objects, and licensed verbs ("opened" only if an aperture event or a sim span exists). Fallback: a deterministic template | Muse Spark 1.3 | MVP |
| F34 | **Event-level reality diff** ⭐ | `git diff`-style: `-` expert event, `+` robot event, with measurements and times | Event extraction from both runs, aligned by LCS (Myers) on event signatures, **not** timestamps | — | MVP |
| F35a | **Blame target, real footage** | `t* = 0:03.8 · frame 114 · LeRobot index 58231` (+ action chunk if the policy's chunk size is known) | Native-fps frame + dataset metadata | — | MVP |
| F35b | **Blame target, sim code** ⭐ | `pick_place.py:42 -> gripper.open()` | Runtime **span logging** wraps the robot API (`gripper.open/close`, `arm.move_to`, `lift`, `wait`). Maps t* → latest span of the matching actuation class. AST resolves the statement | — | MVP |
| F36 | **Prefix salvage** 🧪 | `--salvage` exports the valid pre-failure part `[0, t* − 0.5 s]` as clean training data | Cut so that no action chunk crosses `t*`; flagged partial | — | Strong (experiment arm) / MVP (export flag) |
| F37 | **Corrective hint** | `hint: release_time +0.4 s` or `place_xy −2.6 cm (camera-x)` | The single scalar or ordering change that flips the blamed margin to ≥ +σ, from the fact table and the demo event | — | MVP |

**Example (illustrative):**
```diff
--- demo.mp4 (expert)
+++ episode_000123 (attempt)
  step 1: moves_with(gripper, red_block) and lifted(red_block, 4.2 cm)        [PASS · 0:01.4]
- step 2: red_block released on green_block (offset 0.3 cm, after contact)
+ step 2: red_block released 2.6 cm camera-left of green_block (0.4 s before contact · 0:03.8)
```

### 4.4 Closing the Loop: Native Muse Code Plugin ⭐

| ID | Feature | What it does | How it works | Meta product | Tier |
|----|---------|--------------|--------------|-------------|------|
| F38 | **MCP tool `Kodiac.verify`** | Muse Code calls `verify` and receives the verdict, blame, diff, hint, and evidence paths | MCP Python SDK 2.x (`MCPServer`). Declared in the project `.mcp.json` with `env` passthrough | Muse Code | MVP |
| F39 | **Done-gate** 🛡 ⭐ | `/goal` **cannot complete** until a *fresh* `Kodiac run` returns PASS **and** the `.green` hash and threshold config are unchanged (the agent can't cheat by weakening the test) | Muse Code **Stop hook** (`.muse/hooks.json`) runs `Kodiac gate`, which exits 2 with the blame text unless PASS. Muse Code keeps working with that text as its instruction. Hash pin + nonce + attempt cap | Muse Code | MVP |
| F40 | **`/goal` recipe** | `/goal Fix pick_place.py so the robot stacks red on green. Done ONLY when Kodiac run prints PASS.` | Follows Meta's official goal-tracking cookbook ("name the oracle in the objective") | Muse Code | MVP |
| F41 | **Sim harness** | `Kodiac run --sim pick_place.py` renders and grades a scripted attempt | **ManiSkill3 `StackCube-v1`** (red cube on green, a built-in success oracle, a motion-planning expert) + a robot-API wrapper with span logging. Fallback: Meta's cookbook MuJoCo Panda (`14_muse_robotics`) | — | MVP |
| F42 | **10 seeded physical bugs + fix-rate eval** 🧪 | "N/10 fixed automatically." The hero fix is recorded in **one unedited take** | B1 early release · B2 xy offset · B3 low lift · B4 short dwell · B5 inverted order · B6 grasp too high · B7 missing close · B8 wrong object · B9 never releases · B10 release too high. Fix = gate PASS ∧ oracle success ∧ test hash unchanged within ≤5 iterations. All transcripts published | Muse Code | MVP |

### 4.5 Proof Suite 🧪

| ID | Feature | What it shows | How | Tier |
|----|---------|---------------|-----|------|
| F43 | **Headline: "Only the judge changed"** ⭐ | Downstream robot success vs. each judge's false-PASS rate | ManiSkill3 StackCube: weak-policy practice rollouts plus pre-registered perturbed-expert near-misses → each judge labels the same pool → retrain the **same** state-based policy (fixed gradient steps, 3 seeds) on each judge's accepted set → evaluate on ≥200 oracle-scored episodes per seed | MVP-min / Strong |
| F44 | **Fair baselines** | Kodiac vs. a single-pass VLM (Muse Spark 1.3 on the whole clip at 2 fps: "same Meta model, better method"), **Robometer-4B**, **TOPReward** (both in LeRobot v0.6), Oracle, Accept-all, a size-matched random control, and an oracle + k% injected false-PASS dose-response series | Thresholds for score-based judges are tuned on a held-out calibration split (their best case) | MVP (≥4 arms) / Strong (all) |
| F45 | **Judge benchmark table** | False-PASS, accepted-set contamination, false-REJECT, **coverage**, balanced accuracy, AUROC, with Wilson 95% CIs and McNemar tests | Same episodes for every judge. CAN'T TELL counts as "not accepted" for filtering, and coverage is always shown (so abstaining can't game the metric) | MVP |
| F46 | **Real-footage validation** | The false-PASS ranking holds on real robot video | Real-video subsets with independent human labels (RoboRewardBench test split; FailBench subsets if released) + **our own blind-labelled DROID slice** (stated annotator count; Cohen's κ if 2 raters) | Strong |
| F47 | **Proof chart** ⭐ | The 1:50 chart: y = downstream success, x = false-PASS rate, one point per judge with CIs | matplotlib/Plotly; sim clearly labelled | MVP |
| F48 | **Meta ablation ladder** | "Each stage adds": R1 SAM 3.1 + predicates → R2 + Spark single question on mask crops → R3 + two-way questioning → R4 + Wonder escalation → R5 + calibrated σ gate | Benchmark that **includes appearance tasks**, so the VLM rungs have something to do | Strong |

**Experiment lineage (cite correctly):** the recipe follows autonomous-improvement work where a judge picks which practice episodes count
(SOAR, CoRL 2024; Self-Improving EFMs, NeurIPS 2025; VERITAS, RSS 2026). The closest "only the reward changed" design is RoboReward (2026).
Oracle filtering is the MimicGen-style ceiling. Robot Utility Models (NYU, 2024) used a GPT-4o check to decide when to *retry*, not to
filter practice data.

### 4.6 Public Dataset Audit (the opening shot) ⭐

| ID | Feature | What it does | How | Meta model | Tier |
|----|---------|--------------|-----|-----------|------|
| F49 | **Audit of public robot datasets** | Runs Kodiac over 2–3 popular public datasets (LeRobot hub / DROID). On screen: *"N episodes published as successful demonstrations checked · at least X% didn't do their task · hand-verified."* Three flagged episodes freeze at the blame frame | Text-compile per task string → batch `run` → **human verification** of every flag shown | SAM 3.1, Muse Spark 1.3 | MVP (≥20 flags, 1 dataset) / Strong (≥40 flags, 2–3 datasets) |
| F50 | **Failure-Norm Digest** | "Most failures in this dataset happen at step 2 (release): 68% [CI]" (illustrative) | **Numbers are computed deterministically** (histogram + Wilson CI over blame records). **Muse Wonder** clusters and narrates them over its 1M context, and keeps a persisted memory file across audits (`previous_response_id` chaining). Described as "Muse Wonder's long-horizon memory over the dataset", not as an "Active Memory API" | Muse Wonder | MVP (narration) / Full (cross-dataset memory) |
| F51 | **LeRobot-compatible verdict export** | `Kodiac_verdicts.parquet` keyed by `episode_index` (verdict, t*, step, predicate, margin, σ, evidence URI, model versions) | Mirrors LeRobot's reward-parquet conventions; optional filtered dataset | — | MVP |
| F52 | **Helpful community reports** | One consolidated, hand-verified, polite report per dataset (HF discussion / PR with the verdict file) | `huggingface_hub` `create_discussion` / `upload_file(create_pr=True)`. **Outward action: human approval required.** Opened early so maintainers can reply before judging (external validation) | — | Strong |

### 4.7 Live Hosted Demo ⭐

| ID | Feature | What it does | How | Tier |
|----|---------|--------------|-----|------|
| F53 | **Hosted web app** | Paste a curated dataset ID (episode + camera picker), upload a clip, or record a webcam clip → verdict + diff + blame frame | Modal `@asgi_app` (FastAPI + Gradio), **CPU** container; the hosted Meta APIs do the heavy lifting | MVP |
| F54 | **Live wall-clock timer, "<12 s"** | The timer starts on "Grade" and stops when the verdict renders | Fast path F13. Metadata pre-fetch on paste (disclosed). Live Wonder capped at 3 s. Public claim is p95 < 12 s, **only if measured** | MVP |
| F55 | **Camera-cover test + occlusion brush** 🛡 | Cover the webcam → `CAN'T TELL (view blocked)`. Or paint an occluder over a robot clip → `CAN'T TELL (target occluded 46% at step 2)`. Works without props | Browser `MediaRecorder` clip; occluder rectangles applied before grading | MVP |
| F56 | **"Instant Cached Replay" (labelled)** 🛡 | Precomputed results for curated episodes, with a visible **CACHED** badge | Results stored in a Modal Volume, keyed by content hash | MVP |
| F57 | **Operations guard** 🛡 | Works Nov 4–16; rate limits; clip caps (20 s / 50 MB); uploads auto-deleted after 24 h (visible notice); spend caps; uptime monitor | Modal + server-side limiter + daily spend check | MVP |

### 4.8 Shipping

| ID | Feature | Detail | Tier |
|----|---------|--------|------|
| F58 | **pip package + CLI** | `pip install Kodiac-robotics` → `Kodiac` command; `uvx --from Kodiac-robotics Kodiac` | MVP |
| F59 | **3-minute video** | 8 concepts, banned-word lint, plain-language voiceover with dev terms as on-screen text | MVP |
| F60 | **README + write-up** | Live URL at the top, theme sentence, a "which Meta model does what" table, an eval table with n/CI, a failure gallery, a **shipped-status table**, a dated `BUILD_LOG.md`, `ATTRIBUTIONS.md` | MVP |

---

## 5. The `.green` Test Language (summary)

- **Closed vocabulary:** 6 predicates (`on`, `inside`, `near`, `lifted`, `moves_with`, `dwell`), `looks(obj, "state" | "opposite")` for
  appearance checks, and `MANUAL("…")` for non-visual requirements. Boolean `and`, `or` (warned), `not`.
- **Canonical form is literally 4 lines:** `objects:` + 3 steps (the `steps:` header is optional). Units are always cm / s.
- **Provenance is data:** `# "spoken instruction" [m:ss.s–m:ss.s]` is bound to its step by the grammar.
- **Machine state lives in `<name>.green.lock`** (transcript, baselines, rim ellipses, size priors, demo events, model IDs, hashes).
- **Parameters have fixed directions** (`align_xy_cm` is an upper bound, `min_cm` a lower bound). The wrong direction is error E004.
- **Proof-task variant** `stackcube.green` uses `align_xy_cm<=3.33, gap_cm<=0.5` plus `dwell(for_s=0.5)` and `not moves_with` to **approximate** ManiSkill's oracle (differences listed in the pre-registration; ground truth = oracle `success` at the final step).
- Full grammar, types, and diagnostics: `ARCHITECTURE.md` §6.

More examples:
```text
# fruit_in_bowl.green
objects: [gripper, apple(size_cm=7), bowl(role=container, size_cm=16)]
1. grasp:   moves_with(gripper, apple) and lifted(apple, min_cm=3.0)          # "pick up the apple" [0:00.8–0:03.1]
2. place:   inside(apple, bowl)                                               # "drop it in the bowl" [0:03.2–0:06.0]
3. release: not moves_with(gripper, apple) and dwell(apple, bowl, for_s=0.5)  # "let go" [0:06.1–0:08.7]

# close_drawer.green
objects: [gripper, drawer(role=articulated)]
1. push:   near(gripper, drawer, max_cm=1.0)                                                          # "push the drawer" [0:00.5–0:02.0]
2. flush:  looks(drawer, "closed flush with the cabinet" | "open or sticking out") and dwell(drawer, for_s=1.0) # "until it's flush" [0:02.0–0:03.9]
3. gentle: MANUAL("closing impact force / no slam")                                                   # "don't slam it" [0:04.0–0:05.2] — W101: force is not visual
```

---

## 6. Why Kodiac Is Better (and honest about what it isn't)

### 6.1 Comparison

| Capability | Single-pass VLM judge | Reward models (Robometer, TOPReward, RoboReward) | VLM success detectors (commercial and open) | Sim-state checkers (oracle code, sim agents) | **Kodiac** |
|---|---|---|---|---|---|
| Works on real footage with no simulator state | ✓ | ✓ | ✓ | ✗ | **✓** |
| Spec from **one spoken demo**, human-readable | ✗ | ✗ | rubric / text | code | **✓ `.green`** |
| Decision from **measured geometry** (cm, s, ± σ) | ✗ | ✗ | ✗ (VLM) | ✓ (state) | **✓ (pixels)** |
| **Abstains** with a reason (`CAN'T TELL`) | rarely | ✗ | "needs review" | n/a | **✓ calibrated noise floor** |
| **Exact onset frame** + physical cause | ✗ | progress curve, no cause | subtask captions | state-based | **✓ `blame` t* + margin** |
| Demo-vs-attempt **event diff** | ✗ | ✗ | ✗ | ✗ | **✓ `diff`** |
| Points to the **line of code** (sim) | ✗ | ✗ | ✗ | partial | **✓ span logging** |
| **Coding-agent done-gate** | ✗ | ✗ | ✗ | bespoke agent | **✓ Muse Code plugin** |
| **Downstream retraining proof** | n/a | RoboReward (RL) | not offered | ✗ | **✓ only the judge changed** |

### 6.2 Novelty statement (defensible; use this wording)
> Each ingredient has prior art: VLM success detectors and reward models (SuccessVQA, GVL, RoboReward, Robometer, TOPReward); geometric
> constraint monitors (Code-as-Monitor, Cybo-Waiter); predicate goal checks on simulator state (BDDL, LIBERO); test oracles for robots
> (VISOR, MANGO); failure localization (RoboFAC, KITE, ProTracer); judge-filtered self-improvement (SOAR, RoboReward, VERITAS); and agentic
> code-repair loops (HyCodePolicy, RAPID). **What we did not find in published work, as of Oct 2026, is all five together:**
> (1) a human-readable test compiled from one spoken demonstration, in the same predicate vocabulary as BDDL/LIBERO;
> (2) graded from ordinary monocular video, with no simulator state or telemetry, using measured predicates with an explicit noise margin and a
> three-valued verdict;
> (3) returning the first failing step, the onset frame and the measured margin, plus an event diff against the demo;
> (4) used as a done-gate for a coding agent; and
> (5) evaluated by a controlled "only the judge changed" retraining experiment that reports each judge's false-PASS rate next to downstream success.
> We claim a **tool and an empirical result**, not a new detector model.

**Never say:** "first ever" · "only Meta's stack can do this" · "cancels positivity bias".

### 6.3 Honest limits (we say these out loud; it's a strength)
- **Monocular depth is the hard axis.** Offsets toward or away from the camera carry 2–5× the σ of lateral ones. The σ-gate turns that into
  `CAN'T TELL`, not a false PASS. We report **coverage**.
- **Low-resolution real footage** (DROID is 320×180 at 15 fps) limits precision. We report frames at native fps, and headline precision
  claims come from 30 fps sim (labelled).
- **The vocabulary is small by design.** Tasks outside the 6 predicates use `looks(...)` (VLM, with abstention) or `MANUAL`. We report
  what fraction of benchmark tasks is expressible.
- **The retraining result is simulated** (labelled). Real-world evidence is judge accuracy on real footage, not real-robot retraining.

### 6.4 Answers to the three strongest reviewer objections
1. *"In sim your predicates just reimplement the oracle."* Kodiac reads **rendered pixels only**, never sim state. Its thresholds are
   pre-registered and matched to the oracle's definitions. We report sim agreement, **real-video** balanced accuracy on independent labels,
   and coverage side by side.
2. *"Per-task tests don't scale."* A test takes a ~10 s demo and three sentences (we measure the time and cost per test), or one task
   string via text-compile. Reward models are dense RL signals; Kodiac is an **auditable gate** for data admission and regression tests.
   It's the same split as telemetry vs. unit tests.
3. *"The downstream gain is an artifact."* We use size-matched random controls, an accept-all row, an oracle + injected-noise dose-response
   curve, baselines calibrated to their best case, natural failures from a weak policy (not only scripted perturbations), ≥3 seeds,
   ≥200 eval episodes per seed, and 95% CIs.

---

## 7. Meta Stack: Each Model's Job (load-bearing map)

| Meta model / product | Its one job in Kodiac | What breaks without it | The "didn't know it could do that" moment |
|---|---|---|---|
| **SAM 3.1** (`sam-3.1`, hosted; `facebook/sam3.1`, open) | **Measuring instrument and time machine:** object type-check at compile time; masks for all 6 predicates; **backward propagation** in the bisect window to find t* | Everything: no measurement, no blame | **Run backward in time from the failure to find frame 114**, used as an instrument, not a segmenter |
| **Muse Spark 1.3** (`muse-spark-1.3`) | **Compiler and appearance judge:** speech → `.green` (structured output); two-way crop questions; the fact-bound blame sentence; and the single-pass baseline ("same model, better method") | No `test` verb, no appearance checks, no plain-English blame | A spoken sentence becomes an executable, lintable test |
| **Muse Voice Transcribe 1.0** | **Anchors intent to time:** spoken instructions → step windows + provenance spans | Provenance (I2) and step windows | Your words become the test's line-by-line citations |
| **Muse Wonder 1.0** | **Adjudicator and dataset memory:** resolves contested crops ("check before committing a verdict"); clusters and narrates the failure-norm digest over a whole dataset in its 1M context | Hard-case resolution; the digest | One model call reads a whole dataset's blame log and names the systematic failure |
| **Muse Code** | **Closes the loop:** hosts the MCP tool and the Stop-hook done-gate; `/goal` patches the blamed line until PASS | I7, the agentic beat | A coding agent that **cannot declare victory** until a physical test passes |
| **Muse Glimmer 30B / Muse Spark Open** (open weights via Modal / Baseten / Fireworks) | **Private and bulk judging:** the same crop judge with no pixels leaving your infrastructure; the open-weights row in the benchmark with cost/latency per 1,000 episodes | Privacy story; open-weights bonus | Same verdicts, open weights, measured parity |
| **Meta OSS helpers (optional):** CoTracker3, MapAnything, torchcodec, MMS forced aligner | Point tracks for `moves_with`; metric depth for Tier A′ scale; frame-accurate decoding; word timing | Robustness only (not invariants) | — |

**Not used:** Muse Image. **Never claim "every product in Meta's release is load-bearing."** Claim: **"every Meta model we use is load-bearing,
and we show each one's measured contribution"** (F48 ablation).

---

## 8. Proof Plan (what we will show, and how we may phrase it)

| Proof | Artifact | Allowed phrasing once measured |
|---|---|---|
| **P-1 Headline** | Chart: success vs. false-PASS per judge (sim, 3 seeds, CIs) | "Same robot, same practice data, only the judge changed: **+Y points** of success (95% CI [a, b], simulation)." If the CI includes 0, show the measured value anyway. **Never fabricate** |
| **P-2 Audit** | Audit card + 3 frozen episodes + digest | "N episodes published as successful demonstrations checked · at least X% didn't do their task · hand-verified." |
| **P-3 Real-footage accuracy** | Benchmark table on real video subsets with independent labels | "On real robot footage (n = …), Kodiac's false-PASS rate is … vs. … for the best baseline." |
| **P-4 Agent loop** | One unedited take + batch log of 10 bugs | "Muse Code fixed N/10 seeded bugs; the done-gate refused every premature 'done'." |
| **P-5 Ablation** | Ladder table | "Each stage adds +X points of specificity." (Not "each Meta model adds", since not every rung is a model) |
| **P-6 Live** | Hosted page with timer | "p95 < 12 s on curated clips (measured over n runs)." |
| **P-7 Time saved** | `experiments/results/time_saved.json` (label-tool timing: scrub vs. blame-jump) | "Reviewing with `blame` took X s per episode vs. Y s scrubbing (n = …), about Z hours saved per 1,000 episodes." |

**Pre-registration** (`experiments/PREREGISTRATION.md`, committed before any labels are revealed): hypotheses, task, perturbation
distribution, thresholds (incl. the oracle alignment), arms, seeds, metrics, stopping rule, and the rule that CAN'T TELL counts as "not accepted".

---

## 9. User Journeys

*(Illustrative personas, not real users. Never quote them in the README or video.)*

1. **Robot-learning engineer (Maya):** records a 10 s demo → `Kodiac test` → runs `Kodiac run` over 1,000 overnight practice
   rollouts → keeps only PASS episodes (+ salvaged prefixes) → retrains → better policy, without scrubbing video. When something fails,
   `Kodiac blame` sends her to frame 114.
2. **Dataset maintainer (Ravi):** gets one polite, hand-verified report with a verdict parquet and evidence frames → filters 37 silent
   failures → replies "confirmed, thanks" (external validation).
3. **Muse Code developer (Lee):** writes `pick_place.py` with Muse Code → `/goal … Done ONLY when Kodiac run prints PASS` → the agent
   reads blame ("released 0.4 s early", `pick_place.py:42`), patches, re-runs; the gate refuses "done" until PASS.
4. **Hackathon judge:** opens the live URL → pastes a curated dataset ID → watches the timer stop at ~8 s with FAIL + blame frame → covers
   the webcam → `CAN'T TELL (view blocked)` → trusts the numbers in the video.

---

## 10. Demo & Video

### 10.1 Concept ledger (the 8 spoken concepts; v3 features appear only as visuals)

| # | Spoken concept | Beat | Shown on screen (not spoken as new concepts) |
|---|---|---|---|
| C1 | Robot "success" data is often wrong | 0:00–0:12 | SAM outline, blame frame, audit card, digest card |
| C2 | Code has tests and `git blame`; robots have someone scrubbing video | 0:12–0:24 | Title card **Kodiac** |
| C3 | Show it once → a test | 0:24–0:50 | Voice → 4-line `.green`, SAM object check, MANUAL tag |
| C4 | The exact moment and the physical cause | 0:50–1:20 | `blame` + `diff` text, 2-stage bisect animation, a contrasting PASS |
| C5 | The coding agent can't say "done" until the test passes | 1:20–1:50 | Muse Code `/goal`, done-gate refusal, `pick_place.py:42`, N/10 (sim labelled) |
| C6 | Same robot, same data, only the judge changed: +Y points | 1:50–2:25 | Proof chart, open-weights point, salvage point, real-footage accuracy line |
| C7 | It says CAN'T TELL instead of guessing (live) | 2:25–2:48 | Hosted page, timer, occlusion brush/camera cover, CACHED badge |
| C8 | The same test checks the demonstrations robots learn from | 2:48–3:00 | Human-hand demo graded by the same test, `pip install Kodiac-robotics`, tagline |

### 10.2 Script (v3.1)

| Time | Visual & audio |
|------|----------------|
| 0:00–0:12 | Three real public robot episodes published as successful demonstrations freeze at the exact failure frame, with red SAM 3.1 outlines. Card: *"N episodes checked · at least X% didn't do their task · hand-verified."* |
| 0:12–0:24 | VO: *"Code has tests and git blame. Robots have someone scrubbing video."* Title card: **Kodiac**. |
| 0:24–0:50 | Real hands on a webcam; three spoken instructions compile live into a 4-line test, each line citing its sentence. SAM 3.1 confirms the objects. |
| 0:50–1:20 | On a real robot attempt: the exact frame it went wrong and the measured cause (on screen: `blame: released 0.4 s before contact · 2.6 cm left · frame 114`), plus the side-by-side `diff` and a contrasting PASS. VO in plain words: *"the exact moment it went wrong, and why."* |
| 1:20–1:50 | One unedited take in Muse Code (simulation labelled): it reads the blame, patches line 42, re-runs, and the gate refuses "done" until PASS. N of 10 planted bugs fixed (bug list in the repo). |
| 1:50–2:25 | The proof chart. VO: *"In simulation: same robot, same practice data, only the judge changed: plus Y points of success."* On screen: `SIMULATION · ManiSkill3 · 3 seeds · 95% CI`. Baselines, the open-weights point, and the real-footage accuracy line. |
| 2:25–2:48 | The live hosted page: paste a dataset, the timer runs and stops under 12 s. Cover the camera → **CAN'T TELL**. |
| 2:48–3:00 | VO: *"The same test checks the demonstrations robots learn from."* `pip install Kodiac-robotics`. VO: ***"Robots can finally fail a test."*** |

### 10.3 Voiceover discipline (lint-enforced)
- **Banned spoken/on-screen words:** receipts · deterministic engine · answer key · mutation · counterfactual · toolchain · "Muse alone" ·
  **image analyzer** · **UNKNOWN** · "first ever" · "only Meta can" · plus every term in the private lineage list (`docs/private/lineage_terms.txt`).
- Dev terms (`bisect`, `blame`, `diff`, predicates, σ) appear as **on-screen text**. The voiceover uses plain words.
- Every on-screen number is a measured value from the repo (`artifacts/`), with its source file recorded in `docs/VIDEO_NUMBERS.md`.
- On-screen measured numbers must satisfy |m| ≥ 3σ; otherwise show the labelled SIM clip for cm-level numbers. Use ≤ 2 dev terms per beat on screen, each with a plain caption.

---

## 11. Scope Ladder (what ships first)

| Tier | Contents | Est. agent-hours |
|------|----------|------------------|
| **MVP** (every invariant holds) | F01–F16, F18–F24, F28–F35b, F37–F45, F47, F49 (≥20 flags), F50 (narration), F51, F53–F60; `inside` lite; ≥4 proof arms × 2–3 seeds | ≈ 62–68 h + 10 h buffer |
| **Strong** | + F25–F26 two-way crop judge + Wonder escalation · full 2.5D `inside` (F17) · all proof arms + prefix salvage (F36) · Glimmer / Spark-Open benchmark row (F27) · real-footage validation (F46) · ≥40 flags across 2–3 datasets · ablation ladder (F48) · Rerun/HTML trace viewer · community reports (F52, human-approved) | + ≈ 20–25 h |
| **Full v3** | + end-to-end `--local-glimmer` privacy mode · arbitrary dataset IDs in the app · cross-dataset Wonder memory · DROID two-view triangulation · transient-break warnings · real lid/drawer examples | + ≈ 15–25 h |

**Cut order when time runs short (first → last):** community reports → cross-dataset memory → arbitrary IDs → end-to-end private mode →
trace viewer polish → ablation down to 2 rungs → prefix-salvage arm (keep the flag) → real-footage slice size → two-way judge + Wonder →
full 2.5D `inside`.
**Never cut:** `test`, `run` (fast path + 3 verdicts), `blame` + `diff`, the `/goal` done-gate, the headline experiment with ≥4 arms, the
audit opener, the hosted page with timer + CAN'T TELL + cached replay, and the 8-concept video with the tagline.

---

## 12. Claims Discipline (targets vs. results)

| Spec number | Status | Rule |
|---|---|---|
| False-PASS < 3% | **Target** | Publish only the measured value + CI |
| ~24% baseline false-PASS | **Placeholder** | Replace with the measured value |
| "+Y points" | **Placeholder** | Measured value + CI; if not significant, say so |
| "<12 s" live | **Target** | Claim only if measured p95 < 12 s over n ≥ 30 runs |
| "$0.01 / ~5 s per window" | Cost verified ($0.20 / 1k frames, 50-frame minimum); latency **unverified** | Measure on day 1 |
| "N/10 bugs fixed" | **Placeholder** | Batch log + transcripts |
| Internal self-scores | **No rubric basis** | Never publish |
| Hero line "0:03.8 · 3.8 cm" | **Illustrative** (the digits collide) | Replace with the real hero clip's measured values |

---

## 13. Glossary

| Term | Meaning |
|---|---|
| `.green` | Kodiac's test file: objects + ordered steps of predicate expressions, with provenance |
| `.green.lock` | Machine sidecar: transcript, baselines, rim ellipses, demo events, model IDs, hashes |
| Predicate | One of 6 measured spatial/temporal relations: `on`, `inside`, `near`, `lifted`, `moves_with`, `dwell` |
| `looks(...)` | Appearance check answered by the crop judge (two opposite questions) |
| `MANUAL(...)` | A requirement the camera can't verify; listed, never evaluated |
| Margin `m` | Signed distance from a threshold in the predicate's unit; positive = satisfied |
| σ (sigma) | Measurement uncertainty of a margin (cm/s), from pixel jitter + scale-model uncertainty |
| CAN'T TELL | Third verdict: evidence is below the noise floor, occluded, or not visible. JSON `CANT_TELL`, exit code 2 |
| t* | Onset frame: the first frame of the fatal break of the blamed prerequisite |
| Carried literal | A step condition that must stay true until a later step negates it (e.g., `moves_with` during transport) |
| Two-stage bisect | Coarse keyframes → halving → dense window. Makes live grading fast and frame-exact |
| Fact table | Measured numbers at t*: the only input to the blame sentence |
| Done-gate | Muse Code Stop hook that refuses completion unless a fresh `Kodiac run` returns PASS with a pinned test hash |
| Prefix salvage | Keeping the valid pre-failure part of a failed episode as training data |
| False-PASS rate | Fraction of true failures a judge accepts: FP / (FP + TN) |
| Contamination | Fraction of accepted episodes that are actually failures: FP / (TP + FP) |
| Coverage | Fraction of episodes the judge decided (not CAN'T TELL) |
| Effector aliasing | `gripper` resolves to the robot gripper or a human hand, depending on the clip |
| Tier A/B/C | Scale-model quality: calibrated / ground-plane self-calibrated / single reference |

---

## 14. Changelog

| Version | Date | Change | Reason |
|---|---|---|---|
| v3.0 | pre-event | Original master spec (kept privately in `docs/private/`; **not** for the public repo) | — |
| **v3.1** | 2026-10-27 | Public wording no longer describes pre-event design history (terms in the private lineage list) | New-work rule (`HACKATHON.md` R1) |
| v3.1 | 2026-10-27 | Closing line → "The same test checks the demonstrations robots learn from" (**awaiting human confirmation**) | Anti-project rule R2 |
| v3.1 | 2026-10-27 | Problem/proof claims rewritten in sourced wording; RUM attribution corrected; SOAR/RoboReward/VERITAS cited | Claims verification |
| v3.1 | 2026-10-27 | `pip install Kodiac` → `pip install Kodiac-robotics` (CLI stays `Kodiac`) | PyPI name taken |
| v3.1 | 2026-10-27 | `UNKNOWN` → `CAN'T TELL` everywhere; one public latency number (<12 s p95) | Internal inconsistency |
| v3.1 | 2026-10-27 | Gap fixes added: Stage 1.5 halving, static proxies at keyframes, monotone bisect target, px→cm scale tiers, effector aliasing, demo self-test, text-compile, lock file, summary validator, defined "0.4 s before contact", defined corrective hint, hash-pinned done-gate | Analysis §5 |
| v3.1 | 2026-10-27 | Muse Wonder "Active Memory" → deterministic digest numbers + Wonder narration + persisted memory file | No memory API found |
| v3.1 | 2026-10-27 | `--local-glimmer` → an OpenAI-compatible open-weights switch (Glimmer via Modal/Baseten/llama.cpp, or Muse Spark Open on partners) | Glimmer bf16 needs 72 GB VRAM; serving paths partly unattested |
| v3.1 | 2026-10-27 | Hosted demo on a Modal **CPU** endpoint (no GPU warm pool) | Cost: a warm GPU pool for Nov 4–9 ≈ $100–500 |
| v3.1 | 2026-10-27 | Hosted demo: "paste any LeRobot dataset ID" → a curated, pre-indexed allowlist; arbitrary IDs are best-effort (Full tier) | Live reliability (KD-14) |
| v3.1 | 2026-10-27 | On geometry-only tasks (StackCube), Kodiac cloud ≡ open-weights (no VLM call): one chart point; the open-weights comparison is measured on the appearance benchmark | Avoid a duplicated chart point |
| v3.1 | 2026-10-27 | Community issues → one consolidated, human-approved HF report per dataset, started early (P06) | Outward-action policy + external validation |
| v3.1 | 2026-10-27 | I2 acceptance clarified: demo-compiled steps carry quote + span; text-compiled steps carry `source=text` + the task string | Review R1-35 |
| v3.1 | 2026-10-27 | Blame output always shows ± σ; hero mocks badged SIM (30 fps); VO says "In simulation"; added §1.1 and the P-7 time-saved proof | Review round 1 (R1/R2) applied |
| v3.1 | 2026-10-27 | "Every product in the release" → "every Meta model we use" | Muse Image is unused |
