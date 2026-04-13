# Fixed-Wing Camera, Path, and Spray Decision Guide

Date: 2026-04-08
Project: FTL-2
Use: Technical reference + presenter story for PPT and demo day

Companion implementation runbook:
- [docs/ardupilot-fixed-wing-integration-runbook.md](docs/ardupilot-fixed-wing-integration-runbook.md)

## 1. One-Sentence Story
We do not chase every point like a quadcopter; we map stressed regions, convert them into flyable spray legs, and trigger spray only when timing and safety gates are valid for a fixed-wing aircraft.

## 2. Why Fixed-Wing Needs Different Logic
A fixed-wing aircraft has momentum and a non-zero turning radius, so instant point-by-point targeting is not physically reliable.

Minimum-turn-radius model:

$$
R = \frac{v^2}{g\tan\phi}
$$

Where:
- $R$ is turn radius in meters
- $v$ is airspeed in m/s
- $g \approx 9.81$ m/s^2
- $\phi$ is bank angle

Typical values:
- At $v=12$ m/s and $\phi=30^\circ$, $R \approx 25$ m
- At $v=15$ m/s and $\phi=30^\circ$, $R \approx 40$ m

Reasoning:
- This is why the mission is leg-based (entry -> spray -> exit), not point-chasing.

## 3. Camera Mounting Specification (Practical Baseline)

### 3.1 Physical mount
1. Mount camera close to fuselage centerline and near CG to reduce motion distortion.
2. Use rigid bracket + soft vibration damping washers.
3. Keep camera unobstructed by propeller, landing gear, or wing root.

### 3.2 Orientation
1. Use downward-looking camera with 10 to 15 degree forward tilt from nadir.
2. Start at 12 degree forward tilt for first field demo.
3. Keep roll alignment square to fuselage axis; no sideways yaw offset initially.

### 3.3 Camera settings
1. Resolution: 1080p at 30 fps.
2. Processing input can be downsampled (for example 640 x 360) for onboard speed.
3. Shutter in daylight: at least 1/1000 s to reduce motion blur.
4. Lock exposure when possible to reduce frame-to-frame index drift.

### 3.4 Measurement required before flight
Measure forward offset from camera optical center to nozzle projection point on fuselage axis:
- $d_{cam\to nozzle}$ in meters (usually 0.3 to 0.5 m).

This offset must be included in spray timing.

## 4. Flight Height and Speed Profiles

### 4.1 Two-pass method (recommended)
1. Pass A: Mapping pass (spray OFF)
- Height: 16 to 20 m AGL
- Speed: 14 to 16 m/s

2. Pass B: Spray pass (spray armed)
- Height: 8 to 12 m AGL
- Speed: 10 to 13 m/s

Reasoning:
- Mapping higher improves coverage and route planning context.
- Spraying lower reduces drift and improves placement.
- Spraying slower reduces timing error and turn burden.

### 4.2 Spray attitude constraints
- Spray ON only when roll magnitude <= 12 degrees
- Spray OFF during major turns and transition arcs

## 5. Detection-Then-Spray Decision Logic

## 5.1 Detect gate (perception active)
Enable detection only when:
1. mode = AUTO
2. altitude within mission range
3. camera freshness OK
4. roll magnitude <= 20 degrees

### 5.2 Patch candidate acceptance
Accept a target when:
1. confidence >= threshold (start: 0.55)
2. age_frames >= threshold (start: 2 or 3)
3. inside active corridor for current mission strip

### 5.3 Spray authorization (strict)
Spray only when all are true:
1. Active spray leg exists
2. Heading error to target <= 15 degrees
3. Distance to target is inside lead window
4. Roll magnitude <= 12 degrees
5. Speed in spray envelope (10 to 13 m/s)
6. No hard safety inhibits active

Hard inhibits:
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

## 6. Timing Mathematics and Why It Matters
Spray cannot be triggered exactly on top of a target because every stage has delay.

Total timing delay:

$$
t_{total} = t_{capture} + t_{process} + t_{command} + t_{valve} + t_{droplet}
$$

Lead distance model:

$$
d_{lead} = v \cdot t_{total} + d_{cam\to nozzle}
$$

Trigger condition:

$$
|d_{target} - d_{lead}| \le w_{trigger}
$$

Recommended start values:
- $v = 12$ m/s
- $t_{total} = 0.45$ s
- $d_{cam\to nozzle} = 0.4$ m
- $w_{trigger} = 1.5$ m

Then:

$$
d_{lead} = 12 \cdot 0.45 + 0.4 = 5.8\,m
$$

Reasoning:
- Faster speed or larger delay requires earlier spray trigger.
- Narrow trigger window increases precision but can miss targets.
- Wider trigger window improves hit rate but increases overspray risk.

## 7. Mapping Geometry and Lane Spacing
Ground footprint width from height and camera HFOV:

$$
W = 2h\tan\left(\frac{\alpha}{2}\right)
$$

