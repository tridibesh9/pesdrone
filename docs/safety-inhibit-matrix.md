# Safety Inhibit Matrix

## Hard Inhibits
Any true condition below must block spray command emission:

- `mode_not_auto`: flight mode is not AUTO
- `manual_override`: pilot override or emergency stop is active
- `geofence_breach`: mission boundary is violated
- `battery_low_reserve`: battery is below return-to-home reserve
- `gps_invalid`: no valid GPS fix
- `depth_stale`: depth sensor data stale past timeout
- `camera_stale`: camera frame stale past timeout
- `fc_link_lost`: flight controller heartbeat timeout
- `arduino_link_lost`: Arduino heartbeat timeout
- `mission_not_armed`: mission state does not allow spray

## Soft Constraints
Soft constraints do not block by themselves but reduce confidence and may trigger local throttling:

- `high_latency`
- `high_cpu_temp`
- `dropped_frames`

## Required Logging
Every deny decision must log:
- timestamp
- mission state
- inhibit reason codes (list)
- latest telemetry summary
