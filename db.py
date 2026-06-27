"""SQLite storage. Two tables:
  sessions  - one row per interview (resume, JD, final scores)
  qa_pairs  - one row per question/answer, the data you preprocess later

Swap to Postgres later by changing the connection; the schema stays the same.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "interviews.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume TEXT,
        job_description TEXT,
        created_at TEXT,
        ended_at TEXT,
        evaluation_json TEXT
    );
    CREATE TABLE IF NOT EXISTS qa_pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        turn_number INTEGER,
        phase TEXT,
        question TEXT,
        answer TEXT,
        created_at TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );
    """)
    conn.commit()
    conn.close()


def create_session(resume: str, job_description: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sessions (resume, job_description, created_at) VALUES (?, ?, ?)",
        (resume, job_description, datetime.utcnow().isoformat()),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def log_qa(session_id: int, turn_number: int, phase: str, question: str, answer: str):
    """Called on every turn - this is the core logging step for preprocessing."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO qa_pairs (session_id, turn_number, phase, question, answer, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, turn_number, phase, question, answer, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def save_evaluation(session_id: int, evaluation: dict):
    conn = get_conn()
    conn.execute(
        "UPDATE sessions SET ended_at = ?, evaluation_json = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), json.dumps(evaluation), session_id),
    )
    conn.commit()
    conn.close()


def get_transcript(session_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT turn_number, phase, question, answer FROM qa_pairs "
        "WHERE session_id = ? ORDER BY turn_number",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_all_qa() -> list[dict]:
    """Everything across all sessions - feed this into your preprocessing."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, turn_number, phase, question, answer, created_at "
        "FROM qa_pairs ORDER BY session_id, turn_number"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
