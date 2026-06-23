"""Grad Question Bank - Main Flask Application."""

import json
import os
import requests
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, g,
)
from database import get_db, init_db, seed_db, dict_from_row, dicts_from_rows, DB_PATH

app = Flask(__name__)
app.secret_key = os.urandom(24)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# ── Database lifecycle ─────────────────────────────────────

@app.before_request
def before_request():
    g.db = get_db()

@app.teardown_request
def teardown_request(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# ── Mastery level labels ───────────────────────────────────

MASTERY_LABELS = {0: "未标记", 1: "完全不会", 2: "模糊", 3: "已掌握"}
MASTERY_COLORS = {0: "secondary", 1: "danger", 2: "warning", 3: "success"}

@app.context_processor
def inject_constants():
    return {
        "MASTERY_LABELS": MASTERY_LABELS,
        "MASTERY_COLORS": MASTERY_COLORS,
    }

# ── Home / Dashboard ───────────────────────────────────────

@app.route("/")
def index():
    db = g.db
    stats = {}
    stats["subjects"] = db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    stats["chapters"] = db.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    stats["knowledge_points"] = db.execute("SELECT COUNT(*) FROM knowledge_points").fetchone()[0]
    stats["questions"] = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    stats["mastered"] = db.execute("SELECT COUNT(*) FROM questions WHERE mastery_level = 3").fetchone()[0]
    stats["fuzzy"] = db.execute("SELECT COUNT(*) FROM questions WHERE mastery_level = 2").fetchone()[0]
    stats["weak"] = db.execute("SELECT COUNT(*) FROM questions WHERE mastery_level = 1").fetchone()[0]

    recent_questions = dicts_from_rows(
        db.execute("SELECT q.*, s.name as subject_name FROM questions q "
                    "JOIN subjects s ON q.subject_id = s.id "
                    "ORDER BY q.created_at DESC LIMIT 10").fetchall()
    )

    return render_template("index.html", stats=stats, recent_questions=recent_questions)

# ── Subject management ─────────────────────────────────────

@app.route("/subjects")
def subjects_list():
    subjects = dicts_from_rows(
        g.db.execute("""
            SELECT s.*, 
                   COUNT(DISTINCT c.id) as chapter_count,
                   COUNT(DISTINCT kp.id) as kp_count,
                   COUNT(DISTINCT q.id) as question_count
            FROM subjects s
            LEFT JOIN chapters c ON c.subject_id = s.id
            LEFT JOIN knowledge_points kp ON kp.chapter_id = c.id
            LEFT JOIN questions q ON q.subject_id = s.id
            GROUP BY s.id
            ORDER BY s.id
        """).fetchall()
    )
    return render_template("subjects.html", subjects=subjects)


@app.route("/subjects/add", methods=["POST"])
def subject_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("学科名称不能为空", "danger")
        return redirect(url_for("subjects_list"))
    try:
        g.db.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
        g.db.commit()
        flash(f"已添加学科：{name}", "success")
    except Exception:
        flash(f"学科 '{name}' 已存在", "danger")
    return redirect(url_for("subjects_list"))


@app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
def subject_delete(subject_id):
    g.db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    g.db.commit()
    flash("学科已删除", "success")
    return redirect(url_for("subjects_list"))

# ── Chapter management ─────────────────────────────────────

@app.route("/subjects/<int:subject_id>")
def subject_detail(subject_id):
    subject = dict_from_row(
        g.db.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    )
    if not subject:
        flash("学科不存在", "danger")
        return redirect(url_for("subjects_list"))

    chapters = dicts_from_rows(
        g.db.execute("""
            SELECT c.*, COUNT(kp.id) as kp_count
            FROM chapters c
            LEFT JOIN knowledge_points kp ON kp.chapter_id = c.id
            WHERE c.subject_id = ?
            GROUP BY c.id
            ORDER BY c.sort_order, c.id
        """, (subject_id,)).fetchall()
    )
    return render_template("subject_detail.html", subject=subject, chapters=chapters)


@app.route("/subjects/<int:subject_id>/chapters/add", methods=["POST"])
def chapter_add(subject_id):
    name = request.form.get("name", "").strip()
    if name:
        max_order = g.db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM chapters WHERE subject_id = ?",
            (subject_id,)
        ).fetchone()[0]
        g.db.execute(
            "INSERT INTO chapters (subject_id, name, sort_order) VALUES (?, ?, ?)",
            (subject_id, name, max_order + 1),
        )
        g.db.commit()
        flash(f"已添加章节：{name}", "success")
    return redirect(url_for("subject_detail", subject_id=subject_id))


