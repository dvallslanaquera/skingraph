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
from src.state import RoutineProduct, UserProfile

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

# Per-user "shelf" of products the user currently uses. ingredients is stored as
# a JSON list of canonical INCI names so a saved product can be re-audited
# against a new scan without re-running OCR.
_ROUTINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS routine_products (
    product_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    brand         TEXT,
    product_name  TEXT,
    ingredients   TEXT,
    is_quasi_drug INTEGER,
    added_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.execute(_ROUTINE_SCHEMA)
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


def get_user_name(user_id: str) -> Optional[str]:
    """Return the stored display name for a user id, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT name FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["name"] if row else None


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


# --- Routine ("shelf") of products a user currently uses --------------------


def _row_to_routine_product(row: sqlite3.Row) -> RoutineProduct:
    return RoutineProduct(
        product_id=row["product_id"],
        brand=row["brand"] or "",
        product_name=row["product_name"] or "",
        ingredients=json.loads(row["ingredients"]) if row["ingredients"] else [],
        is_quasi_drug=(
            bool(row["is_quasi_drug"]) if row["is_quasi_drug"] is not None else None
        ),
    )


def add_routine_product(
    user_id: str,
    brand: str,
    product_name: str,
    ingredients: List[str],
    is_quasi_drug: Optional[bool] = None,
) -> str:
    """Save a product into the user's routine. Returns its product_id.

    Dedupes on (user_id, lower(brand), lower(product_name)) — re-adding the same
    product refreshes its ingredient list instead of creating a duplicate row.
    """
    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT product_id FROM routine_products
            WHERE user_id = ? AND lower(brand) = ? AND lower(product_name) = ?
            """,
            (user_id, brand.strip().lower(), product_name.strip().lower()),
        ).fetchone()
        product_id = existing["product_id"] if existing else str(uuid4())

        conn.execute(
            """
            INSERT OR REPLACE INTO routine_products (
                product_id, user_id, brand, product_name, ingredients,
                is_quasi_drug, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                user_id,
                brand,
                product_name,
                json.dumps(ingredients),
                None if is_quasi_drug is None else int(is_quasi_drug),
                _now(),
            ),
        )
        conn.commit()
    return product_id


def get_routine(user_id: str) -> List[RoutineProduct]:
    """Return the user's saved routine products, most recently added first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM routine_products WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_routine_product(r) for r in rows]


def remove_routine_product(product_id: str) -> bool:
    """Delete a routine product by id. Returns True if a row was removed."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM routine_products WHERE product_id = ?", (product_id,)
        )
        conn.commit()
        return cur.rowcount > 0
