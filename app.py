"""Grad Question Bank - REST API Backend (Flask).

Replaces the original server-rendered app. Serves JSON for the React frontend.
Supports both SQLite and PostgreSQL (Neon) via NEON_DATABASE_URL env var.
"""

import json
import os
import re
import hashlib
import sys
import requests as http_requests
from datetime import datetime
from io import BytesIO
import threading

from flask import Flask, request, jsonify, send_file, send_from_directory, g
from flask_cors import CORS

from latex_utils import clean_latex
from pipeline.canonical import normalize_kp_name
from pipeline.task_manager import TaskManager, run_pipeline_background
from database import (
    get_db, init_db, seed_db, seed_from_syllabus, USE_POSTGRES, DB_PATH,
    _execute, _fetchone, _fetchall,
)

app = Flask(__name__)

# Task manager for background PDF pipeline
task_manager = TaskManager()
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Path to built React frontend
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

MASTERY_LABELS = {
    0: "未标记",
    1: "知识盲区",
    2: "只做了开头",
    3: "易错细节",
    4: "独立完成",
    5: "轻松秒杀",
}
MASTERY_COLORS = {0: "secondary", 1: "danger", 2: "danger", 3: "warning", 4: "success", 5: "success"}
# Level 1 receives the strongest weakness contribution.
MASTERY_WEAKNESS_POINTS = {1: 1.5, 2: 1.0, 3: 0.55, 4: 0.2, 5: 0.0}

PH = "%s" if USE_POSTGRES else "?"


# -- DB lifecycle ----------------------------------------------------------

@app.before_request
def before_request():
    g.db = get_db()

@app.teardown_request
def teardown_request(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# -- Helpers ---------------------------------------------------------------

def _safe_weight(val, default=1.0):
    try:
        return max(0.1, min(1.0, float(val)))
    except (ValueError, TypeError):
        return default


def _source_pages_to_list(value):
    """Normalize stored source page data to a list of ints."""
    if isinstance(value, list):
        return [int(x) for x in value if str(x).strip().isdigit()]
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if str(x).strip().isdigit()]
        except (json.JSONDecodeError, ValueError):
            pass
        return [int(x) for x in re.findall(r"\d+", value)]
    return []

def _get_setting(key, default=""):
    """Get a setting value from the database."""
    try:
        row = _fetchone(_execute(g.db, f"SELECT value FROM settings WHERE key = {PH}", (key,)))
        return row["value"] if row else default
    except Exception:
        return default


def _set_setting(key, value):
    """Set a setting value in the database."""
    if USE_POSTGRES:
        _execute(g.db,
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value))
    else:
        _execute(g.db,
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value))
    g.db.commit()




def _ai_headers(config):
    """Build auth headers based on provider."""
    if config["provider"] == "local":
        return {"Content-Type": "application/json"}
    if config["provider"] == "mimo":
        return {
            "api-key": config["api_key"],
            "Content-Type": "application/json",
        }
    else:
        return {
            "Authorization": "Bearer " + config["api_key"],
            "Content-Type": "application/json",
        }

def _get_ai_config():
    """Get AI configuration from database settings, with env var fallback."""
    provider = _get_setting("ai_provider", "deepseek")
    # Read provider-specific API key first, fall back to generic key
    api_key = _get_setting(f"api_key_{provider}", "")
    if not api_key:
        api_key = _get_setting("api_key", "")
    api_url = _get_setting("api_url", "")

    # Fallback to environment variables
    if not api_key:
        api_key = DEEPSEEK_API_KEY
    if not api_url:
        api_url = DEEPSEEK_API_URL

    return {
        "provider": provider,
        "api_key": api_key,
        "api_url": api_url,
        "model": _get_setting("ai_model", "deepseek-chat"),
        "vision": provider in ("local", "mimo", "openai"),
    }




def _insert_or_ignore_sql(table, columns):
    cols = ", ".join(columns)
    phs = ", ".join([PH] * len(columns))
    if USE_POSTGRES:
        return f"INSERT INTO {table} ({cols}) VALUES ({phs}) ON CONFLICT DO NOTHING"
    return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({phs})"


def _insert_returning_id(conn, sql, params):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(sql + " RETURNING id", params)
        row = cur.fetchone()
        return row[0] if row else None
    else:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def _save_analysis(db, question_id, subject_id, parsed):
    for kp in parsed.get("knowledge_points", []):
        kp_name = kp.get("name", "").strip()
        if not kp_name:
            continue
        chapter_name = str(kp.get("chapter") or "").strip() or "未分类"
        role = kp.get("role", "primary")
        weight = _safe_weight(kp.get("weight", 1.0))

        chapter = _fetchone(_execute(db,
            f"SELECT id FROM chapters WHERE name = {PH} AND subject_id = {PH}",
            (chapter_name, subject_id)))
        if not chapter:
            chapter_id = _insert_returning_id(db,
                f"INSERT INTO chapters (subject_id, name) VALUES ({PH}, {PH})",
                (subject_id, chapter_name))
        else:
            chapter_id = chapter["id"]

        kp_row = _fetchone(_execute(db,
            f"SELECT id FROM knowledge_points WHERE name = {PH} AND chapter_id = {PH}",
            (kp_name, chapter_id)))
        if not kp_row:
            kp_id = _insert_returning_id(db,
                f"INSERT INTO knowledge_points (chapter_id, name) VALUES ({PH}, {PH})",
                (chapter_id, kp_name))
        else:
            kp_id = kp_row["id"]

        _execute(db,
            _insert_or_ignore_sql("question_knowledge_points",
                                  ["question_id", "knowledge_point_id", "role", "weight"]),
            (question_id, kp_id, role, weight))

    for tag_name in parsed.get("tags", []):
        tag_name = tag_name.strip()
        if not tag_name:
            continue
        tag = _fetchone(_execute(db, f"SELECT id FROM tags WHERE name = {PH}", (tag_name,)))
        if not tag:
            tag_id = _insert_returning_id(db, f"INSERT INTO tags (name) VALUES ({PH})", (tag_name,))
        else:
            tag_id = tag["id"]
        _execute(db,
            _insert_or_ignore_sql("question_tags", ["question_id", "tag_id"]),
            (question_id, tag_id))


# -- Constants -------------------------------------------------------------

@app.route("/api/constants")
def api_constants():
    return jsonify({
        "mastery_labels": {str(k): v for k, v in MASTERY_LABELS.items()},
        "mastery_colors": {str(k): v for k, v in MASTERY_COLORS.items()},
        "use_postgres": USE_POSTGRES,
    })


# -- Dashboard -------------------------------------------------------------

