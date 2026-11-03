# TODO.md: Remaining Tasks & Blockers Tracker

> **Status:** Active Tracking  
> **Rule:** Every item below is marked `- [ ]` (not completed). We will proceed by tackling and resolving them one by one.  
> **Deadlines:**  
> - Feature Freeze: **Nov 4, 04:59 UTC** (~25 hours remaining)  
> - Internal Submit Target: **Nov 4, 17:00 UTC** (~37 hours remaining)  
> - Official Hackathon Deadline: **Nov 5, 02:00 UTC** (~46 hours remaining)  

---

## Track 1: Public Mirror Repository & Hosting

- [ ] **Task 1.1: Push Clean Public Mirror to GitHub**
  - **Location:** `C:\Users\LOUJAN B\kodiac-public` (pre-built 1-commit clean git repository)
  - **Action Required:**
    1. Create a new public repository on GitHub (e.g. `https://github.com/<your-username>/kodiac`).
    2. Run:
       ```powershell
       cd "C:\Users\LOUJAN B\kodiac-public"
       git remote add origin https://github.com/<your-username>/kodiac.git
       git push -u origin main
       ```
  - **Acceptance Criteria:** Public repository accessible on GitHub with 0 private strategy files (`.agents/`, `docs/private/`, `HACKATHON.md`).

- [ ] **Task 1.2: Enable GitHub Pages for Live Demo**
  - **Location:** GitHub Repository Settings $\to$ Pages
  - **Action Required:** Set source to **GitHub Actions** (uses `.github/workflows/pages.yml`).
  - **Acceptance Criteria:** `https://<your-username>.github.io/kodiac/` serves `site/index.html` with all 6 cached replays and verdict cards without authentication.

- [ ] **Task 1.3: Update Repo & Live Demo URLs in Submission Manifest**
  - **Location:** [`docs/SUBMISSION.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/SUBMISSION.md)
  - **Action Required:** Replace `[PENDING]` in the table with your actual public GitHub URL and GitHub Pages URL.

---

## Track 2: Video Production & Media Verification

- [ ] **Task 2.1: Record the 8 Video Beats**
  - **Location:** [`video/SCRIPT.md`](file:///C:/Users/LOUJAN%20B/Kodiac/video/SCRIPT.md) and [`docs/DEMO_FILMING_GUIDE.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/DEMO_FILMING_GUIDE.md)
  - **Action Required:** Screen-record terminal and UI sequences corresponding to the 8 concepts (opening hook, `.green` test compilation, `Kodiac run` PASS/FAIL, blame $t^*$, fast-path bisect, done-gate verification, proof matrix, closing demonstration check).
  - **Acceptance Criteria:** Total runtime $\le$ 3:00 minutes. Zero prohibited marketing adjectives.

- [ ] **Task 2.2: Upload & Verify Video Playback**
  - **Action Required:** Upload to YouTube (Unlisted or Public), Vimeo, or Loom.
  - **Acceptance Criteria:** Link plays cleanly in an incognito window without login.

- [ ] **Task 2.3: Record Video URL in Submission Manifest**
  - **Location:** [`docs/SUBMISSION.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/SUBMISSION.md)
  - **Action Required:** Replace `[PENDING]` under `Video URL`.

---

## Track 3: Credentials & External Live Services (Optional / Real-Run Upgrades)

- [ ] **Task 3.1: Meta Model API Credentials (`MODEL_API_KEY`)**
  - **Context:** Currently, perception runs on reproducible fixture tracks and compiler uses deterministic template fallback per Prime Directive Law 1.
  - **Action Required:** If you wish to run live SAM 3.1 or Muse Spark/Voice API calls, claim the $150 credit on Cerebral Valley / Discord and export `MODEL_API_KEY`.
  - **Acceptance Criteria:** Key provided or explicitly kept as fixture double with honest badges.

- [ ] **Task 3.2: Modal Compute Token (`modal token new`)**
  - **Context:** Distributed retraining pool is currently mock-based; headline experiment is marked `NOT_MEASURED`.
  - **Action Required:** If GPU retraining is to be run, authenticate Modal CLI.
  - **Acceptance Criteria:** Authenticated or confirmed as `NOT_MEASURED` baseline disclosure.

- [ ] **Task 3.3: PyPI Package Reservation (`Kodiac-robotics`)**
  - **Action Required:** Reserve the package name on PyPI to prevent squatting.
  - **Acceptance Criteria:** Name registered on PyPI or kept as local/GitHub install.

---

## Track 4: Announcement & Portal Submission

- [ ] **Task 4.1: Fill In Contributor Details**
  - **Location:** [`docs/SUBMISSION.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/SUBMISSION.md)
  - **Action Required:** Replace `[PENDING]` under Contributors with your team/author names.

- [ ] **Task 4.2: Publish Announcement on X (Twitter)**
  - **Location:** Draft text in [`docs/SUBMISSION.md §2`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/SUBMISSION.md#L44-L48)
  - **Action Required:** Post tweet with project link, video link, and tagging `@Meta` and `#PushTheFrontier`. Copy tweet URL.

- [ ] **Task 4.3: Submit to Cerebral Valley Hackathon Portal**
  - **URL:** `https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit`
  - **Action Required:** Copy-paste fields from [`docs/SUBMISSION.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/SUBMISSION.md) and submit before Nov 4, 17:00 UTC.
