from __future__ import annotations

import time

import numpy as np

from pi_companion.io.mavlink_client import MavlinkClient
from pi_companion.mission_orchestrator import MissionOrchestrator, OrchestratorConfig
from pi_companion.perception.capture_pipeline import CapturePipeline
from pi_companion.perception.detector_classical import ClassicalDetector
from pi_companion.perception.geotag_projection import GeotagProjector
from pi_companion.safety_supervisor import SafetySupervisor


def run_demo() -> None:
    mavlink = MavlinkClient()
    capture = CapturePipeline()
    detector = ClassicalDetector()
    projector = GeotagProjector()
    safety = SafetySupervisor()
    orchestrator = MissionOrchestrator(
        safety,
        OrchestratorConfig(detection_confidence_min=0.5, detection_min_age_frames=1),
    )

    orchestrator.load_mission()
    orchestrator.set_preflight_ok(True)
    orchestrator.request_auto_start()

    now_ms = _now_ms()
    mavlink.ingest_message({"type": "HEARTBEAT", "mode": "AUTO"})
    mavlink.ingest_message(
        {
            "type": "GLOBAL_POSITION_INT",
            "lat": 22.5726,
            "lon": 88.3639,
            "alt_m": 40.0,
        }
    )
    mavlink.ingest_message({"type": "GPS_RAW_INT", "gps_valid": True})
    mavlink.ingest_message({"type": "ATTITUDE", "yaw_deg": 95.0})
    mavlink.ingest_message({"type": "BATTERY_STATUS", "battery_pct": 82.0})

    for _ in range(6):
        frame = _build_mock_frame()
        depth = np.full((240, 320), 4.0, dtype=np.float32)
        capture.ingest_rgb(frame, now_ms)
        capture.ingest_depth(depth, now_ms)

        bundle = capture.latest_bundle()
        assert bundle is not None

        detections = detector.detect(bundle)
        telemetry = mavlink.get_telemetry()
        targets = [
            projector.project(detection, telemetry, frame_width=320, frame_height=240)
            for detection in detections
        ]

        output = orchestrator.tick(
            telemetry=telemetry,
            sensor_freshness=capture.sensor_freshness(now_ms),
            targets=targets,
            arduino_heartbeat_age_ms=100,
            manual_override=False,
            control_latency_ms=90,
            cpu_temp_c=59.0,
            dropped_frame_rate=0.01,
        )

        spray = "YES" if output.spray_command is not None else "NO"
        print(
            f"state={output.state.value} allow={output.safety.allow_spray} "
            f"spray={spray} reasons={output.safety.reasons}"
        )

        now_ms += 100
        time.sleep(0.02)


def _build_mock_frame() -> np.ndarray:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:, :, 1] = 140
    frame[:, :, 0] = 60

    # Synthetic stressed patch for detection testing.
    frame[90:130, 130:170, 0] = 110
    frame[90:130, 130:170, 1] = 180
    return frame


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    run_demo()