@app.route("/chapters/<int:chapter_id>/delete", methods=["POST"])
def chapter_delete(chapter_id):
    row = g.db.execute("SELECT subject_id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    if row:
        g.db.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
        g.db.commit()
        flash("章节已删除", "success")
        return redirect(url_for("subject_detail", subject_id=row["subject_id"]))
    return redirect(url_for("subjects_list"))

# ── Knowledge point management ─────────────────────────────

@app.route("/chapters/<int:chapter_id>")
def chapter_detail(chapter_id):
    chapter = dict_from_row(
        g.db.execute("""
            SELECT c.*, s.name as subject_name, s.id as subject_id
            FROM chapters c JOIN subjects s ON c.subject_id = s.id
            WHERE c.id = ?
        """, (chapter_id,)).fetchone()
    )
    if not chapter:
        flash("章节不存在", "danger")
        return redirect(url_for("subjects_list"))

    kps = dicts_from_rows(
        g.db.execute("""
            SELECT kp.*,
                   COUNT(qkp.question_id) as question_count
            FROM knowledge_points kp
            LEFT JOIN question_knowledge_points qkp ON qkp.knowledge_point_id = kp.id
            WHERE kp.chapter_id = ?
            GROUP BY kp.id
            ORDER BY kp.sort_order, kp.id
        """, (chapter_id,)).fetchall()
    )
    return render_template("chapter_detail.html", chapter=chapter, kps=kps)


@app.route("/chapters/<int:chapter_id>/kp/add", methods=["POST"])
def kp_add(chapter_id):
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    if name:
        max_order = g.db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM knowledge_points WHERE chapter_id = ?",
            (chapter_id,)
        ).fetchone()[0]
        g.db.execute(
            "INSERT INTO knowledge_points (chapter_id, name, description, sort_order) VALUES (?, ?, ?, ?)",
            (chapter_id, name, desc or None, max_order + 1),
        )
        g.db.commit()
        flash(f"已添加知识点：{name}", "success")

    chapter = g.db.execute("SELECT subject_id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return redirect(url_for("chapter_detail", chapter_id=chapter_id))


@app.route("/kp/<int:kp_id>/delete", methods=["POST"])
def kp_delete(kp_id):
    row = g.db.execute(
        "SELECT c.id as chapter_id FROM knowledge_points kp "
        "JOIN chapters c ON kp.chapter_id = c.id WHERE kp.id = ?",
        (kp_id,)
    ).fetchone()
    if row:
        g.db.execute("DELETE FROM knowledge_points WHERE id = ?", (kp_id,))
        g.db.commit()
        flash("知识点已删除", "success")
        return redirect(url_for("chapter_detail", chapter_id=row["chapter_id"]))
    return redirect(url_for("subjects_list"))

# ── Questions ──────────────────────────────────────────────

@app.route("/questions")
def questions_list():
    db = g.db
    subject_id = request.args.get("subject_id", type=int)
    chapter_id = request.args.get("chapter_id", type=int)
    kp_id = request.args.get("kp_id", type=int)
    mastery = request.args.get("mastery", type=int)
    search = request.args.get("search", "").strip()

    query = """
        SELECT DISTINCT q.*, s.name as subject_name
        FROM questions q
        JOIN subjects s ON q.subject_id = s.id
    """
    joins = []
    params = []

    if kp_id:
        joins.append("JOIN question_knowledge_points qkp ON qkp.question_id = q.id")
        params.append(kp_id)
        kp_filter = "qkp.knowledge_point_id = ?"
    else:
        kp_filter = None

    if chapter_id:
        joins.append("JOIN question_knowledge_points qkp2 ON qkp2.question_id = q.id")
        joins.append("JOIN knowledge_points kp2 ON kp2.id = qkp2.knowledge_point_id")
        params.append(chapter_id)
        chapter_filter = "kp2.chapter_id = ?"
    else:
        chapter_filter = None

    conditions = []
    if subject_id:
        conditions.append("q.subject_id = ?")
        params.append(subject_id)
    if mastery is not None:
        conditions.append("q.mastery_level = ?")
        params.append(mastery)
    if search:
        conditions.append("q.content LIKE ?")
        params.append(f"%{search}%")

    if kp_filter:
        conditions.append(kp_filter)
    if chapter_filter:
        conditions.append(chapter_filter)

    full_query = query
    for j in joins:
        full_query += "\n" + j
    if conditions:
        full_query += "\nWHERE " + " AND ".join(conditions)
    full_query += "\nORDER BY q.created_at DESC"

    questions = dicts_from_rows(db.execute(full_query, params).fetchall())

    # Attach knowledge points to each question
    for q in questions:
        q["knowledge_points"] = dicts_from_rows(db.execute("""
            SELECT kp.id, kp.name, c.name as chapter_name, s.name as subject_name
            FROM question_knowledge_points qkp
            JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
            JOIN chapters c ON kp.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE qkp.question_id = ?
        """, (q["id"],)).fetchall())

    subjects = dicts_from_rows(db.execute("SELECT * FROM subjects ORDER BY id").fetchall())
    chapters = []
    if subject_id:
        chapters = dicts_from_rows(
            db.execute("SELECT * FROM chapters WHERE subject_id = ? ORDER BY sort_order", (subject_id,)).fetchall()
        )

    return render_template("questions.html",
                           questions=questions, subjects=subjects, chapters=chapters,
                           selected_subject=subject_id, selected_chapter=chapter_id,
                           selected_kp=kp_id, selected_mastery=mastery, search=search)


@app.route("/questions/add", methods=["GET", "POST"])
def question_add():
    db = g.db
    subjects = dicts_from_rows(db.execute("SELECT * FROM subjects ORDER BY id").fetchall())

    if request.method == "POST":
        subject_id = request.form.get("subject_id", type=int)
        content = request.form.get("content", "").strip()
        answer = request.form.get("answer", "").strip()
        source = request.form.get("source", "").strip()

        if not content:
            flash("题干不能为空", "danger")
            return redirect(url_for("question_add"))

        cursor = db.execute(
            "INSERT INTO questions (subject_id, content, answer, source) VALUES (?, ?, ?, ?)",
            (subject_id, content, answer or None, source or None),
        )
        db.commit()
        question_id = cursor.lastrowid

        # Redirect to knowledge point review (AI analysis)
        return redirect(url_for("question_review", question_id=question_id))

    return render_template("add_question.html", subjects=subjects)


@app.route("/questions/<int:question_id>")
def question_detail(question_id):
    db = g.db
    question = dict_from_row(
        db.execute("""
            SELECT q.*, s.name as subject_name
            FROM questions q JOIN subjects s ON q.subject_id = s.id
            WHERE q.id = ?
        """, (question_id,)).fetchone()
    )
    if not question:
        flash("题目不存在", "danger")
        return redirect(url_for("questions_list"))

    kps = dicts_from_rows(db.execute("""
        SELECT kp.*, c.name as chapter_name
        FROM question_knowledge_points qkp
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        WHERE qkp.question_id = ?
    """, (question_id,)).fetchall())

    return render_template("question_detail.html", question=question, kps=kps)



@app.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
def question_edit(question_id):
    db = g.db
    subjects = dicts_from_rows(db.execute("SELECT * FROM subjects ORDER BY id").fetchall())
    question = dict_from_row(
        db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    )
    if not question:
        flash("题目不存在", "danger")
        return redirect(url_for("questions_list"))

    if request.method == "POST":
        subject_id = request.form.get("subject_id", type=int)
        content = request.form.get("content", "").strip()
        answer = request.form.get("answer", "").strip()
        source = request.form.get("source", "").strip()

        if not content:
            flash("题干不能为空", "danger")
            return redirect(url_for("question_edit", question_id=question_id))

        db.execute(
            "UPDATE questions SET subject_id=?, content=?, answer=?, source=?, updated_at=? WHERE id=?",
            (subject_id, content, answer or None, source or None, datetime.now().isoformat(), question_id),
        )
        db.commit()
        flash("题目已更新", "success")
        return redirect(url_for("question_detail", question_id=question_id))

    return render_template("edit_question.html", question=question, subjects=subjects)

@app.route("/questions/<int:question_id>/mastery", methods=["POST"])
def question_mastery(question_id):
    level = request.form.get("level", type=int)
    if level in (0, 1, 2, 3):
        g.db.execute(
            "UPDATE questions SET mastery_level = ?, updated_at = ? WHERE id = ?",
            (level, datetime.now().isoformat(), question_id),
        )
        g.db.commit()
        flash(f"掌握度已更新为：{MASTERY_LABELS.get(level, '未知')}", "success")
    return redirect(url_for("question_detail", question_id=question_id))


@app.route("/questions/<int:question_id>/delete", methods=["POST"])
def question_delete(question_id):
    g.db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    g.db.commit()
    flash("题目已删除", "success")
    return redirect(url_for("questions_list"))

# ── Knowledge point review (AI analysis) ───────────────────

@app.route("/questions/<int:question_id>/review", methods=["GET", "POST"])
def question_review(question_id):
    db = g.db
    question = dict_from_row(
        db.execute("""
            SELECT q.*, s.name as subject_name
            FROM questions q JOIN subjects s ON q.subject_id = s.id
            WHERE q.id = ?
        """, (question_id,)).fetchone()
    )
    if not question:
        flash("题目不存在", "danger")
        return redirect(url_for("questions_list"))

    # Get all available knowledge points grouped by chapter for the subject
    all_kps = dicts_from_rows(db.execute("""
        SELECT kp.id, kp.name, c.name as chapter_name, c.id as chapter_id
        FROM knowledge_points kp
        JOIN chapters c ON kp.chapter_id = c.id
        WHERE c.subject_id = ?
        ORDER BY c.sort_order, kp.sort_order
    """, (question["subject_id"],)).fetchall())

    # Get currently linked knowledge points
    linked_kp_ids = set()
    if request.method == "GET":
        existing = db.execute(
            "SELECT knowledge_point_id FROM question_knowledge_points WHERE question_id = ?",
            (question_id,)
        ).fetchall()
        linked_kp_ids = {r["knowledge_point_id"] for r in existing}

    if request.method == "POST":
        selected_ids = request.form.getlist("kp_ids")
        selected_ids = [int(x) for x in selected_ids]

        # Also handle custom new knowledge points
        new_kps_raw = request.form.get("new_kps", "").strip()
        if new_kps_raw:
            # Format: "chapter_id:kp_name" per line
            for line in new_kps_raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":", 1)
                if len(parts) == 2:
                    ch_id_str, kp_name = parts[0].strip(), parts[1].strip()
                    try:
                        ch_id = int(ch_id_str)
                        cursor = db.execute(
                            "INSERT INTO knowledge_points (chapter_id, name) VALUES (?, ?)",
                            (ch_id, kp_name),
                        )
                        db.commit()
                        selected_ids.append(cursor.lastrowid)
                    except (ValueError, Exception):
                        pass

        # Update associations
        db.execute("DELETE FROM question_knowledge_points WHERE question_id = ?", (question_id,))
        for kp_id in selected_ids:
            db.execute(
                "INSERT OR IGNORE INTO question_knowledge_points (question_id, knowledge_point_id) VALUES (?, ?)",
                (question_id, kp_id),
            )
        db.commit()
        flash("知识点关联已保存", "success")
        return redirect(url_for("question_detail", question_id=question_id))

    return render_template("review_knowledge.html",
                           question=question, all_kps=all_kps, linked_kp_ids=linked_kp_ids)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Call DeepSeek API to analyze question knowledge points."""
    data = request.get_json()
    content = data.get("content", "")
    subject_name = data.get("subject_name", "")

    if not DEEPSEEK_API_KEY:
        return jsonify({"error": "未配置 DEEPSEEK_API_KEY 环境变量"}), 400

    # Get available knowledge points for context
    db = g.db
    subjects = dicts_from_rows(db.execute("SELECT * FROM subjects").fetchall())
    kps_context = ""
    for subj in subjects:
        chapters = dicts_from_rows(
            db.execute("SELECT * FROM chapters WHERE subject_id = ? ORDER BY sort_order", (subj["id"],)).fetchall()
        )
        kps_context += f"\n【{subj['name']}】\n"
        for ch in chapters:
            kps = dicts_from_rows(
                db.execute("SELECT name FROM knowledge_points WHERE chapter_id = ? ORDER BY sort_order", (ch["id"],)).fetchall()
            )
            kp_names = ", ".join(k["name"] for k in kps)
            kps_context += f"  {ch['name']}：{kp_names}\n"

    prompt = f"""你是一个考研题库分析助手。请分析以下题目涉及的知识点。

