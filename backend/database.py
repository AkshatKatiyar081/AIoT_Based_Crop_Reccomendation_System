import sqlite3
import os
from config import DATABASE_PATH


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    """Create all required tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            region        TEXT    NOT NULL,
            soil_type     TEXT    DEFAULT '',
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS crop_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            crop_name        TEXT    NOT NULL,
            reason           TEXT    DEFAULT '',
            harvest_duration TEXT    DEFAULT '',
            planting_month   TEXT    DEFAULT '',
            harvest_month    TEXT    DEFAULT '',
            date_recorded    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    # Schema Migrations
    for column in ("planting_cost_per_hectare", "total_cost", "taluka", "soil_snapshot"):
        try:
            cursor.execute(f"ALTER TABLE crop_history ADD COLUMN {column} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()


# ─── User helpers ─────────────────────────────────────────────────────────────

def get_user_by_email(email: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id: int):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def add_user(name: str, email: str, password_hash: str, region: str, soil_type: str = ""):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash, region, soil_type) VALUES (?, ?, ?, ?, ?)",
            (name, email, password_hash, region, soil_type),
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # Email already exists


# ─── Crop history helpers ─────────────────────────────────────────────────────

def get_crop_history(user_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM crop_history WHERE user_id = ? ORDER BY date_recorded DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_crop_history(user_id: int, crop_name: str, reason: str = "",
                     harvest_duration: str = "", planting_month: str = "",
                     harvest_month: str = "", planting_cost: str = "", total_cost: str = "",
                     taluka: str = "", soil_snapshot: str = ""):
    conn = get_db()
    conn.execute(
        """INSERT INTO crop_history
           (user_id, crop_name, reason, harvest_duration, planting_month, harvest_month,
            planting_cost_per_hectare, total_cost, taluka, soil_snapshot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, crop_name, reason, harvest_duration, planting_month, harvest_month,
         planting_cost, total_cost, taluka, soil_snapshot),
    )
    conn.commit()
    entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return entry_id


def delete_crop_history(entry_id: int, user_id: int) -> bool:
    """Delete one of the user's history entries; returns False if it didn't exist."""
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM crop_history WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0