@app.route("/api/dashboard")
def api_dashboard():
    db = g.db
    stats = {}
    for key, sql in [
        ("subjects", "SELECT COUNT(*) as cnt FROM subjects"),
        ("chapters", "SELECT COUNT(*) as cnt FROM chapters"),
        ("knowledge_points", "SELECT COUNT(*) as cnt FROM knowledge_points"),
        ("questions", "SELECT COUNT(*) as cnt FROM questions"),
        ("mastered", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level >= 4"),
        ("fuzzy", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level = 3"),
        ("weak", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level IN (1, 2)"),
    ]:
        stats[key] = _fetchone(_execute(db, sql))["cnt"]

    recent = _fetchall(_execute(db, """
        SELECT q.*, s.name as subject_name FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        ORDER BY q.created_at DESC LIMIT 10
    """))
    return jsonify({"stats": stats, "recent_questions": recent})


# -- Subjects --------------------------------------------------------------

# -- Exams -----------------------------------------------------------------

@app.route("/api/exams")
def api_exams_list():
    rows = _fetchall(_execute(g.db, "SELECT * FROM exams ORDER BY sort_order"))
    # Add subject count for each exam
    for row in rows:
        cnt = _fetchone(_execute(g.db,
            "SELECT COUNT(*) as cnt FROM exam_subjects WHERE exam_id = ?", (row['id'],)))
        row['subject_count'] = cnt['cnt']
    return jsonify(rows)


@app.route("/api/exams", methods=["POST"])
def api_exam_add():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "考试名称不能为空"}), 400
    max_order = _fetchone(_execute(g.db, "SELECT COALESCE(MAX(sort_order), 0) as m FROM exams"))["m"]
    _execute(g.db, "INSERT INTO exams (name, sort_order) VALUES (?, ?)", (name, max_order + 1))
    g.db.commit()
    return jsonify({"message": f"已添加考试：{name}"})


@app.route("/api/exams/<int:exam_id>")
def api_exam_detail(exam_id):
    exam = _fetchone(_execute(g.db, "SELECT * FROM exams WHERE id = ?", (exam_id,)))
    if not exam:
        return jsonify({"error": "考试不存在"}), 404
    # Get linked subjects
    subjects = _fetchall(_execute(g.db, f"""
        SELECT s.*, 
            (SELECT COUNT(*) FROM chapters c WHERE c.subject_id = s.id) as chapter_count,
            (SELECT COUNT(*) FROM knowledge_points kp 
             JOIN chapters c2 ON kp.chapter_id = c2.id WHERE c2.subject_id = s.id) as kp_count,
            (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) as question_count
        FROM subjects s
        JOIN exam_subjects es ON es.subject_id = s.id
        WHERE es.exam_id = {PH}
        ORDER BY s.name
    """, (exam_id,)))
    return jsonify({"exam": exam, "subjects": subjects})


@app.route("/api/exams/<int:exam_id>", methods=["DELETE"])
def api_exam_delete(exam_id):
    _execute(g.db, "DELETE FROM exams WHERE id = ?", (exam_id,))
    g.db.commit()
    return jsonify({"message": "考试已删除"})


@app.route("/api/exams/<int:exam_id>/subjects", methods=["POST"])
def api_exam_add_subject(exam_id):
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    if not subject_id:
        return jsonify({"error": "subject_id is required"}), 400
    _execute(g.db, "INSERT OR IGNORE INTO exam_subjects (exam_id, subject_id) VALUES (?, ?)", (exam_id, subject_id))
    g.db.commit()
    return jsonify({"message": "已关联学科"})


@app.route("/api/exams/<int:exam_id>/subjects/<int:subject_id>", methods=["DELETE"])
def api_exam_remove_subject(exam_id, subject_id):
    _execute(g.db, "DELETE FROM exam_subjects WHERE exam_id = ? AND subject_id = ?", (exam_id, subject_id))
    g.db.commit()
    return jsonify({"message": "已取消关联"})


@app.route("/api/subjects")
def api_subjects_list():
    rows = _fetchall(_execute(g.db, """
        SELECT s.*,
               COUNT(DISTINCT c.id) as chapter_count,
               COUNT(DISTINCT kp.id) as kp_count,
               COUNT(DISTINCT q.id) as question_count
        FROM subjects s
        LEFT JOIN chapters c ON c.subject_id = s.id
        LEFT JOIN knowledge_points kp ON kp.chapter_id = c.id
        LEFT JOIN questions q ON q.subject_id = s.id
        GROUP BY s.id ORDER BY s.id
    """))
    return jsonify(rows)


@app.route("/api/subjects", methods=["POST"])
def api_subject_add():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "学科名称不能为空"}), 400
    try:
        _execute(g.db, f"INSERT INTO subjects (name) VALUES ({PH})", (name,))
        g.db.commit()
        return jsonify({"message": f"已添加学科：{name}"})
    except Exception:
        return jsonify({"error": f"学科 '{name}' 已存在"}), 409


@app.route("/api/subjects/<int:subject_id>", methods=["DELETE"])
def api_subject_delete(subject_id):
    _execute(g.db, f"DELETE FROM subjects WHERE id = {PH}", (subject_id,))
    g.db.commit()
    return jsonify({"message": "学科已删除"})


@app.route("/api/subjects/<int:subject_id>")
def api_subject_detail(subject_id):
    subject = _fetchone(_execute(g.db,
        f"SELECT * FROM subjects WHERE id = {PH}", (subject_id,)))
    if not subject:
        return jsonify({"error": "学科不存在"}), 404
    chapters = _fetchall(_execute(g.db, f"""
        SELECT c.*, COUNT(kp.id) as kp_count
        FROM chapters c LEFT JOIN knowledge_points kp ON kp.chapter_id = c.id
        WHERE c.subject_id = {PH}
        GROUP BY c.id ORDER BY c.sort_order, c.id
    """, (subject_id,)))
    return jsonify({"subject": subject, "chapters": chapters})


@app.route("/api/subjects/<int:subject_id>/chapters", methods=["POST"])
def api_chapter_add(subject_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "章节名称不能为空"}), 400
    max_order = _fetchone(_execute(g.db,
        f"SELECT COALESCE(MAX(sort_order), 0) as m FROM chapters WHERE subject_id = {PH}",
        (subject_id,)))["m"]
    _execute(g.db,
        f"INSERT INTO chapters (subject_id, name, sort_order) VALUES ({PH}, {PH}, {PH})",
        (subject_id, name, max_order + 1))
    g.db.commit()
    return jsonify({"message": f"已添加章节：{name}"})


# -- Chapters --------------------------------------------------------------

@app.route("/api/chapters/<int:chapter_id>")
def api_chapter_detail(chapter_id):
    chapter = _fetchone(_execute(g.db, f"""
        SELECT c.*, s.name as subject_name, s.id as subject_id
        FROM chapters c JOIN subjects s ON c.subject_id = s.id
        WHERE c.id = {PH}
    """, (chapter_id,)))
    if not chapter:
        return jsonify({"error": "章节不存在"}), 404
    kps = _fetchall(_execute(g.db, f"""
        SELECT kp.*, COUNT(qkp.question_id) as question_count
        FROM knowledge_points kp
        LEFT JOIN question_knowledge_points qkp ON qkp.knowledge_point_id = kp.id
        WHERE kp.chapter_id = {PH}
        GROUP BY kp.id ORDER BY kp.sort_order, kp.id
    """, (chapter_id,)))
    return jsonify({"chapter": chapter, "knowledge_points": kps})


@app.route("/api/chapters/<int:chapter_id>", methods=["DELETE"])
def api_chapter_delete(chapter_id):
    row = _fetchone(_execute(g.db,
        f"SELECT subject_id FROM chapters WHERE id = {PH}", (chapter_id,)))
    if row:
        _execute(g.db, f"DELETE FROM chapters WHERE id = {PH}", (chapter_id,))
        g.db.commit()
        return jsonify({"message": "章节已删除", "subject_id": row["subject_id"]})
    return jsonify({"error": "章节不存在"}), 404


@app.route("/api/chapters/<int:chapter_id>/kps", methods=["POST"])
def api_kp_add(chapter_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    desc = (data.get("description") or "").strip()
    if not name:
        return jsonify({"error": "知识点名称不能为空"}), 400
    max_order = _fetchone(_execute(g.db,
        f"SELECT COALESCE(MAX(sort_order), 0) as m FROM knowledge_points WHERE chapter_id = {PH}",
        (chapter_id,)))["m"]
    _execute(g.db,
        f"INSERT INTO knowledge_points (chapter_id, name, description, sort_order) VALUES ({PH}, {PH}, {PH}, {PH})",
        (chapter_id, name, desc or None, max_order + 1))
    g.db.commit()
    return jsonify({"message": f"已添加知识点：{name}"})


# -- Knowledge Points ------------------------------------------------------

@app.route("/api/kps/<int:kp_id>", methods=["DELETE"])
def api_kp_delete(kp_id):
    row = _fetchone(_execute(g.db, f"""
        SELECT c.id as chapter_id FROM knowledge_points kp
        JOIN chapters c ON kp.chapter_id = c.id WHERE kp.id = {PH}
    """, (kp_id,)))
    if row:
        _execute(g.db, f"DELETE FROM knowledge_points WHERE id = {PH}", (kp_id,))
        g.db.commit()
        return jsonify({"message": "知识点已删除", "chapter_id": row["chapter_id"]})
    return jsonify({"error": "知识点不存在"}), 404



@app.route("/api/knowledge-tree")
def api_knowledge_tree():
    """Return knowledge points as a tree (with parent_id relationships)."""
    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)
    where = ["1=1"]
    params = []
    if chapter_id:
        where.append(f"kp.chapter_id = {PH}")
        params.append(chapter_id)
    elif subject_id:
        where.append(f"c.subject_id = {PH}")
        params.append(subject_id)
    rows = _fetchall(_execute(g.db, f"""
        SELECT kp.id, kp.name, kp.description, kp.chapter_id, kp.parent_id, kp.sort_order,
               c.name as chapter_name, s.name as subject_name
        FROM knowledge_points kp
        JOIN chapters c ON kp.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        WHERE {' AND '.join(where)}
        ORDER BY s.name, c.sort_order, kp.sort_order
    """, params))
    # Build tree: group by parent_id
    by_id = {r['id']: {**r, 'children': []} for r in rows}
    roots = []
    for r in rows:
        node = by_id[r['id']]
        if r['parent_id'] and r['parent_id'] in by_id:
            by_id[r['parent_id']]['children'].append(node)
        else:
            roots.append(node)
    return jsonify(roots)


