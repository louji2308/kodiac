# T12: Ship tooling: compliance sweep, script/banned-word lint, public mirror, submission & ops docs
phase: P10 · owner: IMPL-12 (Sonnet 5.5 @ medium) · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P10.S01, S07, S07b, S09, S10 · AGENTS §12 · HACKATHON.md §2 (disqualifiers), §9 · IDEA §10 (video script, banned words, 8-concept cap)
depends_on: [] · blocks: []
owns_paths: [scripts/compliance_check.py, scripts/lint_script.py, scripts/lint_public.py, scripts/make_public_mirror.sh, scripts/make_public_mirror.ps1, video/SCRIPT.md, video/concepts.yaml, docs/SUBMISSION.md, docs/OPS_RUNBOOK.md, tests/ship/**]
reads_only: [everything; HACKATHON.md, IDEA.md §10, AGENTS.md §12]
timebox: 100 min

## Mission
Protect against kill-shots (disqualifiers, leaked secrets/strategy docs, banned words, >8 concepts) and have the submission package ready for the human to press the button. **Nothing in this card publishes, pushes, posts or submits**: those are human actions (AGENTS §12.3).

## Steps
1. Read HACKATHON.md §2 (disqualifiers), §9; IDEA §10 (script structure, banned-word list §10.3, concept cap), §12.
2. `scripts/lint_script.py <script.md>`: banned-word list parsed from IDEA §10.3 (read it from the doc at runtime so it can't drift; fail loudly if not found); concept count from `video/concepts.yaml` (≤8, each concept maps to ≥1 script line); every number token in the script must appear in `docs/VIDEO_NUMBERS.md` with status `Measured` (not Target/Placeholder), else a violation; length ≤ 3:00 estimated at 150 wpm; first 5 s hook present; last VO line == tagline "Robots can finally fail a test."
3. `video/SCRIPT.md`: a **draft** script following IDEA §10 with every unmeasured number written as `[MEASURED VALUE PENDING]` (never a made-up value) and `video/concepts.yaml` (≤8). The linter must currently report the pending numbers as violations (that is correct and expected; document it). I16 closing line stays as in IDEA §0 until the human confirms (HUMAN_TODO §3); mark the pending decision.
4. `scripts/compliance_check.py`: first commit date ≥ 2026-10-26; `BUILD_LOG.md` dated entries; `ATTRIBUTIONS.md` rows for SAM license, DROID CC-BY, LeRobot Apache, ManiSkill Apache, Robometer/TOPReward, cookbook MIT (report the gaps; **append the missing rows to ATTRIBUTIONS.md only if you can state the licence from the upstream repo/model card with a cited URL; otherwise list them as OPEN for the human**: do not guess licences); LICENSE present; `docs/private/` not tracked; secrets scan over tracked files **and `git log -p`** (patterns: api key/secret/token assignments with high-entropy values; `detect-secrets` if installed else regex), files >20 MB tracked; lineage/voiceover term scan using `docs/private/lineage_terms.txt` **if it exists, else report `UNVERIFIABLE: docs/private/lineage_terms.txt missing` (do not invent a list)**. Exit non-zero on any hit; JSON + human-readable report.
5. `scripts/lint_public.py --history` + `scripts/make_public_mirror.sh` (and a `.ps1` equivalent for this Windows machine): fresh clone → `git filter-repo --invert-paths --path HACKATHON.md --path docs/research/ --path docs/private/ --path .agents/ --path HUMAN_TODO.md` → run lint over the mirror's files, full history **and commit messages** → print the push command but **never run it**. If `git filter-repo` is missing, print install guidance and exit 3. Default to `--dry-run`.
6. `docs/SUBMISSION.md`: form text skeleton (title, one-liner, track Indie, theme "Push the Frontier", description, Meta tools used, links) with `[PENDING]` placeholders for repo/video/live URL, X post draft, gallery text, and the human checklist (repo public ☐, video link ☐, contributors ☐, X link ☐). Only claims backed by `docs/features.yaml` `done` rows or labelled "planned (not shipped)".
7. `docs/OPS_RUNBOOK.md`: Nov 5–16 daily checklist (uptime, spend, replay health, Discord), incident playbook (API down → cached-mode banner; credits low → cache-only), finals prep outline (Nov 9 17:00 UTC, 3-minute live pitch + hot demo path).
## Definition of Done
- [ ] Tests (`tests/ship/**`, offline, tmp git repos for history scans): banned word caught; unmeasured number caught; >8 concepts caught; secret planted in a temp repo's history caught; large tracked file caught; missing lineage list reported UNVERIFIABLE (not pass); mirror script refuses to push; `publish`-style commands absent.
- [ ] Run `scripts/compliance_check.py` on this repo and put the real output in the report (expect findings; do not hide any).
- [ ] ruff clean; no `TODO|NotImplemented`; full suite green. Committed `feat(p10/t12): …`.

## Report (filled by owner at DONE)
