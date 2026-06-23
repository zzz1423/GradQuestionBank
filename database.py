"""Database setup, helpers, and seed data for Grad Question Bank."""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "grad.db")


def get_db():
    """Get a database connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
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

        CREATE TABLE IF NOT EXISTS question_knowledge_points (
            question_id INTEGER NOT NULL,
            knowledge_point_id INTEGER NOT NULL,
            PRIMARY KEY (question_id, knowledge_point_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()


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
    cursor = conn.cursor()

    # Only seed if subjects table is empty
    cursor.execute("SELECT COUNT(*) FROM subjects")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    for subject_name, chapters in SEED_DATA.items():
        cursor.execute("INSERT INTO subjects (name) VALUES (?)", (subject_name,))
        subject_id = cursor.lastrowid

        for sort_idx, (chapter_name, kps) in enumerate(chapters.items()):
            cursor.execute(
                "INSERT INTO chapters (subject_id, name, sort_order) VALUES (?, ?, ?)",
                (subject_id, chapter_name, sort_idx),
            )
            chapter_id = cursor.lastrowid

            for kp_idx, kp_name in enumerate(kps):
                cursor.execute(
                    "INSERT INTO knowledge_points (chapter_id, name, sort_order) VALUES (?, ?, ?)",
                    (chapter_id, kp_name, kp_idx),
                )

    conn.commit()
    conn.close()


# ── Helper functions ───────────────────────────────────────

def dict_from_row(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def dicts_from_rows(rows):
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]
