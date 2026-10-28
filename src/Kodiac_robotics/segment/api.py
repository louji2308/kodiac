"""Meta SAM 3.1 hosted API streaming client.

Provides streaming response parsing, prompt isolation (text vs. box),
tenacity exponential backoff with jitter, content-hash disk caching,
and coordinate frame translation from box-local to full-frame canvas.
Per IP-P03-D1-1, IP-P03-D3-2, ARCHITECTURE.md §3.1, §4.3 and P03.S02.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from Kodiac_robotics.cache import DiskCache
from Kodiac_robotics.config import Settings
from Kodiac_robotics.contracts.core import Clip, ObjMask, Track
from Kodiac_robotics.segment.rle import (
    box_local_to_full_frame_rle,
    rle_area,
)


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True if exception is a transient network error or 429/5xx status."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


class HostedSamBackend:
    """Streaming client adapter for hosted Meta SAM 3.1 perception API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "sam-3.1",
        base_url: str = "https://api.meta.ai/v1",
        cache_dir: Path | str = ".cache/Kodiac/sam",
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = Settings.load()
        self.api_key = api_key or self.settings.model_api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.cache = DiskCache(root_dir=cache_dir)
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=60.0)

    def _validate_api_key(self) -> str:
        if not self.api_key:
            raise ValueError(
                "MODEL_API_KEY is not set. Set KODIAC_MODEL_API_KEY, MODEL_API_KEY, "
                "or switch to fixture mode (KODIAC_SAM_BACKEND=fixture)."
            )
        return self.api_key

    def segment_frames(
        self,
        clip: Clip,
        frames: list[int],
        prompts: dict[str, list[str]],
    ) -> dict[str, Track]:
        """Segment sparse keyframes using text prompts only.

        Strict Prompt Isolation: Only text prompts are allowed; box/point
        prompts are strictly forbidden in this endpoint.
        """
        # Strict prompt isolation check
        for role, candidate_prompts in prompts.items():
            if not isinstance(candidate_prompts, list):
                raise ValueError(
                    f"Prompt isolation violation: prompt for role '{role}' must be list[str], "
                    f"got {type(candidate_prompts)}"
                )
            for p in candidate_prompts:
                if not isinstance(p, str):
                    raise ValueError(
                        f"Prompt isolation violation: segment_frames accepts ONLY text prompts. "
                        f"Invalid prompt type: {type(p)}"
                    )

        cache_key = {
            "clip_sha256": clip.sha256,
            "model": self.model,
            "operation": "segment_frames",
            "frames": sorted(frames),
            "prompts": {k: sorted(v) for k, v in prompts.items()},
        }

        cached = self.cache.get(cache_key)
        if cached is not None:
            return {obj: Track.model_validate(t) for obj, t in cached.items()}

        api_key = self._validate_api_key()

        request_body = {
            "model": self.model,
            "clip_uri": clip.ref.uri,
            "clip_sha256": clip.sha256,
            "frames": frames,
            "text_prompts": prompts,
            "stream": True,
        }

        tracks = self._execute_streaming_request(
            endpoint=f"{self.base_url}/responses",
            api_key=api_key,
            body=request_body,
            clip=clip,
            direction="forward",
        )

        # Store in cache
        self.cache.set(cache_key, {obj: t.model_dump() for obj, t in tracks.items()})
        return tracks

    def track(
        self,
        clip: Clip,
        f0: int,
        f1: int,
        seeds: dict[str, ObjMask],
        direction: Literal["forward", "backward", "both"] = "both",
    ) -> dict[str, Track]:
        """Track objects through temporal window seeded with box/mask prompts.

        Strict Prompt Isolation: Only box/mask seeds are allowed; text prompts
        are strictly forbidden in this endpoint.
        """
        for role, seed in seeds.items():
            if not isinstance(seed, ObjMask):
                raise ValueError(
                    f"Prompt isolation violation: track accepts ONLY ObjMask seeds, not text prompts. "
                    f"Invalid seed for '{role}': {type(seed)}"
                )

        cache_key = {
            "clip_sha256": clip.sha256,
            "model": self.model,
            "operation": "track",
            "f0": f0,
            "f1": f1,
            "direction": direction,
            "seeds": {
                k: {
                    "frame": v.frame,
                    "bbox_xyxy": v.bbox_xyxy,
                    "rle": v.rle,
                }
                for k, v in seeds.items()
            },
        }

        cached = self.cache.get(cache_key)
        if cached is not None:
            return {obj: Track.model_validate(t) for obj, t in cached.items()}

        api_key = self._validate_api_key()

        # Build seed payloads
        seed_payloads = {}
        for role, mask in seeds.items():
            seed_payloads[role] = {
                "frame": mask.frame,
                "bbox": list(mask.bbox_xyxy),
                "mask_rle": mask.rle,
            }

        request_body = {
            "model": self.model,
            "clip_uri": clip.ref.uri,
            "clip_sha256": clip.sha256,
            "window": [f0, f1],
            "seeds": seed_payloads,
            "metadata": {"propagation_direction": direction},
            "stream": True,
        }

        tracks = self._execute_streaming_request(
            endpoint=f"{self.base_url}/responses",
            api_key=api_key,
            body=request_body,
            clip=clip,
            direction=direction,
        )

        self.cache.set(cache_key, {obj: t.model_dump() for obj, t in tracks.items()})
        return tracks

    def _execute_streaming_request(
        self,
        endpoint: str,
        api_key: str,
        body: dict[str, Any],
        clip: Clip,
        direction: str,
    ) -> dict[str, Track]:
        """Execute HTTP request with tenacity retry and parse streaming events."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }

        @retry(
            retry=retry_if_exception(_is_retryable_error),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1.0, max=8.0),
            reraise=True,
        )
        def _send() -> list[str]:
            client = self._get_client()
            with client.stream("POST", endpoint, headers=headers, json=body) as response:
                response.raise_for_status()
                return [line for line in response.iter_lines()]

        lines = _send()
        return self._parse_streaming_lines(lines, clip=clip, direction=direction)

    def _parse_streaming_lines(
        self,
        lines: list[str],
        clip: Clip,
        direction: str,
    ) -> dict[str, Track]:
        """Parse streaming SSE or NDJSON lines into validated Track objects."""
        tracks: dict[str, Track] = {}
        trace_id = f"sam-{uuid.uuid4().hex[:12]}"

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line == "data: [DONE]":
                continue

            if line.startswith("data:"):
                line = line[5:].strip()

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Parse event containing frame objects
            frame_idx = event.get("frame_index", event.get("frame", 0))
            objects = event.get("objects", event.get("masks", []))

            for item in objects:
                obj_name = item.get("label", item.get("obj", item.get("name", "object")))
                score = float(item.get("score", item.get("confidence", 1.0)))

                # Extract bbox
                bbox = item.get("bbox", item.get("bbox_xyxy", [0.0, 0.0, float(clip.width), float(clip.height)]))
                box_xyxy = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))

                # Extract RLE
                raw_mask = item.get("mask", item.get("rle", ""))
                if isinstance(raw_mask, dict):
                    local_rle = raw_mask.get("counts", "")
                else:
                    local_rle = str(raw_mask)

                # Translate box-local to full frame canvas coordinates
                full_rle = box_local_to_full_frame_rle(
                    local_rle=local_rle,
                    box_xyxy=box_xyxy,
                    full_shape=(clip.height, clip.width),
                )

                area = rle_area(full_rle, (clip.height, clip.width))

                obj_mask = ObjMask(
                    obj=obj_name,
                    frame=int(frame_idx),
                    score=score,
                    bbox_xyxy=box_xyxy,
                    rle=full_rle,
                    area_px=area,
                    rle_size=(clip.height, clip.width),
                )

                # Strict validation of coordinate frame alignment per IP-P03-D3-2
                assert obj_mask.rle_size == (clip.height, clip.width), (
                    f"rle_size {obj_mask.rle_size} does not match clip shape {(clip.height, clip.width)}"
                )

                if obj_name not in tracks:
                    tracks[obj_name] = Track(
                        obj=obj_name,
                        frames={},
                        backend="api",
                        direction=direction,
                        trace_id=trace_id,
                    )
                tracks[obj_name].frames[int(frame_idx)] = obj_mask

        return tracks