Lane spacing for overlap target:

$$
S = W(1 - overlap)
$$

Recommended overlap for mapping: 25 to 35 percent.

Example:
- $h=18$ m
- $\alpha=78^\circ$
- $W \approx 29.1$ m
- For 30 percent overlap, $S \approx 20.4$ m

Reasoning:
- Adequate overlap stabilizes patch reconstruction and clustering.
- Too little overlap creates fragmented zones.

## 8. Path Shape for Multiple Patches

### 8.1 Clustering
Nearby detections are merged into stable patch zones using a cluster radius.

### 8.2 Leg generation
For each cluster, generate spray leg length:

$$
L = clamp(2r + 14, L_{min}, L_{max})
$$

Recommended starts:
- $L_{min}=30$ m
- $L_{max}=70$ m
- pre-entry = 25 m
- post-exit = 25 m

### 8.3 Route ordering
Choose next leg using a cost that balances distance, turning burden, and patch priority:

$$
cost = distance + turn\_cost - priority\_bonus
$$

$$
turn\_cost = \left(\frac{|\Delta heading|}{180}\right)\cdot R_{min}
$$

Reasoning:
- Keeps route flyable and efficient for fixed-wing kinematics.

## 9. Parameter Tuning Cookbook

### 9.1 Camera and geometry
- camera tilt: 10 to 15 deg (start 12)
- spray altitude: 8 to 12 m
- mapping altitude: 16 to 20 m
- lane overlap: 25 to 35 percent

If detections are unstable near edges:
- reduce tilt slightly
- increase overlap
- tighten active corridor mask

### 9.2 Detection thresholds
- vegetation_threshold: start 0.20
- stress_upper_threshold: start 0.35
- confidence_min: start 0.55
- age_frames_min: start 2

If too many false positives:
- increase confidence_min (for example 0.55 -> 0.62)
- increase age_frames_min (2 -> 3)
- reduce max_detections

If missing obvious brown zones:
- lower vegetation_threshold slightly
- widen stress band using threshold tuning
- increase max_detections for denser patch candidates

### 9.3 Timing and spray
- system_delay_s: start 0.45
- trigger_window_m: start 1.5
- spray speed: 10 to 13 m/s

If spray lands late:
- increase system_delay_s or measured nozzle offset

If spray lands early:
- decrease system_delay_s or nozzle offset

### 9.4 Clustering and route
- cluster_radius: start 5 to 8 m ground equivalent
- pre-entry and post-exit: start 25 m each

If too many tiny clusters:
- increase cluster radius

If unrelated regions merge:
- decrease cluster radius

## 10. Exactly Where to Change Parameters in Code
1. Mission thresholds and spray pulse:
- [pi-companion/src/pi_companion/mission_orchestrator.py](pi-companion/src/pi_companion/mission_orchestrator.py)
- class OrchestratorConfig

2. Safety limits and freshness timeouts:
- [pi-companion/src/pi_companion/safety_supervisor.py](pi-companion/src/pi_companion/safety_supervisor.py)
- class SafetyPolicy

3. Route and clustering behavior:
- [pi-companion/src/pi_companion/planning/multi_patch_planner.py](pi-companion/src/pi_companion/planning/multi_patch_planner.py)
- class PlannerConfig

4. One-image trial settings for PPT output:
- [pi-companion/src/pi_companion/image_patch_trial.py](pi-companion/src/pi_companion/image_patch_trial.py)
- CLI arguments and defaults

## 11. Presenter Story You Can Speak (Concise)
1. Problem:
"Fixed-wing cannot hover and chase points. If we try that, we miss timing and create unsafe spray behavior."

2. Design choice:
"So we map detections first, cluster them into spray zones, then generate flyable legs with entry and exit geometry."

3. Math explanation:
"Spray timing is not guesswork. We calculate lead distance from speed and total delay, then trigger only inside a narrow window."

4. Safety claim:
"Even if detection finds a target, spray still needs mission state, heading alignment, freshness, link health, and safety supervisor approval."

5. Outcome:
"This gives a practical fixed-wing workflow: stable path, explainable decisions, and controlled actuation."

## 12. Demo-Day Checklist
1. Verify camera tilt and lens cleanliness.
2. Confirm measured camera-to-nozzle offset in config.
3. Fly short mapping pass and inspect cluster map.
4. Validate lead distance with water-only test strip.
5. Enable spray only after safety gate checks pass.
6. Keep manual override ready and tested.

## 13. Recommended Baseline Profile (Use First)
- mapping height: 18 m AGL
- mapping speed: 15 m/s
- spray height: 10 m AGL
- spray speed: 12 m/s
- lead delay: 0.45 s
- cam-to-nozzle offset: 0.4 m
- lead distance: 5.8 m
- trigger window: plus/minus 1.5 m
- max bank for spray: 12 deg

This baseline is conservative enough for demonstration and tunable after first calibration runs.
