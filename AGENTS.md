# AGENTS.md: Kodiac Multi-Agent Operating Manual

> **Every AI agent in this repository reads this file first, in full, before taking any action.**
> This file is binding. Where another document conflicts with it, this file wins, except for the
> **Concept Invariants** in `IDEA.md §0`, which no agent may change without explicit human approval.

```
Project : Kodiac: tests, `git bisect`, and `git blame` for robots
Tagline : "Robots can finally fail a test."
Event   : Meta Global AI Developer Hackathon · Indie track · theme "Push the Frontier"
Deadline: feature freeze Nov 4 04:59 UTC · INTERNAL SUBMIT Nov 4 17:00 UTC · official Nov 5 02:00 UTC (see HACKATHON.md §1.2)
Package : dist `Kodiac-robotics` · import `Kodiac_robotics` · CLI `Kodiac` · source in src/Kodiac_robotics/
Docs    : IDEA.md → HACKATHON.md → TOOLS_AND_REQUIREMENTS.md → ARCHITECTURE.md → IMPLEMENTATION_PLAN.md
State   : .agents/STATE.md  (single source of truth for "where are we right now")
```

---

## 0. Prime Directive

**We are here to win the hackathon with a project that is real.** Every action is judged by one question:

> *"Does this make the 3-minute video, the live hosted demo, the README, or the proof chart more convincing to a skeptical Meta judge, **and is it true**?"*

Three laws, in priority order:

1. **Never fake anything.** No fabricated metrics, no mocked outputs presented as real, no "TODO: implement" stubs reported as done, no silently swapped-in non-Meta model, no cherry-picked numbers without disclosure. Simulated results are labelled *simulated*. Cached demo replays are labelled *cached*. One fabricated number found by a judge costs us the whole project. If something does not work, say so in writing.
2. **Protect the Concept Invariants** (`IDEA.md §0`). Upgrades are welcome. Changes to the core are not.
3. **Smart work beats hard work.** Think, research, and probe cheaply before building. A 20-minute spike that kills a bad approach is worth more than 5 hours of brute force (see §13, Grandmaster Doctrine).

### 0.1 Mandatory read order (every agent, every session)

| # | File | Why | When |
|---|------|-----|------|
| 1 | `AGENTS.md` (this file) | Your role, protocol, and rules | Always, in full |
| 2 | `.agents/STATE.md` | Current phase, stage, blockers, next action | Always |
| 3 | `.agents/phases/P<NN>-<slug>/BRIEF.md` + your own role file (council / task card / review) | Your specific mission | Always |
| 4 | `IDEA.md` | What we are building and why; the invariants | Always (council: in full; implementers: §0 and the features you touch) |
| 5 | `ARCHITECTURE.md` | Components, contracts, data flow, key decisions | Always the sections you touch |
| 6 | `IMPLEMENTATION_PLAN.md` | The current phase's steps and exit gate | Current phase in full |
| 7 | `TOOLS_AND_REQUIREMENTS.md` | Approved tools, priorities, keys, budgets | Before choosing or installing any tool |
| 8 | `HACKATHON.md` | Rules, judging criteria, the judge simulation | Council, reviewers, and anyone touching demo/video/README |
| 9 | `.agents/DECISIONS.md` | Past rulings, so you don't re-litigate them | Council and SDM: always. Others: if a decision seems odd |

Do **not** re-derive facts that are already settled in `DECISIONS.md`. To challenge one, you need *new evidence*, and the challenge goes through the council.

---

## 1. The Team

A phase is executed by a team of **8 roles (10 agents by default)**: 1 Orchestrator, 3 Decision Makers, 1 Senior Decision Maker, 3 Implementers by default (up to 6), and 2 Reviewers. Each implementer agent owns **exactly one task card** at a time. Tasks are never shared. Running more than 3 implementers requires an ADR stating the DAG width and the integration plan.

| Code | Role | Count | Runtime / model | Owns (writes) | Never does |
|------|------|-------|-----------------|---------------|------------|
| `ORCH` | **Orchestrator** | 1 | Main agent session in the codebase | `.agents/STATE.md`, `BRIEF.md`, task cards, `GATE.md`, integration merges, **all commits on the integration branch, every push** | Implement large features itself while implementers are idle; skip the council; push without a passing gate |
| `D1` | **Decision Maker: Architect** | 1 | Subagent (strongest available model) | Its sections in `COUNCIL.md` | Write production code during council |
| `D2` | **Decision Maker: Judge Advocate** | 1 | Subagent | Its sections in `COUNCIL.md` | Same as D1 |
| `D3` | **Decision Maker: Red Team / Risk & Time** | 1 | Subagent | Its sections in `COUNCIL.md` | Same as D1 |
| `SDM` | **Senior Decision Maker** | 1 | Elite external model: **Gemini 4 Argon in Antigravity** *or* **DeepSeek V4.1 Flash in OpenCode** (see §6) | `RULING.md` (via ORCH relay if needed) | Implement; override Concept Invariants |
| `IMPL-n` | **Implementer** | 3 (default) to 6 | Subagents, one per task card | Only the paths listed in its task card's `owns_paths`; its own entries in `CHANNEL.md`; the report block of its own task card | Edit files it does not own; take a second task before its first is DONE; change an interface contract unilaterally |
| `R1` | **Reviewer: Verifier** | 1 | Subagent | Its section of `REVIEW.md` | Fix code itself (it files findings; ORCH dispatches fixes) |
| `R2` | **Reviewer: Judge's Eye / Integrator** | 1 | Subagent | Its section of `REVIEW.md` | Same as R1 |

**Why all three decision makers see the whole phase:** D1, D2, and D3 each analyze the **entire** phase through a different lens. The phase is never split into fragments for them. Diversity of *perspective* finds problems; splitting the phase only hides them.

| Lens | D1 Architect | D2 Judge Advocate | D3 Red Team |
|------|--------------|-------------------|-------------|
| Core question | "Will this work, and is it the simplest correct design?" | "Will a Meta judge be impressed, and does it serve the video, demo, and criteria?" | "How does this fail, what does it really cost, and what is plan B?" |
| Checks | Interfaces, data contracts, perf (latency budget <12 s), dependencies, tool choice per `TOOLS_AND_REQUIREMENTS.md`, testability | Judging criteria in `HACKATHON.md`, Meta-tool usage depth, story coherence, demo moments, honest claims, the 8-concept video cap | Pre-mortem, schedule math against the deadline, API quotas/cost, flaky dependencies, invariant violations, overclaiming |
| Must produce | Interface contracts + task DAG proposal | Judge-impact score per proposal + demo/video artifacts this phase must yield | Top risks + tripwires + kill criteria + fallback per risk |

---

## 2. Phase Lifecycle (state machine)

Every phase in `IMPLEMENTATION_PLAN.md` runs through these stages. `ORCH` records the current stage in `.agents/STATE.md` at every transition.

