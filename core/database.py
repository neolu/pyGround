# core/database.py
"""SQLite 存储与检索无人机记录。"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_db_path(data_dir: str | Path) -> Path:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    return Path(data_dir) / "drones.db"


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drone_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            drone_id TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            alt REAL NOT NULL,
            speed REAL,
            heading REAL,
            raw TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drone_ts ON drone_records(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drone_id ON drone_records(drone_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drone_lat_lon ON drone_records(lat, lon)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            start_ts REAL NOT NULL,
            end_ts REAL NOT NULL,
            drone_id TEXT NOT NULL DEFAULT '1:1',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES trajectory_runs(id) ON DELETE CASCADE,
            ts REAL NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            alt REAL NOT NULL,
            roll REAL, pitch REAL, yaw REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_traj_run_id ON trajectory_points(run_id)")
    conn.commit()


def insert_record(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    import time
    ts = record.get("ts") or time.time()
    conn.execute(
        """INSERT INTO drone_records (ts, drone_id, lat, lon, alt, speed, heading, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ts,
            record.get("drone_id", ""),
            record["lat"],
            record["lon"],
            record.get("alt", 0),
            record.get("speed", 0),
            record.get("heading", 0),
            record.get("raw", ""),
        ),
    )
    conn.commit()


def search(
    conn: sqlite3.Connection,
    *,
    time_from: float | None = None,
    time_to: float | None = None,
    drone_id: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
    limit: int = 1000,
) -> list[dict]:
    q = "SELECT ts, drone_id, lat, lon, alt, speed, heading, raw FROM drone_records WHERE 1=1"
    params: list = []
    if time_from is not None:
        q += " AND ts >= ?"
        params.append(time_from)
    if time_to is not None:
        q += " AND ts <= ?"
        params.append(time_to)
    if drone_id:
        q += " AND drone_id = ?"
        params.append(drone_id)
    if lat_min is not None:
        q += " AND lat >= ?"
        params.append(lat_min)
    if lat_max is not None:
        q += " AND lat <= ?"
        params.append(lat_max)
    if lon_min is not None:
        q += " AND lon >= ?"
        params.append(lon_min)
    if lon_max is not None:
        q += " AND lon <= ?"
        params.append(lon_max)
    q += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(q, params)
    rows = cur.fetchall()
    return [
        {
            "ts": r[0],
            "drone_id": r[1],
            "lat": r[2],
            "lon": r[3],
            "alt": r[4],
            "speed": r[5],
            "heading": r[6],
            "raw": r[7],
        }
        for r in rows
    ]


# ---------- 轨迹记录（一次运行的轨迹与姿态）---------

def trajectory_list_runs(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """返回轨迹记录列表 [{id, name, start_ts, end_ts, drone_id, created_at}, ...]，按创建时间倒序。"""
    cur = conn.execute(
        "SELECT id, name, start_ts, end_ts, drone_id, created_at FROM trajectory_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [
        {"id": r[0], "name": r[1] or "", "start_ts": r[2], "end_ts": r[3], "drone_id": r[4] or "1:1", "created_at": r[5] or ""}
        for r in cur.fetchall()
    ]


def trajectory_insert_run(
    conn: sqlite3.Connection,
    name: str,
    start_ts: float,
    end_ts: float,
    drone_id: str = "1:1",
) -> int:
    """插入一条轨迹记录，返回 id。"""
    cur = conn.execute(
        "INSERT INTO trajectory_runs (name, start_ts, end_ts, drone_id) VALUES (?, ?, ?, ?)",
        (name or "", start_ts, end_ts, drone_id),
    )
    conn.commit()
    return cur.lastrowid


def trajectory_insert_points(
    conn: sqlite3.Connection,
    run_id: int,
    points: list[tuple[float, float, float, float, float, float, float]],
) -> None:
    """批量插入轨迹点，每项 (ts, lat, lon, alt, roll, pitch, yaw)。"""
    conn.executemany(
        "INSERT INTO trajectory_points (run_id, ts, lat, lon, alt, roll, pitch, yaw) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, p[0], p[1], p[2], p[3], p[4], p[5], p[6]) for p in points],
    )
    conn.commit()


def trajectory_delete_run(conn: sqlite3.Connection, run_id: int) -> None:
    """删除一条轨迹记录及其所有点。"""
    conn.execute("DELETE FROM trajectory_points WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM trajectory_runs WHERE id = ?", (run_id,))
    conn.commit()


def trajectory_get_points(
    conn: sqlite3.Connection,
    run_id: int,
) -> list[dict]:
    """返回某次轨迹的所有点，按 ts 升序。"""
    cur = conn.execute(
        "SELECT ts, lat, lon, alt, roll, pitch, yaw FROM trajectory_points WHERE run_id = ? ORDER BY ts",
        (run_id,),
    )
    return [
        {"ts": r[0], "lat": r[1], "lon": r[2], "alt": r[3], "roll": r[4], "pitch": r[5], "yaw": r[6]}
        for r in cur.fetchall()
    ]


