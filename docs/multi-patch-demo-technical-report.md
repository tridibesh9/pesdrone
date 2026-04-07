# Multi-Patch Fixed-Wing Smart Spray Demo

Date: 2026-04-07  
Project: FTL-2  
Document Type: Brief Technical Report (PPT-ready source)

## 1. Executive Summary
This report captures the complete technical story of the multi-patch fixed-wing demo so it can be converted into presentation slides.

What the demo proves:
- multiple detections can be converted into stable field patches,
- nearby patches can be clustered into spray zones,
- fixed-wing-safe spray legs can be generated and sequenced,
- spray can be triggered only when heading alignment and lead-distance timing are valid.

Primary implementation modules:
- pi_companion.planning.multi_patch_planner.MultiPatchPlanner
- pi_companion.multi_patch_demo.run_demo

Core timing relation used by the planner:

$$
lead\_distance\_m = speed\_mps \times system\_delay\_s
$$

With default demo values:
- speed = 14.0 m/s
- delay = 0.40 s
- lead distance = 5.6 m

Meaning: spray is triggered before aircraft reaches the patch center, compensating system latency.

## 2. Demo Goal and Operational Motivation
### 2.1 Goal
Show a practical fixed-wing strategy for multiple infected patches by combining:
- patch mapping,
- patch clustering,
- leg-based spray planning,
- timing-correct spray decisions.

### 2.2 Why leg-based logic is required
A fixed-wing platform cannot safely chase each individual patch point with sharp local maneuvers. The mission must be expressed as flyable legs with predictable entry, spray window, and exit geometry.

### 2.3 Practical mission philosophy
- plan first, spray second,
- only spray inside validated geometry/timing windows,
- keep safety gating independent and always active.

## 3. System Architecture Context
### 3.1 Responsibility boundaries
| Subsystem | Primary responsibility |
|---|---|
| ArduPilot flight controller | Stabilization, navigation, base aircraft failsafes |
| Raspberry Pi 5 companion | Mission FSM, perception, geotag projection, spray decision gating |
| Arduino pump controller | Actuation only (pump/valve), parser safety, watchdog behavior |
| Offline ground station | Telemetry review, event log, emergency command queue |

### 3.2 High-level data flow
1. Flight controller sends MAVLink telemetry to Pi.
2. Pi capture/perception stack emits detections.
3. Pi projects detections to geo targets.
4. Multi-patch planner updates patch map, clusters, and spray legs.
5. Mission logic requests spray opportunity.
6. Safety supervisor allows or denies.
7. If allowed, Pi sends serial spray command to Arduino.
8. Arduino actuates and emits status heartbeats/acks.
9. Ground station stores telemetry/spray events and can queue emergency disable commands.

### 3.3 Nominal loop cadence targets
- telemetry ingest: 10 Hz
- perception output: 5 to 10 Hz
- safety evaluation: every control tick (10 Hz)
- Arduino heartbeat expectation: 200 ms

## 4. Multi-Patch Planner: Technical Design
### 4.1 Planner data model
Main dataclasses used:
- PlannerConfig
- PatchPoint
- PatchCluster
- SprayLeg
- AircraftPose
- SprayOpportunity

### 4.2 Patch ingestion and deduplication
For each projected target:
- if within dedupe radius of existing patch, update that patch,
- otherwise create a new patch id.

Update behavior for repeated hits:
- hits increment,
- confidence smoothed: new_conf = 0.7 * old + 0.3 * incoming,
- age_frames promoted to max(existing, incoming).

### 4.3 Clustering algorithm
Cluster seed strategy:
- patches sorted by priority score (confidence weighted by hit count),
- highest-priority patch selected as seed,
- nearby patches merged if within cluster radius from evolving centroid,
- centroid recomputed as members are added.

Cluster metrics computed:
- centroid lat/lon,
- cluster radius (max member distance to centroid),
- mean confidence,
- priority score (sum of member priorities).

### 4.4 Spray leg generation
For each cluster:
- heading initialized from reference heading,
- leg length computed and clamped.

Leg length formula:

$$
length\_m = clamp(2 \times cluster\_radius\_m + 14,\ min\_leg\_length\_m,\ max\_leg\_length\_m)
$$

Generated points:
- spray_start at half-leg behind centroid,
- spray_end at half-leg ahead of centroid,
- entry before spray_start by pre-entry distance,
- exit after spray_end by post-exit distance.

### 4.5 Route sequencing heuristic
A nearest-cost heuristic orders legs using:
- distance from current position to leg entry,
- heading change (turn cost proxy),
- priority bonus.

Cost structure:

$$
cost = distance\_m + turn\_cost - priority\_bonus
$$

where:

$$
turn\_cost = \left(\frac{|heading\_delta|}{180}\right) \times min\_turn\_radius\_m
$$

