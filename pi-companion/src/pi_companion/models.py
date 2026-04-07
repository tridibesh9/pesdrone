from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FlightMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    RTL = "RTL"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class FlightTelemetry:
    timestamp_ms: int
    lat: float
    lon: float
    alt_m: float
    yaw_deg: float
    battery_pct: float
    gps_valid: bool
    mode: FlightMode
    geofence_breach: bool
    fc_heartbeat_age_ms: int


@dataclass(slots=True)
class SensorFreshness:
    camera_age_ms: int
    depth_age_ms: int


@dataclass(slots=True)
class Detection:
    detection_id: str
    frame_id: int
    pixel_x: int
    pixel_y: int
    confidence: float
    severity: str
    age_frames: int


@dataclass(slots=True)
class ProjectedTarget:
    detection_id: str
    lat: float
    lon: float
    confidence: float
    age_frames: int


@dataclass(slots=True)
class SprayCommand:
    duration_ms: int
    pump_pwm: int
    target: ProjectedTarget


@dataclass(slots=True)
class SafetyInputs:
    telemetry: FlightTelemetry
    sensor_freshness: SensorFreshness
    mission_armed: bool
    manual_override: bool
    arduino_heartbeat_age_ms: int
    control_latency_ms: int | None = None
    cpu_temp_c: float | None = None
    dropped_frame_rate: float | None = None


@dataclass(slots=True)
class SafetyDecision:
    allow_spray: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FrameBundle:
    frame_id: int
    timestamp_ms: int
    rgb: Any
    depth: Any | None
