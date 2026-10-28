"""High-level robot API and controller with @span tracking.

Provides ArmController, GripperController, and RobotController
for Franka Panda pick-and-place execution.
Per ARCHITECTURE.md §4, §5.7, and P02 RULING.
"""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.sim.env import SimEnv, SimState
from Kodiac_robotics.sim.spans import SimSpan, set_active_robot, span


class ArmController:
    """End-effector trajectory generation and arm motion primitives."""

    def __init__(self, robot: RobotController) -> None:
        self.robot = robot

    @span("arm.move_to")
    def move_to(
        self,
        target_pos: np.ndarray | tuple[float, float, float] | list[float],
        speed: float = 0.12,
        steps: int | None = None,
    ) -> None:
        """Move end-effector to target position in world coordinates."""
        self._execute_motion(np.asarray(target_pos, dtype=np.float32), speed=speed, steps=steps)

    @span("arm.lift")
    def lift(self, distance: float = 0.12, speed: float = 0.12) -> None:
        """Lift end-effector vertically by distance meters."""
        target = self.robot.ee_pos.copy()
        target[2] += float(distance)
        self._execute_motion(target, speed=speed)

    @span("arm.retract")
    def retract(self, distance: float = 0.15, speed: float = 0.12) -> None:
        """Retract arm upward and away from the workspace."""
        target = self.robot.ee_pos.copy()
        target[2] += float(distance)
        self._execute_motion(target, speed=speed)

    def _execute_motion(
        self,
        target: np.ndarray,
        speed: float = 0.12,
        steps: int | None = None,
    ) -> None:
        """Interpolate linear trajectory in Cartesian space."""
        current = self.robot.ee_pos.copy()
        delta_total = target - current
        dist = float(np.linalg.norm(delta_total))

        if steps is None:
            # 30 fps, speed in m/s => delta per step = speed * (1/30)
            step_size = max(0.001, speed * (1.0 / 30.0))
            num_steps = max(2, int(np.ceil(dist / step_size)))
        else:
            num_steps = max(1, steps)

        for i in range(1, num_steps + 1):
            alpha = i / float(num_steps)
            next_pos = current + alpha * delta_total
            step_delta = next_pos - self.robot.ee_pos
            action = np.zeros(7, dtype=np.float32)
            action[:3] = step_delta
            action[6] = self.robot.last_gripper_cmd
            self.robot._step(action)


class GripperController:
    """Parallel jaw gripper primitives."""

    def __init__(self, robot: RobotController) -> None:
        self.robot = robot

    @span("gripper.close")
    def close(self, steps: int = 15) -> None:
        """Close parallel jaws firmly around target object."""
        self.robot.last_gripper_cmd = -1.0
        for _ in range(steps):
            action = np.zeros(7, dtype=np.float32)
            action[6] = -1.0
            self.robot._step(action)

    @span("gripper.open")
    def open(self, steps: int = 15) -> None:
        """Open parallel jaws to release grasped object."""
        self.robot.last_gripper_cmd = 1.0
        for _ in range(steps):
            action = np.zeros(7, dtype=np.float32)
            action[6] = 1.0
            self.robot._step(action)


class RobotController:
    """Unified robot controller orchestrating arm, gripper, and sim logging."""

    def __init__(self, env: SimEnv, capture_frames: bool = False) -> None:
        self.env = env
        self.capture_frames = capture_frames
        self.arm = ArmController(self)
        self.gripper = GripperController(self)

        # Execution tracking
        self.current_step = 0
        self.current_time_s = 0.0
        self.ee_pos = np.array([-0.10, 0.22, 0.20], dtype=np.float32)
        self.last_gripper_cmd = 1.0  # open

        # Recorded episode buffers
        self.spans: list[SimSpan] = []
        self.states: list[SimState] = []
        self.frames: list[np.ndarray] = []
        self.actions: list[np.ndarray] = []
        self.obs_states: list[np.ndarray] = []

        set_active_robot(self)

    def reset(self, seed: int | None = None, capture_frames: bool | None = None) -> None:
        """Reset sim environment and clear buffers."""
        if capture_frames is not None:
            self.capture_frames = capture_frames
        obs, _ = self.env.reset(seed=seed)
        self.current_step = 0
        self.current_time_s = 0.0
        state = self.env.privileged_state()
        self.ee_pos = np.array(
            [state.cubeA_pose[0], state.cubeA_pose[1], 0.20], dtype=np.float32
        )
        self.last_gripper_cmd = 1.0

        self.spans.clear()
        self.states.clear()
        self.frames.clear()
        self.actions.clear()
        self.obs_states.clear()

        # Capture initial state (and frame if recording)
        self.states.append(state)
        if self.capture_frames:
            self.frames.append(self.env.render())
        self.obs_states.append(obs)
        set_active_robot(self)

    def _step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one simulation step and log trajectory state."""
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.current_step += 1
        self.current_time_s = self.current_step * (1.0 / 30.0)

        # Update cached EE position from action delta
        self.ee_pos = self.ee_pos + action[:3]
        state = self.env.privileged_state()

        self.actions.append(action.copy())
        self.states.append(state)
        if self.capture_frames:
            self.frames.append(self.env.render())
        self.obs_states.append(obs)

        return obs, reward, terminated, truncated, info

    @span("wait")
    def wait(self, duration_s: float = 0.5) -> None:
        """Hold position and allow physical settling for duration_s seconds."""
        num_steps = max(1, int(round(duration_s * 30.0)))
        for _ in range(num_steps):
            action = np.zeros(7, dtype=np.float32)
            action[6] = self.last_gripper_cmd
            self._step(action)

    def _record_span(self, span: SimSpan) -> None:
        """Internal callback invoked by @span decorator."""
        self.spans.append(span)
