from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pi_companion.models import SafetyDecision, SafetyInputs


class InhibitReason(str, Enum):
    MODE_NOT_AUTO = "mode_not_auto"
    MANUAL_OVERRIDE = "manual_override"
    GEOFENCE_BREACH = "geofence_breach"
    BATTERY_LOW_RESERVE = "battery_low_reserve"
    GPS_INVALID = "gps_invalid"
    DEPTH_STALE = "depth_stale"
    CAMERA_STALE = "camera_stale"
    FC_LINK_LOST = "fc_link_lost"
    ARDUINO_LINK_LOST = "arduino_link_lost"
    MISSION_NOT_ARMED = "mission_not_armed"


class SoftWarning(str, Enum):
    HIGH_LATENCY = "high_latency"
    HIGH_CPU_TEMP = "high_cpu_temp"
    DROPPED_FRAMES = "dropped_frames"


@dataclass(slots=True)
class SafetyPolicy:
    battery_reserve_pct: float = 25.0
    max_depth_age_ms: int = 250
    max_camera_age_ms: int = 250
    max_fc_heartbeat_age_ms: int = 2000
    max_arduino_heartbeat_age_ms: int = 1000
    max_control_latency_ms: int = 200
    max_cpu_temp_c: float = 75.0
    max_dropped_frame_rate: float = 0.05


class SafetySupervisor:
    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def evaluate(self, inputs: SafetyInputs) -> SafetyDecision:
        reasons: list[str] = []
        warnings: list[str] = []

        if inputs.telemetry.mode.value != "AUTO":
            reasons.append(InhibitReason.MODE_NOT_AUTO.value)
        if inputs.manual_override:
            reasons.append(InhibitReason.MANUAL_OVERRIDE.value)
        if inputs.telemetry.geofence_breach:
            reasons.append(InhibitReason.GEOFENCE_BREACH.value)
        if inputs.telemetry.battery_pct <= self.policy.battery_reserve_pct:
            reasons.append(InhibitReason.BATTERY_LOW_RESERVE.value)
        if not inputs.telemetry.gps_valid:
            reasons.append(InhibitReason.GPS_INVALID.value)
        if inputs.sensor_freshness.depth_age_ms > self.policy.max_depth_age_ms:
            reasons.append(InhibitReason.DEPTH_STALE.value)
        if inputs.sensor_freshness.camera_age_ms > self.policy.max_camera_age_ms:
            reasons.append(InhibitReason.CAMERA_STALE.value)
        if inputs.telemetry.fc_heartbeat_age_ms > self.policy.max_fc_heartbeat_age_ms:
            reasons.append(InhibitReason.FC_LINK_LOST.value)
        if inputs.arduino_heartbeat_age_ms > self.policy.max_arduino_heartbeat_age_ms:
            reasons.append(InhibitReason.ARDUINO_LINK_LOST.value)
        if not inputs.mission_armed:
            reasons.append(InhibitReason.MISSION_NOT_ARMED.value)

        if (
            inputs.control_latency_ms is not None
            and inputs.control_latency_ms > self.policy.max_control_latency_ms
        ):
            warnings.append(SoftWarning.HIGH_LATENCY.value)
        if inputs.cpu_temp_c is not None and inputs.cpu_temp_c > self.policy.max_cpu_temp_c:
            warnings.append(SoftWarning.HIGH_CPU_TEMP.value)
        if (
            inputs.dropped_frame_rate is not None
            and inputs.dropped_frame_rate > self.policy.max_dropped_frame_rate
        ):
            warnings.append(SoftWarning.DROPPED_FRAMES.value)

        return SafetyDecision(allow_spray=len(reasons) == 0, reasons=reasons, warnings=warnings)