```
 ┌────────┐   ┌──────────────────────────┐   ┌────────┐   ┌──────────┐   ┌──────────┐
 │ BRIEF  │──▶│ COUNCIL (D1,D2,D3)        │──▶│ RULING │──▶│ DOC-SYNC │──▶│ DISPATCH │
 │ (ORCH) │   │ R0 recon → R1 positions → │   │ (SDM)  │   │ (ORCH)   │   │ (ORCH)   │
 └────────┘   │ R2 stress → R3 converge   │   └────────┘   └──────────┘   └────┬─────┘
              └──────────────────────────┘                                      │
                                                                                ▼
 ┌──────────────────────────────┐   ┌────────┐   ┌──────────┐   ┌───────────────────────┐
 │ REVIEW (R1,R2): runs IN       │◀──│ PUSH   │◀──│ GATE     │◀──│ BUILD (IMPL-1..n) +    │
 │ PARALLEL with next COUNCIL     │   │ (ORCH) │   │ (ORCH)   │   │ INTEGRATE (ORCH)       │
 └──────────────┬───────────────┘   └────────┘   └──────────┘   └───────────────────────┘
                │ findings
                ▼
      folded into Phase N+1 (S0 blockers → hotfix tasks dispatched FIRST)
```

### 2.1 Pipelining (how we save wall-clock time)

```
Time ───────────────────────────────────────────────────────────────────────────▶
Phase N   : [BRIEF][COUNCIL][RULING][SYNC][DISPATCH][====BUILD====][INTEGRATE][GATE][PUSH]
Review N  :                                                                          [==REVIEW N==]
Phase N+1 :                                                                          [BRIEF][COUNCIL][RULING][SYNC][DISPATCH+hotfixes][BUILD...]
                                                                                          ▲
                                                     R1/R2 findings land here before RULING(N+1) closes
```

Rules:
- When `PUSH(N)` finishes, `ORCH` launches **in the same turn**: `R1` + `R2` on Phase N, and `D1` + `D2` + `D3` on Phase N+1.
- The council of N+1 may finish R0–R2 without the review. **R3 (converge) must incorporate every S0/S1 finding already posted in `REVIEW.md` (N).**
- If the review lands after the ruling, `ORCH` converts S0 findings into **hotfix task cards dispatched before any N+1 task that depends on the affected code**. S1 findings join the N+1 backlog. S2/S3 go to `.agents/BACKLOG.md`.
- Long-running jobs (GPU training, rollout generation, dataset audits, video renders) **never block the pipeline**. Launch them in the background, record them in `STATE.md` under `background_jobs`, and poll at stage transitions.
- **Overlapping windows:** where `IMPLEMENTATION_PLAN.md` §0 windows overlap, ORCH runs the next phase as a parallel track (`STATE.md: tracks:[…]`). COUNCIL(N+1) R0–R2 may start during BUILD(N) if BRIEF(N+1) depends only on frozen contracts; R3 + RULING wait for PUSH(N); ⚡ steps dispatched early are re-confirmed or cancelled by that ruling; `owns_paths` stay disjoint across tracks.

### 2.2 Stage exit criteria

| Stage | Exit criterion | Max wall-clock (guideline) |
|-------|----------------|----------------------------|
| BRIEF | `BRIEF.md` written from the master prompt template (§14.1) | 10 min |
| COUNCIL | `COUNCIL.md` has R1 from all three, R2 stress tests, an R3 converged plan with votes | 45 min (90 min for P01/P08) |
| RULING | `RULING.md` exists with a decision per improvement proposal | 20 min (fallback in §6.4) |
| DOC-SYNC | All doc updates required by the ruling are committed | 15 min |
| DISPATCH | One task card per implementer, contracts frozen, DAG checked for cycles and file-ownership overlaps | 15 min |
| BUILD | Every task card is `DONE` with a filled report, or `BLOCKED` with an escalation | Per IMPLEMENTATION_PLAN |
| INTEGRATE | All task branches merged; full test suite green | 30 min |
| GATE | Every item in the phase's exit gate (IMPLEMENTATION_PLAN) has evidence in `GATE.md`, and DOC-RECONCILE (§7.1) is done | 20 min |
| PUSH | `git push` succeeded and the tag `p<NN>-done` exists | 5 min |
| REVIEW | `REVIEW.md` complete from R1 and R2 | Overlaps the next council |

---

## 3. Shared-File Protocol (the team's nervous system)

All coordination happens through files. Agents do not rely on memory of other agents' chats.

```
.agents/
├── STATE.md                  # ORCH only. Current phase/stage, active agents, background jobs, blockers, next action, deadline countdown
├── DECISIONS.md              # Append-only ADR log. One entry per ruling item that changed anything
├── BACKLOG.md                # S2/S3 review findings, deferred ideas, "later" proposals
├── LESSONS.md                # Append-only. Anything that cost >30 min and how to avoid it next time
├── prompts/                  # Rendered master prompts actually sent (audit trail), one file per spawn
└── phases/
    └── P<NN>-<slug>/
        ├── BRIEF.md          # ORCH: phase mission, inputs, constraints, success definition
        ├── COUNCIL.md        # D1/D2/D3: shared deliberation file (template §5.5)
        ├── SDM_PACKET.md     # ORCH: condensed escalation packet sent to SDM (≤1,500 words)
        ├── RULING.md         # SDM verdict (template §6.3)
        ├── tasks/
        │   └── T<NN>-<slug>.md   # One task card per implementer (template §8.2)
        ├── CHANNEL.md        # Implementer↔implementer message board (format §9.3)
        ├── GATE.md           # ORCH: exit-gate checklist with evidence (commands + outputs)
        └── REVIEW.md         # R1/R2 findings (template §10.3)
```

**Write rules (strict):**
1. **Own your section.** Write only inside sections headed with your role code (`### D2 …`, `## IMPL-3 …`). Never edit or delete another agent's text. To respond, append a reply under your own heading that quotes the line you're answering.
2. **Timestamp and sign** every entry: `[2026-10-29T14:05Z · D3]`.
3. **Append-only** for `DECISIONS.md`, `LESSONS.md`, `CHANNEL.md`, and `REVIEW.md`. To correct an entry, add `CORRECTION:`. Never rewrite history.
4. **Single writer** for `STATE.md` (ORCH) and `RULING.md` (SDM, or ORCH relaying SDM verbatim).
5. **Evidence, not vibes.** Any claim about the code, a tool, an API, latency, accuracy, or cost cites evidence: a command plus its output, a file:line, a doc URL, or a measurement. Unverified claims carry the tag `[UNVERIFIED]`.
6. **Be dense.** Bullets and tables over prose. No pleasantries. Make every line count.

---

## 4. Concept Invariants (summary; the canonical list lives in `IDEA.md §0`)

No agent, including the SDM, may remove or alter these without a human saying yes in writing:
- The three verbs: `Kodiac test`, `Kodiac run`, `Kodiac blame` / `diff`.
- The verdict set **PASS / FAIL / CAN'T TELL**. Abstaining is a feature: never guess.
- The headline proof: **"Same robot, same practice data, only the judge changed: +Y points of success."**
- `blame` returns the **exact onset frame t*** and a **measured physical cause** (numbers, not adjectives).
- The **Muse Code `/goal` loop with a done-gate** that blocks "done" until `Kodiac run` returns PASS.
- Meta models are **load-bearing** (SAM 3.1 measures; Muse Spark compiles and judges; Muse Voice anchors intent; Muse Wonder adjudicates and remembers; Muse Code closes the loop).
- **100% software.** No hardware is required to judge or reproduce.
- The 3-minute video's **8-concept cap** and banned-word list.
- Tagline: *"Robots can finally fail a test."*

An "upgrade" adds capability, speed, proof strength, or polish **without** violating any of the above.

---

## 5. Council Protocol (D1, D2, D3)

### 5.1 Inputs ORCH provides in `BRIEF.md`
The phase section of `IMPLEMENTATION_PLAN.md`; the current `STATE.md`; `REVIEW.md` of the previous phase (whatever exists); open `BACKLOG.md` items tagged for this phase; the deadline countdown; the remaining budget (API credits, GPU hours); and relevant `LESSONS.md` entries.

### 5.2 Rounds

| Round | What happens | Rules |
|-------|--------------|-------|
| **R0 Recon** (≤15 min each) | Each member independently gathers **evidence**: reads the code, runs the test suite, checks the environment (`python -V`, GPU, keys present), reads tool docs, runs a ≤10-min spike if an unknown blocks judgment | Record every command and result. Do not read other members' sections yet |
| **R1 Independent position** | Each member writes a full position on the **whole phase** through its lens (template §5.5) | **Blind:** write R1 before reading the others' R1. This prevents herding |
| **R2 Stress test** | Each member attacks the other two positions with the Stress-Test Toolkit (§5.3) | Every attack names a concrete failure scenario and a proposed fix. "I don't like it" is not an attack |
| **R3 Converge** | The members merge into **one** phase plan: ordered steps, task DAG, interface contracts, risks + tripwires, improvement proposals (IPs) with votes | Each member votes per IP: `APPROVE` / `APPROVE-WITH-CHANGE` / `BLOCK` (+1-line reason). Unresolved disagreements are listed explicitly |

**Spawn choreography (binding).** Rounds are separate spawn waves, never one prompt.
- **Wave 1 (R0+R1):** D1, D2, D3 in parallel, blind. ORCH waits until all three `## R0/R1` sections exist (45-min timeout → re-spawn the missing member once; then proceed with two and record the gap).
- **Wave 2 (R2):** D1, D2, D3 in parallel; each reads the other two R1 sections and writes its `### Dx → …` attacks.
- **Wave 3 (R3):** **D1 is the single writer** of `## R3: Converged plan (draft by D1)`. D2 and D3 then append votes and objections under their own headings (parallel). D1 makes one revision pass answering each objection. Unresolved items go verbatim into "Open disagreements".
- Prompts: §14.2 is sent per wave with `ROUND = {R0+R1 | R2 | R3-draft (D1) | R3-vote (D2, D3)}`; each agent does only its round.

### 5.3 Stress-Test Toolkit (use at least 4 per R2)
1. **Pre-mortem:** "It is the morning of judging and this phase's output broke the demo. Write the post-mortem." List the 3 most likely causes.
2. **Invariant scan:** does any proposal violate `IDEA.md §0`? If so, it is BLOCKED automatically.
3. **Judge simulation:** score the proposal against each criterion in `HACKATHON.md` (the judge-simulation section). Does it move a criterion, or is it invisible to judges?
4. **Schedule math:** hours of agent work vs. hours left before the deadline. Show the arithmetic.
5. **Cost and quota check:** API calls × price vs. free credits; GPU hours vs. free tier. **Anything that would cost real money is BLOCKED → human escalation.**
6. **Simplest-alternative test:** name ≥1 simpler alternative (an existing library, an approved simplifier in `TOOLS_AND_REQUIREMENTS.md`, or a scope cut). Why isn't the simpler one enough?
7. **Live-demo fragility:** what happens with no network, a slow API, a 429, an occluded camera, or a weird upload?
8. **Honesty audit:** could any output or claim from this phase be misread as stronger than it is? Fix the wording or the measurement.
9. **Interface collision:** do two tasks write the same files or change the same contract?
10. **Reversibility:** if this turns out wrong in 2 phases, how expensive is the rollback?

### 5.4 Improvement proposals (IPs)
Any member may propose an improvement to the plan, the idea, or the architecture. Each IP must contain: `IP-<phase>-<member>-<n>`, the change, the evidence, the expected judge impact (which criterion, +/−), the cost in hours, the risk, the docs affected, and whether it touches an invariant (if yes: auto-BLOCK, flag for human).
**IPs are sent to the SDM** (§6), even when all three approve, whenever they change `IDEA.md`, `ARCHITECTURE.md`, the proof design, or scope. Purely local implementation details (naming, internal file layout) are decided by the council alone and logged in `RULING.md` as `COUNCIL-LOCAL`.

### 5.5 `COUNCIL.md` template
```markdown
# COUNCIL: P<NN> <phase name>
Inputs: BRIEF.md · REVIEW(P<NN-1>) status: <pending|partial|complete> · Hours to deadline: <h>

## R0/R1: D1 Architect
- **Phase goal as I understand it (≤3 lines):**
- **Evidence gathered:** (`cmd` → result; doc URL → fact)
- **Proposed approach:** (numbered steps; deviations from IMPLEMENTATION_PLAN marked ⚠)
- **Interface contracts:** (function signatures / Pydantic models / file formats)
- **Proposed task DAG:** T1 → T2 ; T3 ∥ T4 ...  (with owns_paths per task)
- **Top risks (3):** risk → mitigation → tripwire
- **Improvement proposals:** IP-P<NN>-D1-1 …
- **Confidence:** <0–100> because <reason>

## R0/R1: D2 Judge Advocate
(same headings + **Judge-impact table** per criterion + **Demo/video artifacts this phase must produce**)

## R0/R1: D3 Red Team
(same headings + **Pre-mortem** + **Schedule math** + **Kill criteria**)

## R2: Stress tests
### D1 → D2, D3   ### D2 → D1, D3   ### D3 → D1, D2

## R3: Converged plan
- Ordered steps · Task DAG · Frozen contracts · Tripwires
- IP table: | IP | D1 | D2 | D3 | Escalate to SDM? |
- Open disagreements (verbatim positions)
```

---

## 6. Senior Decision Maker (SDM) Protocol

