from __future__ import annotations

import math
from dataclasses import dataclass

from pi_companion.models import Detection, FlightTelemetry, ProjectedTarget


@dataclass(slots=True)
class ProjectionConfig:
    ground_sample_m_per_px: float = 0.05


class GeotagProjector:
    def __init__(self, config: ProjectionConfig | None = None) -> None:
        self.config = config or ProjectionConfig()

    def project(
        self,
        detection: Detection,
        telemetry: FlightTelemetry,
        frame_width: int,
        frame_height: int,
    ) -> ProjectedTarget:
        dx_px = detection.pixel_x - (frame_width / 2.0)
        dy_px = detection.pixel_y - (frame_height / 2.0)

        forward_m = -dy_px * self.config.ground_sample_m_per_px
        right_m = dx_px * self.config.ground_sample_m_per_px

        yaw_rad = math.radians(telemetry.yaw_deg)
        north_m = (forward_m * math.cos(yaw_rad)) - (right_m * math.sin(yaw_rad))
        east_m = (forward_m * math.sin(yaw_rad)) + (right_m * math.cos(yaw_rad))

        lat_scale = 111_320.0
        lon_scale = lat_scale * max(math.cos(math.radians(telemetry.lat)), 1e-6)

        target_lat = telemetry.lat + (north_m / lat_scale)
        target_lon = telemetry.lon + (east_m / lon_scale)

        return ProjectedTarget(
            detection_id=detection.detection_id,
            lat=target_lat,
            lon=target_lon,
            confidence=detection.confidence,
            age_frames=detection.age_frames,
        )
