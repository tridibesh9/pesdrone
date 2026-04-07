from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pi_companion.models import (
    FlightTelemetry,
    ProjectedTarget,
    SafetyInputs,
    SafetyDecision,
    SensorFreshness,
    SprayCommand,
)
from pi_companion.safety_supervisor import SafetySupervisor


class MissionState(str, Enum):
    IDLE = "IDLE"
    PREFLIGHT_CHECKS = "PREFLIGHT_CHECKS"
    ARMED = "ARMED"
    AUTO_SCAN = "AUTO_SCAN"
    TARGET_CONFIRMED = "TARGET_CONFIRMED"
    SPRAY_WINDOW = "SPRAY_WINDOW"
    RTH = "RTH"
    FAILSAFE = "FAILSAFE"
    LANDED = "LANDED"


@dataclass(slots=True)
class OrchestratorConfig:
    detection_confidence_min: float = 0.65
    detection_min_age_frames: int = 2
    spray_pulse_ms: int = 120
    spray_pwm: int = 200


@dataclass(slots=True)
class OrchestratorOutput:
    state: MissionState
    safety: SafetyDecision
    spray_command: SprayCommand | None
    selected_target: ProjectedTarget | None
    request_rtl: bool


class MissionOrchestrator:
    def __init__(
        self,
        safety_supervisor: SafetySupervisor,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self.safety_supervisor = safety_supervisor
        self.config = config or OrchestratorConfig()
        self.state = MissionState.IDLE
        self._mission_loaded = False
        self._preflight_ok = False
        self._auto_requested = False
        self._target: ProjectedTarget | None = None

    def load_mission(self) -> None:
        self._mission_loaded = True

    def set_preflight_ok(self, value: bool) -> None:
        self._preflight_ok = value

    def request_auto_start(self) -> None:
        self._auto_requested = True

    def tick(
        self,
        telemetry: FlightTelemetry,
        sensor_freshness: SensorFreshness,
        targets: list[ProjectedTarget],
        arduino_heartbeat_age_ms: int,
        manual_override: bool,
        control_latency_ms: int | None = None,
        cpu_temp_c: float | None = None,
        dropped_frame_rate: float | None = None,
    ) -> OrchestratorOutput:
        self._advance_state_pre_detection(telemetry, manual_override)

        mission_armed = self.state in {
            MissionState.AUTO_SCAN,
            MissionState.TARGET_CONFIRMED,
            MissionState.SPRAY_WINDOW,
        }
        safety = self.safety_supervisor.evaluate(
            SafetyInputs(
                telemetry=telemetry,
                sensor_freshness=sensor_freshness,
                mission_armed=mission_armed,
                manual_override=manual_override,
                arduino_heartbeat_age_ms=arduino_heartbeat_age_ms,
                control_latency_ms=control_latency_ms,
                cpu_temp_c=cpu_temp_c,
                dropped_frame_rate=dropped_frame_rate,
            )
        )

        request_rtl = False
        spray_command: SprayCommand | None = None

        if self._has_critical_fault(safety.reasons):
            self.state = MissionState.FAILSAFE
            request_rtl = True
            return OrchestratorOutput(
                state=self.state,
                safety=safety,
                spray_command=None,
                selected_target=None,
                request_rtl=request_rtl,
            )

        if self.state == MissionState.AUTO_SCAN:
            candidate = self._select_target(targets)
            if candidate is not None:
                self._target = candidate
                self.state = MissionState.TARGET_CONFIRMED

        if self.state == MissionState.TARGET_CONFIRMED:
            self.state = MissionState.SPRAY_WINDOW

        if self.state == MissionState.SPRAY_WINDOW:
            if safety.allow_spray and self._target is not None:
                spray_command = SprayCommand(
                    duration_ms=self.config.spray_pulse_ms,
                    pump_pwm=self.config.spray_pwm,
                    target=self._target,
                )
            self._target = None
            self.state = MissionState.AUTO_SCAN

        if self.state == MissionState.FAILSAFE:
            request_rtl = True
            if telemetry.mode.value == "RTL":
                self.state = MissionState.RTH

        return OrchestratorOutput(
            state=self.state,
            safety=safety,
            spray_command=spray_command,
            selected_target=self._target,
            request_rtl=request_rtl,
        )

    def _advance_state_pre_detection(
        self,
        telemetry: FlightTelemetry,
        manual_override: bool,
    ) -> None:
        if manual_override:
            self.state = MissionState.FAILSAFE
            return

        if self.state == MissionState.IDLE and self._mission_loaded:
            self.state = MissionState.PREFLIGHT_CHECKS

        if self.state == MissionState.PREFLIGHT_CHECKS and self._preflight_ok:
            self.state = MissionState.ARMED

        if (
            self.state == MissionState.ARMED
            and self._auto_requested
            and telemetry.mode.value == "AUTO"
        ):
            self.state = MissionState.AUTO_SCAN

    def _select_target(self, targets: list[ProjectedTarget]) -> ProjectedTarget | None:
        eligible = [
            target
            for target in targets
            if target.confidence >= self.config.detection_confidence_min
            and target.age_frames >= self.config.detection_min_age_frames
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda target: target.confidence)

    @staticmethod
    def _has_critical_fault(reasons: list[str]) -> bool:
        critical = {
            "manual_override",
            "geofence_breach",
            "battery_low_reserve",
            "gps_invalid",
            "fc_link_lost",
            "arduino_link_lost",
        }
        return any(reason in critical for reason in reasons)
