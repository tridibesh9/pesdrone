# Multi-Patch Fixed-Wing Demo Playbook

Date: 2026-04-07

## 1. Demo Goal
Show a practical fixed-wing strategy for multiple infected patches:
- map detections,
- cluster nearby detections into spray zones,
- generate fixed-wing-safe spray legs,
- trigger spray only when lead-distance timing is valid.

## 2. Why This Is Practical
A fixed-wing should not chase each patch point.
It should fly preplanned spray legs and revisit missed zones.

Core timing equation:

- `lead_distance_m = speed_mps * system_delay_s`

If speed is 14 m/s and delay is 0.40 s, lead distance is 5.6 m.
So spray is triggered before reaching patch centroid, not on top of it.

## 3. Implemented Software Components
- `pi_companion.planning.multi_patch_planner.MultiPatchPlanner`
- `pi_companion.multi_patch_demo.run_demo`

Planner responsibilities:
1. Deduplicate repeated detections into stable patch points.
2. Cluster close points into patch clusters.
3. Build spray legs with entry/spray/exit waypoints.
4. Sequence route order with distance + turn-cost + priority heuristic.
5. Decide spray on each tick using heading alignment + lead window.

## 4. Multi-Patch Mission Logic (Operational)
1. Perception emits geotagged projected targets.
2. Planner ingests projected targets and updates patch map.
3. Planner clusters map and computes spray legs.
4. Route planner orders legs for fixed-wing feasibility.
5. In flight, at each control tick:
   - if active leg exists and target is heading-aligned,
   - if distance to target is inside lead window,
   - then emit spray command,
   - else hold and continue.
6. If leg is passed or empty, mark complete and move to next leg.

## 5. Demo Steps
From repository root:

1. Install package in editable mode:
   - `"C:/Program Files/Python313/python.exe" -m pip install -e ".\pi-companion[dev]"`
2. Run demo:
   - `"C:/Program Files/Python313/python.exe" -m pi_companion.multi_patch_demo`

Expected output:
- patch, cluster, and leg counts,
- ordered spray legs,
- tick-by-tick `SPRAY` or `HOLD` decisions with reasons,
- generated `multi_patch_demo.geojson` file.

## 6. How To Present It
1. Explain why fixed-wing requires leg-based mission logic.
2. Show clustered patch map (GeoJSON in GIS viewer).
3. Show planned leg sequence and heading.
4. Show lead-distance timing decisions from console output.
5. Show that system holds spray when heading/timing are not valid.

## 7. Safety Notes For Real Demo
- Keep manual override active and tested.
- Use colored water for first field trials.
- Start with patch-level zones, not single-leaf spot spraying.
- Validate valve and pump response time before airborne spraying.

## 8. Next Practical Upgrade
- Feed active leg waypoints directly into ArduPilot mission item stream.
- Consume emergency queue from offline ground station in Pi control loop.
- Add revisit queue prioritization by confidence and proximity.
