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

- [ ] **Confirm Closing-Line Refinement for Invariant I16 (`IDEA.md §0`)**
  - **Context:** The original draft line *"The same test can check the person who teaches the robot"* borders on prohibited "AI Job Application Screener / Personality Analyzer / People-grading" rules (`HACKATHON.md` §2 R2).
  - **Proposed Wording:** *"The same test checks the demonstrations robots learn from."*
  - **Effect:** Keeps full effector aliasing capability (`gripper ↔ hand`) while moving framing strictly to training data validation.
  - **Decision Required:** Reply to confirm approval of this wording.

---

## 4. Workshops & Office Hours (Optional / High-Leverage)

- [ ] **Agents 102: Verifiable Agents Best Practices** (Yash Khare, Meta DevRel)
  - Date: Wednesday Oct 28, 12:00–1:00 PM ET (16:00–17:00 UTC).
  - Value: Direct alignment with our `Kodiac.verify` / done-gate vocabulary.
