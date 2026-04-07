# Pi-Arduino Serial Protocol

## Frame Format
`[START][CMD][LEN][PAYLOAD...][CHECKSUM]`

- START: `0xAA`
- CMD: 1 byte command code
- LEN: payload length in bytes
- PAYLOAD: command specific bytes
- CHECKSUM: XOR of CMD, LEN, and all payload bytes

## Commands (Pi -> Arduino)
- `0x01` SET_PUMP_PWM: payload `[0..255]`
- `0x02` PULSE_SPRAY_MS: payload `[u16_be duration_ms]`
- `0x03` VALVE_ON_OFF: payload `[0|1]`
- `0x04` HEARTBEAT_REQUEST: empty payload
- `0x05` EMERGENCY_STOP: empty payload

## Status Frames (Arduino -> Pi)
- `0x81` HEARTBEAT_STATUS: payload `[state][fault_code][pump_pwm]`
- `0x82` ACK: payload `[ack_cmd]`
- `0x83` NACK: payload `[nack_cmd][error_code]`

## Safety Rule
Arduino must default to pump OFF on parser errors, heartbeat timeout, or emergency stop.
