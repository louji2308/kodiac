# HACKATHON.md: Meta Global AI Developer Hackathon: Intelligence, Rules & Judge Simulation

> **Purpose.** Everything an agent or human on team Kodiac needs to know about the competition we are entering, and a
> **reverse-engineered judge's view** of what wins. Section 9 is written in the voice of a real judge. It is the bar every
> phase of `IMPLEMENTATION_PLAN.md` is measured against.
>
> **Source quality tags:** **VERIFIED** = official public page or Meta-owned post · **PARTIAL** = login-walled participant guide /
> Official Rules / Discord as quoted by ≥2 independent participants · **UNVERIFIED** = single secondary source or inference.
> Raw research with all links: `docs/research/02_hackathon_intel.md`. Compiled 2026-10-27, build-window day 2.
> **Re-verify PARTIAL items in the CV portal** (rules "can be modified").

---

## 0. TL;DR Card (memorize this)

| Item | Value | Tag |
|------|-------|-----|
| Event | **Meta Global AI Developer Hackathon**: virtual, worldwide, Meta × Cerebral Valley, up to 20,000 participants | VERIFIED |
| Our track | **Indie Developer**: "Judged on **creativity, technical ambition, and whether it works**." One track per project. | VERIFIED |
| Our theme | **Push the Frontier**: "**Give a machine a new capability**, accelerate a scientific experiment, or **unlock a better way to understand and control a physical system.**" | VERIFIED |
| Prize | Indie: **$150K** / $100K / $75K / $50K / $25K, plus **$50K bonus pool** (bonus prizes stack with track prizes) | PARTIAL |
| **Hard deadline** | **Wed Nov 4, 9:00 PM EST = Thu Nov 5, 02:00 UTC** (US DST ends Nov 1). Late = not considered | VERIFIED |
| **Our internal deadline** | **Submit by Wed Nov 4, 12:00 PM EST (17:00 UTC).** Feature freeze Tue Nov 3, 23:59 EST | Team rule |
| Rubric | **Impact 30% · Use of Meta AI Tooling 25% · Demo 25% · Technical Depth & Execution 20%**, each scored 0–10 | PARTIAL (strongly corroborated) |
| Gate (pass/fail) | Fits a problem statement **and** "genuinely" uses the Meta Model API and/or Meta open weights | PARTIAL |
| Primary artifact | **3-minute demo video**, "alongside code and live product" | PARTIAL |
| Must submit | Public repo · working video link · all contributors listed · (optional) X post link for Most Viral | PARTIAL |
| Judging | Nov 4/5 – 8 online; **top 5 per track → live final Mon Nov 9, 12:00 PM EST (17:00 UTC)**; community vote Nov 9–16 | VERIFIED / PARTIAL |
| New-work rule | "**Anything built from 26 Oct to 4 Nov counts. The demo must show only work done during the event, or the project is disqualified.**" | PARTIAL |
| Credits | $150 Meta Model API per participant (claim by Nov 4, 9 PM ET; card pre-auth; **spend alerts do not stop billing**) · Modal $100 (first 1,000) · Baseten $100 + 2M TPM (≤2,000, reviewed) · Fireworks $25 (shortlisted) | VERIFIED / PARTIAL |
| Judges | **Not published.** Expect Meta MSL engineers/researchers + Meta DevRel + partner reps; Meta leadership at finals (inference) | UNVERIFIED |

**Bonus prizes we target** (PARTIAL): **Most Viral** $20K (X engagement through Nov 8 EOD) · **Best Build on Open Weight Models** $10K (`--local-glimmer` / Muse Spark Open on Modal/Baseten) · **Best Agentic Use-Case** $5K (Muse Code `/goal` + done-gate) · **Best Creative Build** $5K ("most original use of Muse Image or **Muse Wonder**": Wonder adjudication + failure memory). Plus Community Vote $10K. **Upside: $150K + up to $50K.**

---

## 1. The Event

