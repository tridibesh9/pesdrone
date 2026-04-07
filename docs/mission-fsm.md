# Mission FSM

## States
- IDLE
- PREFLIGHT_CHECKS
- ARMED
- AUTO_SCAN
- TARGET_CONFIRMED
- SPRAY_WINDOW
- RTH
- FAILSAFE
- LANDED

## Transition Rules
- IDLE -> PREFLIGHT_CHECKS when mission is loaded.
- PREFLIGHT_CHECKS -> ARMED when all required health checks pass.
- ARMED -> AUTO_SCAN when operator starts autonomous mission.
- AUTO_SCAN -> TARGET_CONFIRMED when confidence threshold is met and detection age passes minimum.
- TARGET_CONFIRMED -> SPRAY_WINDOW when geotag projection and timing are valid.
- SPRAY_WINDOW -> AUTO_SCAN after spray pulse or explicit deny from safety supervisor.
- Any state -> FAILSAFE when watchdog, geofence, battery, or link fault occurs.
- FAILSAFE -> RTH when FC accepts return command.
- RTH -> LANDED when landing confirmed.

## Guard Conditions
- Spray can be requested only in SPRAY_WINDOW.
- Spray can be emitted only when safety supervisor returns ALLOW.
- Manual override always forces transition to FAILSAFE or non-spray mode.
