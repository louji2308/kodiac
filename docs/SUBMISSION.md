# SUBMISSION.md: form text, X post, gallery, human checklist (DRAFT)

> Nothing here has been submitted or posted. Submitting, posting, and making the repo public are **human-only** actions (AGENTS.md section 12.3).
> `[PENDING]` = a value that does not exist yet. Do not replace with a guess.
> Claim rule: only `docs/features.yaml` rows with `status: done` may be written as shipped; everything else is labelled "planned (not shipped)". Re-check `docs/features.yaml` immediately before pasting: it is the source of truth, this file is a snapshot (2026-11-02).
> Every number must be `Measured` in `docs/VIDEO_NUMBERS.md` before it appears in any text below. At snapshot time none of the headline numbers are measured; none are written here.

Submit at: `cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit` · internal deadline Nov 4 17:00 UTC (official Nov 5 02:00 UTC).

## 1. Form fields

| Field | Text |
|---|---|
| Project title | Kodiac |
| One-liner | Tests, `git bisect`, and `git blame` for robots: robots can finally fail a test. |
| Track | Indie Developer |
| Theme | Push the Frontier |
| Repo URL | [PENDING] (public mirror, created by the human via `scripts/make_public_mirror.*`) |
| Video URL | [PENDING] (<= 3:00; check in an incognito window) |
| Live demo URL | [PENDING] (hosted page: **planned (not shipped)** at snapshot; F53) |
| Contributors | [PENDING] (human lists every contributor) |
| `pip install` | `pip install Kodiac-robotics` ([PENDING] PyPI publish is a human action; not published at snapshot) |

### Description (draft)
Kodiac turns a robot-success claim into a test. Show a task once and it is compiled into a short, human-readable `.green` test; each attempt is graded frame by frame with a verdict of PASS, FAIL, or CAN'T TELL (it abstains instead of guessing). The goal is spatio-temporal, causal video understanding: when an attempt fails, find the exact onset frame and a measured physical cause.

**Shipped at snapshot (features.yaml `done`, evidence = deterministic unit tests, not live Meta-model runs):** demo capture, the `.green` language and lock file, per-step provenance, compile-time linter, object type-check, demo self-test, text-compile mode, effector aliasing, fps-agnostic ingest, scale model, geometric predicates (on / near / lifted / moves_with / dwell), smoothing and hysteresis, verdict + reason codes + exit codes, evidence frames, and the trace/provenance viewer.

**Partly shipped:** speech to step windows, spec compiler, object tracking (fixture/mocked-API tests only; live Muse Voice / Muse Spark / SAM 3.1 calls never run for lack of keys), simulation harness and the ten seeded bugs (kinematic mock simulator, labelled mock).

**Planned (not shipped) at snapshot:** blame / diff with exact t*, the Muse Code done-gate and `Kodiac.verify` MCP tool, the headline "only the judge changed" experiment and proof chart, the public-dataset audit, the hosted app with live timer, the pip release. [PENDING: update this paragraph from `docs/features.yaml` before submitting.]

### Meta tools used (state only what ran)
| Tool | Role | Status at snapshot |
|---|---|---|
| SAM 3.1 | measures objects | fixture/recorded tracks only; live API [PENDING] |
| Muse Spark | compiles specs, judges crops | mocked-API tests only; live [PENDING] |
| Muse Voice | anchors intent from speech | mocked-API tests only; live [PENDING] |
| Muse Wonder | adjudicates / narrates | planned (not shipped) |
| Muse Code | `/goal` loop with done-gate | planned (not shipped) |

Update this table to `live` only with evidence (artifact path + git sha).

## 2. X post (draft; the human posts it)
> Robots can finally fail a test. Kodiac: tests, git bisect and git blame for robots: show a task once, get a test, and a verdict of PASS, FAIL, or CAN'T TELL. Built for the @Meta Global AI Developer Hackathon (#PushTheFrontier). Repo: [PENDING] · Video: [PENDING] · Live: [PENDING]

Post the link back into the form: X post URL [PENDING].

## 3. Gallery text (draft)
**Kodiac: Robots can finally fail a test.** A test language for robot success: compile a demonstration into a `.green` test, grade every attempt with PASS / FAIL / CAN'T TELL, and (planned) point to the exact frame and measured cause where it went wrong. Simulation results are labelled simulated; cached replays are labelled cached. [PENDING: add one measured headline number only after it is registered in `docs/VIDEO_NUMBERS.md` as Measured.]

## 4. Human checklist (nothing is ticked by an agent)
- [ ] `python scripts/compliance_check.py` run on the final tree; every finding resolved or consciously accepted (lineage list present, ATTRIBUTIONS rows complete)
- [ ] `python scripts/lint_script.py video/SCRIPT.md` is clean (all numbers Measured)
- [ ] I16 closing line confirmed (HUMAN_TODO section 3)
- [ ] Mirror built with `scripts/make_public_mirror.* -Run/--run`, lint passed over full history and commit messages
- [ ] Repo public (human action)
- [ ] Video uploaded; link plays in incognito; <= 3:00
- [ ] Live URL works with zero login (or marked [PENDING] / removed)
- [ ] Contributors listed
- [ ] X post published; link pasted in the form
- [ ] README first screen: what / why / try / proof; names the theme "Push the Frontier"
- [ ] Form submitted before Nov 4 17:00 UTC (internal)
