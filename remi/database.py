"""
SQLite database — users, messages, tasks, reminders
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "/data/remi.db")


class Database:
    def __init__(self):
        self.path = DB_PATH
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    name TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    done INTEGER DEFAULT 0,
                    due_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    sent INTEGER DEFAULT 0,
                    recurring TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            """)

    # ── Users ──────────────────────────────────────────────
    def get_or_create_user(self, phone: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if row:
                return dict(row)
            c.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
            row = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            return dict(row)

    # ── History ────────────────────────────────────────────
    def get_history(self, user_id: int, limit: int = 10) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def save_message(self, user_id: int, role: str, content: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?,?,?)",
                (user_id, role, content),
            )

    # ── Tasks ──────────────────────────────────────────────
    def add_task(self, user_id: int, title: str, due_at: str = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO tasks (user_id, title, due_at) VALUES (?,?,?)",
                (user_id, title, due_at),
            )
            return cur.lastrowid

    def get_tasks(self, user_id: int, done: bool = False) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM tasks WHERE user_id=? AND done=? ORDER BY due_at ASC",
                (user_id, int(done)),
            ).fetchall()
            return [dict(r) for r in rows]

    def complete_task(self, task_id: int, user_id: int):
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET done=1 WHERE id=? AND user_id=?",
                (task_id, user_id),
            )

    # ── Reminders ──────────────────────────────────────────
    def add_reminder(self, user_id: int, text: str, remind_at: str, recurring: str = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO reminders (user_id, text, remind_at, recurring) VALUES (?,?,?,?)",
                (user_id, text, remind_at, recurring),
            )
            return cur.lastrowid

    def get_pending_reminders(self) -> list[dict]:
        """Returns all reminders due now or in the past, not yet sent."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._conn() as c:
            rows = c.execute(
                "SELECT r.*, u.phone FROM reminders r JOIN users u ON r.user_id=u.id "
                "WHERE r.remind_at <= ? AND r.sent=0",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_reminder_sent(self, reminder_id: int):
        with self._conn() as c:
            c.execute("UPDATE reminders SET sent=1 WHERE id=?", (reminder_id,))


db = Database()
