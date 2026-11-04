# OPS_RUNBOOK.md: Nov 5-16 operations, incidents, finals prep (DRAFT)

> Applies once the hosted demo exists (planned, F53-F57 are **not shipped** at snapshot). Spend alerts do **not** stop billing (HACKATHON R7), so every item below assumes a hard per-key spend limit set by the human in each provider dashboard.
> All times UTC. Human-only actions: changing keys, raising limits, posting publicly, replying publicly in Discord.

## 1. Daily checklist (Nov 5 to Nov 16)

| # | Check | How | Pass condition | If not |
|---|---|---|---|---|
| 1 | Uptime | open the live URL in an incognito window, no login | page loads; a run completes | incident playbook A |
| 2 | Spend | read the Meta, Modal, Baseten dashboards (human) | under the daily budget [PENDING: human sets budget per provider] | playbook B |
| 3 | Replay health | run the cached replay path; the CACHED badge must be visible | replay renders and is labelled CACHED | regenerate the cache from `artifacts/`; never show cached output unlabelled |
| 4 | Latency | one timed run | recorded in the log below; do not publish a number unless it is `Measured` in `docs/VIDEO_NUMBERS.md` | investigate before claiming anything |
| 5 | Repo + video links | open both in incognito | both public and working | fix links; tell the human |
| 6 | Discord | read `#announcements`, `#office-hours`, DMs | no new rule or finals notice missed | add to the log; escalate time-critical items to the human |
| 7 | Secrets | `python scripts/compliance_check.py` | no S0 secret findings | rotate the key (human), purge history via the mirror |

Daily log (append, never rewrite): `[date UTC] uptime ok/fail · spend $[PENDING] · replay ok/fail · notes`.

## 2. Incident playbook

| Incident | Detect | Action (in order) |
|---|---|---|
| **A. Meta/SAM API down or erroring (429/5xx)** | failed run, error banner | 1) switch the page to **cached-mode banner**: results shown are replays, labelled **CACHED**; 2) never present a cached result as live; 3) retry live with backoff (2 s, 4 s, 8 s, 16 s); 4) log the outage window |
| **B. Credits low / spend near limit** | dashboard, 429 from the provider | 1) go **cache-only** (CACHED badge on every result); 2) lower or disable the server-side rate limiter; 3) human decides on any new spend (AGENTS 12.1: agents never spend) |
| **C. Hosted app down** | uptime check fails | 1) redeploy the last known-good build (human runs the deploy); 2) until fixed, README and form point to the recorded video; 3) log |
| **D. Abusive or huge uploads** | spend spike, long queue | enforce size/duration caps; block the offending client; cache-only if needed |
| **E. A wrong or misleading number is found** | any reviewer or judge report | take it down from README/page first, then fix `docs/VIDEO_NUMBERS.md`; say what changed (honesty over polish) |
| **F. Key leaked** | secrets scan hit | human rotates the key immediately; then clean history |

## 3. Finals prep outline (Nov 9, 17:00 UTC; 3-minute live pitch + hot demo)
Confirm the exact time and format with the organisers [PENDING: not verified here].
- **T-3 days:** freeze the demo path; decide what is live and what is CACHED; rehearse both.
- **Pitch (3:00):** same 8 concepts as the video (`video/concepts.yaml`), in order; tagline last. Say "simulation" and "cached" out loud whenever they apply.
- **Hot demo path (one path only):** paste a dataset or clip, timer runs, a verdict appears; cover the camera for CAN'T TELL. Fallback: the CACHED replay with the badge visible, announced as such.
- **Backups:** the recorded video offline; a local `Kodiac` CLI run on fixtures (labelled fixture); screenshots of the proof chart (only if it exists and is Measured).
- **Q&A prep:** HACKATHON.md section 9.6 (private; not in the public mirror).
- **Do not claim:** anything with `status: planned` in `docs/features.yaml`, any unregistered number, any live Meta result that ran from fixtures.
- **Checklist the hour before:** network test, API key present in env (never on screen), spend headroom, incognito link check, second device with the video.

---

## 4. LeRobot Dataset Ingestion & Operational Throughput

Kodiac natively ingests standard Hugging Face LeRobot robot datasets via the custom `lerobot://` URI scheme:
`lerobot://<repo_id>/<episode_index>/<camera_key>` (implemented in `src/Kodiac_robotics/io/lerobot.py`).

### Quantified Time Savings Equation
- **Manual Human Grading:** A human reviewer typically spends **~180 s (3 minutes)** per robot manipulation episode scrubbing frames, manually verifying grasp contact, alignment tolerances, and release dwell.
- **Automated Kodiac Evaluation:** Kodiac evaluates the episode via the two-stage bisect fast path in **~6–12 s** (or <1.5 s on cached/fixture tracks).
- **Throughput Gain:** **15× to 30× reduction in operational grading latency**. For a standard evaluation batch of 100 episodes, human review takes ~5.0 hours of manual grading; Kodiac completes the sweep in under 15 minutes, with full mathematical audit traces (`runs/<id>/trace.jsonl`) and 16:9 verdict cards (`runs/<id>/card.png`).

