"""Grad Question Bank - REST API Backend (Flask).

Replaces the original server-rendered app. Serves JSON for the React frontend.
Supports both SQLite and PostgreSQL (Neon) via NEON_DATABASE_URL env var.
"""

import json
import os
import re
import hashlib
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

MASTERY_LABELS = {0: "未标记", 1: "完全不会", 2: "模糊", 3: "已掌握"}
MASTERY_COLORS = {0: "secondary", 1: "danger", 2: "warning", 3: "success"}

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
        "vision": provider in ("mimo", "openai"),
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
        ("mastered", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level = 3"),
        ("fuzzy", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level = 2"),
        ("weak", "SELECT COUNT(*) as cnt FROM questions WHERE mastery_level = 1"),
    ]:
        stats[key] = _fetchone(_execute(db, sql))["cnt"]

    recent = _fetchall(_execute(db, """
        SELECT q.*, s.name as subject_name FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        ORDER BY q.created_at DESC LIMIT 10
    """))
    return jsonify({"stats": stats, "recent_questions": recent})


# -- Subjects --------------------------------------------------------------

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


# -- Questions -------------------------------------------------------------

@app.route("/api/questions")
def api_questions_list():
    db = g.db
    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)
    kp_id = request.args.get("kp_id", type=int)
    mastery = request.args.get("mastery", type=int)
    search = request.args.get("search", "").strip()

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
        conditions.append(f"q.content LIKE {PH}")
        params.append(f"%{search}%")

    full = base
    for j in joins:
        full += "\n" + j
    if conditions:
        full += "\nWHERE " + " AND ".join(conditions)
    full += "\nORDER BY q.created_at DESC"

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

    if not subject_id:
        return jsonify({"error": "请选择学科"}), 400
    if not content:
        return jsonify({"error": "题干不能为空"}), 400

    qid = _insert_returning_id(db,
        f"INSERT INTO questions (subject_id, content, answer, source) VALUES ({PH}, {PH}, {PH}, {PH})",
        (subject_id, content, answer or None, source or None))
    db.commit()
    return jsonify({"id": qid, "message": "题目已保存"})


