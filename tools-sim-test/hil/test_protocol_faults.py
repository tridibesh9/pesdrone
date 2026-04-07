from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi-companion" / "src"))

from pi_companion.io.arduino_client import (
    ArduinoClient,
    Command,
    ProtocolError,
    Status,
    build_frame,
    parse_frame,
)


def test_round_trip_frame() -> None:
    frame = build_frame(Command.SET_PUMP_PWM, bytes([150]))
    cmd, payload = parse_frame(frame)

    assert cmd == int(Command.SET_PUMP_PWM)
    assert payload == bytes([150])


def test_checksum_mismatch_rejected() -> None:
    frame = bytearray(build_frame(Command.PULSE_SPRAY_MS, bytes([0x00, 0x64])))
    frame[-1] ^= 0xFF

    with pytest.raises(ProtocolError):
        parse_frame(bytes(frame))


def test_status_ack_parse() -> None:
    ack_frame = build_frame(Status.ACK, bytes([int(Command.EMERGENCY_STOP)]))
    parsed = ArduinoClient.parse_status(ack_frame)

    assert parsed["type"] == int(Status.ACK)
    assert parsed["ack_cmd"] == int(Command.EMERGENCY_STOP)
