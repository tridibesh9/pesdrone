# FTL-2 Key Findings and Implementation Report

Date: 2026-04-07
Repository: FTL-2

## 1. Purpose
This report summarizes the key technical findings from the current repository and explains:
- how the project is designed to detect and spray in mission flow,
- how detection is performed,
- how spray actuation is performed,
- what fallback and fail-safe behavior exists,
- which parameters can be tuned.

It also calls out what is already implemented versus what is still integration work.

## 2. Executive Summary
The project has a strong safety-first architecture with clear responsibility boundaries:
- ArduPilot handles flight stability, navigation, and base aircraft failsafes.
- Raspberry Pi companion handles mission logic, perception, spray permission, and supervision.
- Arduino handles only actuation with strict parser and watchdog behavior.
- Ground station is offline-first for telemetry, spray events, and operator emergency commands.

Key takeaway:
- The detect-to-spray decision pipeline is implemented in software logic and guarded by a centralized safety gate.
- Multi-layer fallback exists at mission layer, communication layer, and actuator layer.
- Current code still needs one important runtime integration step: when the mission orchestrator creates a spray command, the active runtime loop must send that command to Arduino in production path.

## 3. System Boundaries and Responsibilities

| Subsystem | Primary Role | How It Is Implemented |
|---|---|---|
| Flight Controller (ArduPilot) | Navigation, stabilization, core flight failsafes | MAVLink telemetry is ingested by the Pi companion; Pi can request mode changes such as RTL |
| Raspberry Pi Companion | Mission FSM, perception, geotag projection, safety permission for spray | MissionOrchestrator + SafetySupervisor + perception modules |
| Arduino Pump Controller | Pump and valve actuation only | Framed serial protocol, command parser, checksum validation, timeout and emergency stop behavior |
| Offline Ground Station | Local telemetry/spray logging and emergency command queue | FastAPI backend + Vite/TypeScript frontend |

## 4. How We Actually Do It End-to-End

### 4.1 Control Loop Intent
Designed loop cadence from docs:
- Telemetry ingest: 10 Hz
- Perception output: 5 to 10 Hz
- Safety evaluation: each control tick
- Arduino heartbeat expectation: every 200 ms

### 4.2 Mission-State Flow
Mission states are:
IDLE -> PREFLIGHT_CHECKS -> ARMED -> AUTO_SCAN -> TARGET_CONFIRMED -> SPRAY_WINDOW -> AUTO_SCAN (repeat)
with transitions to FAILSAFE and RTH when required.

Actual behavior in mission orchestrator:
1. Advance state based on mission load, preflight pass, AUTO request, and flight mode.
2. Evaluate safety for this tick using latest telemetry and sensor freshness.
3. If critical fault reason exists, force FAILSAFE and request RTL.
4. In AUTO_SCAN, choose eligible target by confidence and age.
5. In TARGET_CONFIRMED, enter SPRAY_WINDOW.
6. In SPRAY_WINDOW, emit spray command only if safety allows.
7. Clear target and return to AUTO_SCAN.

### 4.3 Detect and Spray in Same Go
Yes, logically this is how it is intended.
In one cycle, a valid target can be selected and a spray command can be produced if all guards pass.

Implementation status note:
- MissionOrchestrator already creates SprayCommand objects with duration and PWM.
- Demo runtime currently prints spray decision but does not yet wire the generated command to Arduino transport in the same loop.

## 5. Detection: How It Works
Detection is currently classical computer vision (phase-1 approach), not deep learning.

### 5.1 Processing Steps
1. Read RGB frame (and depth frame for freshness monitoring).
2. Convert RGB to normalized float channels.
3. Compute vegetation stress proxy index:
   GNDVI-style = (green - red) / (green + red + epsilon)
4. Build vegetation mask and stressed mask using threshold band.
5. Require minimum stressed pixel count.
6. Bin detections into grid cells and rank by stressed pixel count.
7. Convert top cells into detections with confidence, severity, and age in frames.
8. Project detection pixel coordinates into geolocation using aircraft yaw and local scale.

### 5.2 Why This Approach
- Deterministic and lightweight for early Pi deployment.
- Easier to debug and tune in controlled field trials.
- Enables staged safety validation before model-heavy phase-2 stack.

