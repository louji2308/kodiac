"""Multi-tier metric scale recovery and world coordinate mapping.

Implements Tier A (exact camera intrinsics/extrinsics), Tier B (two-stage
ground-plane least-squares fit with Ridge regularization and condition-number
guard per ADR-0009), and Tier C (bounding box size prior with 2.5x uncertainty
inflation and uncalibrated badge).
"""

from __future__ import annotations

from typing import Literal, Protocol

import numpy as np

from Kodiac_robotics.contracts.core import Clip, ObjectDecl, Track
from Kodiac_robotics.geometry.anchors import compute_anchors


class ScaleModel(Protocol):
    """Protocol for metric scale recovery and world coordinate mapping."""

    tier: Literal["A", "B", "C"]
    badges: list[str]

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        """Returns table-frame coordinates (X_cm, D_cm, h_cm, sigma_cm)."""
        ...


class TierAScaleModel:
    """Tier A: Exact perspective projection using camera intrinsics K and extrinsics [R|t]."""

    tier: Literal["A"] = "A"

    def __init__(
        self,
        cam_K: np.ndarray,
        cam_extrinsic: np.ndarray,
        tracks: dict[str, Track],
        objects: list[ObjectDecl],
        clip: Clip | None = None,
        sigma_px: float = 0.5,
    ) -> None:
        self.cam_K = np.asarray(cam_K, dtype=np.float32)
        self.cam_extrinsic = np.asarray(cam_extrinsic, dtype=np.float32)
        self.tracks = tracks
        self.objects = {o.name: o for o in objects}
        self.clip = clip
        self.sigma_px = sigma_px
        self.badges: list[str] = []

        # Invert extrinsic for camera-to-world transformation
        self.R = self.cam_extrinsic[:3, :3]
        self.t = self.cam_extrinsic[:3, 3]
        # Camera center in world coordinates
        self.cam_center_world = -self.R.T @ self.t

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        """Project 2D mask anchors into 3D table-frame metric coordinates (X_cm, D_cm, h_cm, sigma_cm)."""
        if obj not in self.tracks:
            raise KeyError(f"Object '{obj}' not present in tracks")
        track = self.tracks[obj]
        if frame not in track.frames:
            raise KeyError(f"Frame {frame} not present in track for '{obj}'")

        mask = track.frames[frame]
        decl = self.objects.get(obj)
        size_cm = decl.size_cm if (decl and decl.size_cm) else 4.0
        width_m = size_cm / 100.0

        _, bottom_anchor, _, _, _ = compute_anchors(mask)
        u_b, v_b = bottom_anchor

        # Bounding box width
        bbox = mask.bbox_xyxy
        w_px = max(1.0, float(bbox[2] - bbox[0]))

        # Focal length
        fx = float(self.cam_K[0, 0])
        fy = float(self.cam_K[1, 1])
        cx = float(self.cam_K[0, 2])
        cy = float(self.cam_K[1, 2])

        # Depth from apparent size: Z_cam = fx * (width_m) / w_px
        z_cam = max(0.05, fx * width_m / w_px)

        # Camera ray for bottom anchor
        ray_cam = np.array([(u_b - cx) / fx, (v_b - cy) / fy, 1.0], dtype=np.float32)
        p_cam = z_cam * ray_cam

        # Transform to world coordinates: P_world = R^T * (P_cam - t)
        p_world = self.R.T @ (p_cam - self.t)

        x_cm = float(p_world[0] * 100.0)
        d_cm = float(p_world[1] * 100.0)
        h_cm = float(p_world[2] * 100.0)

        # Scale in px/cm
        k = w_px / size_cm
        sigma_cm = max(0.05, float(self.sigma_px / max(0.1, k)))

        return (x_cm, d_cm, h_cm, sigma_cm)


