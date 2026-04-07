# MAVLink Contract (Pi <-> Flight Controller)

## Incoming Telemetry (FC -> Pi)
- HEARTBEAT
- GLOBAL_POSITION_INT
- GPS_RAW_INT
- ATTITUDE
- BATTERY_STATUS
- SYS_STATUS
- MISSION_CURRENT

## Outgoing Commands (Pi -> FC)
- SET_MODE (AUTO, RTL)
- MISSION upload primitives
- Optional: command_long for failsafe triggers

## Minimum Tick Expectations
- HEARTBEAT at least 1 Hz
- Position and attitude 5 to 10 Hz
- Battery and system status 1 to 2 Hz

## Link Failure Rule
If heartbeat is stale for more than configured timeout, Pi must:
1. inhibit spray immediately
2. transition mission orchestrator to FAILSAFE
3. request RTL when link recovers