@app.route("/api/kps/<int:kp_id>/children")
def api_kp_children(kp_id):
    rows = _fetchall(_execute(g.db, f"""
        SELECT id, name, description, sort_order FROM knowledge_points WHERE parent_id = {PH} ORDER BY sort_order
    """, (kp_id,)))
    return jsonify(rows)


@app.route("/api/kps/<int:kp_id>/parent")
def api_kp_parent(kp_id):
    row = _fetchone(_execute(g.db, f"""
        SELECT p.id, p.name, p.description FROM knowledge_points p
        JOIN knowledge_points c ON c.parent_id = p.id WHERE c.id = {PH}
    """, (kp_id,)))
    return jsonify(row or {})


@app.route("/api/kps/move", methods=["POST"])
def api_kp_move():
    data = request.get_json(silent=True) or {}
    kp_id = data.get("kp_id")
    new_parent_id = data.get("new_parent_id")  # null to make root
    if not kp_id:
        return jsonify({"error": "kp_id is required"}), 400
    # Prevent circular references
    if new_parent_id:
        cur_id = new_parent_id
        while cur_id:
            if cur_id == kp_id:
                return jsonify({"error": "不能移动到自己的子节点下"}), 400
            parent = _fetchone(_execute(g.db, f"SELECT parent_id FROM knowledge_points WHERE id = {PH}", (cur_id,)))
            cur_id = parent['parent_id'] if parent else None
    _execute(g.db, f"UPDATE knowledge_points SET parent_id = {PH} WHERE id = {PH}", (new_parent_id, kp_id))
    g.db.commit()
    return jsonify({"message": "已移动"})


@app.route("/api/kps/merge", methods=["POST"])
def api_kp_merge():
    data = request.get_json(silent=True) or {}
    source_id = data.get("source_id")
    target_id = data.get("target_id")
    if not source_id or not target_id:
        return jsonify({"error": "source_id and target_id are required"}), 400
    if source_id == target_id:
        return jsonify({"error": "不能合并到自身"}), 400
    # Move all question associations from source to target
    _execute(g.db, f"""
        INSERT OR IGNORE INTO question_knowledge_points (question_id, knowledge_point_id, role, weight)
        SELECT question_id, {PH}, role, weight FROM question_knowledge_points WHERE knowledge_point_id = {PH}
    """, (target_id, source_id))
    # Delete source associations
    _execute(g.db, f"DELETE FROM question_knowledge_points WHERE knowledge_point_id = {PH}", (source_id,))
    # Move children of source to target
    _execute(g.db, f"UPDATE knowledge_points SET parent_id = {PH} WHERE parent_id = {PH}", (target_id, source_id))
    # Delete source KP
    _execute(g.db, f"DELETE FROM knowledge_points WHERE id = {PH}", (source_id,))
    g.db.commit()
    return jsonify({"message": "已合并", "target_id": target_id})



@app.route("/api/kps/dedup", methods=["POST"])
def api_kp_dedup():
    """Start LLM-based duplicate KP detection in background."""
    import threading
    import uuid
    from pipeline.canonical.kp_dedup import KPDeduplicator
    from pipeline.llm.llm_client import LLMConfig
    task_id = uuid.uuid4().hex[:12]
    # Get all KPs grouped by subject
    rows = _fetchall(_execute(g.db, f"""
        SELECT kp.name, s.name as subject_name
        FROM knowledge_points kp
        JOIN chapters c ON kp.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        ORDER BY s.name, kp.sort_order
    """))
    by_subject: dict[str, list[str]] = {}
    for r in rows:
        by_subject.setdefault(r['subject_name'], []).append(r['name'])
    # Store task state
    dedup_tasks = app.config.setdefault('DEDUP_TASKS', {})
    dedup_tasks[task_id] = {'status': 'running', 'groups': [], 'error': None}
    def run_dedup():
        try:
            llm_config = LLMConfig(
                api_url='http://127.0.0.1:1234/v1/chat/completions',
                model='qwen/qwen3.5-9b',
            )
            dedup = KPDeduplicator(llm_config)
            groups = dedup.find_duplicates(by_subject)
            dedup_tasks[task_id] = {'status': 'completed', 'groups': groups, 'error': None}
        except Exception as e:
            dedup_tasks[task_id] = {'status': 'failed', 'groups': [], 'error': str(e)}
    thread = threading.Thread(target=run_dedup, daemon=True)
    thread.start()
    return jsonify({'task_id': task_id, 'status': 'running'})


@app.route("/api/kps/dedup/<task_id>")
def api_kp_dedup_status(task_id):
    """Check dedup task status and return results if completed."""
    dedup_tasks = app.config.get('DEDUP_TASKS', {})
    task = dedup_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route("/api/kps/dedup/apply", methods=["POST"])
def api_kp_dedup_apply():
    """Apply dedup suggestions: add aliases and optionally merge KPs."""
    from pipeline.canonical.kp_canonical import add_alias
    data = request.get_json(silent=True) or {}
    groups = data.get("groups", [])
    applied = 0
    for g in groups:
        canonical = g.get("canonical", "").strip()
        duplicates = g.get("duplicates", [])
        if not canonical or not duplicates:
            continue
        for dup in duplicates:
            dup = dup.strip()
            if dup and dup != canonical:
                add_alias(dup, canonical)
                applied += 1
    return jsonify({"message": f"已添加 {applied} 条别名映射", "applied": applied})


# -- Sources ---------------------------------------------------------------
@app.route("/api/sources")
def api_sources():
    """Return distinct source values that still have questions."""
    _execute(g.db,
        "UPDATE questions SET source = NULL "
        "WHERE source IS NOT NULL AND TRIM(source) = ''")
    g.db.commit()
    rows = _fetchall(_execute(g.db,
        "SELECT DISTINCT TRIM(source) as source FROM questions "
        "WHERE source IS NOT NULL AND TRIM(source) != '' ORDER BY source"))
    return jsonify([r['source'] for r in rows])


# -- Questions -------------------------------------------------------------

@app.route("/api/questions")
def api_questions_list():
    db = g.db
    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)
    kp_id = request.args.get("kp_id", type=int)
    mastery = request.args.get("mastery", type=int)
    search = request.args.get("search", "").strip()
    source = request.args.get("source", "").strip()
    sort = request.args.get("sort", "question_number_asc")

    base = f"""
        SELECT DISTINCT q.*, s.name as subject_name
        FROM questions q JOIN subjects s ON q.subject_id = s.id
    """
    joins, conditions, params = [], [], []

    if kp_id:
        joins.append("JOIN question_knowledge_points qkp ON qkp.question_id = q.id")
        conditions.append(f"qkp.knowledge_point_id = {PH}")
        params.append(kp_id)
    if chapter_id:
        joins.append("JOIN question_knowledge_points qkp2 ON qkp2.question_id = q.id")
        joins.append("JOIN knowledge_points kp2 ON kp2.id = qkp2.knowledge_point_id")
        conditions.append(f"kp2.chapter_id = {PH}")
        params.append(chapter_id)
    if subject_id:
        conditions.append(f"q.subject_id = {PH}")
        params.append(subject_id)
    if mastery is not None:
        conditions.append(f"q.mastery_level = {PH}")
        params.append(mastery)
    if search:
        conditions.append(f"q.question_number LIKE {PH}")
        params.append(f"%{search}%")
    if source:
        conditions.append(f"q.source = {PH}")
        params.append(source)

    full = base
    for j in joins:
        full += "\n" + j
    if conditions:
        full += "\nWHERE " + " AND ".join(conditions)
    if sort == "question_number_desc":
        full += "\nORDER BY q.question_number IS NULL, CAST(q.question_number AS INTEGER) DESC, q.id DESC"
    else:
        full += "\nORDER BY q.question_number IS NULL, CAST(q.question_number AS INTEGER) ASC, q.id ASC"

    questions = _fetchall(_execute(db, full, params))

    for q in questions:
        q["knowledge_points"] = _fetchall(_execute(db, f"""
            SELECT kp.id, kp.name, c.name as chapter_name, s.name as subject_name
            FROM question_knowledge_points qkp
            JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
            JOIN chapters c ON kp.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE qkp.question_id = {PH}
        """, (q["id"],)))
        q["source_pages"] = _source_pages_to_list(q.get("source_pages"))

    subjects = _fetchall(_execute(db, "SELECT * FROM subjects ORDER BY id"))
    chapters = []
    if subject_id:
        chapters = _fetchall(_execute(db,
            f"SELECT * FROM chapters WHERE subject_id = {PH} ORDER BY sort_order",
            (subject_id,)))

    return jsonify({
        "questions": questions, "subjects": subjects, "chapters": chapters,
        "filters": {
            "subject_id": subject_id, "chapter_id": chapter_id,
            "kp_id": kp_id, "mastery": mastery, "search": search,
            "sort": sort,
        },
    })