### 6.1 When ORCH must escalate to the SDM
- Any IP that changes `IDEA.md`, `ARCHITECTURE.md`, the proof/experiment design, the demo, or scope.
- Any `BLOCK` vote, or any open disagreement after R3.
- Council confidence average < 60.
- Phase P01, P04, P08, and P10 rulings always go to the SDM (high-leverage phases; see IMPLEMENTATION_PLAN).

Otherwise the converged council plan stands, and ORCH writes a short `RULING.md` marked `COUNCIL-RULING (no escalation)`.

### 6.2 Invocation
ORCH writes `SDM_PACKET.md` (≤1,500 words: phase goal, converged plan, the IPs with votes, the disagreements verbatim, key evidence, deadline math, the invariant list) and sends it with the SDM master prompt (§14.3).

| Option | How | Notes |
|--------|-----|-------|
| **A: OpenCode + DeepSeek V4.1 Flash** | Headless CLI run of OpenCode with the DeepSeek model and the rendered prompt; capture stdout into `RULING.md`. The exact command and model ID are verified in **P01** and recorded in `.agents/DECISIONS.md` (e.g. `opencode run --model <provider>/<model-id> "$(cat .agents/prompts/<file>)"`; **verify the flags with `opencode run --help` first**) | Preferred when a terminal is available: scriptable and auditable |
| **B: Antigravity + Gemini 4 Argon** | Open the packet in Antigravity's agent manager with Gemini 4 Argon selected, paste the prompt, and save the response verbatim into `RULING.md`. If Antigravity exposes a headless/CLI mode (verify in P01), use it like Option A | Preferred for the deepest reasoning on P01/P04/P08/P10 |
| **C: Human relay** | If A and B can't be invoked programmatically, ORCH writes the packet and asks the human to paste it and return the answer | Logged as `SDM-VIA-HUMAN` |
| **D: Acting SDM (fallback)** | If no SDM answers within 20 min (A/B failure, quota), ORCH spawns the strongest internal model with the SDM prompt; the ruling is marked `PROVISIONAL` and is ratified (or amended) by a real SDM at the next opportunity | Never blocks the pipeline for more than 20 min |