@app.route("/api/questions/batch", methods=["POST"])
def api_question_batch():
    db = g.db
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    raw_content = (data.get("content") or "").strip()
    source = (data.get("source") or "").strip()
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
            f"INSERT INTO questions (subject_id, content, answer, source) VALUES ({PH}, {PH}, {PH}, {PH})",
            (subject_id, content_text, answer, source or None))
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
        source={PH}, updated_at={PH} WHERE id={PH}
    """, (subject_id, content, answer or None, source or None,
          datetime.now().isoformat(), question_id))
    db.commit()
    return jsonify({"message": "题目已更新"})


@app.route("/api/questions/<int:question_id>", methods=["DELETE"])
def api_question_delete(question_id):
    _execute(g.db, f"DELETE FROM questions WHERE id = {PH}", (question_id,))
    g.db.commit()
    return jsonify({"message": "题目已删除"})


@app.route("/api/questions/<int:question_id>/mastery", methods=["POST"])
def api_question_mastery(question_id):
    data = request.get_json(silent=True) or {}
    level = data.get("level")
    if level not in (0, 1, 2, 3):
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
        "SELECT mastery_level, COUNT(*) as count FROM questions GROUP BY mastery_level"))

    kp_stats = _fetchall(_execute(db, """
        SELECT kp.id, kp.name, c.name as chapter_name, s.name as subject_name,
               q.mastery_level, qkp.weight, COUNT(*) as count
        FROM questions q
        JOIN question_knowledge_points qkp ON qkp.question_id = q.id
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
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
                "total_weight": 0,
                "weighted_mastered": 0,
                "weighted_fuzzy": 0,
                "weighted_weak": 0,
                "question_count": 0,
            }
        w = row["weight"]
        c = row["count"]
        kp_aggregated[kp_id]["total_weight"] += w * c
        kp_aggregated[kp_id]["question_count"] += c
        if row["mastery_level"] == 3:
            kp_aggregated[kp_id]["weighted_mastered"] += w * c
        elif row["mastery_level"] == 2:
            kp_aggregated[kp_id]["weighted_fuzzy"] += w * c
        elif row["mastery_level"] == 1:
            kp_aggregated[kp_id]["weighted_weak"] += w * c

    weak_points = []
    for kp in kp_aggregated.values():
        tw = kp["total_weight"]
        if tw > 0:
            kp["weakness_score"] = (kp["weighted_weak"] * 2 + kp["weighted_fuzzy"]) / (tw * 2)
            kp["mastery_rate"] = kp["weighted_mastered"] / tw * 100
        else:
            kp["weakness_score"] = 0
            kp["mastery_rate"] = 0
        kp["total"] = kp["question_count"]
        weak_points.append(kp)
    weak_points.sort(key=lambda x: -x["weakness_score"])

    subject_stats = _fetchall(_execute(db, """
        SELECT s.name, q.mastery_level, COUNT(*) as count
        FROM questions q JOIN subjects s ON q.subject_id = s.id
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

    subjects = _fetchall(_execute(db, "SELECT * FROM subjects"))
    for subj in subjects:
        subj_data = {"name": subj["name"], "chapters": []}
        chapters = _fetchall(_execute(db,
            f"SELECT * FROM chapters WHERE subject_id = {PH} ORDER BY sort_order",
            (subj["id"],)))
        for ch in chapters:
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

    questions = _fetchall(_execute(db, "SELECT * FROM questions ORDER BY id"))
    for q in questions:
        subj = _fetchone(_execute(db,
            f"SELECT name FROM subjects WHERE id = {PH}", (q["subject_id"],)))
        q_data = {
            "subject_name": subj["name"] if subj else "",
            "content": q["content"],
            "answer": q.get("answer"),
            "source": q.get("source"),
            "mastery_level": q.get("mastery_level", 0),
            "created_at": q.get("created_at"),
            "knowledge_points": [],
        }
        kps = _fetchall(_execute(db, f"""
            SELECT kp.name, c.name as chapter_name, qkp.role, qkp.weight
            FROM question_knowledge_points qkp
            JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
            JOIN chapters c ON kp.chapter_id = c.id
            WHERE qkp.question_id = {PH}
        """, (q["id"],)))
        q_data["knowledge_points"] = [
            {"name": k["name"], "chapter": k["chapter_name"],
             "role": k["role"], "weight": k["weight"]}
            for k in kps
        ]
        data["questions"].append(q_data)

    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        BytesIO(payload),
        as_attachment=True,
        download_name="题库导出.json",
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
                if not kp:
                    _execute(db,
                        f"INSERT INTO knowledge_points (chapter_id, name, description) VALUES ({PH}, {PH}, {PH})",
                        (chapter_id, kp_name, kp_data.get("description")))
    db.commit()

    imported = 0
    for q_data in data.get("questions", []):
        subject_name = q_data.get("subject_name", "")
        subject = _fetchone(_execute(db,
            f"SELECT id FROM subjects WHERE name = {PH}", (subject_name,)))
        if not subject:
            subject_id = _insert_returning_id(db,
                f"INSERT INTO subjects (name) VALUES ({PH})", (subject_name,))
        else:
            subject_id = subject["id"]

        qid = _insert_returning_id(db,
            f"INSERT INTO questions (subject_id, content, answer, source, mastery_level, created_at) VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (subject_id, q_data["content"], q_data.get("answer"),
             q_data.get("source"), q_data.get("mastery_level", 0),
             q_data.get("created_at", datetime.now().isoformat())))

        for kp_data in q_data.get("knowledge_points", []):
            kp_name = kp_data["name"]
            kp_name = normalize_kp_name(kp_name)
            chapter_name = kp_data.get("chapter", "")
            if chapter_name:
                chapter = _fetchone(_execute(db,
                    f"SELECT id FROM chapters WHERE name = {PH} AND subject_id = {PH}",
                    (chapter_name, subject_id)))
                if not chapter:
                    chapter_id = _insert_returning_id(db,
                        f"INSERT INTO chapters (subject_id, name) VALUES ({PH}, {PH})",
                        (subject_id, chapter_name))
                else:
                    chapter_id = chapter["id"]
            else:
                chapter = _fetchone(_execute(db,
                    f"SELECT id FROM chapters WHERE subject_id = {PH} LIMIT 1",
                    (subject_id,)))
                if chapter:
                    chapter_id = chapter["id"]
                else:
                    chapter_id = _insert_returning_id(db,
                        f"INSERT INTO chapters (subject_id, name) VALUES ({PH}, {PH})",
                        (subject_id, "未分类"))

            kp = _fetchone(_execute(db,
                f"SELECT id FROM knowledge_points WHERE name = {PH} AND chapter_id = {PH}",
                (kp_name, chapter_id)))
            if not kp:
                kp_id = _insert_returning_id(db,
                    f"INSERT INTO knowledge_points (chapter_id, name) VALUES ({PH}, {PH})",
                    (chapter_id, kp_name))
            else:
                kp_id = kp["id"]

            role = kp_data.get("role", "primary")
            weight = _safe_weight(kp_data.get("weight", 1.0))
            _execute(db,
                _insert_or_ignore_sql("question_knowledge_points",
                                      ["question_id", "knowledge_point_id", "role", "weight"]),
                (qid, kp_id, role, weight))

        imported += 1

    db.commit()
    return jsonify({"message": f"成功导入 {imported} 道题目", "count": imported})




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
            settings[row["key"]] = row["value"]
            # Track which providers have keys configured
            if row["key"].startswith("api_key_") and row["value"]:
                p = row["key"].replace("api_key_", "")
                provider_keys[p] = True
            elif row["key"] == "api_key" and row["value"]:
                provider_keys.setdefault("deepseek", True)
    except Exception:
        pass

    # Add env var defaults
    settings.setdefault("ai_provider", "deepseek")
    settings.setdefault("api_url", DEEPSEEK_API_URL)
    settings.setdefault("ai_model", "deepseek-chat")

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

    if not config["api_key"]:
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
        reply = result["choices"][0]["message"]["content"].strip()
        return jsonify({"success": True, "message": f"连接成功！回复: {reply}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"连接失败: {e}"}), 500


# -- Static files for React frontend ----------------------------------------

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

    pipeline_kwargs = dict(
        pdf_path=pdf_path,
        output_base=output_base,
        llm_config=LLMConfig(),
        db_path=DB_PATH,
        subjects=subjects,
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
