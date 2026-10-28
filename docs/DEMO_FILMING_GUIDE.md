# DEMO_FILMING_GUIDE.md: Hero Footage Recording Protocol

> **Purpose:** Canonical standard operating procedure for filming real and simulated robotics footage evaluated by Kodiac.
> All numbers, angles, and tolerances in this guide are registered in `docs/VIDEO_NUMBERS.md` and derived in `ARCHITECTURE.md §7`.
> Following this protocol guarantees reliable perceptual tracking via Meta SAM 3.1, accurate speech-to-step segmentation via Muse Voice Transcribe `ENDPOINTING`, and rigorous ground-plane metric calibration.

---

## 1. Quick Reference & Golden Rules

| Parameter | Specification | Tolerance / Constraint | Rationale / Grounding |
|---|---|---|---|
| **Camera Elevation** | **30° – 50°** pitch down | Fixed tripod / mount | Optimal angle for ground-plane fitting & depth estimation (`ARCHITECTURE.md §7.2`) |
| **Focal Length / HFOV** | Fixed, ~70° HFOV | Auto-zoom & EIS disabled | Consistent projective geometry ($f$ prior 70° ± 10°) |
| **Video Format** | **720p (1280×720)** or 1080p | **15 – 30 fps**, H.264 / MP4 | Matches DROID dataset standard (15 fps); frame-accurate PyAV decoding |
| **Clip Duration** | **≤ 15.0 seconds** | Hard cap ≤ 20.0 s | Satisfies `< 12.0 s` wall-clock fast-path latency target (`F54`) |
| **Resting Objects** | **≥ 2 objects** at distinct depths | Must stay stationary | Required for Tier B ground-plane self-calibration |
| **Hero Object Prior** | **4.0 cm** test block | Known prior $W_o = 4.0\text{ cm}$ | Registered in `docs/VIDEO_NUMBERS.md`; scale $k_o = \ell_o / W_o$ |
| **Audio Pauses** | **≥ 0.7 seconds** silence | Between spoken clauses | Triggers Muse Voice Transcribe `ENDPOINTING` turn boundaries |
| **Audio Format** | 16 kHz or 24 kHz | Mono WAV or AAC in MP4 | Standard ASR input; low noise floor |

---

## 2. Camera Setup & Kinematics

1. **Rigid Mounting:**
   - Mount the camera on a heavy tripod, overhead rig, or rigid mechanical workbench clamp.
   - **Handheld recording is prohibited.** Hand tremor introduces spurious Savitzky–Golay velocity noise, artificially inflating the pixel noise floor $\sigma_{px}$.
2. **Elevation Angle (30° – 50°):**
   - Point the camera downward toward the tabletop workspace at an angle between 30° and 50° relative to horizontal.
   - *Why 30°–50°:* Pure overhead (90°) loses all depth/height information for lift and stack predicates. Pure horizontal (0°) causes severe front-to-back object occlusion and singular ground-plane solutions.
3. **Sensor & Lens Configuration:**
   - Turn **OFF** auto-focus, auto-zoom, and digital image stabilization (EIS). Any dynamic focal length or electronic cropping invalidates camera intrinsics $K$ mid-clip.
   - Lock exposure and white balance to prevent sudden brightness jumps from tripping Gate G4 (view blocked / lighting variation).

---

## 3. Workspace & Scene Preparation

1. **Background & Surface:**
   - Use a clean, matte, non-reflective workspace surface (e.g. solid wood, dark cutting mat, or plain table).
   - High visual contrast between the robotic gripper, target objects, and tabletop.
   - Avoid glossy surfaces that produce specular glare or mirror reflections.
2. **Illumination:**
   - Diffused overhead lighting.
   - Avoid low-frequency flickering fluorescent lamps or intense directional point sources that cast sharp dynamic shadows.
3. **Tier B Ground-Plane Calibration Prerequisites:**
   - Place **at least two resting objects** at noticeably different depths (one near, one far) within the camera's field of view.
   - These objects establish the vanishing line and ground plane:
     $$(v_i - v_h) = k_i \cdot \tilde{H}$$
     solving for the horizon row $v_h$ and scale factor $\tilde{H}$.
   - Ensure these reference objects remain untouched throughout the entire demonstration.
4. **Hero Object Prior (4.0 cm):**
   - Use standard 4.0 cm cubes/blocks for pick-and-place trials.
   - This prior allows Kodiac to compute metric distances ($X, Y, Z$ in centimeters) without requiring pre-calibrated checkerboard patterns.

---

