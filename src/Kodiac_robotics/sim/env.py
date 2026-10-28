"""Simulation environments: SimEnv Protocol, KinematicMockEnv, and lazy ManiSkillEnv.

Implements dual-backend simulation per ARCHITECTURE.md §4, §5.7, ADR-0004,
ADR-0007, and P02 RULING.

- KinematicMockEnv: 100% offline pure-Python/NumPy CPU simulation of Panda + StackCube.
  Mandatory indelible visual banner: [MOCK SIMULATION · NOT SAPIEN PHYSICS].
- ManiSkillEnv: Production SAPIEN physics wrapper with lazy import isolation.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal, Protocol

try:
    import cv2
except Exception:
    cv2 = None

import numpy as np
from pydantic import BaseModel, Field

from Kodiac_robotics.sim.spans import SimSpan


class SimState(BaseModel):
    """Privileged ground-truth simulation state at a single control step."""

    step: int
    t_s: float
    gripper_width: float
    cubeA_pose: tuple[float, float, float, float, float, float, float]  # (x, y, z, qx, qy, qz, qw)
    cubeB_pose: tuple[float, float, float, float, float, float, float]
    cubeA_vel: tuple[float, float, float]
    in_contact: bool


class SimEnv(Protocol):
    """Structural protocol satisfied by both KinematicMockEnv and ManiSkillEnv."""

    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]: ...
    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]: ...
    def privileged_state(self) -> SimState: ...
    def oracle_success(self) -> bool: ...
    def render(self) -> np.ndarray: ...  # (512, 512, 3) uint8 RGB


class SimRun(BaseModel):
    """Complete recorded simulation episode metadata and artifact locations."""

    run_id: str
    seed: int
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    video_path: str
    state_path: str
    meta_path: str
    spans: list[SimSpan] = Field(default_factory=list)
    oracle_success: bool
    onset_frame: int | None = None
    perturbation_type: str | None = None


# ==============================================================================
# Camera Geometry & Projections (Tier A Camera Calibration)
# ==============================================================================

def _build_camera_matrices(
    cam_pos: np.ndarray,
    target: np.ndarray,
    fov_deg: float = 65.0,
    width: int = 512,
    height: int = 512,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute 3x3 intrinsic K and 4x4 extrinsic [R | t] for look-at camera."""
    forward = target - cam_pos
    forward = forward / np.linalg.norm(forward)

    up_hint = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    right = np.cross(forward, up_hint)
    if np.linalg.norm(right) < 1e-4:
        right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        right = right / np.linalg.norm(right)

    up = np.cross(right, forward)
    up = up / np.linalg.norm(up)

    # OpenCV camera frame: X right, Y down, Z forward
    R = np.stack([right, -up, forward], axis=0).astype(np.float32)
    t = (-R @ cam_pos).astype(np.float32)

    extrinsic = np.eye(4, dtype=np.float32)
    extrinsic[:3, :3] = R
    extrinsic[:3, 3] = t

    f = (height / 2.0) / np.tan(np.deg2rad(fov_deg / 2.0))
    K = np.array(
        [
            [f, 0.0, width / 2.0],
            [0.0, f, height / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    return K, extrinsic


def _project_point(p_world: np.ndarray, K: np.ndarray, extrinsic: np.ndarray) -> tuple[int, int, float]:
    """Project a 3D world coordinate to 2D image pixel coordinates (u, v, z_cam)."""
    p_h = np.array([p_world[0], p_world[1], p_world[2], 1.0], dtype=np.float32)
    p_cam = extrinsic @ p_h
    z_cam = float(p_cam[2])
    if z_cam <= 1e-3:
        return -999, -999, z_cam
    u = int(round((K[0, 0] * p_cam[0] / z_cam) + K[0, 2]))
    v = int(round((K[1, 1] * p_cam[1] / z_cam) + K[1, 2]))
    return u, v, z_cam


def _fill_poly_np(img: np.ndarray, pts: np.ndarray, color: tuple[int, int, int]) -> None:
    """Pure NumPy scanline polygon fill fallback when OpenCV is not available."""
    min_x = max(0, int(np.min(pts[:, 0])))
    max_x = min(img.shape[1] - 1, int(np.max(pts[:, 0])))
    min_y = max(0, int(np.min(pts[:, 1])))
    max_y = min(img.shape[0] - 1, int(np.max(pts[:, 1])))
    if max_x <= min_x or max_y <= min_y:
        return

    n = len(pts)
    ys = np.arange(min_y, max_y + 1)
    xs = np.arange(min_x, max_x + 1)
    grid_x, grid_y = np.meshgrid(xs, ys)

    # Cross product half-plane test
    inside_pos = np.ones_like(grid_x, dtype=bool)
    inside_neg = np.ones_like(grid_x, dtype=bool)
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        edge = p2 - p1
        cross = (grid_x - p1[0]) * edge[1] - (grid_y - p1[1]) * edge[0]
        inside_pos &= (cross <= 0)
        inside_neg &= (cross >= 0)

    inside = inside_pos | inside_neg
    sub = img[min_y : max_y + 1, min_x : max_x + 1]
    sub[inside] = color


def _draw_line_np(
    img: np.ndarray,
    pt1: tuple[int, int],
    pt2: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = 1,
) -> None:
    """Pure NumPy line drawing fallback."""
    x1, y1 = pt1
    x2, y2 = pt2
    num_pts = max(abs(x2 - x1), abs(y2 - y1), 1)
    xs = np.linspace(x1, x2, num_pts).astype(int)
    ys = np.linspace(y1, y2, num_pts).astype(int)
    h, w = img.shape[:2]
    r = max(1, thickness // 2)
    for x, y in zip(xs, ys):
        y_min = max(0, y - r)
        y_max = min(h, y + r + 1)
        x_min = max(0, x - r)
        x_max = min(w, x + r + 1)
        img[y_min:y_max, x_min:x_max] = color


def _draw_banner_text_np(img: np.ndarray, text: str, start_x: int = 38, start_y: int = 10) -> None:
    """Draw text dots in pure NumPy on top banner."""
    # Simple block rendering for watermark visibility
    color = (0, 50, 255)
    cur_x = start_x
    for ch in text:
        if ch != " ":
            img[start_y : start_y + 12, cur_x : cur_x + 6] = color
        cur_x += 10


# ==============================================================================
# KinematicMockEnv (100% Offline, Zero Torch / GPU)
# ==============================================================================

class KinematicMockEnv:
    """Analytic kinematic Franka Panda StackCube simulator on tabletop.

    - Simulates Franka Panda stacking red cube (cubeA, 4cm) onto green cube (cubeB, 4cm).
    - Runs 100% offline with zero torch/GPU dependencies.
    - Indelibly burns '[MOCK SIMULATION · NOT SAPIEN PHYSICS]' banner on every frame.
    - Implements settling velocity check (v < 0.01 m/s over 0.5s dwell) asserting
      10/10 oracle FAIL on physical perturbations and 10/10 PASS on reference execution.
    """

    backend: Literal["kinematic_mock"] = "kinematic_mock"
    is_mock: bool = True

    def __init__(
        self,
        sim_freq: int = 120,
        control_freq: int = 30,
        render_width: int = 512,
        render_height: int = 512,
    ) -> None:
        self.sim_freq = sim_freq
        self.control_freq = control_freq
        self.dt = 1.0 / control_freq  # 0.03333s
        self.render_width = render_width
        self.render_height = render_height

        # Camera setup
        self.cam_pos = np.array([0.35, -0.28, 0.42], dtype=np.float32)
        self.cam_target = np.array([0.0, 0.22, 0.04], dtype=np.float32)
        self.cam_K, self.cam_extrinsic = _build_camera_matrices(
            self.cam_pos, self.cam_target, fov_deg=65.0, width=render_width, height=render_height
        )

        # Cube geometry (4.0 cm = 0.04 m cubes)
        self.cube_half_size = 0.02  # meters

        # State attributes
        self.step_idx = 0
        self.t_s = 0.0
        self.ee_pos = np.array([-0.10, 0.22, 0.20], dtype=np.float32)
        self.gripper_width = 0.08  # 8cm open
        self.cubeA_pos = np.array([-0.10, 0.22, 0.02], dtype=np.float32)
        self.cubeB_pos = np.array([0.08, 0.22, 0.02], dtype=np.float32)
        self.cubeA_vel = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.in_contact = False
        self.grasped_offset = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.release_step: int | None = None
        self.released_from_z: float | None = None

        # Sliding window for settling velocity check (0.5s = 15 steps at 30Hz)
        self.speed_history: deque[float] = deque(maxlen=15)

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        """Reset environment to initial tabletop configuration with optional seed jitter."""
        rng = np.random.RandomState(seed if seed is not None else 42)
        self.step_idx = 0
        self.t_s = 0.0
        self.release_step = None
        self.released_from_z = None

        # Small seed-based jitter (+- 5mm)
        jitter_a = rng.uniform(-0.005, 0.005, size=2)
        jitter_b = rng.uniform(-0.005, 0.005, size=2)

        self.cubeA_pos = np.array([-0.10 + jitter_a[0], 0.22 + jitter_a[1], 0.02], dtype=np.float32)
        self.cubeB_pos = np.array([0.08 + jitter_b[0], 0.22 + jitter_b[1], 0.02], dtype=np.float32)
        self.ee_pos = np.array([self.cubeA_pos[0], self.cubeA_pos[1], 0.20], dtype=np.float32)
        self.gripper_width = 0.08
        self.cubeA_vel = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.in_contact = False
        self.grasped_offset = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.speed_history.clear()

        obs = self._get_obs()
        info: dict[str, Any] = {
            "seed": seed,
            "is_mock": True,
            "env_backend": "kinematic_mock",
        }
        return obs, info

    def _get_obs(self) -> np.ndarray:
        """Construct proprioceptive observation vector matching pd_ee_delta_pos."""
        # 3 (ee_pos) + 1 (gripper_width) + 3 (cubeA_pos) + 3 (cubeB_pos) + 3 (rel_pos) = 13 dim
        rel = self.cubeB_pos - self.cubeA_pos
        obs = np.concatenate(
            [self.ee_pos, [self.gripper_width], self.cubeA_pos, self.cubeB_pos, rel],
            axis=0,
            dtype=np.float32,
        )
        return obs

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """Advance simulation by one control step (1/30 s).

        action: (7,) float array in pd_ee_delta_pos space:
                [dx, dy, dz, droll, dpitch, dyaw, gripper_cmd]
                gripper_cmd < 0 => close, > 0 => open
        """
        action = np.asarray(action, dtype=np.float32)
        if action.shape[0] < 7:
            raise ValueError(f"Action must be shape (7,), got {action.shape}")

        delta_pos = action[:3]
        gripper_cmd = float(action[6])

        # 1. Update end-effector position
        self.ee_pos = self.ee_pos + delta_pos
        # Table floor collision for gripper fingers
        self.ee_pos[2] = max(0.015, float(self.ee_pos[2]))

        # 2. Update gripper width (delta speed approx 0.006 m/step = ~0.18 m/s)
        grip_rate = 0.006
        if gripper_cmd < 0:
            self.gripper_width = max(0.0, self.gripper_width - grip_rate * abs(gripper_cmd))
        elif gripper_cmd > 0:
            self.gripper_width = min(0.08, self.gripper_width + grip_rate * abs(gripper_cmd))

        # 3. Grasping & contact dynamics
        prev_cubeA_pos = self.cubeA_pos.copy()
        dist_xy = np.linalg.norm(self.ee_pos[:2] - self.cubeA_pos[:2])
        dist_z = abs(self.ee_pos[2] - self.cubeA_pos[2])

        # Gripper pinches cube (width <= 0.045m around 0.04m cube) when aligned
        if self.in_contact:
            if self.gripper_width > 0.045:
                # Gripper released cube
                self.in_contact = False
                self.release_step = self.step_idx
                self.released_from_z = float(self.cubeA_pos[2])
            else:
                # Check low-lift collision with Cube B (obstacle)
                dist_to_B_xy = float(np.linalg.norm(self.cubeA_pos[:2] - self.cubeB_pos[:2]))
                if self.cubeA_pos[2] < 0.045 and dist_to_B_xy < 0.042:
                    # Low-lift collision knocks cube out of gripper
                    self.in_contact = False
                    self.release_step = self.step_idx
                    self.released_from_z = float(self.cubeA_pos[2])
                    push_dir = self.cubeA_pos[:2] - self.cubeB_pos[:2]
                    norm_p = np.linalg.norm(push_dir)
                    if norm_p > 1e-4:
                        self.cubeA_pos[:2] += (push_dir / norm_p) * 0.02
                    self.cubeA_pos[2] = 0.02
                else:
                    # Cube moves rigidly with end-effector
                    self.cubeA_pos = self.ee_pos + self.grasped_offset
        else:
            if self.gripper_width <= 0.045 and dist_xy <= 0.030 and dist_z <= 0.035:
                self.in_contact = True
                self.grasped_offset = self.cubeA_pos - self.ee_pos

        # 4. Free-body physics when not in contact
        if not self.in_contact:
            target_stack_z = float(self.cubeB_pos[2]) + 2 * self.cube_half_size  # 0.06m
            dist_to_B_xy = float(np.linalg.norm(self.cubeA_pos[:2] - self.cubeB_pos[:2]))
            align_threshold_m = 0.0333  # 3.33 cm alignment tolerance per Invariant I8

            # Check for high drop bounce / tumble (B10)
            if self.released_from_z is not None and self.released_from_z > 0.08:
                # Dropped from high release: kinetic energy deflects off Cube B
                if self.cubeA_pos[2] > 0.02:
                    self.cubeA_vel[2] -= 9.81 * self.dt
                    self.cubeA_pos[2] += self.cubeA_vel[2] * self.dt
                    self.cubeA_pos[0] += 0.005  # deflect horizontally
                    if self.cubeA_pos[2] <= 0.02:
                        self.cubeA_pos[2] = 0.02
                        self.cubeA_vel[:] = 0.0
                else:
                    self.cubeA_pos[2] = 0.02
                    self.cubeA_vel[:] = 0.0
            elif dist_to_B_xy <= align_threshold_m and self.cubeA_pos[2] >= (target_stack_z - 0.015):
                # Landed on top of Cube B (target height z = 0.06m)
                # Check premature retraction drag (B04 short dwell)
                if self.release_step is not None and (self.step_idx - self.release_step) < 15:
                    ee_speed = float(np.linalg.norm(delta_pos)) / self.dt
                    if ee_speed > 0.02:
                        # Premature retraction pulls cube off balance
                        self.cubeA_pos[0] += 0.04
                        self.cubeA_pos[2] = 0.02

                if self.cubeA_pos[2] <= target_stack_z + 0.005:
                    self.cubeA_pos[2] = target_stack_z
                    self.cubeA_vel[:] = 0.0
                else:
                    # Falling down onto Cube B
                    self.cubeA_vel[2] -= 9.81 * self.dt
                    self.cubeA_pos[2] += self.cubeA_vel[2] * self.dt
                    if self.cubeA_pos[2] <= target_stack_z:
                        self.cubeA_pos[2] = target_stack_z
                        self.cubeA_vel[:] = 0.0
            else:
                # Not resting on Cube B: topples/falls to table surface (z = 0.02)
                if dist_to_B_xy > align_threshold_m and 0.025 < self.cubeA_pos[2] < (target_stack_z + 0.005):
                    # Slide outward off the edge
                    direction = self.cubeA_pos[:2] - self.cubeB_pos[:2]
                    norm_dir = np.linalg.norm(direction)
                    if norm_dir > 1e-4:
                        self.cubeA_pos[:2] += (direction / norm_dir) * 0.005

                if self.cubeA_pos[2] > 0.02:
                    self.cubeA_vel[2] -= 9.81 * self.dt
                    self.cubeA_pos[2] += self.cubeA_vel[2] * self.dt
                    if self.cubeA_pos[2] <= 0.02:
                        self.cubeA_pos[2] = 0.02
                        self.cubeA_vel[:] = 0.0
                else:
                    self.cubeA_pos[2] = 0.02
                    self.cubeA_vel[:] = 0.0

        # Compute empirical linear velocity
        actual_delta = self.cubeA_pos - prev_cubeA_pos
        self.cubeA_vel = actual_delta / self.dt
        current_speed = float(np.linalg.norm(self.cubeA_vel))
        self.speed_history.append(current_speed)

        self.step_idx += 1
        self.t_s = self.step_idx * self.dt

        obs = self._get_obs()
        reward = 1.0 if self.oracle_success() else 0.0
        terminated = False
        truncated = False
        info = {
            "step": self.step_idx,
            "t_s": self.t_s,
            "oracle_success": self.oracle_success(),
            "in_contact": self.in_contact,
            "cubeA_speed": current_speed,
        }
        return obs, reward, terminated, truncated, info

    def privileged_state(self) -> SimState:
        """Return ground truth state of both cubes and robot at current step."""
        # Quaternion (0, 0, 0, 1) identity
        quat = (0.0, 0.0, 0.0, 1.0)
        pose_a = (
            float(self.cubeA_pos[0]),
            float(self.cubeA_pos[1]),
            float(self.cubeA_pos[2]),
            quat[0],
            quat[1],
            quat[2],
            quat[3],
        )
        pose_b = (
            float(self.cubeB_pos[0]),
            float(self.cubeB_pos[1]),
            float(self.cubeB_pos[2]),
            quat[0],
            quat[1],
            quat[2],
            quat[3],
        )
        vel_a = (float(self.cubeA_vel[0]), float(self.cubeA_vel[1]), float(self.cubeA_vel[2]))
        return SimState(
            step=self.step_idx,
            t_s=round(self.t_s, 4),
            gripper_width=round(float(self.gripper_width), 4),
            cubeA_pose=pose_a,
            cubeB_pose=pose_b,
            cubeA_vel=vel_a,
            in_contact=bool(self.in_contact),
        )

    def oracle_success(self) -> bool:
        """Ground truth success verification with settling velocity check.

        Requires:
        1. Gripper is released (not in contact, width > 0.045m).
        2. Post-release dwell window of at least 0.5s (15 steps) completed.
        3. Horizontal alignment align_xy <= 3.33 cm.
        4. Vertical height gap <= 0.5 cm (|z_A - (z_B + 0.04)| <= 0.005).
        5. Settling velocity check: linear speed < 0.01 m/s over full 0.5s dwell (15 steps).
        """
        # 1. Gripper released
        if self.in_contact or self.gripper_width <= 0.045:
            return False

        # 2. Must have had at least 0.5s (15 steps) post-release dwell
        if self.release_step is None or (self.step_idx - self.release_step) < 15:
            return False

        # 3. Alignment tolerances (Invariant I8 / ADR-0006)
        dist_xy = float(np.linalg.norm(self.cubeA_pos[:2] - self.cubeB_pos[:2]))
        if dist_xy > 0.0333:  # 3.33 cm
            return False

        gap_z = abs(float(self.cubeA_pos[2]) - (float(self.cubeB_pos[2]) + 0.04))
        if gap_z > 0.005:  # 0.5 cm
            return False

        # 4. Settling velocity check (0.5s dwell = 15 steps at 30Hz)
        if len(self.speed_history) < 15:
            return False
        max_speed = max(self.speed_history)
        if max_speed >= 0.01:  # 0.01 m/s = 1.0 cm/s
            return False

        return True

    def render(self) -> np.ndarray:
        """Render 512x512 RGB frame with indelible Law 1 anti-fabrication watermark."""
        img = np.zeros((self.render_height, self.render_width, 3), dtype=np.uint8)

        # 1. Background studio gradient
        for y in range(self.render_height):
            c = int(45 + (y / self.render_height) * 25)
            img[y, :] = (c, c, c + 5)

        # 2. Table surface grid
        table_corners = [
            np.array([-0.35, 0.05, 0.0], dtype=np.float32),
            np.array([0.35, 0.05, 0.0], dtype=np.float32),
            np.array([0.35, 0.45, 0.0], dtype=np.float32),
            np.array([-0.35, 0.45, 0.0], dtype=np.float32),
        ]
        poly_pts = []
        for pt in table_corners:
            u, v, _ = _project_point(pt, self.cam_K, self.cam_extrinsic)
            poly_pts.append([u, v])
        if cv2 is not None:
            cv2.fillPoly(img, [np.array(poly_pts, dtype=np.int32)], (75, 78, 85))
            cv2.polylines(img, [np.array(poly_pts, dtype=np.int32)], True, (110, 115, 125), 2)
            # Draw grid lines on tabletop
            for x_line in np.linspace(-0.3, 0.3, 7):
                p1 = np.array([x_line, 0.05, 0.0], dtype=np.float32)
                p2 = np.array([x_line, 0.45, 0.0], dtype=np.float32)
                u1, v1, _ = _project_point(p1, self.cam_K, self.cam_extrinsic)
                u2, v2, _ = _project_point(p2, self.cam_K, self.cam_extrinsic)
                cv2.line(img, (u1, v1), (u2, v2), (90, 93, 100), 1)
        else:
            _fill_poly_np(img, np.array(poly_pts, dtype=np.int32), (75, 78, 85))

        # 3. Draw Green Cube B (target)
        self._draw_cube(img, self.cubeB_pos, color_rgb=(44, 160, 44))

        # 4. Draw Red Cube A (manipulated)
        self._draw_cube(img, self.cubeA_pos, color_rgb=(214, 39, 40))

        # 5. Draw Robot Gripper
        self._draw_gripper(img, self.ee_pos, self.gripper_width)

        # 6. LAW 1 INDELIBLE BANNER: [MOCK SIMULATION · NOT SAPIEN PHYSICS]
        # Burns across top 32 pixels
        if cv2 is not None:
            cv2.rectangle(img, (0, 0), (self.render_width, 32), (15, 15, 15), -1)
            cv2.line(img, (0, 32), (self.render_width, 32), (0, 0, 200), 2)
            banner_text = "[MOCK SIMULATION · NOT SAPIEN PHYSICS]"
            cv2.putText(
                img,
                banner_text,
                (38, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 50, 255),  # High-visibility warning red/orange
                2,
                cv2.LINE_AA,
            )
        else:
            # Pure NumPy banner drawing fallback
            img[0:32, :] = (15, 15, 15)
            img[32:34, :] = (0, 0, 200)
            _draw_banner_text_np(img, "[MOCK SIMULATION - NOT SAPIEN PHYSICS]", start_x=38, start_y=10)

        return img

    def _draw_cube(self, img: np.ndarray, center: np.ndarray, color_rgb: tuple[int, int, int]) -> None:
        """Render a 3D cube with shaded faces."""
        h = self.cube_half_size
        cx, cy, cz = center[0], center[1], center[2]
        # 8 corners
        corners = [
            np.array([cx - h, cy - h, cz - h], dtype=np.float32),  # 0
            np.array([cx + h, cy - h, cz - h], dtype=np.float32),  # 1
            np.array([cx + h, cy + h, cz - h], dtype=np.float32),  # 2
            np.array([cx - h, cy + h, cz - h], dtype=np.float32),  # 3
            np.array([cx - h, cy - h, cz + h], dtype=np.float32),  # 4
            np.array([cx + h, cy - h, cz + h], dtype=np.float32),  # 5
            np.array([cx + h, cy + h, cz + h], dtype=np.float32),  # 6
            np.array([cx - h, cy + h, cz + h], dtype=np.float32),  # 7
        ]
        pts_2d = [_project_point(c, self.cam_K, self.cam_extrinsic)[:2] for c in corners]

        # Faces: front, top, right
        r, g, b = color_rgb
        faces = [
            ([0, 1, 5, 4], (max(0, r - 30), max(0, g - 30), max(0, b - 30))),  # front
            ([4, 5, 6, 7], (min(255, r + 40), min(255, g + 40), min(255, b + 40))),  # top
            ([1, 2, 6, 5], (r, g, b)),  # right
        ]
        for idxs, col in faces:
            poly = np.array([pts_2d[i] for i in idxs], dtype=np.int32)
            if cv2 is not None:
                cv2.fillPoly(img, [poly], col)
                cv2.polylines(img, [poly], True, (20, 20, 20), 1)
            else:
                _fill_poly_np(img, poly, col)

    def _draw_gripper(self, img: np.ndarray, ee_pos: np.ndarray, width: float) -> None:
        """Render Franka Panda 2-finger parallel gripper."""
        ex, ey, ez = ee_pos[0], ee_pos[1], ee_pos[2]
        half_w = width / 2.0

        # Wrist mount
        wrist_top = np.array([ex, ey, ez + 0.08], dtype=np.float32)
        wrist_base = np.array([ex, ey, ez + 0.04], dtype=np.float32)
        u_wt, v_wt, _ = _project_point(wrist_top, self.cam_K, self.cam_extrinsic)
        u_wb, v_wb, _ = _project_point(wrist_base, self.cam_K, self.cam_extrinsic)
        if cv2 is not None:
            cv2.line(img, (u_wt, v_wt), (u_wb, v_wb), (200, 200, 200), 8)
        else:
            _draw_line_np(img, (u_wt, v_wt), (u_wb, v_wb), (200, 200, 200), thickness=8)

        # Crossbar
        left_mount = np.array([ex - half_w, ey, ez + 0.04], dtype=np.float32)
        right_mount = np.array([ex + half_w, ey, ez + 0.04], dtype=np.float32)
        ulm, vlm, _ = _project_point(left_mount, self.cam_K, self.cam_extrinsic)
        urm, vrm, _ = _project_point(right_mount, self.cam_K, self.cam_extrinsic)
        if cv2 is not None:
            cv2.line(img, (ulm, vlm), (urm, vrm), (180, 180, 180), 5)
        else:
            _draw_line_np(img, (ulm, vlm), (urm, vrm), (180, 180, 180), thickness=5)

        # Fingers
        left_tip = np.array([ex - half_w, ey, ez], dtype=np.float32)
        right_tip = np.array([ex + half_w, ey, ez], dtype=np.float32)
        ult, vlt, _ = _project_point(left_tip, self.cam_K, self.cam_extrinsic)
        urt, vrt, _ = _project_point(right_tip, self.cam_K, self.cam_extrinsic)
        if cv2 is not None:
            cv2.line(img, (ulm, vlm), (ult, vlt), (50, 50, 50), 4)
            cv2.line(img, (urm, vrm), (urt, vrt), (50, 50, 50), 4)
        else:
            _draw_line_np(img, (ulm, vlm), (ult, vlt), (50, 50, 50), thickness=4)
            _draw_line_np(img, (urm, vrm), (urt, vrt), (50, 50, 50), thickness=4)


# ==============================================================================
# ManiSkillEnv (Lazy Import Isolated for Remote GPU Execution)
# ==============================================================================

class ManiSkillEnv:
    """Production SAPIEN physics wrapper executed inside Modal GPU containers."""

    backend: Literal["maniskill"] = "maniskill"
    is_mock: bool = False

    def __init__(
        self,
        env_id: str = "StackCube-v1",
        obs_mode: str = "state_dict",
        control_mode: str = "pd_ee_delta_pos",
        render_mode: str = "rgb_array",
    ) -> None:
        try:
            import gymnasium as gym
            import mani_skill.envs  # noqa: F401

            self.env = gym.make(
                env_id,
                obs_mode=obs_mode,
                control_mode=control_mode,
                render_mode=render_mode,
                sim_freq=120,
                control_freq=30,
            )
        except ImportError as e:
            raise RuntimeError(
                f"ManiSkill/SAPIEN is not installed: {e}. "
                "Use KinematicMockEnv for local CPU execution or run ManiSkillEnv on Modal GPU."
            ) from e

        self.step_idx = 0
        self.t_s = 0.0

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        obs, info = self.env.reset(seed=seed)
        self.step_idx = 0
        self.t_s = 0.0
        return obs, info

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.step_idx += 1
        self.t_s = self.step_idx * (1.0 / 30.0)
        return obs, float(reward), terminated, truncated, info

    def privileged_state(self) -> SimState:
        # Extract privileged poses from ManiSkill env
        info = getattr(self.env, "unwrapped", self.env)
        cubeA = info.cubeA.pose.raw_pose[0].cpu().numpy()
        cubeB = info.cubeB.pose.raw_pose[0].cpu().numpy()
        velA = info.cubeA.linear_velocity[0].cpu().numpy()
        qpos = info.agent.robot.get_qpos()[0].cpu().numpy()
        gripper_w = float(qpos[-2] + qpos[-1])
        return SimState(
            step=self.step_idx,
            t_s=round(self.t_s, 4),
            gripper_width=round(gripper_w, 4),
            cubeA_pose=tuple(float(x) for x in cubeA),  # type: ignore
            cubeB_pose=tuple(float(x) for x in cubeB),  # type: ignore
            cubeA_vel=(float(velA[0]), float(velA[1]), float(velA[2])),
            in_contact=bool(info.is_grasping(info.cubeA)),
        )

    def oracle_success(self) -> bool:
        info = getattr(self.env, "unwrapped", self.env)
        return bool(info.evaluate()["success"].item())

    def render(self) -> np.ndarray:
        frame = self.env.render()
        if frame is None:
            return np.zeros((512, 512, 3), dtype=np.uint8)
        return np.asarray(frame, dtype=np.uint8)
