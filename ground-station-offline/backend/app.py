from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field


RUNTIME_DIR = Path(__file__).resolve().parents[2] / ".runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = RUNTIME_DIR / "ground_station.db"

app = FastAPI(title="FTL Offline Ground Station", version="0.1.0")


class TelemetryIn(BaseModel):
    timestamp_ms: int
    lat: float
    lon: float
    alt_m: float
    mode: str
    battery_pct: float
    gps_valid: bool
    inhibits: list[str] = Field(default_factory=list)


class SprayEventIn(BaseModel):
    timestamp_ms: int
    target_lat: float
    target_lon: float
    confidence: float
    duration_ms: int
    pump_pwm: int
    mission_state: str


class EmergencyCommandIn(BaseModel):
    issued_by: str = "operator"
    reason: str = "manual_emergency"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_ms INTEGER NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                alt_m REAL NOT NULL,
                mode TEXT NOT NULL,
                battery_pct REAL NOT NULL,
                gps_valid INTEGER NOT NULL,
                inhibits_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spray_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_ms INTEGER NOT NULL,
                target_lat REAL NOT NULL,
                target_lon REAL NOT NULL,
                confidence REAL NOT NULL,
                duration_ms INTEGER NOT NULL,
                pump_pwm INTEGER NOT NULL,
                mission_state TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                acknowledged INTEGER NOT NULL DEFAULT 0
            )
            """
        )


@app.on_event("startup")
def _startup() -> None:
    _init_db()


@app.get("/health")
def health() -> dict:
    with _connect() as conn:
        telemetry_count = conn.execute("SELECT COUNT(*) AS c FROM telemetry").fetchone()["c"]
        spray_count = conn.execute("SELECT COUNT(*) AS c FROM spray_events").fetchone()["c"]
        pending_commands = conn.execute(
            "SELECT COUNT(*) AS c FROM commands WHERE acknowledged = 0"
        ).fetchone()["c"]

    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "telemetry_rows": telemetry_count,
        "spray_rows": spray_count,
        "pending_commands": pending_commands,
    }


@app.post("/telemetry")
def ingest_telemetry(payload: TelemetryIn) -> dict:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO telemetry (
                timestamp_ms, lat, lon, alt_m, mode, battery_pct, gps_valid, inhibits_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.timestamp_ms,
                payload.lat,
                payload.lon,
                payload.alt_m,
                payload.mode,
                payload.battery_pct,
                1 if payload.gps_valid else 0,
                json.dumps(payload.inhibits),
            ),
        )
        row_id = cursor.lastrowid

    return {"accepted": True, "id": row_id}


@app.post("/spray-event")
def ingest_spray_event(payload: SprayEventIn) -> dict:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO spray_events (
                timestamp_ms, target_lat, target_lon, confidence, duration_ms, pump_pwm, mission_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.timestamp_ms,
                payload.target_lat,
                payload.target_lon,
                payload.confidence,
                payload.duration_ms,
                payload.pump_pwm,
                payload.mission_state,
            ),
        )
        row_id = cursor.lastrowid

    return {"accepted": True, "id": row_id}


@app.post("/command/emergency-spray-disable")
def emergency_disable(payload: EmergencyCommandIn) -> dict:
    body = {
        "issued_by": payload.issued_by,
        "reason": payload.reason,
    }
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO commands (command_type, payload_json)
            VALUES (?, ?)
            """,
            ("emergency_spray_disable", json.dumps(body)),
        )
        row_id = cursor.lastrowid

    return {"queued": True, "command_id": row_id}


@app.get("/commands/pending")
def get_pending_commands(limit: int = 20) -> dict:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, command_type, payload_json, created_at
            FROM commands
            WHERE acknowledged = 0
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    commands = [
        {
            "id": row["id"],
            "command_type": row["command_type"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {"commands": commands}