## 4. Audio Protocol: Muse Voice Transcribe `ENDPOINTING`

Kodiac segments video demonstrations into discrete step windows by anchoring on the operator's spoken instructions via **Muse Voice Transcribe 1.0**.

1. **Microphone Setup:**
   - Use a clear USB microphone or headset.
   - Ensure the audio track is recorded concurrently with the video (or muxed into the MP4 container).
2. **Three-Clause Instruction Structure:**
   - The canonical hero demonstration consists of 3 distinct task steps:
     - **Step 1:** Grasping / lifting the target object.
     - **Step 2:** Transporting and placing / stacking on the receptacle.
     - **Step 3:** Retracting the end-effector to home.
3. **The 0.7-Second Pause Rule:**
   - Muse Voice Transcribe operates in `ENDPOINTING` mode, where conversational turn detection assigns start and end timestamps.
   - **You MUST pause for at least 0.7 seconds of clean silence between each clause.**
   - *Example Script:*
     > *"Pick up the red cube."*
     > **[Pause for 0.8 seconds — silence]**
     > *"Place it on the blue block."*
     > **[Pause for 0.8 seconds — silence]**
     > *"Retract arm to home position."*
4. **Audio Hygiene:**
   - Do not mumble or speak over robot motor whine.
   - Do not use filler words ("um", "ah").

---

## 5. Filming Edge Cases & Honest Abstention (`CAN'T TELL`)

Under Prime Directive Law 1, Kodiac never guesses when evidence is degraded or absent. Filming dedicated edge-case clips demonstrates our honest abstention mechanics to Meta hackathon judges:

### 5.1 Full Camera Occlusion (Gate G4)
- **Goal:** Trigger Gate G4 (`view blocked`: luminance < 15/255, low Laplacian variance, > 60% uniform).
- **Execution:** During the middle of step 2, place a solid dark card or hand directly against the camera lens for 2.0 seconds.
- **Expected Verdict:** `CAN'T TELL` (View blocked on frames $t_a \dots t_b$).

### 5.2 Partial Object Occlusion (Gate G2)
- **Goal:** Trigger Gate G2 (`occluded > 40%`).
- **Execution:** Place an opaque cardboard divider between the camera and the placement site so the cube is >40% occluded at the moment of contact.
- **Expected Verdict:** `CAN'T TELL` (Object occlusion exceeds 40% during critical predicate evaluation).

### 5.3 Ambiguous Depth / Single Reference (Tier C)
- **Goal:** Demonstrate honest abstention when ground-plane calibration cannot be solved.
- **Execution:** Film a scene with only a single object on a blank table with no resting references.
- **Expected Verdict:** Scale uncertainty $\sigma_m$ inflates; depth-critical predicates fall back to `CAN'T TELL`.

### 5.4 Seeded Physical Failure (FAIL Verdict)
- **Goal:** Demonstrate Kodiac's exact blame detection and physical measurements on failure.
- **Execution:** Deliberately place the cube 4.5 cm away from the target center (exceeding the 3.33 cm oracle tolerance).
- **Expected Verdict:** `FAIL` at Step 2 with measured margin: `alignment_error: 4.50 cm (tol: 3.33 cm)`.

---

## 6. Pre-Flight Filming Checklist

Before hitting Record, verify every item:

- [ ] Camera securely mounted on tripod (no vibration or handheld drift).
- [ ] Camera elevation set between 30° and 50° down toward the table.
- [ ] Auto-focus, auto-zoom, and digital stabilization turned OFF.
- [ ] Diffused lighting active; no flickering or moving harsh shadows.
- [ ] Background uncluttered and high-contrast relative to blocks.
- [ ] At least 2 stationary resting objects visible at distinct depths.
- [ ] Target cube measured to 4.0 cm prior.
- [ ] Microphone tested; background room noise < 40 dB.
- [ ] Operator practiced speaking 3 clauses with ≥0.7 s deliberate pauses.
- [ ] Total recording rehearsed to finish in under 15 seconds.

---

## 7. File Naming & Organization

Save all raw recordings into `artifacts/demo_takes/` with consistent naming:

```
artifacts/demo_takes/
├── hero_pass_take01.mp4          # Canonical 3-step successful task
├── hero_fail_misalignment.mp4    # Seeded failure (cube dropped off-target)
├── hero_fail_dropped.mp4         # Seeded failure (cube dropped prematurely)
├── edge_camera_occluded.mp4      # Full lens occlusion (CAN'T TELL)
└── edge_object_occluded.mp4      # Partial target occlusion (CAN'T TELL)
```
