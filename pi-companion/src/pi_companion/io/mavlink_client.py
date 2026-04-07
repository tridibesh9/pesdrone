from __future__ import annotations

import time
from dataclasses import dataclass

from pi_companion.models import FlightMode, FlightTelemetry


@dataclass(slots=True)
class _TelemetryCache:
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0
    yaw_deg: float = 0.0
    battery_pct: float = 100.0
    gps_valid: bool = False
    mode: FlightMode = FlightMode.UNKNOWN
    geofence_breach: bool = False
    heartbeat_last_ms: int = 0


class MavlinkClient:
    """
    Lightweight message adapter for development and testing.

    In production, replace the ingest path with pymavlink transport handlers.
    """

    def __init__(self) -> None:
        self._cache = _TelemetryCache()

    def ingest_message(self, message: dict) -> None:
        msg_type = message.get("type", "")
        now_ms = _now_ms()

        if msg_type == "HEARTBEAT":
            self._cache.mode = _to_mode(str(message.get("mode", "UNKNOWN")))
            self._cache.heartbeat_last_ms = now_ms
            return

        if msg_type == "GLOBAL_POSITION_INT":
            self._cache.lat = float(message.get("lat", self._cache.lat))
            self._cache.lon = float(message.get("lon", self._cache.lon))
            self._cache.alt_m = float(message.get("alt_m", self._cache.alt_m))
            return

        if msg_type == "ATTITUDE":
            self._cache.yaw_deg = float(message.get("yaw_deg", self._cache.yaw_deg))
            return

        if msg_type == "BATTERY_STATUS":
            self._cache.battery_pct = float(
                message.get("battery_pct", self._cache.battery_pct)
            )
            return

        if msg_type == "GPS_RAW_INT":
            self._cache.gps_valid = bool(message.get("gps_valid", self._cache.gps_valid))
            return

        if msg_type == "SYS_STATUS":
            self._cache.geofence_breach = bool(
                message.get("geofence_breach", self._cache.geofence_breach)
            )

    def get_telemetry(self) -> FlightTelemetry:
        now_ms = _now_ms()
        heartbeat_age_ms = (
            now_ms - self._cache.heartbeat_last_ms
            if self._cache.heartbeat_last_ms > 0
            else 10_000
        )

        return FlightTelemetry(
            timestamp_ms=now_ms,
            lat=self._cache.lat,
            lon=self._cache.lon,
            alt_m=self._cache.alt_m,
            yaw_deg=self._cache.yaw_deg,
            battery_pct=self._cache.battery_pct,
            gps_valid=self._cache.gps_valid,
            mode=self._cache.mode,
            geofence_breach=self._cache.geofence_breach,
            fc_heartbeat_age_ms=heartbeat_age_ms,
        )


def _to_mode(raw_mode: str) -> FlightMode:
    cleaned = raw_mode.upper()
    if cleaned in FlightMode._value2member_map_:
        return FlightMode(cleaned)
    return FlightMode.UNKNOWN


def _now_ms() -> int:
    return int(time.time() * 1000)