当前题库中的知识点体系：
{kps_context}

题目：
{content}

请从两个维度回答：
1. 从上述知识点体系中，选出这道题最相关的知识点（列出名称即可）
2. 如果题目涉及的知识点不在上述体系中，请额外列出你认为应该添加的知识点（格式：章节名 > 知识点名）

请用JSON格式返回，格式如下：
{{"matched": ["知识点1", "知识点2"], "suggested": ["章节名 > 新知识点名"]}}"""

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        ai_text = result["choices"][0]["message"]["content"]

        # Try to extract JSON from response
        # Find JSON block in response
        import re
        json_match = re.search(r'\{[^{}]*\}', ai_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parsed = {"matched": [], "suggested": [], "raw": ai_text}

        return jsonify(parsed)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API 调用失败：{str(e)}"}), 500
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"error": f"解析返回结果失败：{str(e)}", "raw": ai_text if 'ai_text' in dir() else ""}), 500

# ── Statistics ─────────────────────────────────────────────

@app.route("/statistics")
def statistics():
    db = g.db

    # Overall mastery distribution
    mastery_dist = dicts_from_rows(db.execute("""
        SELECT mastery_level, COUNT(*) as count
        FROM questions
        GROUP BY mastery_level
    """).fetchall())

    # Per-knowledge-point mastery
    kp_stats = dicts_from_rows(db.execute("""
        SELECT kp.id, kp.name, c.name as chapter_name, s.name as subject_name,
               q.mastery_level, COUNT(*) as count
        FROM questions q
        JOIN question_knowledge_points qkp ON qkp.question_id = q.id
        JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
        JOIN chapters c ON kp.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        GROUP BY kp.id, q.mastery_level
        ORDER BY s.id, c.sort_order, kp.sort_order
    """).fetchall())

    # Aggregate per knowledge point
    kp_aggregated = {}
    for row in kp_stats:
        kp_id = row["id"]
        if kp_id not in kp_aggregated:
            kp_aggregated[kp_id] = {
                "name": row["name"],
                "chapter_name": row["chapter_name"],
                "subject_name": row["subject_name"],
                "total": 0, "mastered": 0, "fuzzy": 0, "weak": 0,
            }
        kp_aggregated[kp_id]["total"] += row["count"]
        if row["mastery_level"] == 3:
            kp_aggregated[kp_id]["mastered"] += row["count"]
        elif row["mastery_level"] == 2:
            kp_aggregated[kp_id]["fuzzy"] += row["count"]
        elif row["mastery_level"] == 1:
            kp_aggregated[kp_id]["weak"] += row["count"]

    # Calculate weakness score (higher = weaker)
    for kp in kp_aggregated.values():
        if kp["total"] > 0:
            kp["weakness_score"] = (kp["weak"] * 2 + kp["fuzzy"]) / (kp["total"] * 2)
            kp["mastery_rate"] = kp["mastered"] / kp["total"] * 100
        else:
            kp["weakness_score"] = 0
            kp["mastery_rate"] = 0

    # Sort by weakness (most weak first)
    weak_points = sorted(kp_aggregated.values(), key=lambda x: -x["weakness_score"])

    # Per-subject stats
    subject_stats = dicts_from_rows(db.execute("""
        SELECT s.name, q.mastery_level, COUNT(*) as count
        FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        GROUP BY s.id, q.mastery_level
        ORDER BY s.id
    """).fetchall())

    return render_template("statistics.html",
                           mastery_dist=mastery_dist,
                           weak_points=weak_points,
                           subject_stats=subject_stats)

# ── Data import/export ─────────────────────────────────────

@app.route("/api/export")
def api_export():
    db = g.db
    data = {
        "exported_at": datetime.now().isoformat(),
        "subjects": [],
    }

    subjects = dicts_from_rows(db.execute("SELECT * FROM subjects").fetchall())
    for subj in subjects:
        subj_data = {"name": subj["name"], "chapters": []}
        chapters = dicts_from_rows(
            db.execute("SELECT * FROM chapters WHERE subject_id = ? ORDER BY sort_order", (subj["id"],)).fetchall()
        )
        for ch in chapters:
            ch_data = {"name": ch["name"], "knowledge_points": []}
            kps = dicts_from_rows(
                db.execute("SELECT * FROM knowledge_points WHERE chapter_id = ? ORDER BY sort_order", (ch["id"],)).fetchall()
            )
            for kp in kps:
                ch_data["knowledge_points"].append({"name": kp["name"], "description": kp["description"]})
            subj_data["chapters"].append(ch_data)
        data["subjects"].append(subj_data)

    # Export questions
    questions = dicts_from_rows(
        db.execute("SELECT * FROM questions ORDER BY id").fetchall()
    )
    data["questions"] = []
    for q in questions:
        q_data = {
            "subject_name": dict_from_row(
                db.execute("SELECT name FROM subjects WHERE id = ?", (q["subject_id"],)).fetchone()
            )["name"],
            "content": q["content"],
            "answer": q["answer"],
            "source": q["source"],
            "mastery_level": q["mastery_level"],
            "created_at": q["created_at"],
            "knowledge_points": [],
        }
        kps = dicts_from_rows(db.execute("""
            SELECT kp.name, c.name as chapter_name
            FROM question_knowledge_points qkp
            JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
            JOIN chapters c ON kp.chapter_id = c.id
            WHERE qkp.question_id = ?
        """, (q["id"],)).fetchall())
        q_data["knowledge_points"] = [{"name": k["name"], "chapter": k["chapter_name"]} for k in kps]
        data["questions"].append(q_data)

    # Write to temp file and send
    export_path = os.path.join(os.path.dirname(DB_PATH), "export.json")
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return send_file(export_path, as_attachment=True, download_name="题库导出.json")


@app.route("/api/import", methods=["POST"])
def api_import():
    if "file" not in request.files:
        flash("请选择文件", "danger")
        return redirect(url_for("index"))

    file = request.files["file"]
    if not file.filename.endswith(".json"):
        flash("请上传 JSON 文件", "danger")
        return redirect(url_for("index"))

    try:
        data = json.loads(file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        flash(f"文件解析失败：{e}", "danger")
        return redirect(url_for("index"))

    db = g.db
    imported_questions = 0

    for q_data in data.get("questions", []):
        subject_name = q_data.get("subject_name", "")
        subject = db.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,)).fetchone()
        if not subject:
            # Create subject
            cursor = db.execute("INSERT INTO subjects (name) VALUES (?)", (subject_name,))
            subject_id = cursor.lastrowid
        else:
            subject_id = subject["id"]

        cursor = db.execute(
            "INSERT INTO questions (subject_id, content, answer, source, mastery_level, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (subject_id, q_data["content"], q_data.get("answer"), q_data.get("source"),
             q_data.get("mastery_level", 0), q_data.get("created_at", datetime.now().isoformat())),
        )
        question_id = cursor.lastrowid

        # Link knowledge points
        for kp_data in q_data.get("knowledge_points", []):
            kp_name = kp_data["name"]
            chapter_name = kp_data.get("chapter", "")

            # Find or create chapter
            chapter = None
            if chapter_name:
                chapter = db.execute(
                    "SELECT id FROM chapters WHERE name = ? AND subject_id = ?",
                    (chapter_name, subject_id)
                ).fetchone()
                if not chapter:
                    cursor = db.execute(
                        "INSERT INTO chapters (subject_id, name) VALUES (?, ?)",
                        (subject_id, chapter_name),
                    )
                    chapter_id = cursor.lastrowid
                else:
                    chapter_id = chapter["id"]
            else:
                # Use first chapter or create default
                chapter = db.execute(
                    "SELECT id FROM chapters WHERE subject_id = ? LIMIT 1", (subject_id,)
                ).fetchone()
                if chapter:
                    chapter_id = chapter["id"]
                else:
                    cursor = db.execute(
                        "INSERT INTO chapters (subject_id, name) VALUES (?, ?)",
                        (subject_id, "未分类"),
                    )
                    chapter_id = cursor.lastrowid

            # Find or create knowledge point
            kp = db.execute(
                "SELECT id FROM knowledge_points WHERE name = ? AND chapter_id = ?",
                (kp_name, chapter_id)
            ).fetchone()
            if not kp:
                cursor = db.execute(
                    "INSERT INTO knowledge_points (chapter_id, name) VALUES (?, ?)",
                    (chapter_id, kp_name),
                )
                kp_id = cursor.lastrowid
            else:
                kp_id = kp["id"]

            db.execute(
                "INSERT OR IGNORE INTO question_knowledge_points (question_id, knowledge_point_id) VALUES (?, ?)",
                (question_id, kp_id),
            )

        imported_questions += 1

    db.commit()
    flash(f"成功导入 {imported_questions} 道题目", "success")
    return redirect(url_for("index"))

# ── Run ────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    seed_db()
    app.run(debug=True, port=5000)
