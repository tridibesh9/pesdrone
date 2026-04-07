# Test Gates Before Outdoor Flight

## Contract and Protocol Gates
- Pi-Arduino frame parser passes valid/invalid packet tests.
- Checksum mismatch, length mismatch, and invalid start-byte cases are rejected.
- Heartbeat timeout triggers pump-off behavior.

## Safety Gates
- Spray denied when mode is not AUTO.
- Spray denied on geofence breach, battery reserve breach, GPS invalid, or manual override.
- Spray denied on stale camera/depth data and heartbeat loss.
- Every deny action logs reason codes.

## Perception Gates
- End-to-end perception loop output latency p95 <= 150 ms on Pi 5 test profile.
- Detection precision and recall tracked on labeled clips.
- Thermal degrade policy engaged before unsafe latency growth.

## Simulation Gates
- SITL scenarios pass: nominal mission, comm loss, low battery, geofence breach, manual override.
- No unsafe spray command is emitted in any failsafe scenario.

## HIL Gates
- Real Pi + Arduino with injected packet faults demonstrates watchdog and emergency stop behavior.
- No actuator command passes when safety supervisor denies.
