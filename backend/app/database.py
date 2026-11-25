import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.config import DB_FILE_PATH

_db_initialized = False

def get_connection() -> sqlite3.Connection:
    global _db_initialized
    os.makedirs(os.path.dirname(os.path.abspath(DB_FILE_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not _db_initialized:
        _db_initialized = True
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
        """)
        conn.commit()
    return conn

def init_db() -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
        """)
        conn.commit()
    finally:
        conn.close()

def check_db_health() -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        res = cursor.fetchone()
        conn.close()
        return res is not None
    except Exception:
        return False

def save_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        created_at = datetime.now(timezone.utc).isoformat()
        metadata_str = json.dumps(metadata) if metadata is not None else None
        cursor.execute(
            """
            INSERT INTO messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, metadata_str, created_at)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_session_messages(session_id: str) -> Optional[List[Dict[str, Any]]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content, metadata, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        
        results = []
        for row in rows:
            item: Dict[str, Any] = {
                "role": row["role"],
                "content": row["content"]
            }
            if row["metadata"]:
                try:
                    item["metadata"] = json.loads(row["metadata"])
                except Exception:
                    item["metadata"] = None
            results.append(item)
        return results
    finally:
        conn.close()
