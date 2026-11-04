# Kodiac 3-minute video: RECORDABLE LOCKED script (IDEA.md section 10.2, v3.1)

STATUS: LOCKED. Ready for recording.
- Every number is registered as `Measured` in `docs/operations/VIDEO_NUMBERS.md`.
- `python scripts/lint_script.py video/SCRIPT_LOCKED.md` passes with 0 violations.
- Concept ledger count: exactly 8 concepts (C1–C8), no undeclared or unmapped concepts.
- Spoken pace: ~150 words per minute, strictly within the 180-second hard limit.
- Tagline (I12): "Robots can finally fail a test." is the final spoken line.
- Invariant I16: "The same test checks the demonstrations robots learn from."

## 0:00-0:12 [C1]
SCREEN: Three public robot episodes labelled as successful freeze at the failure frame, red SAM 3.1 outlines. Card: "5 episodes checked, 5 did not do their task, hand-verified."
VO: Some of the robot demonstrations labelled successful are not.

## 0:12-0:24 [C2]
VO: Code has tests and git blame. Robots have someone scrubbing video.
SCREEN: Title card: Kodiac.

## 0:24-0:50 [C3]
SCREEN: Real hands on a webcam; three spoken instructions compile live into a short test, each line citing its sentence. SAM 3.1 confirms the objects. MANUAL tag shown.
VO: Show it once, and it becomes a test.

## 0:50-1:20 [C4]
SCREEN: Real robot attempt. On-screen text: `blame: released 0.4 s before contact, 2.6 cm left, frame 114`. Side-by-side diff and a contrasting PASS.
VO: The exact moment it went wrong, and why.

## 1:20-1:50 [C5]
SCREEN: One unedited take in Muse Code (simulation labelled): it reads the blame, patches the line, re-runs; the gate refuses "done" until PASS. 10 of 10 planted bugs fixed.
VO: The coding agent cannot say it is done until the test passes.

## 1:50-2:25 [C6]
SCREEN: Proof chart. Label: `SIMULATION, ManiSkill3, 3 seeds, 95% CI`. Baselines, open-weights point, real-footage accuracy line.
VO: In simulation: same robot, same practice data, only the judge changed: plus 5 points of success.

## 2:25-2:48 [C7]
SCREEN: Live hosted page: paste a dataset, the timer runs and stops. Cover the camera: CAN'T TELL. CACHED badge if replaying.
VO: And when it cannot see, it says so instead of guessing.

## 2:48-3:00 [C8]
SCREEN: Human-hand demonstration graded by the same test. `pip install Kodiac-robotics`.
VO: The same test checks the demonstrations robots learn from.
VO: Robots can finally fail a test.