@app.route("/api/questions", methods=["POST"])
def api_question_add():
    db = g.db
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    content = (data.get("content") or "").strip()
    answer = (data.get("answer") or "").strip()
    source = (data.get("source") or "").strip()
    question_number = (data.get("question_number") or "").strip() or None
    question_number = (data.get("question_number") or "").strip() or None

    if not subject_id:
        return jsonify({"error": "请选择学科"}), 400
    if not content:
        return jsonify({"error": "题干不能为空"}), 400

    qid = _insert_returning_id(db,
        f"INSERT INTO questions (subject_id, content, answer, source, question_number) VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
        (subject_id, content, answer or None, source or None, question_number))
    db.commit()
    return jsonify({"id": qid, "message": "题目已保存"})


@app.route("/api/questions/batch", methods=["POST"])
def api_question_batch():
    db = g.db
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    raw_content = (data.get("content") or "").strip()
    source = (data.get("source") or "").strip()
    question_number = (data.get("question_number") or "").strip() or None
    auto_analyze = data.get("auto_analyze", False)

    if not raw_content:
        return jsonify({"error": "题目内容不能为空"}), 400

    questions_raw = re.split(r"\n---\n|\n---$|^---\n", raw_content)
    questions_raw = [q.strip() for q in questions_raw if q.strip()]

    imported = 0
    for q_text in questions_raw:
        answer_match = re.search(r"[\n]?答案[：:](.+)$", q_text, re.MULTILINE)
        if answer_match:
            answer = answer_match.group(1).strip()
            content_text = q_text[: answer_match.start()].strip()
        else:
            answer = None
            content_text = q_text
        if not content_text:
            continue

        qid = _insert_returning_id(db,
            f"INSERT INTO questions (subject_id, content, answer, source, question_number) VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
            (subject_id, content_text, answer, source or None, question_number))
        imported += 1

        if auto_analyze and DEEPSEEK_API_KEY:
            try:
                subj = _fetchone(_execute(db,
                    f"SELECT name FROM subjects WHERE id = {PH}", (subject_id,)))
                subj_name = subj["name"] if subj else ""
                ck = hashlib.md5(f"{subj_name}:{content_text}".encode()).hexdigest()
                cached = _fetchone(_execute(db,
                    f"SELECT response_json FROM api_cache WHERE content_hash = {PH}", (ck,)))
                if cached:
                    _save_analysis(db, qid, subject_id, json.loads(cached["response_json"]))
            except Exception:
                pass

    db.commit()
    return jsonify({"message": f"成功录入 {imported} 道题目", "count": imported})


@app.route("/api/questions/<int:question_id>")
def api_question_detail(question_id):
    db = g.db
    question = _fetchone(_execute(db, f"""
        SELECT q.*, s.name as subject_name
        FROM questions q JOIN subjects s ON q.subject_id = s.id
        WHERE q.id = {PH}
    """, (question_id,)))
    if not question:
        return jsonify({"error": "题目不存在"}), 404
    question["source_pages"] = _source_pages_to_list(question.get("source_pages"))

    kps = _fetchall(_execute(db, f"""
        SELECT kp.*, c.name as chapter_name, qkp.role, qkp.weight
        FROM question_knowledge_points qkp
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        WHERE qkp.question_id = {PH}
    """, (question_id,)))

    tags = _fetchall(_execute(db, f"""
        SELECT t.name FROM question_tags qt
        JOIN tags t ON qt.tag_id = t.id WHERE qt.question_id = {PH}
    """, (question_id,)))

    return jsonify({"question": question, "knowledge_points": kps, "tags": tags})


@app.route("/api/questions/<int:question_id>", methods=["PUT"])
def api_question_edit(question_id):
    db = g.db
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    content = (data.get("content") or "").strip()
    answer = (data.get("answer") or "").strip()
    source = (data.get("source") or "").strip()

    if not content:
        return jsonify({"error": "题干不能为空"}), 400

    _execute(db, f"""
        UPDATE questions SET subject_id={PH}, content={PH}, answer={PH},
        source={PH}, question_number={PH}, updated_at={PH} WHERE id={PH}
    """, (subject_id, content, answer or None, source or None, question_number,
          datetime.now().isoformat(), question_id))
    db.commit()
    return jsonify({"message": "题目已更新"})


@app.route("/api/questions/<int:question_id>", methods=["DELETE"])
def api_question_delete(question_id):
    _execute(g.db, f"DELETE FROM questions WHERE id = {PH}", (question_id,))
    g.db.commit()
    return jsonify({"message": "题目已删除"})


