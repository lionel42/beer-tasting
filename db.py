"""SQLite storage. Ratings are stored in long format: one row per (participant, beer)."""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "tasting.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS beers (
    id       INTEGER PRIMARY KEY,
    position INTEGER NOT NULL,          -- tasting order
    name     TEXT NOT NULL,
    brewery  TEXT,
    style    TEXT,
    abv      REAL,
    ibu      REAL,
    price    REAL
);
CREATE TABLE IF NOT EXISTS ratings (
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    beer_id        INTEGER NOT NULL REFERENCES beers(id) ON DELETE CASCADE,
    score          REAL NOT NULL CHECK (score BETWEEN 1 AND 10),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (participant_id, beer_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

BEER_FIELDS = ["position", "name", "brewery", "style", "abv", "ibu", "price"]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


# --- participants -----------------------------------------------------------

def participants() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql("SELECT id, name FROM participants ORDER BY id", conn)


def add_participant(name: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO participants (name) VALUES (?)", (name,))


def rename_participant(pid: int, name: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE participants SET name = ? WHERE id = ?", (name, pid))


def delete_participant(pid: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM participants WHERE id = ?", (pid,))


# --- beers ------------------------------------------------------------------

def beers() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(
            f"SELECT id, {', '.join(BEER_FIELDS)} FROM beers ORDER BY position, id", conn
        )


def add_beer(**fields) -> None:
    with connect() as conn:
        if fields.get("position") is None:
            fields["position"] = conn.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM beers"
            ).fetchone()[0]
        cols = [f for f in BEER_FIELDS if f in fields]
        conn.execute(
            f"INSERT INTO beers ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [fields[c] for c in cols],
        )


def update_beer(bid: int, **fields) -> None:
    # Clearing the order or name cell keeps the old value instead of breaking NOT NULL
    cols = [f for f in BEER_FIELDS
            if f in fields and not (f in ("position", "name") and fields[f] is None)]
    if not cols:
        return
    with connect() as conn:
        conn.execute(
            f"UPDATE beers SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
            [fields[c] for c in cols] + [bid],
        )


def delete_beer(bid: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM beers WHERE id = ?", (bid,))


# --- ratings ----------------------------------------------------------------

def ratings() -> pd.DataFrame:
    """Long format, joined with names: participant_id, participant, beer_id, score."""
    with connect() as conn:
        return pd.read_sql(
            """SELECT r.participant_id, p.name AS participant, r.beer_id, r.score, r.created_at
               FROM ratings r JOIN participants p ON p.id = r.participant_id""",
            conn,
        )


def set_rating(pid: int, bid: int, score: float | None) -> None:
    """Upsert a score, or delete it when score is None."""
    with connect() as conn:
        if score is None:
            conn.execute(
                "DELETE FROM ratings WHERE participant_id = ? AND beer_id = ?", (pid, bid)
            )
        else:
            conn.execute(
                """INSERT INTO ratings (participant_id, beer_id, score) VALUES (?, ?, ?)
                   ON CONFLICT (participant_id, beer_id)
                   DO UPDATE SET score = excluded.score, created_at = datetime('now')""",
                (pid, bid, score),
            )


# --- settings ---------------------------------------------------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# --- export -----------------------------------------------------------------

def export_long() -> pd.DataFrame:
    """Everything in one tidy table, handy for CSV backup and notebooks."""
    r = ratings()
    b = beers().rename(columns={"id": "beer_id", "name": "beer"})
    return r.merge(b, on="beer_id", how="left")[
        ["participant", "beer", "position", "brewery", "style", "abv", "ibu", "price",
         "score", "created_at"]
    ]