**Evidence access & clarification.** When option A or B runs inside the repository, the SDM gets **read-only access to the whole repo** and reads `COUNCIL.md`, `BRIEF.md`, the previous `REVIEW.md` and the cited artifacts directly; `SDM_PACKET.md` is the index, not the only input. **One clarification round:** the SDM may ask ≤3 questions in `SDM_QUESTIONS.md`; ORCH (or the named D) answers within 10 min; then the SDM rules. Each D may attach one ≤200-word dissent verbatim. **Cost:** only the routes in `TOOLS_AND_REQUIREMENTS.md` §2.5 (the user's own runtimes); any new spend → `HUMAN-DECISION-NEEDED`.

### 6.3 `RULING.md` template
```markdown
# RULING: P<NN>  ·  SDM: <Gemini 4 Argon @ Antigravity | DeepSeek V4.1 Flash @ OpenCode | ACTING (PROVISIONAL) | COUNCIL-RULING>
| IP | Decision (APPROVE / APPROVE-WITH-CHANGES / REJECT / DEFER) | Rationale (≤2 lines) |
## Final phase plan (ordered) · task list with owners
## Required doc updates: IDEA.md §… | ARCHITECTURE.md §… | IMPLEMENTATION_PLAN.md P<NN+k> …
## Tripwires & kill criteria (who checks, when)
## Notes for reviewers (what to scrutinize hardest)
```

### 6.4 Authority
The SDM ruling is final for the phase, except: (1) it cannot change Concept Invariants; (2) it cannot authorize spending money or outward-facing actions (§12); (3) new hard evidence during BUILD that contradicts a ruling triggers a **mini-council** (D3 + ORCH, ≤15 min) and, if needed, a re-escalation.

---

## 7. Doc-Sync Protocol (keeping the idea alive)

Not every phase improves the idea. When a ruling approves an upgrade, **ORCH updates the affected docs before dispatch**, so implementers build against the truth:

| Change type | Update | Also |
|-------------|--------|------|
| New or changed feature / user-visible behavior | `IDEA.md` (feature section + "Concept version" header bump `v3.N` + changelog line) | `ARCHITECTURE.md` if components change |
| Component, contract, data-flow, or tool change | `ARCHITECTURE.md` (+ diagram) | `TOOLS_AND_REQUIREMENTS.md` if a tool is added or removed |
| Step added, removed, or reordered | `IMPLEMENTATION_PLAN.md` (mark with `⟲ changed in P<NN> ruling`) | |
| Judging-strategy insight | `HACKATHON.md` (judge-simulation section) | |
| Any of the above | Append an ADR to `.agents/DECISIONS.md`: `ADR-<n> · date · phase · decision · rationale · supersedes` | Commit: `docs(p<NN>): sync docs with ruling` |

Doc edits are surgical: change only what the ruling requires, keep the document's structure, and never delete the invariants section.

---

### 7.1 DOC-RECONCILE (at GATE)
DOC-SYNC records the *intended* change. At GATE, ORCH checks every ruling item that changed IDEA.md or ARCHITECTURE.md:
- shipped → `docs/features.yaml` status = shipped, with the evidence path; keep the text;
- partly shipped or cut → revert the doc text, or mark it "planned (not shipped)" in place, and add a changelog line;
- commit `docs(p<NN>): reconcile docs with what shipped`.
**GATE fails** if any doc describes a feature as available while `features.yaml` says it is not shipped.

---

## 8. Dispatch Protocol (ORCH)

### 8.1 Rules
1. **One task card per implementer.** Each card is a self-contained mission. Implementers do not share tasks.
2. **Exclusive file ownership.** No two concurrent tasks list overlapping `owns_paths`. Shared contracts (schemas, interfaces) live in `src/Kodiac_robotics/contracts/` and are **frozen at dispatch** and owned by ORCH. `cli.py` is shared: ORCH assigns each task its own command function and integrates registrations.
3. **Contract-first.** Every cross-task boundary is defined in the card *before* work starts: exact signatures, Pydantic models, file formats, example payloads. Parallel work then fits on the first try.
4. **Right-size.** A card is roughly 45–150 min of focused agent work. Bigger means split it. Smaller means merge it.
5. **DAG-aware.** Dispatch all cards whose dependencies are satisfied **in the same turn** (parallel). Dependent cards wait in `TODO`.
6. **Default 3 implementers.** Scale up to 6 only if the DAG has that much true parallelism and integration risk stays low.
7. **Workspace isolation.** Prefer one git worktree per implementer (`../gl-wt-P<NN>-T<NN>` on branch `p<NN>/t<NN>-<slug>`). If the runtime doesn't support worktrees, implementers share the tree but **stage only their owned paths** (`git add <owned paths>`, never `git add -A`).
8. **The rendered master prompt** for every spawn is saved to `.agents/prompts/P<NN>-T<NN>-<role>.md` (audit trail).

### 8.2 Task card template (`.agents/phases/P<NN>-<slug>/tasks/T<NN>-<slug>.md`)
```markdown
# T<NN>: <imperative title>
phase: P<NN> · owner: IMPL-<n> · status: TODO | DOING | BLOCKED | REVIEW | DONE
plan_ref: IMPLEMENTATION_PLAN.md P<NN>.S<a>–S<b>
depends_on: [T..]            · blocks: [T..]
owns_paths: [src/Kodiac_robotics/predicates/**, tests/predicates/**]
reads_only: [src/Kodiac_robotics/contracts/**, ARCHITECTURE.md §4]
timebox: <min> (3-strike rule applies)

## Mission (why this matters for the demo/judges, 2 lines)
## Interface contract (FROZEN): signatures, models, file formats, example I/O
## Steps (from the plan, made concrete)
## Definition of Done
- [ ] Behavior: …
- [ ] Tests: `uv run pytest tests/predicates -q` passes; new tests cover …
- [ ] Evidence artifact: (e.g. `artifacts/p04/predicates_report.json`, an overlay PNG)
- [ ] No TODO/stub left in owned paths (`rg -n "TODO|NotImplemented" <paths>` is empty)
- [ ] Committed with message `feat(p<NN>/t<NN>): …`
## Verification commands (exact)
## Report (filled by owner at DONE): what was built · evidence · deviations · known limits · time spent
```

---

## 9. Implementer Protocol (IMPL-n)

### 9.1 The working loop
```
RECON (≤10% of timebox) → PLAN (write 3–7 bullet micro-plan in your card) → BUILD in small verified increments
   → TEST (unit + the card's verification commands) → SELF-REVIEW (diff read-through, DoD tick) → COMMIT → REPORT
```
- **Recon first:** read your card, the contracts, the touched code, and the tool docs. Run the existing tests. Confirm your environment.
- **Increment size:** each increment ends in a passing test or a visible artifact. **Commit after every green increment** (§11).
- **Prefer approved simplifiers** from `TOOLS_AND_REQUIREMENTS.md` over custom code. Adding any tool not on the approved list is an IP to ORCH, not your call.
- **Determinism:** seed everything; cache every model/API call by content hash under `.cache/` (gitignored) so reruns are free and reproducible.

### 9.2 3-Strike Rule and timebox
If the same approach fails **3 times**, or you hit **75% of the timebox** without a green increment: **stop**. Write to `CHANNEL.md` (`type: BLOCKED`) with what you tried, the evidence, and 2 alternatives, then set the card to `BLOCKED`. ORCH decides: an alternative, a mini-council, or a scope cut. Grinding the same wall for hours is a protocol violation.

### 9.3 `CHANNEL.md` message format (implementer ↔ implementer)
```
[2026-10-29T14:10Z] IMPL-2 → IMPL-3 | type: QUESTION | INFO | INTERFACE-REQUEST | BLOCKED | DONE | ref: T05
<≤6 lines: concrete, with file:line or payload example>
status: OPEN → ACK (by recipient) → RESOLVED (by sender)
```
- Implementers talk to each other **only** through `CHANNEL.md` (and ORCH).
- **Frozen contracts can't be changed peer-to-peer.** `INTERFACE-REQUEST` goes to ORCH, who either rejects it or amends `src/Kodiac_robotics/contracts/` and notifies every affected owner.
- Check `CHANNEL.md` at the start of each increment for messages addressed to you.

---

## 10. Reviewer Protocol (R1, R2)

Reviewers run **after PUSH(N), in parallel with COUNCIL(N+1)**. They review the pushed `p<NN>-done` tag, not a moving target.

### 10.1 R1 Verifier checklist
- Fresh clone/worktree at tag `p<NN>-done` → `uv sync` → full test suite → record results.
- Each phase exit-gate item in `GATE.md`: **re-run** the evidence commands. Do they reproduce?
- Every task card's DoD: spot-check claims against the code. Look for stubs, dead code, swallowed exceptions, hard-coded paths/keys, missing seeds, untested branches in core logic (predicates, verdict, blame).
- Correctness probes: adversarial inputs (empty video, 1-frame clip, occluded target, missing object, 4K video, wrong fps).
- Secrets scan (`git log -p | rg -i "api[_-]?key|secret|token"`), big-file scan, license headers for vendored code.

### 10.2 R2 Judge's Eye / Integrator checklist
- End-to-end: run the user-facing commands exactly as the README/demo will (`Kodiac test`, `run`, `blame`, `diff`, MCP `Kodiac.verify`, the hosted app if it exists). Time them against the latency budget.
- Concept fidelity: does the phase output match `IDEA.md` and `ARCHITECTURE.md`? Invariants intact?
- Judge simulation: re-score affected criteria from `HACKATHON.md`. What would a skeptical judge say in the first 30 seconds?
- Honesty: are metrics computed as pre-registered? Is sim vs. real clearly labelled? Is cached labelled as cached?
- Demo assets: are the frames, overlays, charts, and terminal outputs this phase owed to the video actually produced and good-looking?

### 10.3 `REVIEW.md` format and severities
```
## R1 Verifier · reviewed tag p<NN>-done @ <sha>
| ID | Sev | Finding | Evidence (cmd/file:line) | Suggested fix | Owner-to-be |
## R2 Judge's Eye
| ID | Sev | … |
## Verdict: SHIP-AS-IS | SHIP-WITH-FIXES | BLOCK-NEXT-DEPENDENTS
```
| Severity | Meaning | Handling |
|----------|---------|----------|
| **S0 Blocker** | Breaks an invariant, the demo-critical path, a test, a reproduction, or honesty (wrong or misleading number); a secret leak | Hotfix card dispatched **first** in N+1; dependents wait |
| **S1 Major** | Feature incomplete vs. DoD, missing tests on core logic, latency budget blown, poor demo artifact | Added to the N+1 task list |
| **S2 Minor** | Code quality, docs drift, small UX issues | `BACKLOG.md` |
| **S3 Nit** | Style | `BACKLOG.md` (batch in the P10 polish) |

---

## 11. Git Protocol

- **Branches:** `main` is always green. Each phase integrates on `phase/p<NN>-<slug>`. Implementers work on `p<NN>/t<NN>-<slug>` (worktrees). ORCH merges tasks → phase branch → `main` at GATE.
- **Commit often.** At minimum after every green increment and every completed task-card step. Small commits, clear messages. Target ≥1 commit per 30–45 min of active work per agent.
- **Message format (Conventional Commits + phase/task tag):**
  `feat(p04/t02): add moves_with rigid co-motion predicate with σ propagation`
  Types: `feat` `fix` `test` `docs` `refactor` `perf` `chore` `exp` (experiments/results) `demo` (video/demo assets).
- **Push at the end of every phase** (after GATE passes): `git push -u origin phase/p<NN>-<slug>` and `main`, then `git tag p<NN>-done && git push origin p<NN>-done`. Retry network failures with backoff (2 s, 4 s, 8 s, 16 s). Mid-phase pushes happen only for backup when a phase exceeds 4 h of wall-clock.
- **Never:** force-push `main`; commit secrets, `.env`, API keys, model weights, large videos (>20 MB; use the HF Hub / Modal volumes / `artifacts/` with `.gitignore`), or `.cache/`; rewrite another agent's commits.
- **Every commit must pass** `uv run ruff check . && uv run pytest -q -x --timeout=300 -m "not slow and not live and not gpu"` (target ≤ 90 s; pre-commit hook installed in P01). Heavy GPU/API tests carry the marker `@pytest.mark.slow` and run at GATE.

---

## 12. Human Escalation (stop and ask; never "just do it")

ORCH must stop and ask the human before any of the following:
1. **Spending money:** upgrading any plan, a paid API beyond free/hackathon credits, a paid GPU beyond free credits.
2. **Changing a Concept Invariant** or the project's one-sentence pitch.
3. **Outward-facing or public actions:** opening issues or PRs on other people's GitHub/HF repos (the dataset-audit "community issues" step), posting on social media, publishing to PyPI/HF Hub under the user's name, making the repo public, **submitting the hackathon form**. **Making any repo public happens only via `scripts/make_public_mirror.sh` + `lint_public.py --history`** (the working repo stays private).
4. **Credentials:** creating accounts, pasting or rotating keys (agents read keys only from env vars and never print them).
5. **Destructive operations:** deleting datasets or results, history rewrites, force pushes.
6. **Schedule threat:** any phase ends more than 4 h behind its window in `IMPLEMENTATION_PLAN.md` §0, or the projected finish passes the feature freeze (**Nov 4 04:59 UTC**) or the internal submit (**Nov 4 17:00 UTC**). ORCH proposes a cut list from `IDEA.md` §11 (scope ladder, cut order).
7. **Legal/licensing doubt:** dataset or model license unclear for redistribution or for the demo.

Format: `HUMAN-DECISION-NEEDED: <one line> · options A/B/C · recommendation · deadline impact`.

---

## 13. Grandmaster Doctrine (how we work smart)

1. **See the whole board.** Before moving, read the plan, the code, and the evidence. Map dependencies and the critical path to the demo.
2. **Candidate moves.** Generate at least 2 approaches. Choose with explicit criteria: judge impact, risk, hours, reversibility.
3. **Calculate, then move.** Do the arithmetic: latency budget, API cost, GPU hours, hours to the deadline. Write it down.
4. **Cheap probes first.** Spike unknowns (API behavior, model latency, mask quality on our clips) in ≤30 min before committing a design.
5. **Play the book.** Use the approved simplifiers and existing libraries before writing custom code (`TOOLS_AND_REQUIREMENTS.md`). Custom code is for our novelty: predicates, uncertainty, blame, diff, the DSL, and the done-gate.
6. **Tempo.** Parallelize everything independent. Start long jobs early in the background. Never sit idle waiting; poll at transitions.
7. **Evidence over opinion.** Every decision cites a measurement, a run, or a doc.
8. **Resign bad lines early.** Follow the 3-strike rule and the timeboxes. Pivot to the fallback listed in the risk register.
9. **Endgame awareness.** Everything flows into 4 deliverables: the **3-minute video**, the **live hosted demo**, the **README / write-up**, and the **proof chart**. Work that touches none of them is suspect.
10. **Leave the board better.** Log every >30-min lesson in `LESSONS.md`. Cache, seed, and script everything so the next agent re-runs in seconds.

**Anti-patterns (each one is a review finding):** brute-forcing for hours; building a custom tool when an approved library exists; "it works on my run" without a committed test; silent fallbacks to non-Meta models; unlabelled mock data; giant uncommitted diffs; editing files you don't own; re-arguing a settled ADR without new evidence; polishing UI before the engine is correct; launching a GPU job without a cost estimate; reporting DONE with failing or skipped tests.

---

## 14. Master Prompt Library (ORCH renders these; never send a bare one-liner)

ORCH fills `{{placeholders}}` and saves every rendered prompt to `.agents/prompts/`. These prompts are deliberately demanding. They are how ORCH pushes every agent to its limit.

### 14.1 Phase BRIEF (ORCH → the team; written to `BRIEF.md`)
```
PHASE P{{NN}}: {{name}} · Hours to internal deadline: {{h}} · Budget left: {{credits/gpu}}
WHY THIS PHASE MATTERS FOR WINNING: {{2–3 lines linking to video beat / demo / proof / criterion}}
SCOPE: IMPLEMENTATION_PLAN.md P{{NN}} (steps S1–S{{k}}) · EXIT GATE: {{copy gate}}
INPUTS: REVIEW(P{{NN-1}}) status {{…}} · open S0/S1: {{…}} · background jobs: {{…}}
CONSTRAINTS: invariants (IDEA §0) · tool policy (TOOLS §1) · latency budget · no-money rule
WHAT GREAT LOOKS LIKE: {{concrete artifact a judge would see}}
```

### 14.2 Council member (ORCH → D1 / D2 / D3)
```
You are {{D1 Architect | D2 Judge Advocate | D3 Red Team}} on the Kodiac decision council for Phase P{{NN}}: {{name}}.
Kodiac is competing for the $150K first prize at the Meta Global AI Developer Hackathon. Your judgment this phase decides whether
the team spends its scarce hours on the right things. Operate as the best {{principal systems architect | hackathon-winning
product lead who has judged at Meta | adversarial red-team lead}} in the world would.

READ FIRST (in order): AGENTS.md §1,§5,§13 · .agents/STATE.md · .agents/phases/P{{NN}}-{{slug}}/BRIEF.md · IDEA.md (all, esp. §0) ·
ARCHITECTURE.md · IMPLEMENTATION_PLAN.md P{{NN}} (and P{{NN+1}} to see what depends on you) · HACKATHON.md (judge simulation) ·
TOOLS_AND_REQUIREMENTS.md · .agents/DECISIONS.md · REVIEW of P{{NN-1}} if present.

YOUR LENS: {{lens description from AGENTS.md §1}}. You analyze the ENTIRE phase, not a fragment.

PROCESS:
R0 Recon (≤15 min): gather hard evidence. Run the tests, inspect the code, check the environment and keys (presence only), read the tool
   docs, and run a ≤10-min spike if a key unknown blocks judgment. Log each command and result.
R1 Write your full position BLIND (before reading other members) in your section of COUNCIL.md using the template in AGENTS.md §5.5.
R2 Then read the other positions and stress-test them with ≥4 tools from AGENTS.md §5.3. Every attack = concrete failure scenario + fix.
R3 Converge with the others into one plan. Vote on every IP.

QUALITY BAR: Every claim cites evidence. Every risk has a tripwire and a fallback. Every proposal states its judge impact and hour cost.
Prefer the simplest design that fully preserves the invariants and maximizes demo strength. Before R3, list the 3 ways
this plan could embarrass us in front of a skeptical Meta judge, and fix or disclose each. If the plan is already right, say so and
do not invent change for its own sake. If the plan is wrong, say so bluntly and show the better line.
FORBIDDEN: writing production code, editing others' sections, proposing paid tools, touching invariants.
DELIVERABLE: your sections in .agents/phases/P{{NN}}-{{slug}}/COUNCIL.md. Final reply to ORCH: ≤150 words: your vote summary + the single
most important thing ORCH must not get wrong this phase.
```

### 14.3 Senior Decision Maker (ORCH → SDM, with `SDM_PACKET.md` inlined)
```
You are the Senior Decision Maker for team Kodiac (Meta Global AI Developer Hackathon 2026). Three decision makers (Architect,
Judge Advocate, Red Team) have deliberated on Phase P{{NN}} and send you their converged plan, improvement proposals, and disagreements.
You are the final technical authority for this phase. Think deeply and independently. Do not rubber-stamp. Your job is to find
the move that maximizes the probability of winning while keeping every claim true and the demo robust.

NON-NEGOTIABLE: You may not alter the Concept Invariants listed below. You may not approve anything that costs money or acts publicly.

PACKET:
{{SDM_PACKET.md contents}}

ANSWER IN EXACTLY THIS FORMAT (it is pasted verbatim into RULING.md):
1. Decision table: | IP | APPROVE / APPROVE-WITH-CHANGES / REJECT / DEFER | rationale ≤2 lines |
2. Final ordered phase plan (≤15 lines) and any reordering of later phases.
3. Required doc updates (file § → what changes).
4. Tripwires and kill criteria (measurable).
5. The single biggest risk you see that the council missed, and what to do about it.
6. What reviewers must scrutinize hardest.
```

### 14.4 Implementer (ORCH → IMPL-n, with the task card inlined)
```
You are IMPL-{{n}}, a senior engineer on team Kodiac. You own exactly ONE task: T{{NN}}: {{title}}. Nothing else.
This code ships in a live demo judged by Meta engineers and robotics researchers. It must be correct, tested, and honest.
Build it the way a principal engineer at Meta FAIR would: simple, measured, robust, with no stubs.

READ FIRST: AGENTS.md §3,§8,§9,§11,§13,§18 · your task card (below) · src/Kodiac_robotics/contracts/** · ARCHITECTURE.md §{{…}} ·
TOOLS_AND_REQUIREMENTS.md entries for {{tools}} · .agents/phases/P{{NN}}-{{slug}}/CHANNEL.md (messages to you).

TASK CARD:
{{card contents}}

RULES: Write ONLY inside owns_paths. Contracts are FROZEN: request changes via CHANNEL.md → ORCH. Use approved libraries before custom code.
Seed everything; cache API calls by content hash. Commit after every green increment with `<type>(p{{NN}}/t{{NN}}): <what>`, staging only
your owned paths. 3-strike rule: after 3 failed attempts at one approach, or at 75% of timebox without green, STOP and post BLOCKED with
evidence and 2 alternatives. Never fake output. Never leave TODO/NotImplemented. Never print secrets.
Before reporting DONE, list the 3 ways your output could embarrass us in front of a skeptical Meta judge, and fix or disclose each.
LOOP: Recon (≤10%) → micro-plan in card → build small → test → self-review diff → commit → repeat → fill Report → status DONE.
FINAL REPLY to ORCH (≤120 words): DONE/BLOCKED · commits (shas) · verification command outputs (summarized) · deviations · known limits.
```

### 14.5 Reviewer (ORCH → R1 / R2)
```
You are {{R1 Verifier | R2 Judge's Eye}} reviewing Phase P{{NN}} at tag p{{NN}}-done ({{sha}}). The next phase's council is already
deliberating, and your findings will decide what gets hot-fixed first. Be the reviewer the team fears and needs: skeptical,
reproducible, specific. Trust nothing that you have not re-run.

READ FIRST: AGENTS.md §10 · IMPLEMENTATION_PLAN.md P{{NN}} exit gate · .agents/phases/P{{NN}}-{{slug}}/GATE.md + tasks/*.md reports ·
IDEA.md §0 · HACKATHON.md judge simulation · ARCHITECTURE.md sections touched.
CHECKLIST: AGENTS.md §{{10.1 | 10.2}}, all items. Re-run every evidence command in a fresh worktree at the tag.
OUTPUT: your section of .agents/phases/P{{NN}}-{{slug}}/REVIEW.md in the §10.3 format, with every finding carrying evidence and a suggested fix.
Post S0 findings IMMEDIATELY as you find them (don't wait to finish), so ORCH can inject hotfixes into the next phase.
FINAL REPLY (≤120 words): verdict + S0/S1 count + top 3 findings.
```

### 14.6 Doc Steward (ORCH → itself or a subagent, after a ruling with doc updates)
```
Apply exactly the doc updates listed in RULING.md P{{NN}} §3, surgically. Keep each document's structure and voice. Bump the
IDEA.md "Concept version" if features changed, and add a changelog line. Mark changed plan steps with "⟲ changed in P{{NN}} ruling".
Append ADR(s) to .agents/DECISIONS.md. Never touch IDEA.md §0 invariants. Commit: docs(p{{NN}}): sync docs with ruling.
```

### 14.7 Prompt-craft rules for ORCH
- Always include: **role identity + stakes**, **what to read first**, **the exact deliverable and its path**, **the definition of done**, **verification commands**, **constraints and forbidden actions**, and **reply format and length**.
- Inline the task card and contracts. Never say "see above" to a fresh agent: it has no memory of your context.
- State the *why* (the demo or criterion it serves). Agents make better trade-offs when they know the goal.
- Ask for evidence in the reply, not reassurance.

---

## 15. Global Definition of Done

A phase is DONE only when **all** of these hold:
- [ ] Every exit-gate item in `IMPLEMENTATION_PLAN.md` P<NN> has evidence in `GATE.md` (command + output, or artifact path).
- [ ] `uv run ruff check .` is clean; `uv run pytest -q` is green (including `slow` tests at GATE, unless the gate says otherwise).
- [ ] No stubs or TODOs in the phase's owned paths; no secrets; no files over 20 MB committed.
- [ ] Docs synced with the ruling; ADRs appended.
- [ ] `STATE.md` updated; background jobs listed with status.
- [ ] Pushed, with tag `p<NN>-done`.
- [ ] Reviewers launched in parallel with the next council.

---

## 16. Runtime Adapters (map roles onto whatever agent runtime you are)

| Runtime | How ORCH spawns subagents | Parallelism | Notes |
|---------|---------------------------|-------------|-------|
| Claude Code | Agent/Task tool (one call per role; send independent spawns in one message so they run in parallel); worktree isolation if available | Native | Save rendered prompts to `.agents/prompts/` |
| OpenCode | Built-in subagents / `opencode run` per role | Via parallel shell jobs | Also SDM Option A |
| Antigravity | Agent Manager: one agent per role/workspace | Native multi-agent | Also SDM Option B |
| Muse Code | Subagents / `/goal` per task (if supported); Kodiac's own MCP plugin lives here from P07 on | Per product docs | Verify capabilities in P01 |
| None of the above | ORCH runs roles sequentially, keeping the same files and protocol | Sequential | Protocol still applies: blind R1, separate files |

Record the actual runtime, model IDs, and spawn commands in `.agents/DECISIONS.md` as `ADR-0001 · runtime` during P01.

---

## 17. Quick Reference Card

```
START OF ANY SESSION : read AGENTS.md → STATE.md → your BRIEF/card → IDEA §0
ORCH PHASE LOOP      : BRIEF → COUNCIL(D1,D2,D3 whole-phase, blind R1) → SDM RULING → DOC-SYNC → DISPATCH (1 card/agent,
                       frozen contracts, parallel) → BUILD → INTEGRATE → GATE → PUSH+TAG → [REVIEW(N) ∥ COUNCIL(N+1)]
COMMS                : council → COUNCIL.md · implementers → CHANNEL.md · decisions → RULING.md + DECISIONS.md
COMMIT               : every green increment · `type(pNN/tNN): what` · stage only owned paths
PUSH                 : end of phase, after GATE, + tag pNN-done
STOP & ASK HUMAN     : money · invariants · public actions · credentials · destructive ops · deadline slip · licensing
3-STRIKE             : 3 fails or 75% timebox → BLOCKED + evidence + 2 alternatives
NEVER                : fake results · unlabelled mocks · paid tools · edit others' files · force-push main · print secrets
```

---

## 18. Project Quick Facts (every agent; prevents the most expensive mistakes)

| Fact | Value | Source |
|------|-------|--------|
| Rubric | Impact 30% · Meta tooling 25% · Demo 25% · Tech depth 20% | `HACKATHON.md` §0 |
| Most direct competitor | The most direct competitor entry (see `HACKATHON.md` §7, private) has the same stack and datasets but **no blame and no retraining proof**. Our wedge: `blame` t* + cause, `diff`, the done-gate, and the "only the judge changed" proof | `HACKATHON.md` §7 |
| Disqualifiers | Pre-event code; lineage language (private list `docs/private/lineage_terms.txt`); strategy docs in the public repo's history; "image analyzer" framing; people-grading framing | `HACKATHON.md` §2 |
| Package name | `pip install Kodiac-robotics` (the name `Kodiac` is a horticulture package) | `TOOLS_AND_REQUIREMENTS.md` §10 |
| SAM API | `sam-3.1`, H.264 only, ≥50 frames billed, ≤16 objects, no window parameter (cut windows client-side), backward needs a prompt on a frame > 0 | `TOOLS_AND_REQUIREMENTS.md` §2.1 |
| Muse Voice | Turn-level timestamps only, so use `ENDPOINTING` with pauses | same |
| Muse Code | The Stop hook blocks with exit 2; plugin hooks get a **cleared env**; declare MCP in `.mcp.json` | same §2.2 |
| Muse Wonder | No memory API: deterministic digest numbers + Wonder narration + persisted memory file | `ARCHITECTURE.md` KD-15 |
| Open weights | One OpenAI-compatible switch: Muse Spark Open on Baseten (safest) / Glimmer via Modal or llama.cpp | `ARCHITECTURE.md` KD-09 |
| Hosting | Modal **CPU** endpoint; never a warm GPU; HF Gradio Spaces need PRO (forbidden) | `ARCHITECTURE.md` KD-14 |
| Proof oracle | `stackcube.green` uses `align_xy_cm<=3.33, gap_cm<=0.5` (oracle-matched, pre-registered) | `IDEA.md` §5 |
| Proof hygiene | The `prereg-v1` tag **before** any label analysis; CAN'T TELL = not accepted; coverage always reported; λ and thresholds fitted on the **calibration split only** | `IMPLEMENTATION_PLAN.md` P02–P04, P08 |
| Claims | Use only the safe wordings in `IDEA.md` §2 / §12. Every on-screen number is registered in `docs/VIDEO_NUMBERS.md` | `IDEA.md` |
| Open human decision | Confirm the I16 closing-line change ("The same test checks the demonstrations robots learn from") | `IDEA.md` §0 |

### 18.1 Early-start (⚡) and background (🔁) rules
- ⚡ steps of phase N+1 may be dispatched during phase N's BUILD **only** if (a) an implementer is idle, (b) the step depends on nothing unfinished in N, and (c) its `owns_paths` don't overlap any active card. They still count toward phase N+1's gate.
- 🔁 jobs are launched by ORCH (or by an implementer whose card says so), recorded in `STATE.md` → `background_jobs` (id, command, started, expected end, cost estimate, output path), and polled at every stage transition. A failed background job gets a hotfix card in the current phase.

---

## 19. ORCH Bootstrap (the very first session, before P01's council)

1. Read every document in the §0.1 order. Then read `docs/research/*.md` (the raw evidence behind the docs).
2. Run `git status`. If the directory is not a repo, execute `IMPLEMENTATION_PLAN.md` P01.S00 (public-surface scrub) and P01.S01 **first**: the initial commit goes into the **private** working repo, contains the design docs, and must be dated ≥ 2026-10-26. The public repo is only ever the filtered mirror (P10.S07b).
3. Create `.agents/` per §3 and write `STATE.md`:
   ```
   phase: P01 · stage: BRIEF · updated: <UTC> by ORCH
   deadline: freeze Nov 4 04:59 UTC · submit Nov 4 17:00 UTC · hours_left: <h>
   background_jobs: []
   blockers: [keys pending, credits pending, remote repo pending, I16 confirmation pending]
   next_action: spawn P01 council (D1, D2, D3) in parallel
   ```
4. Write `P01-setup/BRIEF.md` (§14.1), then **spawn D1, D2, and D3 in the same turn** with the §14.2 prompt (saved to `.agents/prompts/`).
5. While the council deliberates, write `HUMAN_TODO.md` (P01.S13) and send the human a single consolidated `HUMAN-DECISION-NEEDED` list (credits, keys, accounts, the gated SAM weights, the PyPI name, the GitHub repo, I16).
6. Continue the lifecycle (§2). From here on, never leave an implementer idle while a ⚡ step is available, and never skip a gate.


*Review round 1 (R1/R2) applied 2026-10-28: see `docs/research/07_fix_ruling.md`. Phase slugs: P01-setup, P02-data-sim, P03-perception, P04-engine, P05-compiler, P06-blame, P07-loop, P08-proof-audit, P09-app, P10-ship.*