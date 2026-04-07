from __future__ import annotations

import time
from dataclasses import dataclass

from pi_companion.models import FrameBundle, SensorFreshness


@dataclass(slots=True)
class CaptureState:
    frame_counter: int = 0
    rgb_timestamp_ms: int = 0
    depth_timestamp_ms: int = 0


class CapturePipeline:
    def __init__(self) -> None:
        self._state = CaptureState()
        self._latest_rgb = None
        self._latest_depth = None

    def ingest_rgb(self, rgb_frame, timestamp_ms: int | None = None) -> None:
        self._state.frame_counter += 1
        self._latest_rgb = rgb_frame
        self._state.rgb_timestamp_ms = timestamp_ms or _now_ms()

    def ingest_depth(self, depth_frame, timestamp_ms: int | None = None) -> None:
        self._latest_depth = depth_frame
        self._state.depth_timestamp_ms = timestamp_ms or _now_ms()

    def latest_bundle(self) -> FrameBundle | None:
        if self._latest_rgb is None:
            return None
        return FrameBundle(
            frame_id=self._state.frame_counter,
            timestamp_ms=self._state.rgb_timestamp_ms,
            rgb=self._latest_rgb,
            depth=self._latest_depth,
        )

    def sensor_freshness(self, now_ms: int | None = None) -> SensorFreshness:
        reference_ms = now_ms or _now_ms()
        camera_age_ms = (
            reference_ms - self._state.rgb_timestamp_ms
            if self._state.rgb_timestamp_ms > 0
            else 1_000_000
        )
        depth_age_ms = (
            reference_ms - self._state.depth_timestamp_ms
            if self._state.depth_timestamp_ms > 0
            else 1_000_000
        )
        return SensorFreshness(camera_age_ms=camera_age_ms, depth_age_ms=depth_age_ms)


def _now_ms() -> int:
    return int(time.time() * 1000)