def _question_ids_from_payload(data):
    raw_ids = data.get("ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [int(x) for x in raw_ids if str(x).strip().lstrip("-").isdigit()]


@app.route("/api/questions/batch-delete", methods=["POST"])
def api_questions_batch_delete():
    ids = _question_ids_from_payload(request.get_json(silent=True) or {})
    if not ids:
        return jsonify({"error": "请选择要删除的题目"}), 400
    placeholders = ", ".join([PH] * len(ids))
    cur = _execute(g.db,
        f"DELETE FROM questions WHERE id IN ({placeholders})",
        tuple(ids))
    g.db.commit()
    return jsonify({"message": f"已删除 {cur.rowcount} 道题目", "deleted": cur.rowcount})


@app.route("/api/questions/batch-mastery", methods=["POST"])
def api_questions_batch_mastery():
    data = request.get_json(silent=True) or {}
    ids = _question_ids_from_payload(data)
    level = data.get("level")
    if not ids:
        return jsonify({"error": "请选择要标记的题目"}), 400
    if level not in MASTERY_LABELS:
        return jsonify({"error": "无效的掌握度等级"}), 400
    placeholders = ", ".join([PH] * len(ids))
    cur = _execute(g.db,
        f"UPDATE questions SET mastery_level = {PH}, updated_at = {PH} WHERE id IN ({placeholders})",
        (level, datetime.now().isoformat(), *ids))
    g.db.commit()
    return jsonify({"message": f"已更新 {cur.rowcount} 道题目的掌握度", "updated": cur.rowcount})


@app.route("/api/questions/batch-source", methods=["POST"])
def api_questions_batch_source():
    data = request.get_json(silent=True) or {}
    ids = _question_ids_from_payload(data)
    source = (data.get("source") or "").strip()
    if not ids:
        return jsonify({"error": "请选择要修改的题目"}), 400
    placeholders = ", ".join([PH] * len(ids))
    cur = _execute(g.db,
        f"UPDATE questions SET source = {PH} WHERE id IN ({placeholders})",
        (source or None, *ids))
    g.db.commit()
    return jsonify({"message": f"已更新 {cur.rowcount} 道题目的来源", "updated": cur.rowcount})


@app.route("/api/questions/<int:question_id>/mastery", methods=["POST"])
def api_question_mastery(question_id):
    data = request.get_json(silent=True) or {}
    level = data.get("level")
    if level not in MASTERY_LABELS:
        return jsonify({"error": "无效的掌握度等级"}), 400
    _execute(g.db,
        f"UPDATE questions SET mastery_level = {PH}, updated_at = {PH} WHERE id = {PH}",
        (level, datetime.now().isoformat(), question_id))
    g.db.commit()
    return jsonify({"message": f"掌握度已更新为：{MASTERY_LABELS.get(level, '未知')}"})


# -- Review / KP Linking ---------------------------------------------------

@app.route("/api/questions/<int:question_id>/review")
def api_question_review(question_id):
    db = g.db
    question = _fetchone(_execute(db, f"""
        SELECT q.*, s.name as subject_name
        FROM questions q JOIN subjects s ON q.subject_id = s.id
        WHERE q.id = {PH}
    """, (question_id,)))
    if not question:
        return jsonify({"error": "题目不存在"}), 404

    all_kps = _fetchall(_execute(db, f"""
        SELECT kp.id, kp.name, c.name as chapter_name, c.id as chapter_id
        FROM knowledge_points kp JOIN chapters c ON kp.chapter_id = c.id
        WHERE c.subject_id = {PH}
        ORDER BY c.sort_order, kp.sort_order
    """, (question["subject_id"],)))

    linked = _fetchall(_execute(db, f"""
        SELECT kp.id, kp.name, c.name as chapter, qkp.role, qkp.weight
        FROM question_knowledge_points qkp
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        WHERE qkp.question_id = {PH}
    """, (question_id,)))

    return jsonify({"question": question, "all_kps": all_kps, "linked_kps": linked})


@app.route("/api/questions/<int:question_id>/review", methods=["POST"])
def api_question_review_save(question_id):
    db = g.db
    data = request.get_json(silent=True) or {}
    kps = data.get("knowledge_points", [])

    _execute(db,
        f"DELETE FROM question_knowledge_points WHERE question_id = {PH}",
        (question_id,))

    for kp in kps:
        kp_id = kp.get("id")
        role = kp.get("role", "primary")
        weight = _safe_weight(kp.get("weight", 1.0))
        if kp_id:
            _execute(db,
                f"INSERT INTO question_knowledge_points (question_id, knowledge_point_id, role, weight) VALUES ({PH}, {PH}, {PH}, {PH})",
                (question_id, kp_id, role, weight))

    _execute(db, f"DELETE FROM question_tags WHERE question_id = {PH}", (question_id,))
    tag_names = list(set(kp.get("name", "") for kp in kps if kp.get("name")))
    for tag_name in tag_names:
        tag = _fetchone(_execute(db, f"SELECT id FROM tags WHERE name = {PH}", (tag_name,)))
        if not tag:
            tag_id = _insert_returning_id(db,
                f"INSERT INTO tags (name) VALUES ({PH})", (tag_name,))
        else:
            tag_id = tag["id"]
        _execute(db,
            _insert_or_ignore_sql("question_tags", ["question_id", "tag_id"]),
            (question_id, tag_id))

    db.commit()
    return jsonify({"message": "知识点关联已保存"})


# -- AI Analysis ------------------------------------------------------------

def _fix_json_escapes(text):
    """Fix unescaped backslashes in AI-generated JSON containing LaTeX."""
    import json as _json
    try:
        _json.loads(text)
        return text
    except (_json.JSONDecodeError, ValueError):
        pass

    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char in ('"', '\\', '/', 'n', 'r', 't', 'b', 'f', 'u'):
                result.append(text[i:i+2])
                i += 2
            else:
                result.append('\\\\')
                i += 1
        else:
            result.append(text[i])
            i += 1

    fixed = ''.join(result)
    try:
        _json.loads(fixed)
        return fixed
    except (_json.JSONDecodeError, ValueError):
        return text


@app.route("/api/analyze-question", methods=["POST"])
def api_analyze_question():
    db = g.db
    data = request.get_json(silent=True) or {}
    text_content = (data.get("content") or "").strip()
    image_base64 = data.get("image", "")
    subject_name = (data.get("subject_name") or "").strip()

    config = _get_ai_config()
    if config["provider"] != "local" and not config["api_key"]:
        return jsonify({"error": "请在设置页面配置 API Key"}), 400

    subjects = _fetchall(_execute(db, "SELECT * FROM subjects"))
    kps_context = ""
    for subj in subjects:
        chapters = _fetchall(_execute(db,
            f"SELECT * FROM chapters WHERE subject_id = {PH} ORDER BY sort_order",
            (subj["id"],)))
        kps_context += f"\n[{subj['name']}]\n"
        for ch in chapters:
            kps = _fetchall(_execute(db,
                f"SELECT name FROM knowledge_points WHERE chapter_id = {PH} ORDER BY sort_order",
                (ch["id"],)))
            kp_names = ", ".join(k["name"] for k in kps)
            kps_context += f"  {ch['name']}: {kp_names}\n"

    cache_key = hashlib.md5(f"{subject_name}:{text_content}".encode()).hexdigest() if text_content else None
    if text_content and cache_key:
        cached = _fetchone(_execute(db,
            f"SELECT response_json FROM api_cache WHERE content_hash = {PH}",
            (cache_key,)))
        if cached:
            return jsonify(json.loads(cached["response_json"]))

    prompt = (
        "你是一个考研题库分析助手。请分析以下题目，返回 JSON 格式结果。\n\n"
        f"当前题库中的知识点体系：\n{kps_context}\n\n"
        '请返回以下 JSON 格式：\n'
        '{\n'
        '    "content": "清理后的题目文字",\n'
        '    "latex_content": "LaTeX 格式的题目",\n'
        '    "answer": "答案",\n'
        '    "knowledge_points": [\n'
        '        {"name": "知识点名", "role": "primary", "weight": 1.0, "chapter": "章节名", "is_new": false}\n'
        '    ],\n'
        '    "tags": ["标签1"]\n'
        '}'
    )

    messages = [{"role": "system", "content": prompt}]
    if image_base64:
        # Image provided but no text - use vision if provider supports it
        if config.get("vision"):
            vision_content = []
            vision_content.append({"type": "image_url", "image_url": {"url": image_base64}})
            vision_content.append({"type": "text", "text": """请仔细分析这张图片中的所有题目。对于每道题：
1. 题目内容：完整提取，数学公式用LaTeX（行内$...$，独立$$...$$）
2. 答案：只填最终结果

图中可能有多道题，请全部识别。严格按JSON数组格式返回：
[{"content": "题目1内容", "answer": "答案1", "knowledge_points": [{"name": "知识点", "role": "primary", "weight": 1.0}], "tags": ["标签"]},
 {"content": "题目2内容", "answer": "答案2", "knowledge_points": [{"name": "知识点", "role": "primary", "weight": 1.0}], "tags": ["标签"]}]

如果只有一道题，也返回数组（长度为1）。"""})
            messages.append({"role": "user", "content": vision_content})
        else:
            return jsonify({"error": "请先输入题目内容，或使用 OCR 识别图片中的文字"}), 400
    else:
        messages.append({"role": "user", "content": text_content})

    # Update system prompt to focus on content + answer extraction
    system_prompt = messages[0]["content"] if messages else ""
    messages[0] = {"role": "system", "content": system_prompt + """

请额外注意：返回的JSON中必须包含 "content" 和 "answer" 两个字段。
- content: 清理后的题目内容（含LaTeX公式）
- answer: 题目的答案（只填答案本身）"""}

    try:
        resp = http_requests.post(
            config["api_url"],
            headers=_ai_headers(config),
            json={
                "model": config["model"],
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        ai_text = result["choices"][0]["message"]["content"]

        # Strip markdown code fences if present
        clean_text = ai_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        # Try to parse the full cleaned text as JSON first
        parsed = None
        try:
            full_parsed = json.loads(_fix_json_escapes(clean_text))
            if isinstance(full_parsed, list):
                parsed = full_parsed  # array of questions
            elif isinstance(full_parsed, dict):
                parsed = full_parsed  # single object
        except (json.JSONDecodeError, ValueError):
            pass

        if parsed is None:
            # Fallback: try regex matching on the full text (outermost match)
            json_array_match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", clean_text)
            json_obj_match = re.search(r"\{[\s\S]*\}", clean_text)

            if json_array_match:
                try:
                    parsed = json.loads(_fix_json_escapes(json_array_match.group()))
                except (json.JSONDecodeError, ValueError):
                    pass
            if parsed is None and json_obj_match:
                try:
                    parsed = json.loads(_fix_json_escapes(json_obj_match.group()))
                except (json.JSONDecodeError, ValueError):
                    pass

        if parsed is None:
            parsed = {
                "content": text_content,
                "latex_content": text_content,
                "knowledge_points": [],
                "tags": [],
                "raw": ai_text,
            }

        # Handle array (multi-question) vs single object
        if isinstance(parsed, list):
            for item in parsed:
                if "latex_content" not in item:
                    item["latex_content"] = item.get("content", text_content)
            if len(parsed) == 1:
                parsed = parsed[0]
                if "latex_content" not in parsed:
                    parsed["latex_content"] = parsed.get("content", text_content)
            else:
                parsed = {"questions": parsed}
        elif isinstance(parsed, dict):
            if "latex_content" not in parsed:
                parsed["latex_content"] = parsed.get("content", text_content)

        if text_content and cache_key:
            _execute(db,
                f"INSERT INTO api_cache (content_hash, subject_name, response_json) VALUES ({PH}, {PH}, {PH})",
                (cache_key, subject_name, json.dumps(parsed, ensure_ascii=False)))
            db.commit()

        return jsonify(parsed)

    except http_requests.exceptions.RequestException as e:
        return jsonify({"error": f"API 调用失败: {e}"}), 500
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"error": f"解析返回结果失败: {e}"}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Text-only analysis (legacy compat)."""
    db = g.db
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    subject_name = (data.get("subject_name") or "").strip()

    config = _get_ai_config()
    if not config["api_key"]:
        return jsonify({"error": "请在设置页面配置 API Key"}), 400

    subjects = _fetchall(_execute(db, "SELECT * FROM subjects"))
    kps_context = ""
    for subj in subjects:
        chapters = _fetchall(_execute(db,
            f"SELECT * FROM chapters WHERE subject_id = {PH} ORDER BY sort_order",
            (subj["id"],)))
        kps_context += f"\n[{subj['name']}]\n"
        for ch in chapters:
            kps = _fetchall(_execute(db,
                f"SELECT name FROM knowledge_points WHERE chapter_id = {PH} ORDER BY sort_order",
                (ch["id"],)))
            kps_context += f"  {ch['name']}: {', '.join(k['name'] for k in kps)}\n"

    content_hash = hashlib.md5(content.encode()).hexdigest()
    cached = _fetchone(_execute(db,
        f"SELECT response_json FROM api_cache WHERE content_hash = {PH}",
        (content_hash,)))
    if cached:
        return jsonify(json.loads(cached["response_json"]))

    prompt = (
        "你是一个考研题库分析助手。请分析以下题目涉及的知识点。\n\n"
        f"当前题库中的知识点体系：\n{kps_context}\n\n"
        f"题目：\n{content}\n\n"
        '请用JSON格式返回：\n'
        '{"knowledge_points": [{"name": "知识点名", "role": "primary", "weight": 1.0, '
        '"chapter": "章节名", "is_new": false}], "tags": ["标签"]}'
    )

    try:
        resp = http_requests.post(
            config["api_url"],
            headers=_ai_headers(config),
            json={
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        ai_text = resp.json()["choices"][0]["message"]["content"]

        json_match = re.search(r"\{[\s\S]*\}", ai_text)
        parsed = (
            json.loads(json_match.group())
            if json_match
            else {"knowledge_points": [], "tags": [], "raw": ai_text}
        )

        _execute(db,
            f"INSERT INTO api_cache (content_hash, subject_name, response_json) VALUES ({PH}, {PH}, {PH})",
            (content_hash, subject_name, json.dumps(parsed, ensure_ascii=False)))
        db.commit()
        return jsonify(parsed)

    except http_requests.exceptions.RequestException as e:
        return jsonify({"error": f"API 调用失败: {e}"}), 500
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"error": f"解析失败: {e}"}), 500


# -- Statistics -------------------------------------------------------------

@app.route("/api/statistics")
def api_statistics():
    db = g.db

    mastery_dist = _fetchall(_execute(db,
        "SELECT mastery_level, COUNT(*) as count FROM questions WHERE mastery_level > 0 GROUP BY mastery_level"))

    kp_stats = _fetchall(_execute(db, """
        SELECT kp.id, kp.name, c.name as chapter_name, s.name as subject_name,
               NULL as exam_name,
               q.mastery_level, qkp.weight, COUNT(*) as count
        FROM questions q
        JOIN question_knowledge_points qkp ON qkp.question_id = q.id
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        WHERE q.mastery_level > 0
        GROUP BY kp.id, q.mastery_level, qkp.weight
        ORDER BY s.id, c.sort_order, kp.sort_order
    """))

    kp_aggregated = {}
    for row in kp_stats:
        kp_id = row["id"]
        if kp_id not in kp_aggregated:
            kp_aggregated[kp_id] = {
                "name": row["name"],
                "chapter_name": row["chapter_name"],
                "subject_name": row["subject_name"],
                "exam_name": row["exam_name"] or "未分类",
                "total_weight": 0,
                "weighted_weakness": 0,
                "question_count": 0,
            }
        w = row["weight"]
        c = row["count"]
        kp_aggregated[kp_id]["total_weight"] += w * c
        kp_aggregated[kp_id]["question_count"] += c
        points = MASTERY_WEAKNESS_POINTS.get(row["mastery_level"], 0)
        kp_aggregated[kp_id]["weighted_weakness"] += points * w * c

    weak_points = []
    for kp in kp_aggregated.values():
        tw = kp["total_weight"]
        if tw > 0:
            max_weakness = max(MASTERY_WEAKNESS_POINTS.values())
            kp["weakness_score"] = kp["weighted_weakness"] / (tw * max_weakness)
            kp["mastery_rate"] = (1 - kp["weakness_score"]) * 100
        else:
            kp["weakness_score"] = 0
            kp["mastery_rate"] = 0
        kp["total"] = kp["question_count"]
        weak_points.append(kp)
    weak_points.sort(key=lambda x: -x["weakness_score"])

    subject_stats = _fetchall(_execute(db, """
        SELECT s.name, q.mastery_level, COUNT(*) as count
        FROM questions q JOIN subjects s ON q.subject_id = s.id
        WHERE q.mastery_level > 0
        GROUP BY s.id, q.mastery_level ORDER BY s.id
    """))

    return jsonify({
        "mastery_distribution": mastery_dist,
        "weak_points": weak_points,
        "subject_stats": subject_stats,
    })


# -- Import / Export --------------------------------------------------------

@app.route("/api/export")
def api_export():
    db = g.db
    data = {"exported_at": datetime.now().isoformat(), "subjects": [], "questions": []}

    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)

    scope_subject_ids: list[int] = []
    scope_chapter_ids: list[int] = []
    subject_name = ""
    chapter_name = ""

    if chapter_id is not None:
        chapter = _fetchone(_execute(db,
            f"SELECT * FROM chapters WHERE id = {PH}", (chapter_id,)))
        if not chapter:
            return jsonify({"error": "章节不存在"}), 404
        scope_subject_ids = [chapter["subject_id"]]
        scope_chapter_ids = [chapter_id]
        subject_name = _fetchone(_execute(db,
            f"SELECT name FROM subjects WHERE id = {PH}", (chapter["subject_id"],)))["name"]
        chapter_name = chapter["name"]
    elif subject_id is not None:
        subject = _fetchone(_execute(db,
            f"SELECT * FROM subjects WHERE id = {PH}", (subject_id,)))
        if not subject:
            return jsonify({"error": "学科不存在"}), 404
        scope_subject_ids = [subject_id]
        subject_name = subject["name"]

    if scope_subject_ids:
        subjects = _fetchall(_execute(db,
            f"SELECT * FROM subjects WHERE id = {PH} ORDER BY id",
            (scope_subject_ids[0],)))
    else:
        subjects = _fetchall(_execute(db, "SELECT * FROM subjects ORDER BY id"))

    for subj in subjects:
        subj_data = {"name": subj["name"], "chapters": []}
        if scope_chapter_ids:
            chapters = _fetchall(_execute(db,
                f"SELECT * FROM chapters WHERE id = {PH} ORDER BY sort_order",
                (scope_chapter_ids[0],)))
        elif scope_subject_ids:
            chapters = _fetchall(_execute(db,
                f"SELECT * FROM chapters WHERE subject_id = {PH} ORDER BY sort_order",
                (subj["id"],)))
        else:
            chapters = _fetchall(_execute(db,
                "SELECT * FROM chapters ORDER BY subject_id, sort_order"))
        for ch in chapters:
            if ch["subject_id"] != subj["id"]:
                continue
            ch_data = {"name": ch["name"], "knowledge_points": []}
            kps = _fetchall(_execute(db,
                f"SELECT * FROM knowledge_points WHERE chapter_id = {PH} ORDER BY sort_order",
                (ch["id"],)))
            for kp in kps:
                ch_data["knowledge_points"].append({
                    "name": kp["name"],
                    "description": kp.get("description"),
                })
            subj_data["chapters"].append(ch_data)
        data["subjects"].append(subj_data)

    if scope_chapter_ids:
        questions = _fetchall(_execute(db, f"""
            SELECT DISTINCT q.* FROM questions q
            JOIN question_knowledge_points qkp ON qkp.question_id = q.id
            JOIN knowledge_points kp ON kp.id = qkp.knowledge_point_id
            WHERE kp.chapter_id = {PH}
            ORDER BY q.id
        """, (scope_chapter_ids[0],)))
    elif scope_subject_ids:
        questions = _fetchall(_execute(db,
            f"SELECT * FROM questions WHERE subject_id = {PH} ORDER BY id",
            (scope_subject_ids[0],)))
    else:
        questions = _fetchall(_execute(db, "SELECT * FROM questions ORDER BY id"))

    for q in questions:
        subj = _fetchone(_execute(db,
            f"SELECT name FROM subjects WHERE id = {PH}", (q["subject_id"],)))
        q_data = {
            "subject_name": subj["name"] if subj else "",
            "content": q["content"],
            "answer": q.get("answer"),
            "source": q.get("source"),
            "question_number": q.get("question_number"),
            "source_page": q.get("source_page"),
            "source_pages": _source_pages_to_list(q.get("source_pages")),
            "needs_review": q.get("needs_review", 0),
            "review_note": q.get("review_note"),
            "mastery_level": q.get("mastery_level", 0),
            "created_at": q.get("created_at"),
            "knowledge_points": [],
        }
        kp_where = ["qkp.question_id = ?"]
        kp_params: list = [q["id"]]
        if scope_chapter_ids:
            kp_where.append(f"kp.chapter_id = {PH}")
            kp_params.append(scope_chapter_ids[0])
        elif scope_subject_ids:
            kp_where.append(f"c.subject_id = {PH}")
            kp_params.append(q["subject_id"])
        else:
            kp_where.append(f"c.subject_id = {PH}")
            kp_params.append(q["subject_id"])
        kps = _fetchall(_execute(db, f"""
            SELECT kp.name, c.name as chapter_name, qkp.role, qkp.weight
            FROM question_knowledge_points qkp
            JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
            JOIN chapters c ON kp.chapter_id = c.id
            WHERE {" AND ".join(kp_where)}
        """, tuple(kp_params)))
        q_data["knowledge_points"] = [
            {"name": k["name"], "chapter": k["chapter_name"],
             "role": k["role"], "weight": k["weight"]}
            for k in kps
        ]
        data["questions"].append(q_data)

    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if chapter_name:
        download_name = f"题库导出-{subject_name}-{chapter_name}.json"
    elif subject_name:
        download_name = f"题库导出-{subject_name}.json"
    else:
        download_name = "题库导出.json"
    download_name = re.sub(r'[\\/:*?"<>|]', "-", download_name)
    return send_file(
        BytesIO(payload),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/json",
    )


@app.route("/api/import", methods=["POST"])
def api_import():
    db = g.db

    if "file" in request.files:
        file = request.files["file"]
        if not file.filename.endswith(".json"):
            return jsonify({"error": "请上传 JSON 文件"}), 400
        try:
            data = json.loads(file.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return jsonify({"error": f"文件解析失败: {e}"}), 400
    else:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "请提供 JSON 数据"}), 400

    # Subjects / chapters / KPs
    for subj_data in data.get("subjects", []):
        subj_name = (subj_data.get("name") or "").strip()
        if not subj_name:
            continue
        subject = _fetchone(_execute(db,
            f"SELECT id FROM subjects WHERE name = {PH}", (subj_name,)))
        if not subject:
            subject_id = _insert_returning_id(db,
                f"INSERT INTO subjects (name) VALUES ({PH})", (subj_name,))
        else:
            subject_id = subject["id"]
        for ch_data in subj_data.get("chapters", []):
            ch_name = (ch_data.get("name") or "").strip()
            if not ch_name:
                continue
            chapter = _fetchone(_execute(db,
                f"SELECT id FROM chapters WHERE name = {PH} AND subject_id = {PH}",
                (ch_name, subject_id)))
            if not chapter:
                chapter_id = _insert_returning_id(db,
                    f"INSERT INTO chapters (subject_id, name) VALUES ({PH}, {PH})",
                    (subject_id, ch_name))
            else:
                chapter_id = chapter["id"]
            for kp_data in ch_data.get("knowledge_points", []):
                kp_name = (kp_data.get("name") or "").strip()
                kp_name = normalize_kp_name(kp_name)
                if not kp_name:
                    continue
                kp = _fetchone(_execute(db,
                    f"SELECT id FROM knowledge_points WHERE name = {PH} AND chapter_id = {PH}",
                    (kp_name, chapter_id)))
                # Import never creates new knowledge-point entries. The
                # knowledge-point manager is the single source of truth.
                if not kp:
                    continue
    db.commit()

    imported = 0
    skipped = []
    for q_data in data.get("questions", []):
        subject_name = q_data.get("subject_name", "")
        subject = _fetchone(_execute(db,
            f"SELECT id FROM subjects WHERE name = {PH}", (subject_name,)))
        if not subject:
            skipped.append({"content": q_data.get("content", "")[:80], "reason": f"未知学科：{subject_name}"})
            continue
        subject_id = subject["id"]

        resolved_kps = []
        unresolved_kps = []
        for kp_data in q_data.get("knowledge_points", []):
            kp_name = normalize_kp_name(kp_data.get("name", ""))
            chapter_name = (kp_data.get("chapter", "") or "").strip()
            if not kp_name:
                continue
            if chapter_name:
                chapter = _fetchone(_execute(db,
                    f"SELECT id FROM chapters WHERE name = {PH} AND subject_id = {PH}",
                    (chapter_name, subject_id)))
                kp = _fetchone(_execute(db,
                    f"SELECT id FROM knowledge_points WHERE name = {PH} AND chapter_id = {PH}",
                    (kp_name, chapter["id"]))) if chapter else None
                # Models sometimes put a valid knowledge-point name under a
                # neighbouring chapter. Reuse it only when it is unique within
                # the subject; imports never create a replacement entry.
                if not kp:
                    candidates = _fetchall(_execute(db, """
                        SELECT kp.id FROM knowledge_points kp
                        JOIN chapters c ON c.id = kp.chapter_id
                        WHERE kp.name = ? AND c.subject_id = ?
                    """ if not USE_POSTGRES else """
                        SELECT kp.id FROM knowledge_points kp
                        JOIN chapters c ON c.id = kp.chapter_id
                        WHERE kp.name = %s AND c.subject_id = %s
                    """, (kp_name, subject_id)))
                    kp = candidates[0] if len(candidates) == 1 else None
            else:
                kp = _fetchone(_execute(db, """
                    SELECT kp.id FROM knowledge_points kp
                    JOIN chapters c ON c.id = kp.chapter_id
                    WHERE kp.name = ? AND c.subject_id = ?
                    LIMIT 1
                """ if not USE_POSTGRES else """
                    SELECT kp.id FROM knowledge_points kp
                    JOIN chapters c ON c.id = kp.chapter_id
                    WHERE kp.name = %s AND c.subject_id = %s
                    LIMIT 1
                """, (kp_name, subject_id)))
            if kp:
                resolved_kps.append((kp["id"], kp_data))
            else:
                unresolved_kps.append(kp_name)

        if unresolved_kps or not resolved_kps:
            reason = "知识点无法匹配管理条目"
            if unresolved_kps:
                reason += "：" + "、".join(unresolved_kps)
            skipped.append({"content": q_data.get("content", "")[:80], "reason": reason})
            continue

        source_pages = _source_pages_to_list(q_data.get("source_pages"))
        source_page = q_data.get("source_page") or (source_pages[0] if source_pages else None)
        needs_review = 1 if q_data.get("needs_review") else 0
        review_note = (q_data.get("review_note") or "").strip()
        qid = _insert_returning_id(db,
            f"INSERT INTO questions (subject_id, content, answer, source, question_number, source_page, source_pages, needs_review, review_note, mastery_level, created_at) VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (subject_id, q_data.get("content", ""), q_data.get("answer"),
             q_data.get("source"), q_data.get("question_number"), source_page,
             json.dumps(source_pages, ensure_ascii=False) if source_pages else None,
             needs_review, review_note or None,
             q_data.get("mastery_level", 0),
             q_data.get("created_at", datetime.now().isoformat())))

        for kp_id, kp_data in resolved_kps:
            role = kp_data.get("role", "primary")
            weight = _safe_weight(kp_data.get("weight", 1.0))
            _execute(db,
                _insert_or_ignore_sql("question_knowledge_points",
                                      ["question_id", "knowledge_point_id", "role", "weight"]),
                (qid, kp_id, role, weight))

        imported += 1

    db.commit()
    return jsonify({
        "message": f"成功导入 {imported} 道题目",
        "count": imported,
        "skipped_count": len(skipped),
        "skipped": skipped,
    })




# -- Settings ---------------------------------------------------------------

@app.route("/api/settings")
def api_settings_get():
    """Get all settings (masks API key for security)."""
    db = g.db
    settings = {}
    provider_keys = {}
    try:
        rows = _fetchall(_execute(db, "SELECT key, value FROM settings"))
        for row in rows:
            key = row["key"]
            # Never send API key values to the browser.
            if key.startswith("api_key"):
                if row["value"]:
                    p = key.replace("api_key_", "") if key.startswith("api_key_") else "deepseek"
                    provider_keys[p] = True
                continue
            settings[key] = row["value"]
            # Track which providers have keys configured
    except Exception:
        pass

    # Add env var defaults
    settings.setdefault("ai_provider", "local")
    settings.setdefault("api_url", "http://127.0.0.1:1234/v1/chat/completions")
    settings.setdefault("ai_model", "qwen/qwen3.5-9b")

    current_provider = settings.get("ai_provider", "deepseek")
    settings["has_api_key"] = provider_keys.get(current_provider, False)
    settings["provider_keys"] = provider_keys
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    """Save settings."""
    db = g.db
    data = request.get_json(silent=True) or {}

    allowed_keys = {"ai_provider", "api_key", "api_url", "ai_model"}
    for key, value in data.items():
        if key in allowed_keys and isinstance(value, str):
            if key == "api_key":
                # Save to provider-specific key
                provider = data.get("ai_provider") or _get_setting("ai_provider", "deepseek")
                if value.strip():
                    _set_setting(f"api_key_{provider}", value.strip())
                # Don't overwrite other providers' keys
            elif key == "api_url" and not value.strip():
                continue
            else:
                _set_setting(key, value)

    return jsonify({"message": "设置已保存"})


@app.route("/api/settings/test", methods=["POST"])
def api_settings_test():
    """Test AI connection with provided or saved settings."""
    db = g.db
    data = request.get_json(silent=True) or {}

    # Use form values if provided, otherwise fall back to saved config
    config = _get_ai_config()
    if data.get("api_key"):
        config["api_key"] = data["api_key"]
    if data.get("api_url"):
        config["api_url"] = data["api_url"]
    if data.get("ai_model"):
        config["model"] = data["ai_model"]
    if data.get("ai_provider"):
        config["provider"] = data["ai_provider"]

    if config["provider"] != "local" and not config["api_key"]:
        return jsonify({"success": False, "error": "未配置 API Key"}), 400

    try:
        resp = http_requests.post(
            config["api_url"],
            headers=_ai_headers(config),
            json={
                "model": config["model"],
                "messages": [{"role": "user", "content": "Hello, respond with 'ok' only."}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        message = result["choices"][0].get("message", {})
        reply = (message.get("content") or "").strip()
        if not reply:
            reply = (message.get("reasoning_content") or "").strip()
        if not reply:
            return jsonify({"success": False, "error": "接口返回为空，请检查模型名称和模式"}), 502
        return jsonify({"success": True, "message": f"连接成功！回复: {reply}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"连接失败: {e}"}), 500


# -- Static files for React frontend ----------------------------------------


# -- Recommendation ---------------------------------------------------------

@app.route("/api/recommend")
def api_recommend():
    """Get recommended questions for review based on mastery and KP weakness."""
    db = g.db
    limit = request.args.get("limit", 20, type=int)
    subject_id = request.args.get("subject_id", type=int)

    # 1. Get KP weakness scores
    kp_stats = _fetchall(_execute(db, """
        SELECT kp.id,
               SUM(CASE WHEN q.mastery_level = 1 THEN qkp.weight * 1.5
                        WHEN q.mastery_level = 2 THEN qkp.weight
                        WHEN q.mastery_level = 3 THEN qkp.weight * 0.55
                        WHEN q.mastery_level = 4 THEN qkp.weight * 0.2
                        ELSE 0 END) as weakness_score,
               SUM(qkp.weight) as total_weight
        FROM question_knowledge_points qkp
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN questions q ON qkp.question_id = q.id
        GROUP BY kp.id
    """))

    kp_weakness = {}
    for row in kp_stats:
        tw = row["total_weight"] or 1
        kp_weakness[row["id"]] = (row["weakness_score"] or 0) / tw

    # 2. Get questions with their KP info
    where = "WHERE 1=1"
    params = []
    if subject_id:
        where += f" AND q.subject_id = {PH}"
        params.append(subject_id)

    questions = _fetchall(_execute(db, f"""
        SELECT q.id, q.content, q.answer, q.source, q.question_number,
               q.source_page, q.source_pages, q.mastery_level, q.updated_at,
               qkp.knowledge_point_id, qkp.role, qkp.weight,
               kp.name as kp_name
        FROM questions q
        JOIN question_knowledge_points qkp ON qkp.question_id = q.id
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        {where} AND q.mastery_level > 0
    """, tuple(params)))

    # 3. Score each question
    mastery_scores = {0: 8, 1: 10, 2: 8, 3: 5, 4: 2, 5: 1}
    now = datetime.now()
    scored = []
    seen_ids = set()

    for q in questions:
        qid = q["id"]
        if qid in seen_ids:
            continue
        seen_ids.add(qid)

        ms = mastery_scores.get(q["mastery_level"], 8)
        kp_w = 1 + kp_weakness.get(q["knowledge_point_id"], 0)
        role_w = 1.0 if q["role"] == "primary" else 0.5

        # Time factor: days since last update (capped at 30)
        updated = q["updated_at"] or q.get("created_at", "")
        try:
            if updated:
                dt = datetime.fromisoformat(str(updated))
                days = min((now - dt).days, 30)
            else:
                days = 15
        except (ValueError, TypeError):
            days = 15
        time_w = 1 + days / 30

        score = ms * kp_w * time_w * role_w
        scored.append({
            "id": qid,
            "content": q["content"],
            "answer": q["answer"],
            "source": q["source"],
            "question_number": q.get("question_number"),
            "source_page": q.get("source_page"),
            "source_pages": _source_pages_to_list(q.get("source_pages")),
            "mastery_level": q["mastery_level"],
            "kp_name": q["kp_name"],
            "score": round(score, 2),
        })

    # 4. Sort by score descending, return top N
    scored.sort(key=lambda x: -x["score"])
    return jsonify({"questions": scored[:limit], "total": len(scored)})


@app.route("/")
def serve_index():
    return send_from_directory(DIST_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    # Don't intercept API routes
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    # If the path matches a file in dist, serve it
    file_path = os.path.join(DIST_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(DIST_DIR, path)
    # Otherwise serve index.html (SPA fallback for React Router)
    return send_from_directory(DIST_DIR, "index.html")


# -- Run -------------------------------------------------------------------

# -- PDF Import (Background Task) -----------------------------------------

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")


@app.route("/api/pdf/import", methods=["POST"])
def api_pdf_import():
    """Upload a PDF and start background pipeline processing."""
    if "file" not in request.files:
        return jsonify({"error": "请上传 PDF 文件"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 文件"}), 400

    # Save uploaded file
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    pdf_name = file.filename
    pdf_path = os.path.join(UPLOAD_DIR, pdf_name)
    file.save(pdf_path)

    # Optional: subjects filter from form data
    subjects_raw = request.form.get("subjects", "")
    subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()] or None
    auto_import = request.form.get("auto_import", "1") == "1"
    # Create output directory
    stem = os.path.splitext(pdf_name)[0]
    output_base = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "pipeline-output", stem,
    )

    # Create task
    task = task_manager.create_task(
        pdf_name=pdf_name,
        pdf_path=pdf_path,
        output_directory=output_base,
    )

    # Start pipeline in background thread
    from pipeline.llm.llm_client import LLMConfig

    ai_config = _get_ai_config()
    if ai_config["provider"] != "local" and not ai_config["api_key"]:
        return jsonify({"error": "请在设置页面配置 API Key"}), 400
    llm_config = LLMConfig(
        api_url=ai_config["api_url"],
        model=ai_config["model"],
        api_key=ai_config["api_key"] if ai_config["provider"] != "local" else "",
        temperature=0.1,
        max_tokens=8192,
        timeout=180,
        supports_json_schema=ai_config["provider"] == "local",
    )
    pipeline_kwargs = dict(
        pdf_path=pdf_path,
        output_base=output_base,
        mineru_cmd=[sys.executable, "-m", "mineru.cli.client"],
        llm_config=llm_config,
        db_path=DB_PATH,
        subjects=subjects,
        auto_import=auto_import,
    )

    thread = threading.Thread(
        target=run_pipeline_background,
        args=(task_manager, task.task_id, pipeline_kwargs),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task.task_id, "status": "pending"})


@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    """List all tasks."""
    limit = request.args.get("limit", 50, type=int)
    tasks = task_manager.list_tasks(limit=limit)
    return jsonify([t.to_dict() for t in tasks])


@app.route("/api/tasks/<task_id>", methods=["GET"])
def api_get_task(task_id):
    """Get a single task by ID."""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task.to_dict())




@app.route("/api/tasks/<task_id>/result", methods=["GET"])
def api_get_task_result(task_id):
    """Get the import_ready.json result for a completed task."""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    if task.status != "completed":
        return jsonify({"error": "任务尚未完成", "status": task.status}), 400

    import_ready = os.path.join(task.output_directory, "import_ready.json")
    if not os.path.isfile(import_ready):
        return jsonify({"error": "结果文件不存在"}), 404

    with open(import_ready, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)
if __name__ == "__main__":
    init_db()
    seed_db()
    # Load exam syllabi (idempotent, skips existing)
    for f in ["data/exam_syllabus/math1.json", "data/exam_syllabus/math2.json",
             "data/exam_syllabus/math3.json", "data/exam_syllabus/computer408.json"]:
        seed_from_syllabus(f)
    print(f"Database: {'Postgres (Neon)' if USE_POSTGRES else 'SQLite'}")
    app.run(debug=True, port=5000)