### 5.3 Detection Quality Controls
- Confidence threshold filter
- Minimum age in frames filter (suppresses one-frame noise)
- Maximum number of detections per frame
- Sensor freshness gates in safety supervisor

## 6. Spray: How It Works
Spray control is pulse-based and command-driven.

### 6.1 Pi-Side Spray Command
When safety allows in SPRAY_WINDOW, Pi produces command payload with:
- pulse duration in milliseconds
- pump PWM value
- projected target coordinates and confidence metadata

### 6.2 Pi-Arduino Protocol
Frame format:
START, CMD, LEN, PAYLOAD, CHECKSUM

Supported actuator commands:
- Set pump PWM
- Pulse spray for duration
- Valve on or off
- Heartbeat request
- Emergency stop

### 6.3 Arduino Actuation Behavior
- Parses framed commands
- Validates frame length and checksum
- For pulse spray command:
  - opens valve
  - starts pump (uses current PWM or default)
  - closes valve and pump when pulse timer ends
- Emits heartbeat status every 200 ms

## 7. Fallback and Fail-Safe Layers
Fallback is not a single mechanism; it is layered.

### 7.1 Mission and Safety Supervisor Layer (Pi)
Hard inhibit reasons block spray command emission immediately:
- mode not AUTO
- manual override active
- geofence breach
- battery below reserve
- GPS invalid
- stale depth
- stale camera
- FC heartbeat stale
- Arduino heartbeat stale
- mission not armed

Critical fault subset triggers FAILSAFE and RTL request.

### 7.2 Flight-Link Layer
If FC heartbeat becomes stale beyond timeout:
- spray must be inhibited,
- mission transitions to FAILSAFE,
- RTL request path is used when possible.

### 7.3 Arduino Hardware Layer
Arduino forces pump off when:
- parser/checksum errors occur,
- command heartbeat timeout occurs,
- emergency stop command is received.

### 7.4 Operator Layer (Ground Station)
Ground station can queue emergency spray disable commands locally.
This supports offline-first operator intervention.

## 8. Tunable Parameters

### 8.1 Mission Orchestrator Tunables
| Parameter | Default | Effect |
|---|---:|---|
| detection_confidence_min | 0.65 | Higher value reduces false positives but may miss weak targets |
| detection_min_age_frames | 2 | Higher value improves temporal stability but adds delay |
| spray_pulse_ms | 120 | Higher value increases delivered volume per event |
| spray_pwm | 200 | Higher value increases pump drive strength |

### 8.2 Safety Policy Tunables
| Parameter | Default | Effect |
|---|---:|---|
| battery_reserve_pct | 25.0 | Earlier spray inhibition as reserve protection increases |
| max_depth_age_ms | 250 | Tight freshness gate for depth validity |
| max_camera_age_ms | 250 | Tight freshness gate for vision validity |
| max_fc_heartbeat_age_ms | 2000 | FC link-loss sensitivity |
| max_arduino_heartbeat_age_ms | 1000 | Actuator link-loss sensitivity |
| max_control_latency_ms | 200 | Soft warning threshold for control loop lag |
| max_cpu_temp_c | 75.0 | Soft warning threshold for thermal stress |
| max_dropped_frame_rate | 0.05 | Soft warning threshold for perception reliability |

### 8.3 Detector Tunables
| Parameter | Default | Effect |
|---|---:|---|
| vegetation_threshold | 0.20 | Lower value accepts more vegetation regions |
| stress_upper_threshold | 0.35 | Controls stressed-vegetation band upper bound |
| min_pixels | 25 | Rejects tiny/noisy stressed regions |
| max_detections | 4 | Limits actuation candidates per frame |
| cell_size_px | 32 | Spatial aggregation granularity |

### 8.4 Projection Tunables
| Parameter | Default | Effect |
|---|---:|---|
| ground_sample_m_per_px | 0.05 | Pixel-to-ground conversion scale; directly affects geotag placement |

### 8.5 Arduino Timing Tunables
| Parameter | Default | Effect |
|---|---:|---|
| HEARTBEAT_EMIT_MS | 200 | Status frame frequency |
| COMMAND_TIMEOUT_MS | 1000 | Timeout window before forced FAULT and pump off |

## 9. Validation and Test Evidence
Implemented test suites validate critical behavior:

