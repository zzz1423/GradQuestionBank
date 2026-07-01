"""Database abstraction layer supporting both SQLite and PostgreSQL (Neon).

Set NEON_DATABASE_URL environment variable to use Postgres.
Otherwise, SQLite is used (data/grad.db).
"""

import os
import json
from datetime import datetime

# Detect which backend to use
DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "grad.db")


# ── Connection helpers ─────────────────────────────────────

def get_db():
    """Get a database connection."""
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        import sqlite3
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _adapt_sql(sql):
    """Convert SQLite-style SQL to Postgres-compatible SQL."""
    if not USE_POSTGRES:
        return sql
    # Replace ? placeholders with %s
    result = sql.replace("?", "%s")
    # Replace INSERT OR IGNORE with INSERT ... ON CONFLICT DO NOTHING
    result = result.replace("INSERT OR IGNORE", "INSERT")
    # Replace AUTOINCREMENT
    result = result.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                            "SERIAL PRIMARY KEY")
    # Replace CURRENT_TIMESTAMP (both support it, but be explicit)
    # No change needed - both databases support CURRENT_TIMESTAMP
    return result


def _execute(conn, sql, params=None):
    """Execute SQL with appropriate cursor and return it."""
    adapted = _adapt_sql(sql)
    if USE_POSTGRES:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(adapted, params or ())
        return cur
    else:
        cur = conn.execute(adapted, params or ())
        return cur


def _fetchone(cur):
    """Fetch one row as dict."""
    if USE_POSTGRES:
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)
    else:
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)


def _fetchall(cur):
    """Fetch all rows as list of dicts."""
    if USE_POSTGRES:
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    else:
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _lastrowid(cur, conn=None):
    """Get the last inserted row ID."""
    if USE_POSTGRES:
        # With Postgres, use RETURNING id in INSERT statements
        row = cur.fetchone()
        return row["id"] if row else None
    else:
        return cur.lastrowid


# ── Schema initialization ──────────────────────────────────


def _migrate(conn):
    """Add missing columns to existing tables (schema migration)."""
    migrations = [
        ("question_knowledge_points", "role", "TEXT DEFAULT 'primary'"),
        ("question_knowledge_points", "weight", "REAL DEFAULT 1.0"),
    ]
    for table, column, col_def in migrations:
        try:
            if USE_POSTGRES:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table}' AND column_name = '{column}'"
                )
                if cur.fetchone() is None:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                    conn.commit()
            else:
                cur = conn.execute(f"PRAGMA table_info({table})")
                cols = [row[1] for row in cur.fetchall()]
                if column not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                    conn.commit()
        except Exception:
            pass


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()

    if USE_POSTGRES:
        _init_postgres(conn)
    else:
        _init_sqlite(conn)

    _migrate(conn)

    conn.close()


def _init_sqlite(conn):
    """SQLite schema creation."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            answer TEXT,
            source TEXT,
            mastery_level INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS question_tags (
            question_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (question_id, tag_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS api_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL UNIQUE,
            subject_name TEXT,
            response_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS question_knowledge_points (
            question_id INTEGER NOT NULL,
            knowledge_point_id INTEGER NOT NULL,
            role TEXT DEFAULT 'primary',
            weight REAL DEFAULT 1.0,
            PRIMARY KEY (question_id, knowledge_point_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


def _init_postgres(conn):
    """Postgres schema creation."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_points (
            id SERIAL PRIMARY KEY,
            chapter_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            answer TEXT,
            source TEXT,
            mastery_level INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );

        CREATE TABLE IF NOT EXISTS tags (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS question_tags (
            question_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (question_id, tag_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS api_cache (
            id SERIAL PRIMARY KEY,
            content_hash TEXT NOT NULL UNIQUE,
            subject_name TEXT,
            response_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS question_knowledge_points (
            question_id INTEGER NOT NULL,
            knowledge_point_id INTEGER NOT NULL,
            role TEXT DEFAULT 'primary',
            weight REAL DEFAULT 1.0,
            PRIMARY KEY (question_id, knowledge_point_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


# ── Seed data ──────────────────────────────────────────────

SEED_DATA = {
    "政治": {
        "马克思主义基本原理": [
            "唯物论", "唯物辩证法", "认识论", "唯物史观",
            "剩余价值理论", "资本主义的本质与规律", "科学社会主义",
        ],
        "毛泽东思想和中国特色社会主义理论体系概论": [
            "毛泽东思想", "邓小平理论", "三个代表重要思想",
            "科学发展观", "习近平新时代中国特色社会主义思想",
        ],
        "中国近现代史纲要": [
            "旧民主主义革命", "新民主主义革命",
            "社会主义改造", "改革开放与现代化建设",
        ],
        "思想道德与法治": [
            "人生观与价值观", "社会主义核心价值观",
            "道德修养与道德实践", "法治思维与法律素养",
        ],
        "形势与政策": [
            "国内形势", "国际形势",
        ],
    },
    "计算机408": {
        "数据结构": [
            "线性表", "栈和队列", "串", "树与二叉树",
            "图", "查找", "排序",
        ],
        "计算机组成原理": [
            "数据的表示和运算", "存储器层次结构", "指令系统",
            "中央处理器", "总线", "输入/输出系统",
        ],
        "操作系统": [
            "操作系统概述", "进程管理", "内存管理",
            "文件管理", "输入/输出管理",
        ],
        "计算机网络": [
            "计算机网络体系结构", "物理层", "数据链路层",
            "网络层", "传输层", "应用层",
        ],
    },
}


def seed_db():
    """Insert preset subjects, chapters, and knowledge points if empty."""
    conn = get_db()
    cur = _execute(conn, "SELECT COUNT(*) as cnt FROM subjects")
    count = _fetchone(cur)["cnt"]
    if count > 0:
        conn.close()
        return

    for subject_name, chapters in SEED_DATA.items():
        if USE_POSTGRES:
            cur = _execute(conn,
                "INSERT INTO subjects (name) VALUES (%s) RETURNING id",
                (subject_name,))
        else:
            cur = _execute(conn,
                "INSERT INTO subjects (name) VALUES (?)",
                (subject_name,))
        subject_id = _lastrowid(cur, conn) if USE_POSTGRES else cur.lastrowid
        if not USE_POSTGRES:
            # For SQLite, re-fetch to get the ID
            pass

        for sort_idx, (chapter_name, kps) in enumerate(chapters.items()):
            if USE_POSTGRES:
                cur = _execute(conn,
                    "INSERT INTO chapters (subject_id, name, sort_order) VALUES (%s, %s, %s) RETURNING id",
                    (subject_id, chapter_name, sort_idx))
            else:
                cur = _execute(conn,
                    "INSERT INTO chapters (subject_id, name, sort_order) VALUES (?, ?, ?)",
                    (subject_id, chapter_name, sort_idx))
            chapter_id = _lastrowid(cur, conn) if USE_POSTGRES else cur.lastrowid

            for kp_idx, kp_name in enumerate(kps):
                _execute(conn,
                    "INSERT INTO knowledge_points (chapter_id, name, sort_order) VALUES (?, ?, ?)",
                    (chapter_id, kp_name, kp_idx))

    conn.commit()
    conn.close()


# ── Legacy helpers (for backward compatibility) ───────────

def dict_from_row(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def dicts_from_rows(rows):
    """Convert a list of rows to a list of dicts."""
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    return [dict(r) for r in rows]
