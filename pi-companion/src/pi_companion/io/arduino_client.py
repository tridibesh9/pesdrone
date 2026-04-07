from __future__ import annotations

from enum import IntEnum
from typing import Protocol


START_BYTE = 0xAA


class Command(IntEnum):
    SET_PUMP_PWM = 0x01
    PULSE_SPRAY_MS = 0x02
    VALVE_ON_OFF = 0x03
    HEARTBEAT_REQUEST = 0x04
    EMERGENCY_STOP = 0x05


class Status(IntEnum):
    HEARTBEAT_STATUS = 0x81
    ACK = 0x82
    NACK = 0x83


class Transport(Protocol):
    def write(self, payload: bytes) -> int:  # pragma: no cover - interface
        ...


class ProtocolError(RuntimeError):
    pass


def _checksum(cmd: int, payload: bytes) -> int:
    value = cmd ^ len(payload)
    for byte in payload:
        value ^= byte
    return value & 0xFF


def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    if len(payload) > 255:
        raise ValueError("payload too large")
    checksum = _checksum(cmd, payload)
    return bytes([START_BYTE, cmd, len(payload)]) + payload + bytes([checksum])


def parse_frame(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 4:
        raise ProtocolError("frame too short")
    if frame[0] != START_BYTE:
        raise ProtocolError("invalid start byte")

    cmd = frame[1]
    length = frame[2]
    expected_len = 4 + length
    if len(frame) != expected_len:
        raise ProtocolError("invalid frame length")

    payload = frame[3 : 3 + length]
    checksum = frame[-1]
    expected_checksum = _checksum(cmd, payload)
    if checksum != expected_checksum:
        raise ProtocolError("checksum mismatch")

    return cmd, payload


class ArduinoClient:
    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport

    def send(self, cmd: Command, payload: bytes = b"") -> bytes:
        frame = build_frame(int(cmd), payload)
        if self.transport is not None:
            self.transport.write(frame)
        return frame

    def set_pump_pwm(self, pwm: int) -> bytes:
        if pwm < 0 or pwm > 255:
            raise ValueError("pwm must be in range [0, 255]")
        return self.send(Command.SET_PUMP_PWM, bytes([pwm]))

    def pulse_spray(self, duration_ms: int) -> bytes:
        if duration_ms <= 0 or duration_ms > 5000:
            raise ValueError("duration_ms must be in range [1, 5000]")
        payload = duration_ms.to_bytes(2, byteorder="big", signed=False)
        return self.send(Command.PULSE_SPRAY_MS, payload)

    def set_valve(self, on: bool) -> bytes:
        return self.send(Command.VALVE_ON_OFF, bytes([1 if on else 0]))

    def request_heartbeat(self) -> bytes:
        return self.send(Command.HEARTBEAT_REQUEST)

    def emergency_stop(self) -> bytes:
        return self.send(Command.EMERGENCY_STOP)

    @staticmethod
    def parse_status(frame: bytes) -> dict[str, int]:
        cmd, payload = parse_frame(frame)

        if cmd == Status.HEARTBEAT_STATUS:
            if len(payload) != 3:
                raise ProtocolError("heartbeat status payload must be 3 bytes")
            return {
                "type": int(Status.HEARTBEAT_STATUS),
                "state": payload[0],
                "fault_code": payload[1],
                "pump_pwm": payload[2],
            }

        if cmd == Status.ACK:
            if len(payload) != 1:
                raise ProtocolError("ack payload must be 1 byte")
            return {"type": int(Status.ACK), "ack_cmd": payload[0]}

        if cmd == Status.NACK:
            if len(payload) != 2:
                raise ProtocolError("nack payload must be 2 bytes")
            return {
                "type": int(Status.NACK),
                "nack_cmd": payload[0],
                "error_code": payload[1],
            }

        raise ProtocolError("unknown status frame")
