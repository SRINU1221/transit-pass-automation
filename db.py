"""
db.py — PostgreSQL database layer for plant credentials
Database: automationDB
Table:    rayalty (plant_name, username, password, pdf_save_folder)
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

# ── Connection URL ─────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/automationDB"
)

# ── Table DDL ─────────────────────────────────────────────────────────────────
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS rayalty (
    id               SERIAL PRIMARY KEY,
    plant_name       VARCHAR(100) UNIQUE NOT NULL,
    username         VARCHAR(100) NOT NULL,
    password         VARCHAR(200) NOT NULL,
    pdf_save_folder  VARCHAR(500) NOT NULL,
    is_active        BOOLEAN      DEFAULT TRUE,
    created_at       TIMESTAMP    DEFAULT NOW(),
    updated_at       TIMESTAMP    DEFAULT NOW()
);
"""

# ── Connection ────────────────────────────────────────────────────────────────

def get_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(DB_URL)


def test_connection() -> tuple[bool, str]:
    """Test DB connectivity. Returns (ok, message)."""
    try:
        conn = get_connection()
        conn.close()
        return True, "✅ Connected to PostgreSQL successfully."
    except Exception as e:
        return False, f"❌ Connection failed: {e}"


def init_db() -> tuple[bool, str]:
    """Create the rayalty table if it doesn't exist."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(_CREATE_TABLE)
        conn.commit()
        cur.close()
        conn.close()
        return True, "✅ Database initialised."
    except Exception as e:
        return False, f"❌ DB init failed: {e}"


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_plants() -> list[dict]:
    """Return all active plants ordered by name."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM rayalty WHERE is_active = TRUE ORDER BY plant_name"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_plant(plant_name: str) -> Optional[dict]:
    """Return a single plant's credentials or None if not found."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM rayalty WHERE plant_name = %s",
            (plant_name,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def upsert_plant(
    plant_name: str,
    username: str,
    password: str,
    pdf_save_folder: str,
) -> tuple[bool, str]:
    """Insert or update a plant record. Returns (ok, message)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO rayalty (plant_name, username, password, pdf_save_folder)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (plant_name) DO UPDATE SET
                username        = EXCLUDED.username,
                password        = EXCLUDED.password,
                pdf_save_folder = EXCLUDED.pdf_save_folder,
                is_active       = TRUE,
                updated_at      = NOW()
        """, (plant_name, username, password, pdf_save_folder))
        conn.commit()
        cur.close()
        conn.close()
        return True, f"✅ Plant '{plant_name}' saved."
    except Exception as e:
        return False, f"❌ Save failed: {e}"


def delete_plant(plant_name: str) -> tuple[bool, str]:
    """Permanently delete a plant record."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM rayalty WHERE plant_name = %s", (plant_name,))
        conn.commit()
        cur.close()
        conn.close()
        return True, f"✅ Plant '{plant_name}' deleted."
    except Exception as e:
        return False, f"❌ Delete failed: {e}"


def set_active(plant_name: str, active: bool) -> tuple[bool, str]:
    """Toggle the is_active flag for a plant."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE rayalty SET is_active = %s, updated_at = NOW() WHERE plant_name = %s",
            (active, plant_name)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, f"✅ Plant '{plant_name}' {'activated' if active else 'deactivated'}."
    except Exception as e:
        return False, f"❌ Update failed: {e}"