### 4.6 Tick-level spray decision logic
For active leg:
1. compute lead distance from current speed and delay,
2. filter targets near active cluster,
3. reject targets with heading error above alignment threshold,
4. choose candidate minimizing |distance_to_target - lead_distance|,
5. spray only if delta is inside trigger window.

Spray decision reasons emitted by planner include:
- within_lead_window
- outside_trigger_window
- heading_misaligned_or_behind
- no_targets_for_leg
- no_active_leg
- cluster_missing

Leg completion behavior:
- leg is marked complete when aircraft is within 8 m of leg exit.

## 5. Default Configuration (Implementation Values)
### 5.1 MultiPatchPlanner defaults
| Parameter | Default |
|---|---:|
| dedupe_radius_m | 3.0 |
| cluster_radius_m | 14.0 |
| min_points_per_cluster | 1 |
| min_leg_length_m | 18.0 |
| max_leg_length_m | 60.0 |
| pre_entry_distance_m | 22.0 |
| post_exit_distance_m | 22.0 |
| min_turn_radius_m | 40.0 |
| heading_alignment_deg | 35.0 |
| trigger_window_m | 2.5 |
| default_speed_mps | 14.0 |
| system_delay_s | 0.40 |

### 5.2 MissionOrchestrator defaults
| Parameter | Default |
|---|---:|
| detection_confidence_min | 0.65 |
| detection_min_age_frames | 2 |
| spray_pulse_ms | 120 |
| spray_pwm | 200 |

### 5.3 SafetySupervisor policy defaults
| Parameter | Default |
|---|---:|
| battery_reserve_pct | 25.0 |
| max_depth_age_ms | 250 |
| max_camera_age_ms | 250 |
| max_fc_heartbeat_age_ms | 2000 |
| max_arduino_heartbeat_age_ms | 1000 |
| max_control_latency_ms | 200 |
| max_cpu_temp_c | 75.0 |
| max_dropped_frame_rate | 0.05 |

### 5.4 ClassicalDetector defaults
| Parameter | Default |
|---|---:|
| vegetation_threshold | 0.20 |
| stress_upper_threshold | 0.35 |
| min_pixels | 25 |
| max_detections | 4 |
| cell_size_px | 32 |

### 5.5 Geotag projector default
| Parameter | Default |
|---|---:|
| ground_sample_m_per_px | 0.05 |

## 6. Safety and Inhibit Model
### 6.1 Hard inhibits (spray must be denied)
- mode_not_auto
- manual_override
- geofence_breach
- battery_low_reserve
- gps_invalid
- depth_stale
- camera_stale
- fc_link_lost
- arduino_link_lost
- mission_not_armed

### 6.2 Soft warnings (non-blocking, degraded operation indicators)
- high_latency
- high_cpu_temp
- dropped_frames

### 6.3 Critical fault handling
Critical reasons force FAILSAFE and RTL request path:
- manual_override
- geofence_breach
- battery_low_reserve
- gps_invalid
- fc_link_lost
- arduino_link_lost

### 6.4 Logging requirement
Every deny event should include:
- timestamp,
- mission state,
- inhibit reason list,
- telemetry summary.

## 7. Control Interfaces and Protocol Contracts
### 7.1 MAVLink (Pi <-> Flight controller)
Incoming telemetry used:
- HEARTBEAT
- GLOBAL_POSITION_INT
- GPS_RAW_INT
- ATTITUDE
- BATTERY_STATUS
- SYS_STATUS
- MISSION_CURRENT

Outgoing actions:
- SET_MODE (AUTO/RTL)
- mission upload primitives
- optional failsafe command_long path

Link failure rule:
1. inhibit spray immediately,
2. transition to FAILSAFE,
3. request RTL when link and control path are available.

### 7.2 Pi-Arduino serial protocol
Frame format:
- START (0xAA)
- CMD
- LEN
- PAYLOAD
- CHECKSUM (XOR of cmd, len, payload bytes)

Pi -> Arduino commands:
- 0x01 SET_PUMP_PWM
- 0x02 PULSE_SPRAY_MS (u16, big-endian)
- 0x03 VALVE_ON_OFF
- 0x04 HEARTBEAT_REQUEST
- 0x05 EMERGENCY_STOP

Arduino -> Pi status:
- 0x81 HEARTBEAT_STATUS [state, fault_code, pump_pwm]
- 0x82 ACK [ack_cmd]
- 0x83 NACK [nack_cmd, error_code]

Actuator fail-safe rule:
- parser/checksum fault, command timeout, or emergency stop must force pump OFF.

## 8. Demo Execution and Expected Deliverables
### 8.1 Demo run commands
From repository root:
1. C:/Program Files/Python313/python.exe -m pip install -e .\pi-companion[dev]
2. C:/Program Files/Python313/python.exe -m pi_companion.multi_patch_demo

