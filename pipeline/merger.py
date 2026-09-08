"""
Merger — combines enriched question files into a single import-ready JSON.

Reads all question_XXXX.enriched.json files from a directory,
validates them, and produces a single database.json file
compatible with the /api/import endpoint.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.canonical import normalize_kp_list

logger = logging.getLogger(__name__)


def _extract_question_number(text: str) -> str | None:
    """Extract a leading question number from question text when visible."""
    content = (text or "").strip().lstrip("\ufeff")
    match = re.match(r"^(?:第\s*)?(\d{1,4})\s*[\.、．)）]?", content)
    if match:
        return match.group(1)
    return None


def build_question_entry(data: dict[str, Any], source_pdf: str = "") -> dict[str, Any] | None:
    """Build one import-ready entry from an enriched question file."""
    enrichment = data.get("enrichment", {})
    content = data.get("content", data.get("stem_text", ""))
    if not content:
        return None

    source_pages = enrichment.get("source_pages") or data.get("source_pages", [])
    source_page = enrichment.get("source_page")
    if source_page is None and source_pages:
        source_page = source_pages[0]

    question_number = enrichment.get("question_number")
    if not question_number:
        question_number = _extract_question_number(content)
    if not question_number:
        detection = data.get("detection", {})
        question_number = detection.get("detected_number")
    if not question_number:
        question_number = str((data.get("question_index", 0) or 0) + 1)

    return {
        "subject_name": enrichment.get("subject_name", "未分类"),
        "content": content,
        "source": data.get("source_pdf", source_pdf),
        "source_page": source_page,
        "source_pages": source_pages,
        "question_number": question_number,
        "needs_review": enrichment.get("needs_review", False),
        "review_note": enrichment.get("review_note", ""),
        "visual_retry": enrichment.get("visual_retry", {}),
        "knowledge_points": normalize_kp_list(enrichment.get("knowledge_points", [])),
    }


def merge_enriched(
    questions_dir: Path | str,
    output_path: Path | str,
    source_pdf: str = "",
) -> dict[str, Any]:
    """Merge all enriched question files into a single import JSON.

    Args:
        questions_dir: Directory containing question_XXXX.enriched.json files
        output_path: Path to write the merged JSON
        source_pdf: Source PDF filename

    Returns:
        The merged import data dict
    """
    questions_dir = Path(questions_dir)
    output_path = Path(output_path)

    # Find all enriched files
    enriched_files = sorted(questions_dir.glob("question_*.enriched.json"))
    # Exclude .repaired. enriched files (only use original enriched)
    enriched_files = [f for f in enriched_files if ".repaired." not in f.name]

    if not enriched_files:
        logger.warning(f"No enriched files found in {questions_dir}")
        return {"exported_at": datetime.now(timezone.utc).isoformat(), "source": "pipeline", "questions": []}

    logger.info(f"Merging {len(enriched_files)} enriched questions")

    questions: list[dict[str, Any]] = []
    skipped: list[str] = []

    for fpath in enriched_files:
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            question_entry = build_question_entry(data, source_pdf)
            if question_entry is None:
                skipped.append(fpath.name)
                continue
            questions.append(question_entry)

        except Exception as e:
            logger.error(f"Failed to read {fpath.name}: {e}")
            skipped.append(fpath.name)

    # Build import data
    import_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "pipeline",
        "questions": questions,
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(import_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(
        f"Merged {len(questions)} questions to {output_path}"
        + (f" ({len(skipped)} skipped)" if skipped else "")
    )

    return import_data
