# Arduino Pump Controller

Firmware for pump and valve actuation with a strict serial protocol.

## Behavior
- Parses framed commands from Pi
- Controls pump PWM and valve pin
- Emits heartbeat status every 200 ms
- Forces pump OFF on heartbeat timeout or emergency stop