### 8.2 Mock scenario details
Demo includes 7 projected targets grouped into:
- Cluster 1: dense infected patch (3 points)
- Cluster 2: elongated strip patch (3 points)
- Cluster 3: isolated high-confidence patch (1 point)

### 8.3 Console outputs expected
- patch_count, cluster_count, leg_count, completed_leg_count, active_leg
- ordered spray leg list with heading and leg length
- tick-wise decision stream with SPRAY or HOLD and reason code

### 8.4 Generated artifact
- multi_patch_demo.geojson

GeoJSON feature categories exported:
- patch points,
- cluster centroids,
- spray leg LineStrings (entry -> spray_start -> spray_end -> exit).

## 9. Test Evidence and Validation Gates
### 9.1 Existing automated tests
SITL-oriented tests validate:
- near-point clustering creates expected group count,
- one leg generated per cluster,
- lead-window timing allows spray for correctly positioned target,
- low battery inhibits spray and triggers failsafe,
- manual override forces failsafe,
- nominal mission path emits spray command.

HIL/protocol tests validate:
- frame build/parse round-trip,
- checksum mismatch rejection,
- ACK status parsing.

### 9.2 Required gate checks before outdoor run
- protocol parser negative/positive cases pass,
- heartbeat timeout drives pump-off behavior,
- all safety inhibits block spray as specified,
- stale sensor and link loss scenarios block spray,
- no unsafe spray command in comm-loss/geofence/low-battery/manual-override simulations,
- HIL confirms watchdog and emergency stop behavior with real Pi + Arduino.

## 10. Ground Station Offline Operations
Backend capabilities:
- health endpoint,
- telemetry ingestion and storage,
- spray event ingestion and storage,
- emergency spray-disable command queue,
- pending command retrieval endpoint.

Frontend capabilities:
- local health refresh,
- emergency spray-disable button,
- offline localhost API integration.

Current integration status:
- queue and API are implemented,
- Pi-side consumer loop for pending emergency commands is pending full integration.

## 11. Implementation Status and Gaps
Implemented now:
- multi-patch dedupe, clustering, leg planning, route ordering,
- lead-distance spray decision logic,
- safety supervisor hard-inhibit logic,
- mission FSM transitions and spray command object generation,
- serial protocol framing/parsing and Arduino fail-safe behavior,
- demo GeoJSON export and console decision trace.

Open integration gaps:
1. connect MissionOrchestrator spray_command output to live Arduino transport in the active runtime loop,
2. consume ground-station pending emergency commands in Pi control loop,
3. calibrate and validate projection model for field geometry precision,
4. add full end-to-end integration test from detection to serial ACK.

## 12. Field Trial Safety Checklist (First Real Demo)
- manual override path tested and operator rehearsed,
- colored water used instead of pesticide,
- patch-level area spray strategy used first,
- valve/pump response latency measured and folded into lead-distance settings,
- geofence and battery reserve thresholds validated before takeoff,
- SITL and HIL gates passed on the exact software revision to be flown.

## 13. PPT Slide Mapping Guide
Recommended slide flow:
1. Problem and fixed-wing constraint
2. Architecture and subsystem boundaries
3. End-to-end data and control flow
4. Multi-patch planner pipeline
5. Lead-distance timing concept and equation
6. Safety inhibit matrix and failsafe path
7. Protocol interfaces (MAVLink + serial)
8. Demo setup and mock patch geometry
9. Output evidence (logs + GeoJSON)
10. Validation status and test gates
11. Open gaps and next upgrades
12. Deployment readiness checklist

## 14. Source Material Used
- docs/multi-patch-demo-playbook.md
- docs/system-architecture.md
- docs/mission-fsm.md
- docs/safety-inhibit-matrix.md
- docs/protocols/mavlink-contract.md
- docs/protocols/pi-arduino-serial.md
- docs/test-gates.md
- docs/key-findings-report.md
- pi-companion/src/pi_companion/planning/multi_patch_planner.py
- pi-companion/src/pi_companion/multi_patch_demo.py
- pi-companion/src/pi_companion/mission_orchestrator.py
- pi-companion/src/pi_companion/safety_supervisor.py
- pi-companion/src/pi_companion/perception/detector_classical.py
- pi-companion/src/pi_companion/perception/geotag_projection.py
- pi-companion/src/pi_companion/perception/capture_pipeline.py
- pi-companion/src/pi_companion/io/mavlink_client.py
- pi-companion/src/pi_companion/io/arduino_client.py
- pi-companion/src/pi_companion/main.py
- arduino-pump/src/main.ino
- tools-sim-test/sitl/test_multi_patch_planner.py
- tools-sim-test/sitl/test_mission_safety.py
- tools-sim-test/hil/test_protocol_faults.py
- ground-station-offline/backend/app.py
- ground-station-offline/frontend/src/main.ts
