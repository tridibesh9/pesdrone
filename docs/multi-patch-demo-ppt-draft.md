# PPT Draft: Multi-Patch Fixed-Wing Smart Spray Demo

Date: 2026-04-08  
Project: FTL-2  
Use: Direct source for slide creation (technical story format)

Companion technical guide:
- [docs/fixed-wing-operations-story-and-parameter-guide.md](docs/fixed-wing-operations-story-and-parameter-guide.md)

## Deck Intent
Build a story from field problem to validated solution:
1. Why fixed-wing spraying is hard
2. How our architecture solves it safely
3. How detection and planning actually work
4. What evidence we have today
5. What to upgrade next

## Story Arc
- Act 1: Problem and constraints
- Act 2: System design choices
- Act 3: Detection + planning mechanics
- Act 4: Safety and validation proof
- Act 5: Upgrade path to production

---

## Slide 1 - Title and One-Line Outcome
### Slide title
Multi-Patch Fixed-Wing Smart Spray: From Detection to Safe Actuation

### Key points
- We built a practical multi-patch spray workflow for fixed-wing aircraft.
- The system maps detections, clusters spray zones, plans flyable legs, and triggers spray with timing compensation.
- Safety gate is centralized and non-bypassable.

### Presenter line
"This demo is not point-chasing; it is mission-grade, leg-based spray control for fixed-wing constraints."

---

## Slide 2 - Real Problem in Field Operations
### Slide title
Why Point-by-Point Spray Fails on Fixed-Wing

### Key points
- Fixed-wing cannot hover or aggressively stop/turn around each infected point.
- Chasing points causes unstable trajectories and unsafe actuation timing.
- Practical requirement: convert noisy detections into preplanned spray legs.

### Visual suggestion
- Left: scattered patch points
- Right: smoothed leg-based path crossing clustered zones

### Presenter line
"The shift is from reactive point targeting to geometry-aware, speed-aware mission execution."

---

## Slide 3 - Architecture Boundaries (Who Does What)
### Slide title
System Responsibility Split

### Key points
- ArduPilot: flight stabilization, navigation, base failsafes.
- Pi companion: perception, mission FSM, planner, safety supervisor.
- Arduino: actuator-only endpoint (pump/valve) with parser watchdog.
- Offline ground station: telemetry, replay, emergency command queue.

### Visual suggestion
Block diagram with four boxes and arrows.

### Presenter line
"Safety comes from strict responsibility boundaries, not from one monolithic loop."

---

## Slide 4 - End-to-End Control and Data Flow
### Slide title
From Telemetry and Frames to Spray Pulse

### Key points
1. MAVLink telemetry arrives at Pi.
2. Camera/depth pipeline emits frame bundle and freshness.
3. Detector generates image-space detections.
4. Projector converts detections to geo targets.
5. MultiPatchPlanner updates patch map, clusters, and active leg.
6. Mission logic asks: spray now or hold?
7. Safety supervisor allow/deny gate decides.
8. If allow, serial command goes to Arduino.

### Cadence references
- telemetry ingest: 10 Hz
- perception: 5 to 10 Hz
- safety eval: every control tick

---

## Slide 5 - Detection Process (Technical Core)
### Slide title
How Detection Is Computed (Classical CV, Phase 1)

### Process steps
1. Convert RGB frame to normalized channels.
2. Compute stress proxy index:

$$
I = \frac{G - R}{G + R + \epsilon}
$$

3. Build vegetation mask:

$$
M_v = (I > T_v)
$$

4. Build stressed mask:

$$
M_s = M_v \land (I < T_s)
$$

5. Reject if stressed pixels < min_pixels.
6. Bin stressed pixels into grid cells.
7. Rank cells by stressed-pixel count.
8. Convert top cells to detections with confidence and age.

### Why this approach now
- deterministic, lightweight, and explainable on Pi 5,
- easier threshold tuning for early field trials,
- lower deployment and debugging complexity than deep models in phase 1.

---

## Slide 6 - Detection Confidence and Stability Controls
### Slide title
How We Reduce False Triggers

### Key formulas/logic
Confidence from stressed pixels per cell:

$$
area\_ratio = min\left(1, \frac{cell\_count}{0.02 \times frame\_area}\right)
$$

$$
confidence = 0.45 + 0.55 \times area\_ratio
$$

Stability controls:
- confidence threshold,
- minimum age_frames,
- max detections per frame,
- sensor freshness gating before spray permission.

### Key point
We do not spray from one noisy frame; temporal and safety filters are layered.

---

## Slide 7 - Geotag Projection (Image to World)
### Slide title
From Pixel Coordinate to GPS Target

### Process
1. Pixel offset from image center gives forward/right meter offsets.
2. Rotate offsets by aircraft yaw.
3. Convert north/east meters to latitude/longitude deltas.

### Equations
$$
forward = -\Delta y_{px} \times s
$$

$$
right = \Delta x_{px} \times s
$$

$$
north = forward\cos\psi - right\sin\psi
$$

$$
east = forward\sin\psi + right\cos\psi
$$

$$
lat_t = lat + \frac{north}{111320}, \quad lon_t = lon + \frac{east}{111320\cos(lat)}
$$

Where:
- $s$ is ground_sample_m_per_px,
- $\psi$ is yaw.

---

