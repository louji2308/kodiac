# Kodiac 3-minute video: DRAFT script (IDEA.md section 10.2, v3.1)

STATUS: DRAFT. Not recordable yet.
- Every unmeasured number is the literal marker `[MEASURED VALUE PENDING]`; no value has been invented.
- `python scripts/lint_script.py video/SCRIPT.md` is EXPECTED to report those markers as violations until
  each number is measured, registered as `Measured` in `docs/VIDEO_NUMBERS.md`, and substituted here.
- HUMAN DECISION CONFIRMED (HUMAN_TODO section 3, invariant I16): the closing VO line below is the confirmed v3.1 wording
  from IDEA.md section 0 ("The same test checks the demonstrations robots learn from.").
- Format is machine-read: `## M:SS-M:SS [Cn]` heading, then `VO:` and `SCREEN:` lines. Dev terms appear on screen only.

## 0:00-0:12 [C1]
SCREEN: Three public robot episodes labelled as successful freeze at the failure frame, red SAM 3.1 outlines. Card: "[MEASURED VALUE PENDING] episodes checked, at least [MEASURED VALUE PENDING] did not do their task, hand-verified."
VO: Some of the robot demonstrations labelled successful are not.

## 0:12-0:24 [C2]
VO: Code has tests and git blame. Robots have someone scrubbing video.
SCREEN: Title card: Kodiac.

## 0:24-0:50 [C3]
SCREEN: Real hands on a webcam; three spoken instructions compile live into a short test, each line citing its sentence. SAM 3.1 confirms the objects. MANUAL tag shown.
VO: Show it once, and it becomes a test.

## 0:50-1:20 [C4]
SCREEN: Real robot attempt. On-screen text: `blame: released [MEASURED VALUE PENDING] s before contact, [MEASURED VALUE PENDING] cm left, frame [MEASURED VALUE PENDING]`. Side-by-side diff and a contrasting PASS.
VO: The exact moment it went wrong, and why.

## 1:20-1:50 [C5]
SCREEN: One unedited take in Muse Code (simulation labelled): it reads the blame, patches the line, re-runs; the gate refuses "done" until PASS. [MEASURED VALUE PENDING] of [MEASURED VALUE PENDING] planted bugs fixed.
VO: The coding agent cannot say it is done until the test passes.

## 1:50-2:25 [C6]
SCREEN: Proof chart. Label: `SIMULATION, ManiSkill3, [MEASURED VALUE PENDING] seeds, 95% CI`. Baselines, open-weights point, real-footage accuracy line.
VO: In simulation: same robot, same practice data, only the judge changed: plus [MEASURED VALUE PENDING] points of success.

## 2:25-2:48 [C7]
SCREEN: Live hosted page: paste a dataset, the timer runs and stops. Cover the camera: CAN'T TELL. CACHED badge if replaying.
VO: And when it cannot see, it says so instead of guessing.

## 2:48-3:00 [C8]
SCREEN: Human-hand demonstration graded by the same test. `pip install Kodiac-robotics`.
VO: The same test checks the demonstrations robots learn from.
VO: Robots can finally fail a test.
