"""Import pipeline question entries directly into the local SQLite database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pipeline.canonical import normalize_kp_name


def _safe_weight(val: Any, default: float = 1.0) -> float:
    try:
        return max(0.1, min(1.0, float(val)))
    except (ValueError, TypeError):
        return default


def import_entries(db_path: str | Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Insert import-ready question entries using only existing knowledge points."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    imported = 0
    skipped: list[dict[str, Any]] = []

    for entry in entries:
        subject_name = (entry.get("subject_name") or "").strip()
        row = conn.execute(
            "SELECT id FROM subjects WHERE name = ?", (subject_name,)
        ).fetchone()
        if not row:
            skipped.append({
                "content": str(entry.get("content", ""))[:80],
                "reason": f"未知学科：{subject_name}",
            })
            continue
        subject_id = row["id"]

        resolved: list[tuple[int, dict[str, Any]]] = []
        unresolved: list[str] = []
        for kp_data in entry.get("knowledge_points", []):
            kp_name = normalize_kp_name(kp_data.get("name", ""))
            chapter_name = (kp_data.get("chapter") or "").strip()
            if not kp_name:
                continue
            kp_row = None
            if chapter_name:
                chapter = conn.execute(
                    "SELECT id FROM chapters WHERE name = ? AND subject_id = ?",
                    (chapter_name, subject_id),
                ).fetchone()
                if chapter:
                    kp_row = conn.execute(
                        "SELECT id FROM knowledge_points WHERE name = ? AND chapter_id = ?",
                        (kp_name, chapter["id"]),
                    ).fetchone()
                if not kp_row:
                    candidates = conn.execute(
                        """
                        SELECT kp.id FROM knowledge_points kp
                        JOIN chapters c ON c.id = kp.chapter_id
                        WHERE kp.name = ? AND c.subject_id = ?
                        """,
                        (kp_name, subject_id),
                    ).fetchall()
                    kp_row = candidates[0] if len(candidates) == 1 else None
            else:
                kp_row = conn.execute(
                    """
                    SELECT kp.id FROM knowledge_points kp
                    JOIN chapters c ON c.id = kp.chapter_id
                    WHERE kp.name = ? AND c.subject_id = ?
                    LIMIT 1
                    """,
                    (kp_name, subject_id),
                ).fetchone()
            if kp_row:
                resolved.append((kp_row["id"], kp_data))
            else:
                unresolved.append(kp_name)

        if unresolved or not resolved:
            reason = "知识点无法匹配管理条目"
            if unresolved:
                reason += "：" + "、".join(unresolved)
            skipped.append({
                "content": str(entry.get("content", ""))[:80],
                "reason": reason,
            })
            continue

        source_pages = [
            int(p) for p in (entry.get("source_pages") or [])
            if str(p).strip().isdigit()
        ]
        source_page = entry.get("source_page") or (source_pages[0] if source_pages else None)
        needs_review = 1 if entry.get("needs_review") else 0
        review_note = (entry.get("review_note") or "").strip()
        cur = conn.execute(
            """
            INSERT INTO questions (
                subject_id, content, answer, source, question_number,
                source_page, source_pages, needs_review, review_note,
                mastery_level, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject_id,
                entry.get("content", ""),
                entry.get("answer"),
                entry.get("source"),
                entry.get("question_number"),
                source_page,
                json.dumps(source_pages, ensure_ascii=False) if source_pages else None,
                needs_review,
                review_note or None,
                entry.get("mastery_level", 0),
                entry.get("created_at"),
            ),
        )
        question_id = cur.lastrowid
        for kp_id, kp_data in resolved:
            role = kp_data.get("role", "primary")
            weight = _safe_weight(kp_data.get("weight", 1.0))
            conn.execute(
                """
                INSERT OR IGNORE INTO question_knowledge_points (
                    question_id, knowledge_point_id, role, weight
                ) VALUES (?, ?, ?, ?)
                """,
                (question_id, kp_id, role, weight),
            )
        imported += 1

    conn.commit()
    conn.close()
    return {
        "imported": imported,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }
