# ArduPilot Fixed-Wing Integration Runbook

Date: 2026-04-09
Project: FTL-2
Use: Step-by-step guide to connect Raspberry Pi companion, ArduPilot fixed-wing, and spray controller.

## 1. Goal
Bring up a safe, testable end-to-end pipeline:
1. ArduPilot provides stable flight and telemetry.
2. Pi companion receives telemetry and runs detection/planning.
3. Pi sends spray commands to Arduino only when mission and safety gates allow.

## 2. Safety First (Do This Before Anything)
1. First tests must be with propeller removed or motor disabled.
2. Use water only, no pesticide, until timing and safety are validated.
3. Keep RC manual takeover switch active and tested.
4. Keep geofence enabled and return-to-launch action configured.
5. Never disable arming checks for outdoor testing.

## 3. Hardware Wiring

### 3.1 Flight controller to Raspberry Pi (telemetry)
Use one method only for first bring-up:

Method A (recommended first): USB cable
- Flight controller USB -> Pi USB
- Appears as serial device on Pi

Method B: UART TELEM port
- FC TX -> Pi RX
- FC RX -> Pi TX
- FC GND -> Pi GND
- Verify logic voltage compatibility (3.3V vs 5V) before direct UART wiring

### 3.2 Pi to Arduino (spray controller)
- Pi USB -> Arduino USB
- Or UART with common GND
- Keep command heartbeat enabled
- Ensure Arduino defaults pump OFF on timeout or parse error

### 3.3 Power
- Use separate clean power rail for Pi and controller electronics
- Isolate pump high-current path from signal ground where possible
- Add flyback protection and noise suppression on pump driver path

## 4. ArduPilot Setup (Mission Planner / QGroundControl)

## 4.1 Airframe baseline
1. Load correct fixed-wing firmware.
2. Complete all calibrations:
- accelerometer
- compass
- radio calibration
- control surface direction and failsafe checks
3. Verify flight modes include Manual, FBWA, Auto, RTL.

### 4.2 Companion telemetry port
Configure the serial port used by Pi companion as MAVLink2.

Key parameters to verify:
- SERIALx_PROTOCOL = MAVLink2
- SERIALx_BAUD = 115200 or 57600

Recommendation:
- Start with 115200 if link is stable.
- If noisy link, drop to 57600.

### 4.3 Failsafe and geofence
Configure in GCS UI and verify actual actions by simulation.

Must-have checks:
1. GCS/telemetry loss action set to safe mode (typically RTL).
2. Battery failsafe configured with conservative reserve.
3. Geofence enabled with action set to RTL.
4. RC failsafe tested and confirmed.

### 4.4 Logging
Enable logs required for analysis:
1. Log while disarmed for bench testing.
2. Log attitude, GPS, battery, mode changes, mission events.
3. Keep synchronized timestamps for post-run replay.

## 5. Companion Computer Setup (Pi)

### 5.1 Environment
1. Install Python environment and dependencies.
2. Install project package in editable mode.
3. Verify camera stream and serial permissions.

### 5.2 Telemetry bring-up test
1. Connect Pi to FC.
2. Confirm heartbeats arrive continuously.
3. Confirm mode, GPS, and battery fields update in software.
4. Confirm stale-link detection triggers fail-safe logic.

### 5.3 Arduino bring-up test
1. Confirm heartbeat status from Arduino.
2. Send safe commands in bench mode:
- set pwm
- pulse spray
- emergency stop
3. Confirm timeout forces pump OFF.

## 6. Parameter Baseline (Start Here)

### 6.1 Flight envelope
- mapping altitude: 18 m AGL
- mapping speed: 15 m/s
- spray altitude: 10 m AGL
- spray speed: 12 m/s
- spray roll limit: 12 degrees

### 6.2 Timing
- system_delay_s: 0.45
- camera_to_nozzle_offset_m: 0.4
- trigger_window_m: 1.5

Lead distance:

$$
d_{lead} = v \cdot t_{total} + d_{cam\to nozzle}
$$

Baseline value at 12 m/s:

$$
d_{lead} = 12 \cdot 0.45 + 0.4 = 5.8\,m
$$

### 6.3 Planner
- cluster_radius_m: 6 to 8
- pre_entry_distance_m: 25
- post_exit_distance_m: 25
- heading_alignment_deg: 15

### 6.4 Detection
- vegetation_threshold: 0.20 (tune by crop/lighting)
- stress_upper_threshold: 0.35 (or use brown-target mode for brown dieback scenes)
- confidence_min: 0.55
- age_frames_min: 2

### 6.5 Safety freshness and link
- max_camera_age_ms: 250
- max_depth_age_ms: 250
- max_fc_heartbeat_age_ms: 2000
- max_arduino_heartbeat_age_ms: 1000

## 7. How It Decides Detect vs Spray
1. Detection pass creates geotagged candidates with confidence and age.
2. Planner updates patch map and active spray leg.
3. Spray is allowed only if:
- target is on active leg
- heading aligned
- lead-distance window satisfied
- speed and roll in limits
- no hard inhibit active
4. If target is already passed, system queues for revisit leg, not unsafe immediate spray.

## 8. Step-by-Step Commissioning Sequence

### Phase A: Bench (no prop, no spray fluid)
1. FC and Pi connected, telemetry verified.
2. Arduino connected, heartbeat verified.
3. Run mission loop with synthetic detections.
4. Confirm safety inhibits block spray when forced faults are injected.

### Phase B: Bench with water system armed
1. Pump connected with water only.
2. Trigger pulse commands and measure response delay.
3. Verify emergency stop and timeout behavior physically stop output.

### Phase C: SITL and HIL
1. Run ArduPilot SITL scenarios:
- normal mission
- battery low
- telemetry loss
- geofence breach
- manual override
2. Confirm no unsafe spray command under any fail condition.

### Phase D: Field day 1 (mapping only)
1. Fly mapping pass at 18 m AGL.
2. Export detections, clusters, planned legs.
3. Validate leg geometry and revisit logic.

### Phase E: Field day 2 (water spray only)
1. Fly spray pass at 10 m AGL and 12 m/s.
2. Measure spray landing offset from target markers.
3. Recompute delay:

$$
t_{total} = \frac{d_{observed} - d_{cam\to nozzle}}{v}
$$

4. Update system_delay_s and retest.

### Phase F: Controlled mission acceptance
1. Repeat until hit consistency and safety conditions are stable.
2. Only then move toward chemical workflow under local approvals.

## 9. Parameter Change Rules (What to touch first)

If spray lands late:
1. Increase system_delay_s in small steps (0.03 to 0.05 s).
2. Re-measure at same speed and altitude.

If spray lands early:
1. Decrease system_delay_s in small steps.

If too many false detections:
1. Raise confidence_min.
2. Increase age_frames_min.
3. Reduce max_detections.

If obvious patches are missed:
1. Lower detection threshold slightly.
2. Increase max_detections for denser candidate extraction.
3. Improve camera exposure consistency.

If route is too fragmented:
1. Increase cluster_radius_m.
2. Increase pre/post entry distances.

If route merges unrelated regions:
1. Decrease cluster_radius_m.

## 10. Exactly Where To Edit In This Repo
1. Mission and spray thresholds:
- pi-companion/src/pi_companion/mission_orchestrator.py

2. Safety timeouts and inhibits:
- pi-companion/src/pi_companion/safety_supervisor.py

3. Planner geometry and route behavior:
- pi-companion/src/pi_companion/planning/multi_patch_planner.py

4. One-image trial tuning for visual validation:
- pi-companion/src/pi_companion/image_patch_trial.py

## 11. Field Acceptance Checklist
1. RC takeover tested before each sortie.
2. Geofence and RTL action verified.
3. Battery failsafe verified.
4. Companion heartbeat stable.
5. Arduino timeout and emergency stop verified.
6. Water-only spray calibration passes target tolerance.

## 12. Presenter Script (Short)
1. We connect ArduPilot for stable flight and telemetry.
2. Pi companion handles perception and route planning.
3. Arduino is actuator-only and defaults safe on fault.
4. We calibrate lead distance from measured delay, not assumptions.
5. We spray only when timing, geometry, and safety gates all pass.