## Slide 8 - Multi-Patch Mapping and Clustering
### Slide title
Turning Repeated Targets into Spray Zones

### Key process
- Deduplicate nearby targets within dedupe radius.
- Update hit count and smooth confidence over time.
- Cluster nearby patch points using cluster radius and centroid updates.
- Compute cluster priority from confidence and repeat hits.

### Priority concept
Patch priority increases with confidence and repeated observations.

### Key point
This transforms noisy detections into stable, operational spray zones.

---

## Slide 9 - Spray Leg Generation for Fixed-Wing
### Slide title
Flyable Geometry: Entry -> Spray -> Exit

### Leg construction
- Leg centered on cluster centroid.
- Length scales with cluster radius and is clamped.
- Explicit pre-entry and post-exit distances create smoother approach/departure.

### Formula
$$
L = clamp(2r + 14, L_{min}, L_{max})
$$

Where:
- $r$ = cluster radius,
- $L_{min}$ and $L_{max}$ from planner config.

### Key point
Leg geometry respects fixed-wing kinematics instead of point-stop behavior.

---

## Slide 10 - Route Sequencing and Timing Trigger
### Slide title
Which Leg Next, and When to Spray

### Route cost
$$
cost = distance\_to\_entry + turn\_cost - priority\_bonus
$$

$$
turn\_cost = \left(\frac{|\Delta heading|}{180}\right) \times min\_turn\_radius
$$

### Lead-distance trigger
$$
lead\_distance = speed \times system\_delay
$$

Spray condition:
- target heading-aligned,
- distance to target close to lead distance,
- within trigger window.

### Example
At 14 m/s and 0.40 s delay, lead distance is 5.6 m.

---

## Slide 11 - Mission FSM and Safety Gate
### Slide title
State-Machine Controlled Spray Authorization

### FSM path
IDLE -> PREFLIGHT_CHECKS -> ARMED -> AUTO_SCAN -> TARGET_CONFIRMED -> SPRAY_WINDOW -> AUTO_SCAN

### Hard inhibits (deny spray)
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

### Critical faults force
- FAILSAFE transition
- RTL request path

### Key point
Spray can be requested in mission logic, but only emitted through centralized safety approval.

---

## Slide 12 - Actuator Protocol and Hardware Fail-Safe
### Slide title
Pi-Arduino Serial Contract and Default-Safe Behavior

### Protocol frame
[START][CMD][LEN][PAYLOAD][CHECKSUM]

### Critical commands
- set pump pwm
- pulse spray ms
- valve on/off
- heartbeat request
- emergency stop

### Hardware fail-safe behavior
Pump is forced OFF on:
- parser/checksum error,
- command timeout,
- emergency stop.

### Key point
Even if upstream software fails, actuator layer still defaults to safe state.

---

## Slide 13 - Evidence: Demo Output and Tests
### Slide title
What Has Been Proven So Far

### Demo output evidence
- patch, cluster, and leg counts,
- ordered spray leg list,
- tick-by-tick SPRAY/HOLD decisions with reason codes,
- GeoJSON artifact for map visualization.

### Automated test evidence
- clustering behavior tests,
- lead-window spray timing tests,
- mission safety tests (battery/manual override),
- serial protocol checksum and ACK parsing tests.

### Key point
We already have behavior-level proof, not only design claims.

---

## Slide 14 - Why This Design Is Practical
### Slide title
Design Rationale and Trade-Offs

### Why this approach
- Fits fixed-wing flight dynamics.
- Gives deterministic behavior and explainable decisions.
- Enforces safety at multiple layers.
- Works offline-first for field operations.

### Trade-offs
- Classical detector is less robust than model-based perception in edge lighting/complex canopy.
- Geotag projection uses simplified scale assumptions.
- Current runtime integration still needs final wiring for full live actuation loop.

---

## Slide 15 - Upgrade Roadmap (Next Technical Steps)
### Slide title
What We Upgrade Next

### Near-term upgrades (high impact)
1. Wire MissionOrchestrator spray command to live Arduino transport in runtime loop.
2. Consume offline ground-station emergency queue in Pi control loop.
3. Add full detection -> safety -> serial ACK integration test.

### Mid-term upgrades
1. Projection calibration with camera intrinsics, altitude, and attitude compensation.
2. Smarter revisit prioritization (confidence x proximity x missed-pass count).
3. Adaptive trigger window based on latency and wind estimate.

### Long-term upgrades
1. Hybrid perception (classical + lightweight model fallback).
2. Automatic leg heading optimization from wind and strip direction.
3. Direct mission-item streaming of active legs to ArduPilot.

---

## Slide 16 - Close and Ask
### Slide title
Conclusion and Decision Ask

### Final message
- The system already demonstrates a safe, technically grounded multi-patch fixed-wing spray strategy.
- Core planning, timing compensation, and safety inhibition are implemented.
- Remaining work is primarily integration hardening and calibration.

### Ask to stakeholders
- Approve next sprint for integration hardening,
- approve controlled field trial after SITL/HIL gate pass,
- approve instrumentation for latency and projection calibration data capture.

---

## Optional Appendix Slides
### A1 - Full parameter table (planner + safety + detector)
### A2 - Serial protocol command map and error codes
### A3 - Test matrix by failure mode
### A4 - Risk register and mitigation owner list