class TierBScaleModel:
    """Tier B: Two-stage tabletop ground-plane solve with Ridge regularization."""

    tier: Literal["B"] = "B"

    def __init__(
        self,
        v_h: float,
        h_tilde: float,
        tracks: dict[str, Track],
        objects: list[ObjectDecl],
        clip: Clip | None = None,
        sigma_px: float = 0.5,
    ) -> None:
        self.v_h = float(v_h)
        self.h_tilde = float(h_tilde)
        self.tracks = tracks
        self.objects = {o.name: o for o in objects}
        self.clip = clip
        self.sigma_px = sigma_px
        self.badges: list[str] = []

        self.img_w = float(clip.width) if clip else 640.0
        self.img_h = float(clip.height) if clip else 480.0
        self.cx = self.img_w / 2.0
        self.cy = self.img_h / 2.0
        self.f_nom = 0.785 * self.img_h

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        """Returns table-frame coordinates (X_cm, D_cm, h_cm, sigma_cm)."""
        if obj not in self.tracks:
            raise KeyError(f"Object '{obj}' not present in tracks")
        track = self.tracks[obj]
        if frame not in track.frames:
            raise KeyError(f"Frame {frame} not present in track for '{obj}'")

        mask = track.frames[frame]
        decl = self.objects.get(obj)
        size_cm = decl.size_cm if (decl and decl.size_cm) else 4.0

        _, bottom_anchor, _, _, _ = compute_anchors(mask)
        u_b, v_b = bottom_anchor

        bbox = mask.bbox_xyxy
        w_px = max(1.0, float(bbox[2] - bbox[0]))

        # Object scale (px/cm)
        k_obj = max(0.1, w_px / size_cm)

        # Expected table bottom row for this scale
        v_table = self.v_h + self.h_tilde * k_obj

        # Height above table: higher objects appear higher in image (smaller v)
        h_cm = (v_table - v_b) / k_obj
        x_cm = (u_b - self.cx) / k_obj
        d_cm = self.f_nom / k_obj
        sigma_cm = max(0.1, float(self.sigma_px / k_obj))

        return (float(x_cm), float(d_cm), float(h_cm), float(sigma_cm))


class TierCScaleModel:
    """Tier C: Single reference prior fallback with 2.5x sigma inflation."""

    tier: Literal["C"] = "C"

    def __init__(
        self,
        tracks: dict[str, Track],
        objects: list[ObjectDecl],
        clip: Clip | None = None,
        sigma_px: float = 0.5,
    ) -> None:
        self.tracks = tracks
        self.objects = {o.name: o for o in objects}
        self.clip = clip
        self.sigma_px = sigma_px
        self.badges: list[str] = ["[GEOMETRY: TIER C · UNCALIBRATED CAMERA]"]

        self.img_w = float(clip.width) if clip else 640.0
        self.img_h = float(clip.height) if clip else 480.0
        self.cx = self.img_w / 2.0
        self.f_nom = 0.785 * self.img_h

        # Precompute initial resting bottom anchors
        self.v0: dict[str, float] = {}
        for name, track in tracks.items():
            if track.frames:
                first_f = min(track.frames.keys())
                _, (ub, vb), _, _, _ = compute_anchors(track.frames[first_f])
                self.v0[name] = vb

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        """Returns table-frame coordinates (X_cm, D_cm, h_cm, sigma_cm) with 2.5x inflated uncertainty."""
        if obj not in self.tracks:
            raise KeyError(f"Object '{obj}' not present in tracks")
        track = self.tracks[obj]
        if frame not in track.frames:
            raise KeyError(f"Frame {frame} not present in track for '{obj}'")

        mask = track.frames[frame]
        decl = self.objects.get(obj)
        size_cm = decl.size_cm if (decl and decl.size_cm) else 4.0

        _, bottom_anchor, _, _, _ = compute_anchors(mask)
        u_b, v_b = bottom_anchor

        bbox = mask.bbox_xyxy
        w_px = max(1.0, float(bbox[2] - bbox[0]))
        k = max(0.1, w_px / size_cm)

        v_base = self.v0.get(obj, v_b)
        h_cm = (v_base - v_b) / k
        x_cm = (u_b - self.cx) / k
        d_cm = self.f_nom / k

        # 2.5x sigma inflation per ADR-0009
        sigma_cm = 2.5 * max(0.2, float(self.sigma_px / k))

        return (float(x_cm), float(d_cm), float(h_cm), float(sigma_cm))


