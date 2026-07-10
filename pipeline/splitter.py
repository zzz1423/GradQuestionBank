"""
Question Splitter — splits AnnotatedDocument into individual question files.

Each question gets its own JSON file containing:
- Question metadata (index, number, page, detection method)
- Stem block IDs and their full text content
- Source block IDs for traceability

Output format:
  questions/
    question_0001.json
    question_0002.json
    ...

These files are the input for the per-question LLM enrichment step.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pipeline.schema import NormalizedDocument, AnnotatedDocument, InlineType

logger = logging.getLogger(__name__)


def _extract_block_text(doc: NormalizedDocument) -> dict[str, str]:
    """Build a lookup of block_id -> full text content."""
    block_texts: dict[str, str] = {}
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
    return block_texts


def _extract_block_meta(doc: NormalizedDocument) -> dict[str, dict[str, Any]]:
    """Build a lookup of block_id -> metadata (page, bbox, type)."""
    meta: dict[str, dict[str, Any]] = {}
    for page in doc.pages:
        for b in page.blocks:
            meta[b.id] = {
                "page": page.page_number,
                "type": b.type.value,
                "bbox": b.bbox.to_list(),
                "reading_order": b.reading_order,
            }
    return meta


def split_questions(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
    output_dir: Path | str,
) -> list[Path]:
    """Split document into individual question files.

    Args:
        doc: NormalizedDocument (Layer 2 output)
        ann_doc: AnnotatedDocument (Layer 3 output)
        output_dir: Directory to write question files

    Returns:
        List of paths to the created question files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build lookups
    block_texts = _extract_block_text(doc)
    block_meta = _extract_block_meta(doc)

    # Build block position ordering
    block_order: dict[str, tuple[int, int]] = {}
    for page in doc.pages:
        for block in page.blocks:
            block_order[block.id] = (page.page_number - 1, block.reading_order)

    # Extract candidates and boundaries
    candidates = [a for a in ann_doc.annotations if a.type == "question_candidate"]
    candidates.sort(key=lambda a: block_order.get(a.block_ids[0], (999, 999)))

    boundary_map: dict[str, list[str]] = {}
    for a in ann_doc.annotations:
        if a.type == "question_boundary":
            boundary_map[a.block_ids[0]] = a.metadata.get("stem_block_ids", [])

    # Generate individual question files
    created_files: list[Path] = []

    for idx, cand in enumerate(candidates):
        cand_id = cand.block_ids[0]
        stem_ids = boundary_map.get(cand_id, [cand_id])

        # Build stem text
        stem_parts = []
        for sid in stem_ids:
            t = block_texts.get(sid, "")
            if t:
                stem_parts.append(t)

        # Determine page
        pages_seen = set()
        for sid in stem_ids:
            if sid in block_meta:
                pages_seen.add(block_meta[sid]["page"])

        question_data = {
            "question_index": idx,
            "source_pdf": doc.source_path,
            "source_pages": sorted(pages_seen),
            "detection": {
                "method": cand.metadata.get("detection_method", "unknown"),
                "score": cand.score,
                "detected_number": cand.metadata.get("detected_number"),
            },
            "stem_block_ids": stem_ids,
            "stem_text": " ".join(stem_parts),
            "block_metadata": {
                sid: block_meta.get(sid, {}) for sid in stem_ids
            },
        }

        # Write file
        filename = f"question_{idx + 1:04d}.json"
        filepath = output_dir / filename
        filepath.write_text(
            json.dumps(question_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created_files.append(filepath)

    logger.info(f"Split {len(created_files)} questions to {output_dir}")
    return created_files
