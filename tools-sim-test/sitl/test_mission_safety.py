from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi-companion" / "src"))

from pi_companion.mission_orchestrator import MissionOrchestrator, MissionState
from pi_companion.models import FlightMode, FlightTelemetry, ProjectedTarget, SensorFreshness
from pi_companion.safety_supervisor import InhibitReason, SafetySupervisor


def _telemetry(**overrides) -> FlightTelemetry:
    baseline = {
        "timestamp_ms": 1,
        "lat": 22.5,
        "lon": 88.3,
        "alt_m": 40.0,
        "yaw_deg": 90.0,
        "battery_pct": 80.0,
        "gps_valid": True,
        "mode": FlightMode.AUTO,
        "geofence_breach": False,
        "fc_heartbeat_age_ms": 100,
    }
    baseline.update(overrides)
    return FlightTelemetry(**baseline)


def _freshness(**overrides) -> SensorFreshness:
    baseline = {
        "camera_age_ms": 50,
        "depth_age_ms": 50,
    }
    baseline.update(overrides)
    return SensorFreshness(**baseline)


def test_low_battery_inhibits_spray() -> None:
    supervisor = SafetySupervisor()
    orchestrator = MissionOrchestrator(supervisor)

    orchestrator.load_mission()
    orchestrator.set_preflight_ok(True)
    orchestrator.request_auto_start()

    target = ProjectedTarget(
        detection_id="d1", lat=22.5, lon=88.3, confidence=0.9, age_frames=3
    )

    output = orchestrator.tick(
        telemetry=_telemetry(battery_pct=20.0),
        sensor_freshness=_freshness(),
        targets=[target],
        arduino_heartbeat_age_ms=100,
        manual_override=False,
    )

    assert output.state == MissionState.FAILSAFE
    assert output.request_rtl is True
    assert InhibitReason.BATTERY_LOW_RESERVE.value in output.safety.reasons


def test_manual_override_forces_failsafe() -> None:
    supervisor = SafetySupervisor()
    orchestrator = MissionOrchestrator(supervisor)

    orchestrator.load_mission()
    orchestrator.set_preflight_ok(True)
    orchestrator.request_auto_start()

    output = orchestrator.tick(
        telemetry=_telemetry(),
        sensor_freshness=_freshness(),
        targets=[],
        arduino_heartbeat_age_ms=100,
        manual_override=True,
    )

    assert output.state == MissionState.FAILSAFE
    assert output.request_rtl is True
    assert InhibitReason.MANUAL_OVERRIDE.value in output.safety.reasons


def test_nominal_path_emits_spray_command() -> None:
    supervisor = SafetySupervisor()
    orchestrator = MissionOrchestrator(supervisor)

    orchestrator.load_mission()
    orchestrator.set_preflight_ok(True)
    orchestrator.request_auto_start()

    target = ProjectedTarget(
        detection_id="d1", lat=22.5001, lon=88.3001, confidence=0.92, age_frames=4
    )

    output = orchestrator.tick(
        telemetry=_telemetry(),
        sensor_freshness=_freshness(),
        targets=[target],
        arduino_heartbeat_age_ms=100,
        manual_override=False,
    )

    assert output.state == MissionState.AUTO_SCAN
    assert output.safety.allow_spray is True
    assert output.spray_command is not None
    assert output.spray_command.target.detection_id == "d1"
