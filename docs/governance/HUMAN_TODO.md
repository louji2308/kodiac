# HUMAN_TODO.md: Hackathon Day-1 Checklist & Approvals

> **Time-Sensitive:** Hackathon credits are first-come, first-served ("not guaranteed"). Claim them immediately.
> All credentials should be provided via environment variables (e.g. in `.env` which is gitignored). **Never commit secrets.**

---

## 1. Credit Claims & Accounts (P01.S13)

- [ ] **Meta Model API ($150 credit)**
  - Link: Cerebral Valley portal / Discord announcement.
  - Action: Claim credit; card pre-authorization required; **set a hard spend limit in the Meta API dashboard** (spend alerts do NOT stop billing).
  - Key to export: `MODEL_API_KEY="..."`
- [ ] **Modal Compute ($100 credit)**
  - Link: Discord `#resources` Modal credit form (first 1,000 participants).
  - Action: Claim credits; install modal CLI and authenticate (`modal token new`).
- [ ] **Baseten Inference ($100 + 2M TPM)**
  - Link: Discord `#resources` Baseten credit form (≤2,000 participants).
  - Action: Request access for `meta-models/muse-spark-open-1026`.
  - Key to export: `BASETEN_API_KEY="..."`
- [ ] **Fireworks AI ($25 credit)**
  - Link: Discord `#resources` / participant email.
  - Key to export: `FIREWORKS_API_KEY="..."`

---

## 2. Gated Model Access & Package Reservation

- [ ] **Hugging Face SAM 3.1 Gated Access**
  - URL: `https://huggingface.co/facebook/sam3.1`
  - Action: Accept license terms and request gated access under your Hugging Face account.
  - Key to export: `HF_TOKEN="..."`
- [ ] **PyPI Package Reservation**
  - Action: Register or reserve the package name `Kodiac-robotics` on PyPI to prevent name-squatting during the hackathon.

---

## 3. Human Confirmation Needed: Concept Invariant I16

- [x] **Confirm Closing-Line Refinement for Invariant I16 (`IDEA.md §0`)** (Confirmed & approved 2026-11-02)
  - **Context:** The original draft line *"The same test can check the person who teaches the robot"* borders on prohibited "AI Job Application Screener / Personality Analyzer / People-grading" rules (`HACKATHON.md` §2 R2).
  - **Proposed Wording:** *"The same test checks the demonstrations robots learn from."*
  - **Effect:** Keeps full effector aliasing capability (`gripper ↔ hand`) while moving framing strictly to training data validation.
  - **Decision Required:** Reply to confirm approval of this wording.

---

## 4. Git History Scrub Before the Public Mirror (needs your approval)

- [ ] **Approve a `--replace-text` scrub of two synthetic test strings** (AGENTS.md §12.5 destructive op)
  - **Finding:** `scripts/compliance_check.py` reports 2 `secret-history` hits. Both are *fake* keys written as
    test fixtures: `sk-test-SECRET-1234567890` (`tests/judge/test_judge_backends.py` @ `c142535`) and
    `sk-very-secret-value-123` (`tests/loop/test_gate.py` @ `d4258d1`). The working tree is already clean
    (both are now assembled at runtime); only old commits still contain the literals.
  - **Why it matters:** the public mirror keeps history, so `scripts/make_public_mirror.sh --run` will refuse to
    build (`lint_public.py --history` fails) until history is scrubbed. A judge browsing history would also see
    credential-shaped strings, which is exactly the impression we cannot afford.
  - **Proposed command (not run):** `git filter-repo --replace-text <(printf 'sk-test-SECRET-1234567890==>REDACTED\nsk-very-secret-value-123==>REDACTED\n')`
    then re-add every remote (filter-repo drops them) and force-push the *private* repo.
  - **Alternatives:** (A) publish the mirror squashed to a single "hackathon snapshot" commit (no history to scrub,
    but loses the provenance story); (B) leave it and accept a `lint_public.py --history` failure that must be
    disclosed in the submission. Recommendation: **A** if you do not want to rewrite history, otherwise the command above.

---

## 5. Workshops & Office Hours (Optional / High-Leverage)

- [ ] **Agents 102: Verifiable Agents Best Practices** (Yash Khare, Meta DevRel)
  - Date: Wednesday Oct 28, 12:00–1:00 PM ET (16:00–17:00 UTC).
  - Value: Direct alignment with our `Kodiac.verify` / done-gate vocabulary.
