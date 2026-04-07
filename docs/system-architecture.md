# System Architecture

## High-Level Boundaries
- Flight Controller (ArduPilot): stabilization, navigation, vehicle-level failsafes
- Raspberry Pi 5: mission state machine, perception, spray permission logic, telemetry aggregation
- Arduino: pump and valve actuation based on authenticated commands from Pi

## Data Flow
1. Flight controller streams telemetry to Pi over MAVLink.
2. Pi ingests camera and depth streams, computes detections, and evaluates spray permission.
3. Pi sends spray commands to Arduino only when safety supervisor allows.
4. Arduino executes pulse/PWM commands and returns heartbeat + fault status.
5. Pi forwards mission telemetry and spray events to offline ground station.

## Control Loop Cadence
- Telemetry ingest: 10 Hz
- Perception detect output: 5 to 10 Hz
- Safety evaluation: each control tick (10 Hz)
- Arduino heartbeat expectation: every 200 ms

## Safety Model
Spray command emission is centralized in the Pi safety supervisor. No module may bypass this gate.

## MVP Constraints
- Offline-first operation; no cloud required for core mission behavior
- Classical computer vision first, deep learning deferred to phase 2
- Outdoor tests only after SITL and HIL gates pass