- SITL-style mission safety tests verify:
  - low battery inhibits spray and triggers failsafe path,
  - manual override forces failsafe,
  - nominal path emits spray command.

- HIL/protocol tests verify:
  - command frame parse round-trip,
  - checksum mismatch rejection,
  - ACK status parse behavior.

Planned test gates in docs also require no unsafe spray in comm loss, geofence breach, battery reserve breach, and stale sensor scenarios.

## 10. Key Findings and Project Response Matrix

| Key Finding | Why It Matters | How Project Tackles It | Current Status |
|---|---|---|---|
| Spray decisions must be centrally controlled | Prevents bypass paths from perception or UI | SafetySupervisor is the single gate for allow or deny | Implemented |
| Detection must be stable before actuation | Avoids one-frame false triggers | Confidence threshold + minimum age frames + top-cell ranking | Implemented |
| Spatial targeting must map from image to world | Required for targeted spray precision | Geotag projector converts pixel offsets using yaw and scale | Implemented (simplified projection model) |
| Actuator channel must fail safely | Prevents unsafe spray on comm or parser faults | Arduino parser validation + timeout + emergency stop -> pump off | Implemented |
| Operator must have hard interrupt path | Required for real-world safety operations | Emergency spray disable endpoint and UI trigger | Partially integrated (queue exists; consumer path on Pi still to be wired) |
| Mission must degrade safely under faults | Avoids unsafe behavior during link/energy failures | Critical inhibit reasons force FAILSAFE and RTL request | Implemented in orchestrator logic |

## 11. Open Integration Gaps and Practical Next Steps
1. Wire MissionOrchestrator spray_command output to ArduinoClient send flow in active runtime loop.
2. Add Pi-side consumer for pending ground-station emergency commands and map to manual override or direct emergency stop command path.
3. Externalize tunable parameters into config profiles (lab, field-conservative, field-aggressive) instead of hardcoded defaults.
4. Add integration tests that exercise full loop: perception detection -> safety allow -> serial frame send -> Arduino status acknowledgment.
5. Extend projection model calibration against camera intrinsics and altitude dynamics for better geotag precision.

## 12. Files Reviewed for This Report
- README.md
- docs/system-architecture.md
- docs/mission-fsm.md
- docs/safety-inhibit-matrix.md
- docs/test-gates.md
- docs/protocols/mavlink-contract.md
- docs/protocols/pi-arduino-serial.md
- pi-companion/src/pi_companion/mission_orchestrator.py
- pi-companion/src/pi_companion/safety_supervisor.py
- pi-companion/src/pi_companion/perception/detector_classical.py
- pi-companion/src/pi_companion/perception/geotag_projection.py
- pi-companion/src/pi_companion/perception/capture_pipeline.py
- pi-companion/src/pi_companion/io/mavlink_client.py
- pi-companion/src/pi_companion/io/arduino_client.py
- pi-companion/src/pi_companion/planning/multi_patch_planner.py
- pi-companion/src/pi_companion/main.py
- pi-companion/src/pi_companion/multi_patch_demo.py
- arduino-pump/src/main.ino
- tools-sim-test/sitl/test_mission_safety.py
- tools-sim-test/hil/test_protocol_faults.py
- ground-station-offline/backend/app.py
- ground-station-offline/frontend/src/main.ts
- docs/multi-patch-demo-playbook.md

## 13. Multi-Patch Practical Capability Added
The repository now includes practical support for multiple patches in fixed-wing missions:

1. Patch mapping and deduplication from repeated detections.
2. Cluster generation for nearby detections into spray zones.
3. Fixed-wing-safe spray leg generation with entry/spray/exit points.
4. Route ordering using distance + turn cost + priority heuristic.
5. Tick-level spray decision logic based on heading alignment and lead-distance window.
6. GeoJSON export for visual map presentation in demo.

This capability is implemented in:
- `pi_companion.planning.multi_patch_planner`
- `pi_companion.multi_patch_demo`

## 14. Conclusion
The repository already demonstrates a clear and safety-conscious architecture for targeted spray missions. The core mission logic, perception pipeline, safety gating, and actuator fail-safe behavior are present and coherent. The most important near-term work is final runtime wiring between mission spray decisions and actuator command transmission, plus operator command ingestion back into Pi mission control.
