# SQLite-backed store for user skincare profiles.
#
# Keeps personal data (age, gender, goals, conditions, pregnancy, etc.) in a
# local SQLite file so a returning user can be loaded by id instead of passing
# a JSON file every run. List fields (goals, skin_conditions) are stored as JSON
# text columns since SQLite has no native array type.
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from src.config import USER_DB_PATH
from src.state import RoutineProduct, UserProfile, inci_names


class UserNotFoundError(Exception):
    """Raised when a scan/routine call references an unknown user_id."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"No user found with id: {user_id}")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id            TEXT PRIMARY KEY,
    name               TEXT,
    skin_type          TEXT,
    age                INTEGER,
    gender             TEXT,
    fitzpatrick        INTEGER,
    skin_undertone     TEXT,
    goals              TEXT,
    is_pregnant        INTEGER NOT NULL DEFAULT 0,
    skin_conditions    TEXT,
    sun_damage_history TEXT,
    routine_time       TEXT,
    consider_devices   INTEGER NOT NULL DEFAULT 0,
    budget             TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
"""

# Columns added after the initial release. Applied with ALTER TABLE on connect so
# databases created by an earlier version pick up the new profile fields without a
# manual migration. SQLite ignores the rest of the row when adding a column.
_USER_COLUMNS_ADDED = {
    "fitzpatrick": "INTEGER",
    "skin_undertone": "TEXT",
    "consider_devices": "INTEGER NOT NULL DEFAULT 0",
}


def _migrate_users(conn: sqlite3.Connection) -> None:
    """Add any profile columns missing from an older ``users`` table."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    for column, ddl in _USER_COLUMNS_ADDED.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {ddl}")


# Per-user "shelf" of products the user currently uses. ingredients is stored as
# a JSON list of canonical INCI names so a saved product can be re-audited
# against a new scan without re-running OCR.
_ROUTINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS routine_products (
    product_id        TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    brand             TEXT,
    product_name      TEXT,
    ingredients       TEXT,
    is_quasi_drug     INTEGER,
    timing            TEXT,
    application_notes TEXT,
    application_notes_ja TEXT,
    price_usd         REAL,
    price_native      REAL,
    price_currency    TEXT,
    price_market      TEXT,
    months_supply     REAL,
    price_source      TEXT,
    added_at          TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""

# Routine columns added after the initial release (per-product timing, application
# notes, and price metadata). Applied with ALTER TABLE on connect, mirroring
# _USER_COLUMNS_ADDED, so older databases pick them up without a manual migration.
_ROUTINE_COLUMNS_ADDED = {
    "timing": "TEXT",
    "application_notes": "TEXT",
    "application_notes_ja": "TEXT",
    "price_usd": "REAL",
    "price_native": "REAL",
    "price_currency": "TEXT",
    "price_market": "TEXT",
    "months_supply": "REAL",
    "price_source": "TEXT",
}


def _migrate_routine(conn: sqlite3.Connection) -> None:
    """Add any columns missing from an older ``routine_products`` table."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(routine_products)")}
    for column, ddl in _ROUTINE_COLUMNS_ADDED.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE routine_products ADD COLUMN {column} {ddl}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Flipped by init_db() after the first run so the DDL + PRAGMA migrations cost
# nothing on subsequent connections. Tests reset it when repointing USER_DB_PATH.
_initialized = False


def init_db() -> None:
    """Create the tables and apply column migrations, once per process."""
    global _initialized
    if _initialized:
        return
    conn = sqlite3.connect(USER_DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(_SCHEMA)
        _migrate_users(conn)
        conn.execute(_ROUTINE_SCHEMA)
        _migrate_routine(conn)
        conn.commit()
    finally:
        conn.close()
    _initialized = True


def _connect() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Legacy categorical budgets, mapped to a representative monthly USD figure so a
# profile saved before the slider still loads as a number.
_LEGACY_BUDGET_USD = {"budget": 25, "mid-range": 75, "premium": 200}


def _coerce_budget(value) -> int | None:
    """Read a budget column (int, numeric str, or legacy category) as USD int."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return _LEGACY_BUDGET_USD.get(text.lower())


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        skin_type=row["skin_type"],
        age=row["age"],
        gender=row["gender"],
        fitzpatrick=row["fitzpatrick"],
        skin_undertone=row["skin_undertone"],
        goals=json.loads(row["goals"]) if row["goals"] else [],
        is_pregnant=bool(row["is_pregnant"]),
        skin_conditions=(json.loads(row["skin_conditions"]) if row["skin_conditions"] else []),
        sun_damage_history=row["sun_damage_history"],
        routine_time=row["routine_time"],
        consider_devices=bool(row["consider_devices"]),
        budget=_coerce_budget(row["budget"]),
    )


def save_user(
    profile: UserProfile,
    name: str | None = None,
    user_id: str | None = None,
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
                user_id, name, skin_type, age, gender, fitzpatrick,
                skin_undertone, goals, is_pregnant, skin_conditions,
                sun_damage_history, routine_time, consider_devices, budget,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                profile.skin_type,
                profile.age,
                profile.gender,
                profile.fitzpatrick,
                profile.skin_undertone,
                json.dumps(profile.goals),
                int(profile.is_pregnant),
                json.dumps(profile.skin_conditions),
                profile.sun_damage_history,
                profile.routine_time,
                int(profile.consider_devices),
                None if profile.budget is None else str(profile.budget),
                created_at,
                now,
            ),
        )
        conn.commit()
    return user_id


def get_user(user_id: str) -> UserProfile | None:
    """Load a profile by id, or None if it does not exist."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_profile(row) if row else None


def get_user_name(user_id: str) -> str | None:
    """Return the stored display name for a user id, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT name FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else None


def list_users() -> list[tuple[str, str | None]]:
    """Return (user_id, name) pairs, most recently updated first."""
    with _connect() as conn:
        rows = conn.execute("SELECT user_id, name FROM users ORDER BY updated_at DESC").fetchall()
    return [(r["user_id"], r["name"]) for r in rows]


def list_users_with_profiles() -> list[tuple[str, str | None, UserProfile]]:
    """Return (user_id, name, profile) tuples, most recently updated first."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY updated_at DESC").fetchall()
    return [(r["user_id"], r["name"], _row_to_profile(r)) for r in rows]