### 1.1 Identity & format
- **Official name:** Meta Global AI Developer Hackathon ("2026" is not part of the official name). Organizers: **Meta** with **Cerebral Valley** (CV runs the listing, application, Discord, and submission portal). VERIFIED. [CV](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) · [Meta](https://dev.meta.ai/events/global-hackathon)
- **Format:** virtual, worldwide, free if selected: "Ten days, access to Meta's newest models and $1M in prizes." Meta tagline: **"Build the future of superintelligence with us."** VERIFIED.
- **Required Meta tech (public page):** "Use the **Muse Spark series, Muse Image and SAM 3.1** through Meta Model API, run Meta **open weights** models, and code faster with **Muse Code** agentic coding agent." The participant guide adds **Muse Wonder**, **Muse Voice Transcribe**, and the open-weight **Muse Glimmer** and **Muse Spark Open**. VERIFIED / PARTIAL.

### 1.2 Timeline (all times converted; **DST ends Sun Nov 1** → ET = UTC−5 from then)

| Date | Event | ET | UTC | Tag | Our action |
|------|-------|----|-----|-----|-----------|
| Sun Oct 25 | Applications closed | 11:59 PM | Oct 26 03:59 | VERIFIED | n/a |
| Mon Oct 26 | Kickoff livestream; **build window opens** (new-work clock starts) | 12:00 PM | 16:00 | VERIFIED | First commit of the repo must be dated ≥ Oct 26 |
| Tue Oct 27 | Agents 101: build a multimodal agent (Suraj Subramanian, Meta DevRel) | 12–1 PM | 16:00 | PARTIAL | Watch the recording |
| **Wed Oct 28** | **Agents 102: verifiable agents best practices** (Yash Khare) | 12–1 PM | 16:00 | PARTIAL | **Attend live.** Same idea as our done-gate; reuse its vocabulary honestly |
| Fri Oct 30 | Specialized intelligence on Fireworks: Muse Open models (Sinan Ozdemir) | 12–1 PM | 16:00 | PARTIAL | Attend (open-weights bonus) |
| Weekdays | Discord `#office-hours` (Meta team, text) | 10–11 AM | 14:00 → 15:00 from Nov 2 | PARTIAL | Ask the §12 questions |
| **Sun Nov 1** | DST ends | n/a | n/a | n/a | **Backup demo video recorded** (team rule) |
| **Mon Nov 2** | n/a | n/a | n/a | n/a | **Go/no-go on the headline retraining experiment** (team rule) |
| **Tue Nov 3** | n/a | 23:59 | Nov 4 04:59 | n/a | **Feature freeze** (team rule) |
| **Wed Nov 4** | **Submissions due + last day to claim credits** | **9:00 PM** | **Nov 5 02:00** | VERIFIED | **Submit by 12:00 PM ET.** Post the X demo early in the day |
| Nov 4/5–8 | Online judging (video + code + live product) | n/a | n/a | VERIFIED/PARTIAL | **Hosted demo must stay up and funded** |
| Through Nov 8 EOD | Most Viral engagement window | n/a | n/a | PARTIAL | Engage on X |
| **Mon Nov 9** | **Closing ceremony + live finals** (top 5/track) | **12:00 PM** | **17:00** | VERIFIED (12 PM: PARTIAL) | Have a live pitch and a hot demo ready |
| Nov 9–16 | Community vote → winner Nov 16 | n/a | n/a | PARTIAL | Share the gallery link; keep the demo funded through Nov 16 |

> **Deadline trap:** some aggregators list "Nov 5, 6:30 AM IST" = 01:00 UTC (that's 9 PM *EDT*, an hour early). We treat **01:00 UTC Nov 5** as the absolute internal cutoff and aim for 17:00 UTC Nov 4.

### 1.3 Tracks
| Track | Description (verbatim) | Prize pool |
|-------|------------------------|-----------|
| **Indie Developer** (ours) | "For individual builders and students. Judged on creativity, technical ambition, and whether it works." | $400K (150/100/75/50/25) |
| Startup | "For teams and founders building a real product. Judged on technical execution and whether it holds up in production." | $550K (250/150/75/50/25) |

Team size: up to **4**, solo allowed. One submission per team, entered by an appointed **Representative**, who receives the prize. PARTIAL.

---

## 2. Rules That Can Disqualify Us (and our compliance actions)

| # | Rule (verbatim or close) | Risk to Kodiac | Compliance action (binding) |
|---|---|---|---|
| R1 | **New work only:** "Anything built from 26 Oct to 4 Nov counts. The demo must show only work done during the event, or the project is disqualified." "Unclear contribution = immediate disqualification." (PARTIAL) | Our pre-event source spec contains lineage wording (kept in `docs/private/`, never public) | Ideas may predate the event; **all code is written in-window**. The first commit is ≥ Oct 26. Keep a dated `BUILD_LOG.md`. The working repo stays **private**; the public repo is a **filtered mirror** (`git filter-repo`) linted against `docs/private/lineage_terms.txt` over its full history. Third-party OSS is listed in `ATTRIBUTIONS.md` |
| R2 | **Anti-projects:** "…Basic RAG Applications; **Simple Image Analyzers**; … AI Job Application Screener; … Personality Analyzers; Sports analyzers…" (PARTIAL). The sister Google rule explains: "*Basic object identification is obsolete. We want to see **spatial-temporal video understanding that recognizes cause and effect**.*" | A lazy read of Kodiac is "an image analyzer." The source spec's closing line, *"The same test can check the person who teaches the robot,"* reads as **AI grading human workers** (close to the banned screener/analyzer logic) | Always frame Kodiac as **spatio-temporal, causal video understanding**: "finds the exact moment and physical cause." **Replace the closing line** with *"The same test checks the demonstrations robots learn from."* Talk about **data**, not people |
| R3 | **Gate:** must fit a problem statement **and** "genuinely" use the Meta Model API / open weights | Low (Meta models are load-bearing by design) | Name the theme in the README's first screen with the official phrase. Show live Meta calls (provider + latency visible) |
| R4 | Public repo · video link works · all contributors listed | Low | Pre-submit checklist (§11). Test the video link in an incognito window |
| R5 | Open-source components allowed if licenses are followed (PARTIAL) | SAM/Muse weight licenses; DROID/LeRobot dataset licenses | `ATTRIBUTIONS.md`; never redistribute weights; cite datasets |
| R6 | Late submissions not considered | n/a | Internal deadline 17:00 UTC Nov 4 |
| R7 | Credits: spend alerts **do not stop billing** (Discord `#faqs`, PARTIAL) | Real money risk during judging traffic | Hard per-key spend limit, server-side rate limiter, a cached-replay fallback, and a daily spend check (Nov 5–16) |

---

## 3. Prizes & Bonus Strategy

| Award | $ | How it's won | Kodiac lever | Owner phase |
|---|---|---|---|---|
| **Indie 1st** | **150,000** | Top weighted score + live final | The whole project | All |
| Most Viral | 20,000 | Highest X engagement on the demo post through Nov 8 EOD; post link submitted | Cold open: real robot "success" clips freezing at the blamed frame with a red SAM outline. Very shareable | P08 (audit card) + P10 (X post) |
| Best Build on Open Weight Models | 10,000 | Muse Glimmer / Muse Spark Open on own hardware or partner inference | `--local-glimmer` crop judge on Modal/Baseten; open SAM 3.1 batch audit on Modal; **show cost/latency per 1,000 episodes** | P06, P08 |
| Community Vote | 10,000 | Public gallery votes (Nov 9–16) | Gallery post + X thread | P10 |
| Best Agentic Use-Case | 5,000 | "Strongest agent autonomy and multi-step workflows" | Muse Code `/goal` loop: blame → patch → re-run → done-gate PASS, N/10 seeded bugs, one unedited take | P07 |
| Best Creative Build | 5,000 | "Most original use of Muse Image or Muse Wonder" | Muse Wonder as hard-case adjudicator + a failure digest over a whole dataset (deterministic numbers; Wonder narrates over its 1M context) | P06, P08 |

---

## 4. What Meta Wants (verbatim signals → what we do with them)

| Meta said | Source | Implication for Kodiac |
|---|---|---|
| "Build the future of superintelligence with us… build with our **newest** models." | [X](https://x.com/MetaforDevs/status/2110045152601633114) | Use the newest releases (Muse Spark 1.3, Muse Wonder 1.0, SAM 3.1 Multiplex, open weights) where they are load-bearing |
| "Give a machine a new capability… unlock a better way to **understand and control a physical system**." | [CV](https://cerebralvalley.ai/e/meta-ai-developer-hackathon.md) | Our one-liner: **"Kodiac gives robots, and the pipelines that train them, the ability to know when they failed, exactly when, and why."** |
| Muse Spark 1.3 "brings frontier-level reasoning to complex coding and agentic workflows"; Muse Code "out of beta for long-horizon engineering work." | [Meta Connect recap](https://developers.meta.com/blog/meta-connect-recap/) | Spark compiles specs and judges crops. The Muse Code plugin extends Meta's own coding agent with a **physical-world verifier** |
| Muse Wonder: "Frontier Models for Agents" with **Active Memory** and **Active Focus** ("checking before important actions"). | [Meta Newsroom](https://about.fb.com/news/2026/10/introducing-muse-wonder-models/) · [research blog](https://research.meta.ai/blog/muse-wonder) | Wonder adjudicates contested crops (Active Focus = check before committing a verdict) and narrates the dataset failure digest (no memory API is used) |
| "Open weights, meet your favorite stack": Fireworks, Baseten, Modal. | [X](https://x.com/MetaforDevs/status/2112971571321332179) | A real open-weights path, measured, not a checkbox |
| SAM 3.1: **Object Multiplex**, faster multi-object video tracking on "smaller, more accessible hardware." | [GIGAZINE](https://gigazine.net/gsc_news/en/20260331-meta-releasing-sam-3-1) | SAM 3.1 is our measuring instrument and "time machine" (backward tracking to t*). **This is the "unexpected capability" moment** |
| Meta acquired ARI (Lerrel Pinto & Xiaolong Wang) → MSL + Meta Robotics Studio (May 2026). | [SiliconANGLE](https://siliconangle.com/2026/05/01/meta-acquires-robot-software-startup-assured-robot-intelligence/) | Physical AI is strategic for Meta. A robot-learning *data and eval* tool is on-strategy. Robotics-literate judges are plausible |

**Hero products, ranked by how much a creative use will be noticed:** (1) Muse Wonder (two weeks old, own bonus); (2) open weights on partner stacks (own bonus, own X post); (3) Muse Code (GA, few teams will *extend* it); (4) SAM 3.1 (Meta-unique; "no equivalent"); (5) agents + *verifiability* (2 of 3 workshops); (6) physical-world AI.

**Note:** Muse Image is part of the release, and **Kodiac does not use it**. Never claim "every product in Meta's release is load-bearing." Claim **"every Meta model we use is load-bearing, and we show each one's measured contribution."**

---

## 5. Sponsors & Partners

| Sponsor | Gives | Wants to see (inference from their posts) | Our honest appeal |
|---|---|---|---|
| **Meta** (host) | $150 API credits/person, models, Muse Code, $1M | Newest models doing surprising work; open-weights adoption; agents | Ablation ladder showing each Meta model's marginal gain; Muse Code plugin |
| **Cerebral Valley** | Platform, Discord, livestream | Polished, shareable, rule-compliant submissions | Clean README, a working link, an on-time submission, a viral cold open |
| **Modal** | $100 (first 1,000) | Serverless GPU jobs | Open SAM 3.1 batch audit + always-on CPU live endpoint (min_containers=1, Nov 4–16; no warm GPU) |
| **Baseten** | $100 + 2M TPM (reviewed); **use `meta-models/muse-spark-open-1026`** | Production inference of Muse Spark Open | Open-weights crop judge (if credits granted) |
| **Fireworks** | $25 (shortlisted), workshop | Specialized/fine-tuned open models | Optional: report cost/latency of the open-weight crop judge; no fake fine-tune |

---

## 6. People, Sessions, Judges

- **Judges are not published** (VERIFIED absence as of Oct 27). Precedent: LlamaCon 2025 was "judged by a panel from Meta and sponsoring partners"; CV's Anthropic hackathons ran finals in front of the product's creators. **Inference:** a first round by Meta MSL engineers and researchers plus DevRel plus partner reps; finals with Meta leadership and Muse product owners.
- **Suraj Subramanian** (Meta DevRel, PyTorch speaker): values open source, clean quickstarts, research → practice. → `pip install`, a 60-second quickstart, cookbook-grade README.
- **Yash Khare** (Agents 102, "verifiable agents"): the session's existence tells us Meta cares about **verifiable agent behavior**. → The done-gate is "a verifiable agent for the physical world."
- **Sinan Ozdemir** (Fireworks, open-model specialization). → Real open-weights numbers.
- **Lerrel Pinto** is at Meta (MSL, via ARI). He is **not known to be a judge**. His work values real-world evaluation, honest failure analysis, and "nuanced details" (OK-Robot). → If any robotics judge reads the README: failure-mode breakdowns, real DROID footage, accurate citations. **Correction:** Robot Utility Models (RUM) was an NYU + Hello Robot paper. RUM uses an mLLM verifier to decide **when to retry** at deployment; it is **not** a self-practice filter-and-retrain loop. Do not misattribute our experiment design to RUM (see `docs/research/04_related_work.md`).

---

## 7. Community Signal & the Competitive Field (this hackathon)

| Entry (public repo) | What it does | Overlap with us | Our wedge |
|---|---|---|---|
| **[Winnow](https://github.com/kleongf/winnow/blob/main/docs/plan.md)** ⚠ **most direct competitor** | Plain-English description of a good demo → rubric → **SAM 3.1 + Muse Spark 1.3** judge (Glimmer as a second opinion) → keep / reject / needs-review. Uses **droid_100 / droid_1.0.1 + RoboFAC** with the **FailBench protocol** (balanced accuracy, precision on Keep). "**Policy training is explicitly out of scope.**" | **Very high**: same stack, same datasets, same metrics | (1) a `.green` test **compiled from a spoken demo** with measured predicates and ±σ, not a rubric; (2) **`blame`/`diff`**: onset frame + physical cause; (3) the **Muse Code done-gate loop**; (4) **the downstream "only the judge changed" retraining proof, which Winnow explicitly does not do**. Our story must make all four obvious inside 60 s |
| [ReActSim](https://github.com/bigse0u1/ReActSim) | SAM 3.1 + Muse Spark Franka agent in **ManiSkill 3**; diagnoses grasp slip/drop/missed placement "from the physics state," replans; "Chaos Mode" | **High** on the sim self-repair loop | We judge **pixels, not physics state**: it works on **real footage** where no simulator state exists. We output **t*** + a measured cause + `CAN'T TELL`, and a **compiled, human-readable test** from one demo. Our loop is a **Muse Code plugin**, not a bespoke agent |
| [Hasami](https://github.com/nickthelegend/hasami) | SO-101 in MuJoCo that "checks its own work and retries" | Medium | Same wedge, plus the dataset audit and the judge-changed retraining proof |
| [FOROS](https://github.com/Volgat/foros-meta-hackathon) | Voice → spatial reasoning → industrial robot code | Low–medium (voice → spec) | Our voice step compiles a **test**, not a program |
| [before-the-tape](https://github.com/felixbennet/before-the-tape) / [100proof](https://github.com/NextTyrCreator/100proof) | SAM 3.1 video verification (packing bench / home inventory) | Medium (video verification) | Robot-learning domain, temporal predicates, blame, and a downstream training-success proof |
| [verifiable-evidence-agent](https://github.com/genda-benjamin/verifiable-evidence-agent) | Code-checked citations; abstains when evidence is insufficient | Philosophy (abstention) | Our abstention is a **calibrated physical noise floor** (±σ cm) |

**Outside the hackathon:** **Instance** (YC S26) sells a commercial pass/fail success detector with subtask captions. **MANGO** (2026) and **RAPID** (2026) are academic "test oracles / one demo → testable spec → coding agent" work. Judges may know them. Our answer is the *combination* (see `IDEA.md` §6, novelty statement): a readable test from one spoken demo, graded from **pixels only** with abstention, blame + diff, a coding-agent done-gate, and a controlled retraining result.

**Signal:** "verifiable" is a crowded motif, and robotics-in-sim is getting crowded. Winnow already grades real DROID footage with the same Meta stack, so "we grade real robot video" is **not** a wedge by itself. **Nobody (publicly) does frame-level *blame* (onset frame + measured cause) on real robot-learning footage, or proves downstream training impact.** Those are our wedges. Lead with real footage frozen at the **blamed frame**, and close with the **retraining chart**. (Absence from search ≠ proof of absence.)

---

## 8. Past Winners: What 1st Place Has in Common

| Event | Winner | Why it won (pattern) |
|---|---|---|
| Llama 3 Hackathon 2024 (Meta+CV) | **OpenGlass**: $20 open smart glasses | Physical, live "wow"; a novel capability; a 1,500-person waitlist = demand proof |
| Llama 3 Hackathon 2024 | Deb8 (2nd): debate arena with a judge agent | Multi-agent with a **built-in judge** |
| LlamaCon 2025 (Meta+CV) | **OrgLens**: expert matching | Concrete enterprise pain; working full-stack app |
| LlamaCon 2025 | Llama CCTV Operator (3rd): Llama 4 finds video events | **Newest multimodal capability on video**, the closest precedent to us |
| Llama Impact London 2024 | **Guardian**: A&E triage | Named institution + measurable outcome |
| Built with Opus 4.6 (CV, virtual) | **CrossBeam**: permit assistant by a lawyer | Domain expert; real users; a concrete bottleneck |
| Built with Opus 4.6 | TARA: road appraisal from dashcam | **Video → measurement** rewarded |
| Built with Opus 4.7 (CV, virtual) | **Medkit**: an agentic grader scores encounters against published guidelines | **A grader against an explicit spec won 1st** + pilots = impact proof |
| Gemini 3 Hackathon | **Globot**: 4 specialist agents + a 5th agent that **stress-tests the others** | Agentic orchestration with **built-in verification** |

**Seven patterns.** (1) A named beneficiary with felt pain. (2) Proof on real inputs plus an adoption signal. (3) The sponsor's *newest* capability carries the project. (4) **Verification/grading inside agentic systems keeps winning**, which is very favorable for us. (5) One end-to-end flow beats breadth. Pure research depth places but doesn't win. (6) A visual "wow" in the first seconds. (7) Don't borrow banned framings (medical, people-grading).

---

## 9. REVERSE ENGINEERING: The Judge Simulation

> *This section is written from the judge's chair. Every agent reads it before making demo, video, README, or scope decisions.*

### 9.1 Who is judging us (simulated panel)

| Persona | Background | What they reward | What makes them roll their eyes |
|---|---|---|---|
| **J1 "The Perception Researcher"** (Meta MSL / FAIR) | Built or used SAM; knows tracking failure modes | SAM used in a way they hadn't thought of (**measurement over time, backward propagation**); honest failure galleries; numbers with *n* | "SAM segments things" (old news); 2D-projection false passes; no error bars |
| **J2 "The Robotics Researcher"** (MSL robotics / Robotics Studio) | Trains policies on DROID/LeRobot data; has scrubbed video for hours | **"This would save my lab a week"**; real-footage validation; correct citations; the downstream-success experiment | Sim-only claims; misquoted papers (RUM!); "+Y points" without seeds or CIs |
| **J3 "The Platform DevRel"** (Muse/Meta Model API) | Owns Muse Code / API adoption | **Extends Meta's platform** (Muse Code plugin, MCP); a clean quickstart; open weights on partners; distinct jobs per model | Kitchen-sink model lists; "could swap any LLM"; broken install |
| **J4 "The Product/Impact Judge"** (CV / Meta product) | Non-roboticist; watches 100+ videos | Understands the pain in 20 s; a hook in 5 s; who uses it next week; a polished arc | Jargon (bisect, predicates, σ) before the "why"; slides; >3:00 |
| **J5 "The Finals Panel"** (Meta leadership) | Strategy lens | On-strategy for Meta (physical AI, agents, open weights); a crisp story; live robustness | Anything that breaks live; overclaiming |

### 9.2 How a first-round judge actually spends ~5 minutes on us (inference: thousands of submissions)

```
0:00–0:05  Video hook. Do I lean in or reach for the next tab?     → MUST: real robot "success" clip freezes at the failure frame, red outline, one-line caption
0:05–0:30  Do I understand WHO hurts and WHY?                       → MUST: "Robot learning runs on people scrubbing video. Wrong 'success' labels poison training."
0:30–2:30  Is it real? Is it working software? Is Meta doing it?   → MUST: live terminal/UI, real outputs, model names on screen, timer visible
2:30–3:00  Is there proof and a way to use it?                      → MUST: the chart with n/CI, the pip install, the live URL
+60 s      README skim: live URL at top? eval table? shipped table? → MUST: the first screen answers what/why/try-it/proof
+60 s      Click the live demo. Does it work on MY input?           → MUST: zero login, <12 s, graceful CAN'T TELL on weird input
```
**If any MUST fails, we drop ~1–2 points on that criterion. If the live link is dead, Demo drops to ≤5.**

### 9.3 Criterion-by-criterion: what earns a 6 vs. a 9 vs. a 10

#### Impact (30%): "real-world potential, who benefits, how much it matters, could people use it, fits a problem statement"
| Score | What the judge sees |
|---|---|
| 6 | Plausible problem for a niche audience, shown on sim/toy data, "could be used by…" |
| 8 | Real pain quantified with sources, run on **real public datasets**, a clear install path, the theme named |
| **9–10** | All of 8 **plus an adoption signal from outside the team** (a dataset maintainer confirms flagged episodes; a researcher runs it on their own data with permission to quote) **plus** a quantified saving ("N hours of review per 1,000 episodes → minutes") |
**Our levers:** the public-dataset audit with hand-verified flags; one consolidated, helpful issue per dataset (**human-approved outward action**); a LeRobot-compatible verdict export; `pip install`; the official theme sentence. **Kill risk:** one wrong public flag, or a tone that shames maintainers. Every public flag is hand-verified, and the framing is "here to help."

#### Use of Meta AI Tooling (25%): "how creatively… beyond a basic integration… surfaced unexpected capabilities"
| Score | What the judge sees |
|---|---|
| 6 | Sensible API calls in a pipeline; no surprise |
| 8 | Multiple Meta models with distinct, visible jobs; an open-weights path |
| **9–10** | **An "I didn't know SAM/Muse could do that" moment** (SAM 3.1 run **backward in time** as a measuring instrument to find frame 114) **plus measured per-model gains (ablation ladder) plus a platform extension** (a Muse Code plugin whose done-gate makes Meta's agent verifiable in the physical world) |
**Our levers:** lead the tooling story with **one** surprise (backward SAM). Show the ablation numbers on screen for ~5 s. Give each model one job. Show provider and latency live. **Kill risk:** box-ticking (6+ models narrated in 3 minutes), "only Meta can do this" (rebuttable). Say instead **"Meta's stack made this practical."**

#### Demo (25%): "working, impressive demo… holds up live… quality of the demo video"
| Score | What the judge sees |
|---|---|
| 6 | Nice video; the live site is slow, broken, or gated |
| 8 | A good video; the live site works on samples |
| **9–10** | **Unscripted live moment** (judge-supplied clip, or a camera-cover → `CAN'T TELL`), a visible wall-clock timer, the live product matching the video exactly, a one-take agent loop, ≤3:00 with a story arc |
**Our levers:** a zero-login hosted page; always-on CPU container; a labeled "Instant Cached Replay"; uptime monitor + funded keys through Nov 16; a plain-language voiceover ("the exact moment it went wrong") with dev terms as on-screen text. **Kill risk:** a dead URL Nov 5–9; "<12 s" claimed but 40 s live; an unlabeled cached result.

#### Technical Depth & Execution (20%): "engineering is sound and thoughtfully refined… real craft"
| Score | What the judge sees |
|---|---|
| 6 | Ambitious design, partial implementation, impressive but unverified numbers |
| 8 | The hard parts built and tested; an eval table |
| **9–10** | Hard parts **built, measured, and honestly bounded**: eval tables with ***n* and 95% CIs**, a failure gallery, ablations, a pre-registered experiment, a shipped/not-shipped table, tests + CI, one-command reproduction, a dated build log |
**Our levers:** the calibrated uncertainty gate, the predicate engine, two-stage bisect, contrastive crop querying, pre-registration, DROID real-footage validation, `trace.jsonl` provenance. **Kill risk:** half-finished features; the headline experiment missing or underpowered; a misquoted citation.

### 9.4 Scorecard simulation (our estimate as a skeptical panel; an inference, not a prediction)

| Criterion (weight) | Source spec as written, if fully built | **Kodiac as planned in these docs** (fixes applied) | Delta driver |
|---|---|---|---|
| Impact (30%) | 6.5–7.5 | **8.5–9.5** | Real-footage audit first, external confirmation, people-grading framing removed, hours-saved number |
| Meta Tooling (25%) | 8.0–9.0 | **9.0–9.5** | One surprise (backward SAM), ablation ladder, Muse Code plugin, measured open-weights path, accurate claims |
| Demo (25%) | 7.0–8.5 (high variance) | **8.5–9.5** | Reliability engineering (always-on CPU container, cached replay, spend caps, uptime), plain-language VO, judge-supplied input |
| Tech Depth (20%) | 7.5–8.5 | **8.5–9.5** | Scope ladder (MVP first), n + CIs everywhere, honest shipped table, corrected citations |
| **Weighted** | **≈7.2–8.3** | **≈8.6–8.9** (risk-adjusted, per review R2) | |

**Review correction (R2 panel):** the plan *as written* scores ≈ **7.8** risk-adjusted. The review fixes (walking skeleton, appearance benchmark, time-saved study, early outreach, Teach-it-live tab) lift it to ≈ **8.6–8.9**. Closing the gap to the ≥ 9.0 needed for the final (§9.11) depends on live reliability and an external confirmation.

*(Internal self-scores have no grounding in the real rubric. Never quote them anywhere.)*

### 9.5 The winner profile for the Indie track (what the $150K project looks like)

A judge-ready winner in this track will almost certainly have **all seven** of these. Kodiac must hit every one:

1. **A one-sentence capability that is new to machines.** → *"Robots can finally fail a test."*
2. **A real, felt pain with a named user.** → robot-learning teams and dataset curators scrubbing video, plus poisoned training labels.
3. **Real inputs, not toy inputs.** → DROID / LeRobot public footage, hand-verified.
4. **The newest Meta capability doing something surprising and load-bearing.** → SAM 3.1 as a time machine. Muse Wonder adjudicates. The Muse Code done-gate.
5. **Measured proof with honest bounds.** → the judge-changed retraining chart + the judge benchmark with n/CI + the ablation ladder.
6. **A live product that survives a stranger.** → hosted page, <12 s, `CAN'T TELL` under occlusion, works on their clip.
7. **A polished, ≤3:00, jargon-light video with a 5-second hook**, plus a README that answers what/why/try/proof on screen one.

**The one thing that separates 1st from 2nd–5th:** *external validation of impact* (pattern 2 in §8). Start it in P02 (first researcher contact) and send the first maintainer note in P06, and get human approval for every outward contact.

### 9.6 Likely judge questions, with our one-line answers
1. *"Isn't this just VLM-as-a-judge?"* No. SAM 3.1 geometry decides. The VLM only sees zoomed crops for appearance checks, asked both ways, and the ablation shows the difference.
2. *"How do you know your flags are right?"* Hand-verified with *n* stated, our own blind-labelled DROID slice (n, raters stated), and every verdict links to its frames in `trace.jsonl`.
3. *"Sim results don't transfer."* The retraining experiment is labelled simulation. The real-footage accuracy line comes from DROID.
4. *"Single camera, occlusion?"* The uncertainty gate says `CAN'T TELL`. Watch: we cover the camera live.
5. *"Did you build this during the event?"* First commit is Oct 26 or later, the build log is dated, and the external libraries are listed.
6. *"Who uses this next week?"* Dataset maintainers (here's the issue they replied to), robot-learning labs (`pip install`), and any Muse Code user (the plugin).
7. *"Why Meta's stack?"* SAM 3.1 Multiplex makes dense multi-object tracking fast enough for a live path (we publish the measured p95 over n ≥ 30 runs). Muse Code is the host agent. Open weights keep private robot data private. Each model's gain is measured.
8. *"Why not just use the simulator's success flag?"* Real robots have no simulator. Kodiac works from pixels alone, and that's the point.

### 9.7 Kill-shots (instant credibility loss; zero tolerance)
- Any number we can't reproduce on request. Any unlabeled mock or cached output.
- A dead or keyed live link during Nov 5–9.
- A misquoted paper (the RUM characterization) or a wrong dataset claim.
- Lineage language (private list `docs/private/lineage_terms.txt`) / pre-event code / strategy docs leaking into the public repo's history.
- A public dataset flag that turns out wrong.
- A video >3:00, or a first 5 seconds without a hook.
- People-grading framing.

### 9.8 The Strength Bar (quantitative targets; every phase gate maps to these)

| Area | Minimum to ship (MVP) | Winning bar |
|---|---|---|
| Live verdict latency (≤15 s clip) | Measured p95 published, timer on screen | **p95 < 12 s** (n ≥ 30), timer on screen |
| Judge benchmark (labeled clips) | n ≥ 120 sim; real footage optional (Strong) | n ≥ 300, with ≥100 real clips (own blind labels), beating every baseline on false-PASS |
| Public-dataset audit | ≥ 20 hand-verified flags, 1 dataset | **≥ 40 flags across 2–3 datasets** + 1 external confirmation |
| `blame` accuracy | t* within ±0.5 s of ground truth on ≥ 70% of sim failures | ±0.3 s on ≥ 85% + real-footage examples hand-checked |
| `CAN'T TELL` behavior | Fires on occlusion > 40% | Calibrated: abstention rate vs. accuracy curve shown |
| Muse Code `/goal` loop | ≥ 5/10 seeded bugs fixed | **≥ 8/10**, one unedited take |
| Headline experiment | 1 task, ≥4 arms (single-pass Spark, 1 reward model, Kodiac, Oracle) + accept-all, ≥2 seeds, labelled sim | 1–2 tasks, all arms incl. both reward models + controls, ≥3 seeds, CIs, prefix salvage |
| Ablation ladder | — (Strong tier) | ≥2 rungs MVP-Strong; 5 rungs winning, each with a measured Δ on the appearance benchmark |
| Uptime (Nov 5–16) | Cached replay always works | ≥ 99% live, spend-capped, monitored |
| Video | ≤ 3:00, all 8 beats | Non-roboticist test viewer can restate the problem and the solution |
| README | Live URL, quickstart, eval table | + shipped table, failure gallery, build log, attributions, model-role table |

---

### 9.9 Judge memos (first person, simulated)

> **J1, perception researcher.** "Running SAM backward from the failure is a nice use of propagation, but the flag is in the API docs. What would impress me is the *measurement*: centimetre margins with error bars that are honest. Show me one plot, predicted vs. true margin in sim, with the 1σ band covering about 68%. If I see '2.6 ± 0.4 cm' on a 320×180 DROID frame, I stop trusting the project. If I see CAN'T TELL there instead, I start trusting it. The abstention is the part I'd remember."

> **J2, robotics researcher.** "I've scrubbed DROID by hand, so the audit card gets my attention in five seconds. Then I check three things: who verified the flags, whether the dataset's own success definition is quoted, and whether an episode I already know from a HF discussion is being presented as their discovery. The retraining chart is sim, StackCube, state policy. That's fine if it's labelled, if the baselines got the same task definition, and if accept-all and random controls are there. A small +Y with a CI crossing zero won't hurt them. A misquoted paper would."

> **J3, platform DevRel.** "Did they extend Muse Code or just call it? A Stop-hook gate that the agent can't cheat by editing the test is a real extension. I'll paste `pip install Kodiac-robotics` and the quickstart. If the package isn't on PyPI, or the quickstart needs keys or prints results that look canned without saying they're replayed, that's two points gone."

> **J4, product/impact.** "In 20 seconds I need: robots learn from videos, some 'successful' videos are failures, this finds the moment and the reason. If the voiceover says 'bisect' or 'sigma', I'm out. The red outline freezing on the bad frame is the hook. On the live page I'll try my own phone clip; if it throws 'E001 object not found', I'll assume the whole thing is fragile."

> **J5, finals.** "On-strategy? Physical AI, agents, open weights: yes. Will it break on stage? Show me the camera-cover moment and the timer, live, once."

### 9.10 The field: what the other Indie finalists will look like (inference)
| Archetype | Likely shape | Their best version shows | Where they beat us | Our counter |
|---|---|---|---|---|
| Muse Code extensions / agent devtools | MCP servers, "verifiable agent" harnesses | An agent finishing a real multi-step dev task with tests | Every judge is a developer | Ours is the only *physical-world* oracle; show the gate refusing "done" |
| Robot agents in sim (SAM 3.1 + Spark) | Self-correcting sim arms | A live sim robot recovering from a judge-triggered fault | Interactive visual wow | Real footage, pixels only, measured cause, downstream proof chart |
| SAM 3.1 video-verification apps | Everyday video checked against a spec | Relatable domain | Non-roboticist appeal | Temporal cause and effect + error bars + abstention + training impact |
| Open-weights / on-device privacy apps | Glimmer or Spark Open on a laptop/partner | Offline, cost per call | Open-weights bonus | A measured open-weights row with cost per 1,000 crops |
| Wonder-powered long-horizon agents | Memory-heavy agents | Autonomy over hours | Best Creative (Wonder) | Keep our Wonder use honest and measured |
| "Accelerate a scientific experiment" | Lab automation, microscopy | A measured speed-up on a real experiment | Impact numbers | Our measured hours-saved + an external confirmation |

**Implication:** at least two finalists will likely be robotics/SAM entries. We win on *real footage + exact frame + measured cause + training impact*, not on "robots + SAM".

### 9.11 How strong Kodiac must be (quantified bar; inference)
- **Field (planning assumption):** 20,000 seats; virtual CV events convert a minority of seats into submissions → assume **800–2,000 Indie submissions**. Top 5 = the top **≈0.25–0.6%**.
- **What that takes:** a first-round weighted score of **≥ 9.0** with **no criterion below 8.5**. A single 7 (slow live page, jargon-heavy video, unverifiable headline) is enough to miss the final.
- **Where hours buy the most points:** (1) live-demo reliability + an unscripted moment (Demo 25%); (2) an external confirmation + a measured hours-saved number (Impact 30%); (3) the real-footage `blame` beat; (4) the proof chart; (5) everything else.
- **Checkpoint:** at the Nov 2 go/no-go, the council scores the real artifacts with this section. Below 8.5 weighted → cut to IDEA §11 "never cut" and spend the remaining hours on Demo and Impact only.

## 10. Binding Strategy Decisions (derived from this research)

| ID | Decision | Why |
|---|---|---|
| **S1** | **Lead with real footage frozen at the *blamed* frame** (DROID/LeRobot) in the cold open and the README, and close with the **retraining chart**. Sim is the lab, not the headline. Never let the pitch collapse into "a success detector" | Wedge vs. ReActSim/Hasami (sim-state) **and Winnow/Instance** (success detectors without blame or downstream proof); Impact weight |
| **S2** | **One surprise per Meta model**, and lead the tooling story with **SAM 3.1 backward-in-time measurement** | "Surfaced unexpected capabilities" |
| **S3** | **Scope ladder:** the core verbs + audit + hosted demo ship first. The full retraining experiment is protected but has a pre-registered **minimal version** with a go/no-go on Nov 2 | "Whether it works" is the Indie track's headline |
| **S4** | **Honesty engineering:** n + 95% CI on every metric; labelled sim/cached; shipped table; pre-registration; build log | Tech Depth + kill-shot avoidance |
| **S5** | **Replace the people-grading closing line** with "The same test checks the demonstrations robots learn from." Frame everything as **cause-and-effect video understanding** | Anti-project rule R2 |
| **S6** | **No lineage language in public** (terms in `docs/private/lineage_terms.txt`); public repo = filtered mirror | New-work rule R1 |
| **S7** | **Reliability engineering for the live demo is a first-class phase** (always-on CPU container, rate limit, cache, spend cap, uptime monitor through Nov 16) | Demo: "holds up live" |
| **S8** | **Plain-language voiceover**: "the exact moment it went wrong" spoken, `blame` shown as on-screen text | J4 persona |
| **S9** | **Claim "every Meta model we use is load-bearing,"** never "every product in the release" (Muse Image is unused) | Accuracy |
| **S10** | **Fix citations** (RUM is a retry verifier; experiment lineage cited correctly) | J2 persona |
| **S11** | **Target the stackable bonuses:** Most Viral (X post early Nov 4), Open Weights (real measured path), Agentic (Muse Code loop), Creative (Wonder) | +$40K upside |
| **S12** | **External validation** is pursued from P08 (human-approved outreach to maintainers/researchers) | The 1st-vs-2nd separator |

---

## 11. Logistics Checklist

**Human-only (agents prepare, the human executes):**
- [ ] Confirm acceptance; accept the Official Rules/waiver on the CV portal; re-read the rules.
- [ ] **Claim the $150 Meta Model API credit**; add a card; **set the spend limit** (alerts don't stop billing).
- [ ] **Apply for Modal ($100, first 1,000) and Baseten ($100 + 2M TPM)** today: first-come.
- [ ] Join Discord: `#announcements`, `#credit-requests`, `#office-hours`.
- [ ] Attend **Agents 102 (Wed Oct 28, 16:00 UTC)** and the Fireworks session (Fri Oct 30, 16:00 UTC).
- [ ] Decide the team (≤4), the Representative, track = Indie, theme = Push the Frontier.
- [ ] Approve outward actions: dataset-maintainer issues/outreach, the X post, PyPI publish, making the repo public.
- [ ] Record the voiceover (or approve the TTS voice); final video upload (public/unlisted) checked in incognito.
- [ ] **Submit by Wed Nov 4, 12:00 PM EST** on `cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit`.

**Agent-executed (via IMPLEMENTATION_PLAN):** repo hygiene (license, `BUILD_LOG.md`, `ATTRIBUTIONS.md`, no keys) · backup video by Nov 1 · experiment go/no-go Nov 2 · feature freeze Nov 3 · README with live URL, theme sentence, model-role table, eval table, shipped table · uptime/spend monitoring Nov 5–16.

**Pre-submit checklist:** repo public ☐ · license ☐ · first commit ≥ Oct 26 ☐ · video ≤ 3:00 plays in incognito ☐ · live URL works with zero login ☐ · all contributors listed ☐ · X post link pasted ☐ · README first screen = what/why/try/proof ☐ · no secrets in git history ☐.

---

## 12. Questions to Ask in `#office-hours` / `@CV` (post early)
1. Video length cap and accepted hosts (YouTube unlisted? Loom?).
2. The finals format on Nov 9 (live pitch, live demo, or video re-watch?).
3. Does a Muse Code plugin (MCP tool + done-gate) count toward Meta tooling use?
4. Is auditing public HF datasets and opening helpful issues on them acceptable?
5. Confirm the Baseten model ID `meta-models/muse-spark-open-1026`.
6. Do bonus prizes stack with track prizes? (PARTIAL says yes.)
7. Are pre-event *ideas/design docs* fine as long as all code is in-window? (We believe yes.)

---

## 13. Sources
Primary: [CV event](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) · [CV .md](https://cerebralvalley.ai/e/meta-ai-developer-hackathon.md) · [Meta event page](https://dev.meta.ai/events/global-hackathon) · [Meta for Developers X #1](https://x.com/MetaforDevs/status/2110045152601633114) · [X #2 (partners)](https://x.com/MetaforDevs/status/2112971571321332179) · [Meta Connect recap](https://developers.meta.com/blog/meta-connect-recap/) · [Muse Wonder newsroom](https://about.fb.com/news/2026/10/introducing-muse-wonder-models/) · [Muse Spark Open (PyTorch)](https://pytorch.org/blog/muse-spark-open/).
Participant mirrors (PARTIAL): [meta-ai-hackathon/meta-hack](https://github.com/meta-ai-hackathon/meta-hack) · [sholaola23/meta-hackathon-2026](https://github.com/sholaola23/meta-hackathon-2026) · [ay23-byte/meta_hackathon](https://github.com/ay23-byte/meta_hackathon).
Past winners: [Llama 3 recap](https://ai.meta.com/blog/llama-3-hackathon-recap-cerebral-valley/) · [LlamaCon](https://ai.meta.com/blog/llamacon-hackathon/) · [Llama Impact London](https://about.fb.com/news/2024/11/metas-llama-impact-hackathon-pioneering-ai-solutions-for-public-good/) · [Opus 4.6 winners](https://claude.com/blog/meet-the-winners-of-our-built-with-opus-4-6-claude-code-hackathon) · [Opus 4.7 winners](https://claude.com/blog/meet-the-winners-of-built-with-opus-4-7-claude-code-hackathon) · [Gemini 3](https://gemini3.devpost.com/updates).
Robotics context: [ARI acquisition](https://siliconangle.com/2026/05/01/meta-acquires-robot-software-startup-assured-robot-intelligence/) · [RUM arXiv 2409.05865](https://arxiv.org/abs/2409.05865) · [OK-Robot arXiv 2401.12202](https://arxiv.org/abs/2401.12202).
Full annotated research: `docs/research/02_hackathon_intel.md`.


*Review round 1 (R1/R2) applied 2026-10-28: see `docs/research/07_fix_ruling.md`.*