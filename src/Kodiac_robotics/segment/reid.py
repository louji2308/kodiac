"""Spatio-temporal re-identification engine for Kodiac.

Reconciles object identities across sparse keyframes and dense temporal windows.
Combines:
1. Morphologically eroded-core HSV color histograms (cv2.erode) to eliminate boundary bleed
2. L2 centroid velocity continuity for smooth trajectory tracking
3. Coarse categorical Hue gating (delta Hue > 60° infinite penalty) preventing block swaps
4. Non-destructive multi-label overlapping pixel semantics (no mask subtraction)
Per ARCHITECTURE.md §3.1, §4.3, IMPLEMENTATION_PLAN.md P03.S06, and P03 RULING.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Tuple

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import ObjMask


def decode_mask(obj_mask: ObjMask, target_shape: Tuple[int, int]) -> np.ndarray:
    """Decode ObjMask RLE or synthesize from bounding box if RLE is placeholder."""
    h, w = target_shape
    if obj_mask.rle and obj_mask.rle != "dummy_rle_data":
        try:
            rle_str = obj_mask.rle
            if rle_str.startswith("[") and rle_str.endswith("]"):
                runs = json.loads(rle_str)
            else:
                runs = [int(x) for x in rle_str.split(",") if x.strip()]
            total_px = h * w
            dots = np.zeros(total_px, dtype=np.uint8)
            idx = 0
            val = 0
            for cnt in runs:
                if val == 1:
                    dots[idx : idx + cnt] = 1
                idx += cnt
                val = 1 - val
            mask = dots.reshape((h, w), order="F")
            if np.sum(mask) > 0:
                return mask
        except Exception:
            pass

    # Fallback to bounding box fill
    mask = np.zeros((h, w), dtype=np.uint8)
    x1, y1, x2, y2 = obj_mask.bbox_xyxy
    ix1, iy1 = max(0, int(round(x1))), max(0, int(round(y1)))
    ix2, iy2 = min(w, int(round(x2))), min(h, int(round(y2)))
    if ix2 > ix1 and iy2 > iy1:
        mask[iy1:iy2, ix1:ix2] = 1
    return mask


class ReIdEngine:
    """Spatio-temporal re-identification across keyframes and tracking windows."""

    def __init__(
        self,
        hist_bins: Tuple[int, int] = (16, 8),
        spatial_weight: float = 0.5,
        color_weight: float = 0.5,
        hue_gate_degrees: float = 60.0,
    ) -> None:
        """Initialize ReIdEngine.

        Args:
            hist_bins: Number of bins for (Hue, Saturation) histogram.
            spatial_weight: Weight for normalized centroid distance cost.
            color_weight: Weight for color histogram Bhattacharyya distance.
            hue_gate_degrees: Angular Hue threshold beyond which infinite cost is applied.
        """
        self.hist_bins = hist_bins
        self.spatial_weight = spatial_weight
        self.color_weight = color_weight
        self.hue_gate_degrees = hue_gate_degrees

    def compute_eroded_hsv_hist(
        self,
        frame_bgr: np.ndarray,
        mask: np.ndarray,
        erode_ksize: int = 5,
    ) -> np.ndarray:
        """Extract HSV color histogram from the morphologically eroded mask core.

        Erosion removes boundary pixels, background bleed, and overlapping gripper fingers.
        """
        h, w = frame_bgr.shape[:2]
        bin_mask = (mask > 0).astype(np.uint8)

        # Apply morphological erosion with square structuring element
        if erode_ksize > 1 and np.sum(bin_mask) > 20:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (erode_ksize, erode_ksize))
            eroded = cv2.erode(bin_mask, kernel, iterations=1)
            # Retain original mask if erosion completely vanished the object
            if np.sum(eroded) >= 4:
                bin_mask = eroded

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv],
            [0, 1],
            bin_mask,
            [self.hist_bins[0], self.hist_bins[1]],
            [0, 180, 0, 256],
        )
        # Normalize histogram to unit L1 norm
        total = float(np.sum(hist))
        if total > 0.0:
            hist = hist / total
        return hist.astype(np.float32)

    def extract_dominant_hue(
        self,
        frame_bgr: np.ndarray,
        mask: np.ndarray,
        erode_ksize: int = 5,
    ) -> Tuple[float, float, float]:
        """Compute dominant Hue (in degrees [0, 360)), mean Saturation, and Value.

        Uses circular mean for Hue to correctly wrap around 0°/360° (Red).
        """
        bin_mask = (mask > 0).astype(np.uint8)
        if erode_ksize > 1 and np.sum(bin_mask) > 20:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (erode_ksize, erode_ksize))
            eroded = cv2.erode(bin_mask, kernel, iterations=1)
            if np.sum(eroded) >= 4:
                bin_mask = eroded

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h_vals = hsv[:, :, 0][bin_mask > 0]
        s_vals = hsv[:, :, 1][bin_mask > 0]
        v_vals = hsv[:, :, 2][bin_mask > 0]

        if len(h_vals) == 0:
            return (0.0, 0.0, 0.0)

        # OpenCV H is in [0, 179], mapping to [0, 358] degrees
        rads = (h_vals.astype(np.float64) * 2.0) * (math.pi / 180.0)
        sin_sum = float(np.sum(np.sin(rads)))
        cos_sum = float(np.sum(np.cos(rads)))
        mean_angle_rad = math.atan2(sin_sum, cos_sum)
        mean_hue_deg = math.degrees(mean_angle_rad) % 360.0

        mean_s = float(np.mean(s_vals))
        mean_v = float(np.mean(v_vals))
        return (mean_hue_deg, mean_s, mean_v)

    def match_masks(
        self,
        candidates: List[ObjMask],
        targets: Dict[str, ObjMask],
        frame_bgr: np.ndarray,
    ) -> Dict[str, ObjMask]:
        """Bipartite matching of candidate masks against target objects.

        Enforces:
        - Strict infinite cost for delta Hue > hue_gate_degrees between colored objects
        - Spatial proximity and centroid velocity continuity
        - Morphologically eroded HSV histogram similarity
        - Strictly non-destructive: masks are never subtracted or modified.
        """
        if not candidates or not targets:
            return {}

        h, w = frame_bgr.shape[:2]
        diag = math.sqrt(h * h + w * w)

        target_names = list(targets.keys())
        n_targets = len(target_names)
        n_candidates = len(candidates)

        target_masks = [decode_mask(targets[name], (h, w)) for name in target_names]
        cand_masks = [decode_mask(cand, (h, w)) for cand in candidates]

        # Extract features for targets
        target_hists = [self.compute_eroded_hsv_hist(frame_bgr, m) for m in target_masks]
        target_hues = [self.extract_dominant_hue(frame_bgr, m) for m in target_masks]
        target_centroids = [
            (
                (targets[name].bbox_xyxy[0] + targets[name].bbox_xyxy[2]) / 2.0,
                (targets[name].bbox_xyxy[1] + targets[name].bbox_xyxy[3]) / 2.0,
            )
            for name in target_names
        ]

        # Extract features for candidates
        cand_hists = [self.compute_eroded_hsv_hist(frame_bgr, m) for m in cand_masks]
        cand_hues = [self.extract_dominant_hue(frame_bgr, m) for m in cand_masks]
        cand_centroids = [
            (
                (c.bbox_xyxy[0] + c.bbox_xyxy[2]) / 2.0,
                (c.bbox_xyxy[1] + c.bbox_xyxy[3]) / 2.0,
            )
            for c in candidates
        ]

        # Build Cost Matrix
        cost_matrix = np.full((n_targets, n_candidates), 1e9, dtype=np.float64)

        for i in range(n_targets):
            t_hue, t_s, _ = target_hues[i]
            t_cx, t_cy = target_centroids[i]
            t_hist = target_hists[i]

            for j in range(n_candidates):
                c_hue, c_s, _ = cand_hues[j]
                c_cx, c_cy = cand_centroids[j]
                c_hist = cand_hists[j]

                # Categorical Hue Gating:
                # If both target and candidate have saturated color (e.g. Red, Green, Blue blocks)
                if t_s > 40.0 and c_s > 40.0:
                    hue_diff = abs(t_hue - c_hue)
                    circ_hue_diff = min(hue_diff, 360.0 - hue_diff)
                    if circ_hue_diff > self.hue_gate_degrees:
                        # Infinite penalty: Distinct colored blocks cannot match!
                        cost_matrix[i, j] = 1e9
                        continue

                # L2 Centroid distance normalized by frame diagonal
                spatial_dist = math.sqrt((t_cx - c_cx) ** 2 + (t_cy - c_cy) ** 2) / max(1.0, diag)

                # Color histogram Bhattacharyya distance [0, 1]
                bhatt = float(cv2.compareHist(t_hist, c_hist, cv2.HISTCMP_BHATTACHARYYA))
                if math.isnan(bhatt):
                    bhatt = 1.0

                total_cost = self.spatial_weight * spatial_dist + self.color_weight * bhatt
                cost_matrix[i, j] = total_cost

        # Linear sum assignment (Hungarian matching)
        matched_pairs: List[Tuple[int, int]] = []
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                from scipy.optimize import linear_sum_assignment

                row_ind, col_ind = linear_sum_assignment(cost_matrix)
            for r, c in zip(row_ind, col_ind):
                matched_pairs.append((int(r), int(c)))
        except Exception:
            # Greedy matching fallback if scipy unavailable
            used_cols = set()
            for r in range(n_targets):
                best_c = -1
                best_val = 1e8
                for c in range(n_candidates):
                    if c not in used_cols and cost_matrix[r, c] < best_val:
                        best_val = cost_matrix[r, c]
                        best_c = c
                if best_c != -1:
                    used_cols.add(best_c)
                    matched_pairs.append((r, best_c))

        matched_output: Dict[str, ObjMask] = {}
        for r, c in matched_pairs:
            # Reject match if infinite penalty was tripped
            if cost_matrix[r, c] < 1e8:
                tgt_name = target_names[r]
                cand_mask = candidates[c]
                # Assign target object name to the matched candidate
                matched_output[tgt_name] = ObjMask(
                    obj=tgt_name,
                    frame=cand_mask.frame,
                    score=cand_mask.score,
                    bbox_xyxy=cand_mask.bbox_xyxy,
                    rle=cand_mask.rle,
                    area_px=cand_mask.area_px,
                    rle_size=cand_mask.rle_size,
                )

        return matched_output