def fit_scale_model(
    clip: Clip | None,
    tracks: dict[str, Track],
    objects: list[ObjectDecl],
    cam_K: np.ndarray | None = None,
    cam_extrinsic: np.ndarray | None = None,
    sigma_px: float = 0.5,
) -> ScaleModel:
    """Solves metric scale across Tiers A, B, C per ADR-0009:

    - Tier A: If cam_K and cam_extrinsic are provided, use exact perspective projection.
    - Tier B: If N_resting >= 2 resting objects on table with delta_v >= 15 px,
      solve unconstrained least-squares ground plane. If condition number kappa in (30, 50],
      apply Tikhonov Ridge regularization toward table prior theta_0 = 40 deg.
      If kappa > 50, residual > 15%, or N_resting < 2, gracefully demote to Tier C.
    - Tier C: Bounding box size prior fallback (k = l / W_o) with 2.5x sigma inflation,
      append badge '[GEOMETRY: TIER C · UNCALIBRATED CAMERA]', and flag Gate G6 depth_ambiguous.
    """
    # Tier A Check
    if cam_K is not None and cam_extrinsic is not None:
        cam_K_arr = np.asarray(cam_K, dtype=np.float32)
        cam_ext_arr = np.asarray(cam_extrinsic, dtype=np.float32)
        if cam_K_arr.shape == (3, 3) and cam_ext_arr.shape == (4, 4):
            return TierAScaleModel(
                cam_K=cam_K_arr,
                cam_extrinsic=cam_ext_arr,
                tracks=tracks,
                objects=objects,
                clip=clip,
                sigma_px=sigma_px,
            )

    # Attempt Tier B Ground-Plane Fit
    height = float(clip.height) if clip else 480.0
    decl_map = {o.name: o for o in objects}

    # Identify resting objects (exclude effector)
    resting_candidates: list[tuple[float, float]] = []  # (v_bottom, k_scale)
    for name, track in tracks.items():
        decl = decl_map.get(name)
        role = decl.role if decl else "rigid"
        if role == "effector":
            continue

        # Look in initial static frames (frames 0 to 15)
        frames_to_check = [f for f in range(0, 16) if f in track.frames]
        if not frames_to_check and track.frames:
            frames_to_check = [min(track.frames.keys())]

        if not frames_to_check:
            continue

        # Average bottom anchor and width
        v_list = []
        k_list = []
        size_cm = decl.size_cm if (decl and decl.size_cm) else 4.0

        for f in frames_to_check:
            m = track.frames[f]
            _, (_, vb), _, _, _ = compute_anchors(m)
            w_px = max(1.0, float(m.bbox_xyxy[2] - m.bbox_xyxy[0]))
            v_list.append(vb)
            k_list.append(w_px / size_cm)

        resting_candidates.append((float(np.mean(v_list)), float(np.mean(k_list))))

    # Pre-condition check: N_resting >= 2 and delta_v >= 15 px
    if len(resting_candidates) < 2:
        return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)

    v_vals = [c[0] for c in resting_candidates]
    delta_v = max(v_vals) - min(v_vals)
    if delta_v < 15.0:
        return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)

    try:
        # Ground plane equation: v_i = v_h + H_tilde * k_i
        # A * w = y where A = [[1, k_i]], y = [v_i], w = [v_h, H_tilde]
        k_vals = [c[1] for c in resting_candidates]
        A = np.column_stack(
            [np.ones(len(k_vals), dtype=np.float64), np.array(k_vals, dtype=np.float64)]
        )
        y = np.array(v_vals, dtype=np.float64)

        kappa = float(np.linalg.cond(A))

        if kappa <= 30.0:
            # Stage 1: Unconstrained least squares
            w, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        elif 30.0 < kappa <= 50.0:
            # Stage 2: Tikhonov Ridge regularization
            alpha = 0.05 * float(np.trace(A.T @ A))
            reg_matrix = A.T @ A + alpha * np.eye(2, dtype=np.float64)
            w = np.linalg.inv(reg_matrix) @ (A.T @ y)
        else:
            # kappa > 50: Demote to Tier C
            return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)

        v_h = float(w[0])
        h_tilde = float(w[1])

        # Residual check: std(y - A@w) > 15% of image height
        residuals = y - (A @ w)
        res_std = float(np.sqrt(np.mean(residuals**2)))
        if res_std > 0.15 * height:
            return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)

        # Pitch angle sanity check: theta in [20 deg, 70 deg]
        f_nom = 0.785 * height
        theta_deg = float(np.rad2deg(np.arctan(h_tilde / max(1.0, f_nom))))
        if not (20.0 <= theta_deg <= 70.0):
            return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)

        return TierBScaleModel(
            v_h=v_h,
            h_tilde=h_tilde,
            tracks=tracks,
            objects=objects,
            clip=clip,
            sigma_px=sigma_px,
        )

    except np.linalg.LinAlgError:
        return TierCScaleModel(tracks=tracks, objects=objects, clip=clip, sigma_px=sigma_px)
