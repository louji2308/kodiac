"""Reference pick-and-place script for Franka Panda StackCube.

Stacks red cube (cubeA) onto green cube (cubeB).
Verified 10/10 seeds oracle PASS on KinematicMockEnv and ManiSkillEnv.
Supports deterministic bug injection (B01–B10) for testing failure modes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct CLI execution
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from Kodiac_robotics.sim.env import KinematicMockEnv, ManiSkillEnv, SimEnv  # noqa: E402
from Kodiac_robotics.sim.robot import RobotController  # noqa: E402
from Kodiac_robotics.sim.video import save_sim_run  # noqa: E402


def execute_pick_place(robot: RobotController, bug_id: str | None = None) -> bool:
    """Execute pick-and-place sequence with optional bug injection."""
    state = robot.env.privileged_state()
    cubeA_pos = list(state.cubeA_pose[:3])
    cubeB_pos = list(state.cubeB_pose[:3])

    # ---------------------------------------------------------
    # Step 1: Pre-grasp approach above Cube A
    # ---------------------------------------------------------
    if bug_id == "B08":
        # B08 wrong_object: Navigates to wrong location on the table
        pre_grasp = [0.25, -0.10, cubeA_pos[2] + 0.12]
    else:
        pre_grasp = [cubeA_pos[0], cubeA_pos[1], cubeA_pos[2] + 0.12]
    robot.arm.move_to(pre_grasp)

    # ---------------------------------------------------------
    # Step 2: Descend to grasp pose
    # ---------------------------------------------------------
    if bug_id == "B06":
        # B06 high_grasp: Descends to 7cm above cube, grasping empty air
        grasp_pose = [cubeA_pos[0], cubeA_pos[1], cubeA_pos[2] + 0.07]
    elif bug_id == "B08":
        grasp_pose = [0.25, -0.10, cubeA_pos[2]]
    else:
        grasp_pose = [cubeA_pos[0], cubeA_pos[1], cubeA_pos[2]]
    robot.arm.move_to(grasp_pose)

    # ---------------------------------------------------------
    # Step 3: Gripper close & Step 4: Lift
    # ---------------------------------------------------------
    if bug_id == "B05":
        # B05 lift_before_close: Lifts before closing gripper
        robot.arm.lift(distance=0.12)
        robot.gripper.close(steps=15)
    elif bug_id == "B07":
        # B07 missing_close: Never closes gripper
        robot.arm.lift(distance=0.12)
    elif bug_id == "B03":
        # B03 low_lift: Lifts only 0.5 cm, failing vertical clearance
        robot.gripper.close(steps=15)
        robot.arm.lift(distance=0.005)
    else:
        # Standard clean execution
        robot.gripper.close(steps=15)
        robot.arm.lift(distance=0.12)

    # ---------------------------------------------------------
    # Step 5: Transfer above Cube B
    # ---------------------------------------------------------
    if bug_id == "B01":
        # B01 early_release: Opens gripper mid-transit
        mid_transit = [
            (cubeA_pos[0] + cubeB_pos[0]) / 2.0,
            (cubeA_pos[1] + cubeB_pos[1]) / 2.0,
            cubeB_pos[2] + 0.12,
        ]
        robot.arm.move_to(mid_transit)
        robot.gripper.open(steps=15)
        robot.arm.move_to([cubeB_pos[0], cubeB_pos[1], cubeB_pos[2] + 0.12])
    elif bug_id == "B03":
        # B03 low_lift: Transfers horizontally at table level, colliding with Cube B
        low_transfer = [cubeB_pos[0], cubeB_pos[1], cubeA_pos[2] + 0.005]
        robot.arm.move_to(low_transfer)
    else:
        pre_place = [cubeB_pos[0], cubeB_pos[1], cubeB_pos[2] + 0.12]
        robot.arm.move_to(pre_place)

    # ---------------------------------------------------------
    # Step 6: Lower to placement pose
    # ---------------------------------------------------------
    if bug_id == "B02":
        # B02 xy_offset: Places with 5 cm offset from Cube B
        place_pose = [cubeB_pos[0] + 0.05, cubeB_pos[1], cubeB_pos[2] + 0.04]
    elif bug_id == "B10":
        # B10 high_release: Positions 15 cm above Cube B
        place_pose = [cubeB_pos[0], cubeB_pos[1], cubeB_pos[2] + 0.15]
    else:
        place_pose = [cubeB_pos[0], cubeB_pos[1], cubeB_pos[2] + 0.04]
    robot.arm.move_to(place_pose)

    # ---------------------------------------------------------
    # Step 7: Open gripper to release
    # ---------------------------------------------------------
    if bug_id != "B09":
        # B09 never_opens: Skips opening gripper
        robot.gripper.open(steps=15)

    # ---------------------------------------------------------
    # Step 8: Dwell and allow physical settling
    # ---------------------------------------------------------
    if bug_id == "B04":
        # B04 short_dwell: Dwells only 0.03 s (1 step), violating settling check
        robot.wait(duration_s=0.03)
    else:
        robot.wait(duration_s=0.6)

    # ---------------------------------------------------------
    # Step 9: Retract arm upward
    # ---------------------------------------------------------
    robot.arm.retract(distance=0.15)

    return robot.env.oracle_success()


def run_episode(
    env: SimEnv,
    seed: int,
    bug_id: str | None = None,
    out_dir: Path | str | None = None,
    capture_frames: bool | None = None,
) -> bool:
    """Run a single episode with the robot controller and save artifacts."""
    do_capture = capture_frames if capture_frames is not None else (out_dir is not None)
    robot = RobotController(env, capture_frames=do_capture)
    robot.reset(seed=seed, capture_frames=do_capture)

    success = execute_pick_place(robot, bug_id=bug_id)

    if out_dir is not None:
        run_name = f"seed_{seed:03d}_{bug_id or 'clean'}"
        import numpy as np
        actions = np.array(robot.actions, dtype=np.float32)
        obs_states = np.array(robot.obs_states, dtype=np.float32)
        cam_K = getattr(env, "cam_K", np.eye(3, dtype=np.float32))
        cam_extrinsic = getattr(env, "cam_extrinsic", np.eye(4, dtype=np.float32))

        save_sim_run(
            output_dir=out_dir,
            run_id=run_name,
            frames=robot.frames,
            states=robot.states,
            actions=actions,
            obs_states=obs_states,
            cam_K=cam_K,
            cam_extrinsic=cam_extrinsic,
            spans=robot.spans,
            oracle_success=success,
            seed=seed,
            backend=env.backend,
            is_mock=env.is_mock,
            onset_frame=None,
            perturbation_type=bug_id,
        )

    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="Franka Panda StackCube Pick-and-Place")
    parser.add_argument(
        "--backend",
        choices=["mock", "maniskill"],
        default="mock",
        help="Simulation backend (default: mock)",
    )
    parser.add_argument("--seeds", type=int, default=10, help="Number of seeds to run")
    parser.add_argument("--seed", type=int, default=None, help="Specific seed to run")
    parser.add_argument("--bug", type=str, default=None, help="Bug ID to inject (B01-B10)")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory for runs")
    args = parser.parse_args()

    if args.backend == "mock":
        env = KinematicMockEnv()
    else:
        env = ManiSkillEnv()

    seeds = [args.seed] if args.seed is not None else list(range(args.seeds))
    results = []

    print(f"Running pick_place (backend={args.backend}, bug={args.bug or 'NONE'}, seeds={len(seeds)})")
    for s in seeds:
        ok = run_episode(env, seed=s, bug_id=args.bug, out_dir=args.out_dir)
        results.append(ok)
        verdict_str = "PASS" if ok else "FAIL"
        print(f"  Seed {s:02d}: {verdict_str}")

    pass_count = sum(1 for r in results if r)
    total = len(results)
    print(f"Summary: {pass_count}/{total} PASS")

    if args.bug is None:
        if pass_count != total:
            print("ERROR: Clean reference run failed on one or more seeds!")
            exit(1)
    else:
        if pass_count != 0:
            print(f"ERROR: Bug {args.bug} unexpectedly succeeded on {pass_count}/{total} seeds!")
            exit(1)


if __name__ == "__main__":
    main()