def delete_user(user_id: str) -> bool:
    """Delete a profile by id. Returns True if a row was removed."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0


# --- Routine ("shelf") of products a user currently uses --------------------


def _row_to_routine_product(row: sqlite3.Row) -> RoutineProduct:
    # All columns are guaranteed present: init_db() applies the ALTER TABLE
    # migrations before any query runs.
    return RoutineProduct(
        product_id=row["product_id"],
        brand=row["brand"] or "",
        product_name=row["product_name"] or "",
        ingredients=json.loads(row["ingredients"]) if row["ingredients"] else [],
        is_quasi_drug=(bool(row["is_quasi_drug"]) if row["is_quasi_drug"] is not None else None),
        timing=row["timing"],
        application_notes=(
            json.loads(row["application_notes"]) if row["application_notes"] else []
        ),
        application_notes_ja=(
            json.loads(row["application_notes_ja"]) if row["application_notes_ja"] else []
        ),
        price_usd=row["price_usd"],
        price_native=row["price_native"],
        price_currency=row["price_currency"],
        price_market=row["price_market"],
        months_supply=row["months_supply"],
        price_source=row["price_source"],
    )


def add_routine_product(
    user_id: str,
    brand: str,
    product_name: str,
    ingredients: list[str],
    is_quasi_drug: bool | None = None,
    *,
    timing: str | None = None,
    application_notes: list[str] | None = None,
    application_notes_ja: list[str] | None = None,
    price_usd: float | None = None,
    price_native: float | None = None,
    price_currency: str | None = None,
    price_market: str | None = None,
    months_supply: float | None = None,
    price_source: str | None = None,
) -> str:
    """Save a product into the user's routine. Returns its product_id.

    Dedupes on (user_id, lower(brand), lower(product_name)) — re-adding the same
    product refreshes its ingredient list instead of creating a duplicate row.
    The timing / application_notes / price_* fields are optional metadata set when
    a product is added via a scan; manual adds leave them as their defaults.
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
                is_quasi_drug, timing, application_notes, application_notes_ja,
                price_usd, price_native,
                price_currency, price_market, months_supply, price_source, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                user_id,
                brand,
                product_name,
                json.dumps(ingredients),
                None if is_quasi_drug is None else int(is_quasi_drug),
                timing,
                json.dumps(application_notes or []),
                json.dumps(application_notes_ja or []),
                price_usd,
                price_native,
                price_currency,
                price_market,
                months_supply,
                price_source,
                _now(),
            ),
        )
        conn.commit()
    return product_id


def get_routine(user_id: str) -> list[RoutineProduct]:
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
        cur = conn.execute("DELETE FROM routine_products WHERE product_id = ?", (product_id,))
        conn.commit()
        return cur.rowcount > 0


# --- shared entry-point helpers (used by both the CLI and the API) ----------


def load_user_context(
    user_id: str,
) -> tuple[UserProfile, str | None, list[RoutineProduct]]:
    """Load a saved user's (profile, name, routine), or raise UserNotFoundError.

    Single source of truth for the "run as a saved user" lookup shared by the
    CLI and the API service.
    """
    profile = get_user(user_id)
    if profile is None:
        raise UserNotFoundError(user_id)
    return profile, get_user_name(user_id), get_routine(user_id)


def save_scanned_product(user_id: str, final_state: dict) -> str | None:
    """Persist a scanned product to the user's shelf; return its product_id.

    Returns None (saves nothing) when the scan didn't yield a usable product, so
    the CLI's --add-to-routine and the API's add_to_routine behave identically.

    Carries the coach's per-product timing + application notes onto the shelf row,
    and does a best-effort web price lookup so the routine dashboard can show an
    amortized monthly cost. A failed price lookup never blocks the save.
    """
    data = final_state.get("extracted_data")
    if not final_state.get("is_ready_for_logic") or data is None:
        return None
    inci = inci_names(final_state.get("standardized_ingredients"))

    cards = final_state.get("coach_cards")
    timing = (cards.english.timing or None) if cards else None
    application_notes = list(cards.english.application_notes) if cards else []
    application_notes_ja = list(cards.japanese.application_notes) if cards else []

    price = _lookup_price_safe(data.brand, data.product_name)

    return add_routine_product(
        user_id,
        data.brand,
        data.product_name,
        inci,
        data.is_quasi_drug,
        timing=timing,
        application_notes=application_notes,
        application_notes_ja=application_notes_ja,
        price_usd=price.price_usd if price else None,
        price_native=price.price_native if price else None,
        price_currency=price.currency if price else None,
        price_market=price.market if price else None,
        months_supply=price.months_supply if price else None,
        price_source=price.source if price else None,
    )


def _lookup_price_safe(brand: str, product_name: str):
    """Best-effort web price lookup; returns a PriceInfo or None on any failure.

    Imported lazily so the heavy LLM/grounding stack is only loaded when a scan
    is actually being saved (and so a missing API key degrades to no price rather
    than an import error).
    """
    try:
        from src.pricing import lookup_price

        return lookup_price(brand, product_name)
    except Exception:  # pragma: no cover - network/LLM failures are non-fatal
        import logging

        logging.warning("Price lookup failed for %s — %s", brand, product_name)
        return None
