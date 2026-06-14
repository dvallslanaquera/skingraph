# SQLite-backed store for user skincare profiles.
#
# Keeps personal data (age, gender, goals, conditions, pregnancy, etc.) in a
# local SQLite file so a returning user can be loaded by id instead of passing
# a JSON file every run. List fields (goals, skin_conditions) are stored as JSON
# text columns since SQLite has no native array type.
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import uuid4

from src.config import USER_DB_PATH
from src.state import UserProfile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id            TEXT PRIMARY KEY,
    name               TEXT,
    skin_type          TEXT,
    age                INTEGER,
    gender             TEXT,
    goals              TEXT,
    is_pregnant        INTEGER NOT NULL DEFAULT 0,
    skin_conditions    TEXT,
    sun_damage_history TEXT,
    routine_time       TEXT,
    budget             TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def init_db() -> None:
    """Create the users table if it does not exist."""
    with _connect() as conn:
        conn.commit()


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        skin_type=row["skin_type"],
        age=row["age"],
        gender=row["gender"],
        goals=json.loads(row["goals"]) if row["goals"] else [],
        is_pregnant=bool(row["is_pregnant"]),
        skin_conditions=(
            json.loads(row["skin_conditions"]) if row["skin_conditions"] else []
        ),
        sun_damage_history=row["sun_damage_history"],
        routine_time=row["routine_time"],
        budget=row["budget"],
    )


def save_user(
    profile: UserProfile,
    name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Insert a new profile or update an existing one. Returns the user_id.

    When user_id is given and already exists, the original created_at is kept and
    updated_at is refreshed; otherwise a new UUID is generated.
    """
    now = _now()
    with _connect() as conn:
        created_at = now
        if user_id:
            existing = conn.execute(
                "SELECT created_at FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                created_at = existing["created_at"]
        else:
            user_id = str(uuid4())

        conn.execute(
            """
            INSERT OR REPLACE INTO users (
                user_id, name, skin_type, age, gender, goals, is_pregnant,
                skin_conditions, sun_damage_history, routine_time, budget,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                profile.skin_type,
                profile.age,
                profile.gender,
                json.dumps(profile.goals),
                int(profile.is_pregnant),
                json.dumps(profile.skin_conditions),
                profile.sun_damage_history,
                profile.routine_time,
                profile.budget,
                created_at,
                now,
            ),
        )
        conn.commit()
    return user_id


def get_user(user_id: str) -> Optional[UserProfile]:
    """Load a profile by id, or None if it does not exist."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _row_to_profile(row) if row else None


def list_users() -> List[Tuple[str, Optional[str]]]:
    """Return (user_id, name) pairs, most recently updated first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_id, name FROM users ORDER BY updated_at DESC"
        ).fetchall()
    return [(r["user_id"], r["name"]) for r in rows]


def list_users_with_profiles() -> List[Tuple[str, Optional[str], UserProfile]]:
    """Return (user_id, name, profile) tuples, most recently updated first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY updated_at DESC"
        ).fetchall()
    return [(r["user_id"], r["name"], _row_to_profile(r)) for r in rows]


def delete_user(user_id: str) -> bool:
    """Delete a profile by id. Returns True if a row was removed."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0
