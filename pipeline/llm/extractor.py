"""
Unified question extractor — the main entry point for the LLM pipeline.

Combines question extraction and knowledge point classification into a single
LLM call (combined mode), or splits them into two calls if needed.

Usage:
    from pipeline.llm import extract_questions, LLMConfig

    config = LLMConfig(api_url="http://127.0.0.1:1234/v1/chat/completions")
    result = extract_questions(doc, ann_doc, config=config)
    # result is a validated QuestionCollection (Pydantic model)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.schema import (
    NormalizedDocument, AnnotatedDocument, InlineType,
)
from pipeline.llm.models import QuestionCollection, Question, KnowledgePoint
from pipeline.llm.prompt import build_combined_prompt, get_system_prompt
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.llm.validator import extract_and_validate_with_retry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = LLMConfig(
    api_url="http://127.0.0.1:1234/v1/chat/completions",
    model="qwen/qwen3.5-9b",
    temperature=0.1,
    max_tokens=4000,
    timeout=120,
)


# ============================================================
# Question text extraction from NormalizedDocument
# ============================================================

def _extract_question_texts(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
) -> list[dict[str, Any]]:
    """Extract readable text for each question candidate.

    Returns list of dicts with: index, number, type, text, page
    """
    # Build block text lookup
    block_texts: dict[str, str] = {}
    block_pages: dict[str, int] = {}
    for page in doc.pages:
        for b in page.blocks:
            parts = []
            if b.text:
                parts.append(b.text)
            if b.title_content:
                parts.append("".join(i.content for i in b.title_content))
            if b.inline_content:
                for i in b.inline_content:
                    if i.type == InlineType.text:
                        parts.append(i.content)
                    elif i.type == InlineType.formula:
                        parts.append(f"${i.content}$")
            if b.latex and not b.inline_content:
                parts.append(f"${b.latex}$")
            block_texts[b.id] = " ".join(parts).strip()
            block_pages[b.id] = page.page_number

    # Extract candidates sorted by position
    block_order: dict[str, tuple[int, int]] = {}
    for page in doc.pages:
        for block in page.blocks:
            block_order[block.id] = (page.page_number - 1, block.reading_order)

    candidates = [a for a in ann_doc.annotations if a.type == "question_candidate"]
    candidates.sort(key=lambda a: block_order.get(a.block_ids[0], (999, 999)))

    # Build boundary lookup
    boundary_map: dict[str, list[str]] = {}
    for a in ann_doc.annotations:
        if a.type == "question_boundary":
            boundary_map[a.block_ids[0]] = a.metadata.get("stem_block_ids", [])

    results = []
    for idx, cand in enumerate(candidates):
        cand_id = cand.block_ids[0]
        stem_ids = boundary_map.get(cand_id, [cand_id])

        text_parts = []
        first_page = None
        for sid in stem_ids:
            t = block_texts.get(sid, "")
            if t:
                text_parts.append(t)
            if first_page is None and sid in block_pages:
                first_page = block_pages[sid]

        results.append({
            "index": idx,
            "number": cand.metadata.get("detected_number", ""),
            "type": cand.metadata.get("detection_method", "unknown"),
            "text": " ".join(text_parts),
            "page": first_page,
        })

    return results


# ============================================================
# Existing KP hierarchy
# ============================================================

def _get_existing_hierarchy(
    db_path: str = "data/grad.db",
    subjects: list[str] | None = None,
) -> str:
    """Read existing subject/chapter/KP hierarchy from database.

    Args:
        db_path: Path to SQLite database
        subjects: Optional list of subject names to include.
                  If None, all subjects are returned.
    """
    try:
        import sqlite3
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        lines = []
        if subjects:
            placeholders = ",".join("?" for _ in subjects)
            rows = db.execute(
                f"SELECT * FROM subjects WHERE name IN ({placeholders})",
                subjects,
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM subjects").fetchall()
        for s in rows:
            lines.append(f"Subject: {s['name']}")
            chapters = db.execute(
                "SELECT * FROM chapters WHERE subject_id=? ORDER BY sort_order",
                (s["id"],),
            ).fetchall()
            for c in chapters:
                kps = db.execute(
                    "SELECT name FROM knowledge_points WHERE chapter_id=? ORDER BY sort_order",
                    (c["id"],),
                ).fetchall()
                kp_names = ", ".join(k["name"] for k in kps)
                lines.append(f"  {c['name']}: {kp_names}")
        db.close()
        return "\n".join(lines)
    except Exception:
        logger.debug("Failed to read existing hierarchy from %s", db_path, exc_info=True)
        return ""
# ============================================================
# Convert QuestionCollection to import-ready JSON
# ============================================================

def to_import_json(
    collection: QuestionCollection,
    source_pdf: str = "",
) -> dict[str, Any]:
    """Convert a validated QuestionCollection to the /api/import format.

    Returns a dict ready to be saved as JSON or posted to /api/import.
    """
    questions = []
    for q in collection.questions:
        questions.append({
            "subject_name": q.subject_name,
            "content": q.content,
            "source": source_pdf,
            "knowledge_points": [
                {
                    "name": kp.name,
                    "chapter": kp.chapter,
                    "role": kp.role.value,
                    "weight": kp.weight,
                }
                for kp in q.knowledge_points
            ],
        })

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "pipeline",
        "questions": questions,
    }


# ============================================================
# Main entry point
# ============================================================

def extract_questions(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
    config: LLMConfig | None = None,
    db_path: str = "data/grad.db",
    output_path: str | None = None,
) -> QuestionCollection:
    """Extract questions and knowledge points from a document.

    This is the single entry point for the LLM pipeline layer.
    It combines question confirmation + knowledge point extraction
    into one LLM call, with automatic retry on validation failure.

    Args:
        doc: NormalizedDocument (Layer 2 output)
        ann_doc: AnnotatedDocument (Layer 3 output)
        config: LLM API configuration (defaults to LM Studio)
        db_path: Path to database for existing KP hierarchy context
        output_path: If set, save the import-ready JSON here

    Returns:
        Validated QuestionCollection (Pydantic model)

    Raises:
        ExtractionError: If LLM output cannot be parsed/validated after retries
    """
    config = config or DEFAULT_CONFIG
    client = LLMClient(config)

    # Extract question texts
    questions = _extract_question_texts(doc, ann_doc)
    logger.info(f"Extracted {len(questions)} question candidates")

    # Get existing KP hierarchy
    existing_kps = _get_existing_hierarchy(db_path)

    # Build prompts
    system_prompt = get_system_prompt(mode="combined")
    user_prompt = build_combined_prompt(questions, existing_kps)

    # Call LLM with retry
    logger.info(f"Calling LLM ({config.model})...")
    result = extract_and_validate_with_retry(
        client=client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_class=QuestionCollection,
        max_retries=2,
    )

    logger.info(f"Validated {len(result.questions)} questions")

    # Save import-ready JSON if requested
    if output_path:
        import_json = to_import_json(result, source_pdf=doc.source_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(import_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Saved import JSON to {output_path}")

    return result
