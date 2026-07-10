"""
Question Detection Rule Engine (Layer 3)

Detects question boundaries in a NormalizedDocument using heuristic rules.
Produces an AnnotatedDocument without modifying any blocks.

Rules are designed for Chinese graduate exam PDFs (考研数学题).
They are intentionally conservative: high-confidence candidates only.
Low-confidence or ambiguous cases are left for the LLM layer (Layer 4).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pipeline.schema import (
    SCHEMA_VERSION, PIPELINE_VERSION,
    NormalizedDocument, Block, BlockType, Inline, InlineType,
    Annotation, AnnotatedDocument, Provenance,
    make_annotation_id,
)

COMPONENT = "rule_engine"
COMPONENT_VERSION = "0.1.0"


# ============================================================
# Noise patterns — blocks that are definitely NOT question content
# ============================================================

# Matches: 难度★, 难度★★★, 难度☆★
_RE_DIFFICULTY = re.compile(r"^难度[★☆]{1,5}$")

# Matches: 目标分135 0 90必做, 目标分 135 110 90必做, 1目标分1351090必做
_RE_TARGET_SCORE = re.compile(r"^[\d\s]*目标分[\d\sO○o零]+$", re.IGNORECASE)
# Also match the variant without 必做
_RE_TARGET_SCORE2 = re.compile(r"^[\d\s]*目标分[\d\sO○o零必做选做]+$")

# Matches: 计算, 概念, 计算。, 计算 笔记区, 计算。
_RE_CATEGORY = re.compile(r"^(计算|概念|证明|填空|选择|解答|综合)")

# Matches: 笔记区, 笔记区。
_RE_NOTES_AREA = re.compile(r"^笔记区[。、．\s]*$")

# Matches: 答题区
_RE_ANSWER_AREA = re.compile(r"^答题区[。、．\s]*$")

# Matches: 答题收获 □ 核心结论 □ 易错细节 □ 特例反例 □ 知识盲区
_RE_ANSWER_HARVEST = re.compile(r"^答题收获")

# Matches: 核心结论 □, 易错细节 □, etc.
_RE_REVIEW_ITEM = re.compile(r"^(核心结论|易错细节|特例反例|知识盲区)")

# Empty or whitespace-only text
_RE_EMPTY = re.compile(r"^\s*$")

# Page headers/footers (already typed, but just in case)
_RE_PAGE_NUM = re.compile(r"^\d{1,3}$")


# ============================================================
# Question number patterns
# ============================================================

# Matches standalone number at start of text: "5 I = ...", "8 \operatorname..."
# The number must be followed by a space or formula content
_RE_LEADING_NUMBER = re.compile(r"^(\d{1,2})\s+(.+)", re.DOTALL)

# Matches patterns like "(1)", "(2)" for sub-questions
_RE_SUB_QUESTION = re.compile(r"^\((\d{1,2})\)")

# Matches Chinese-style numbering: 一、二、三
_RE_CHINESE_NUMBER = re.compile(r"^(一|二|三|四|五|六|七|八|九|十)[、．.\s]")


# ============================================================
# Content heuristics
# ============================================================

def _get_block_text(block: Block) -> str:
    """Extract the full text content of a block."""
    if block.text:
        return block.text
    if block.title_content:
        return "".join(i.content for i in block.title_content)
    if block.inline_content:
        return "".join(i.content for i in block.inline_content)
    if block.latex:
        return block.latex
    return ""


def _get_inline_text(block: Block) -> str:
    """Extract only the text-type inline content (skip formulas)."""
    parts = []
    inlines = block.inline_content or block.title_content or []
    for inline in inlines:
        if inline.type == InlineType.text:
            parts.append(inline.content)
    return "".join(parts)


def _has_formula(block: Block) -> bool:
    """Check if block contains any formula inlines."""
    if block.latex:
        return True
    for inline in (block.inline_content or []):
        if inline.type == InlineType.formula:
            return True
    return False


def _is_noise(block: Block) -> tuple[bool, str]:
    """
    Check if a block is noise (not question content).
    Returns (is_noise, reason).
    """
    text = _get_block_text(block)
    inline_text = _get_inline_text(block)

    # Skip non-paragraph types that are structural
    if block.type in (BlockType.page_header, BlockType.page_footer,
                      BlockType.page_number):
        return True, f"structural:{block.type.value}"

    if block.type == BlockType.aside:
        return True, "aside"

    if block.type == BlockType.title and block.level and block.level >= 2:
        # Section titles like "填空" are noise for question detection
        # But we mark them specially, not as generic noise
        return True, "section_title"

    # Check text-based noise patterns
    if _RE_DIFFICULTY.match(text):
        return True, "difficulty"

    if _RE_TARGET_SCORE.match(text) or _RE_TARGET_SCORE2.match(text):
        return True, "target_score"

    if _RE_NOTES_AREA.match(text):
        return True, "notes_area"

    if _RE_ANSWER_AREA.match(text):
        return True, "answer_area"

    if _RE_ANSWER_HARVEST.match(text):
        return True, "answer_harvest"

    if _RE_REVIEW_ITEM.match(text):
        return True, "review_item"

    if _RE_CATEGORY.match(text):
        return True, "category"

    if _RE_EMPTY.match(text):
        return True, "empty"

    return False, ""


def _is_question_candidate(block: Block) -> tuple[bool, float, dict[str, Any]]:
    """
    Check if a block is likely a question start.
    Returns (is_candidate, score, metadata).
    """
    text = _get_block_text(block)
    inline_text = _get_inline_text(block)
    metadata: dict[str, Any] = {}

    # Must be a paragraph or title type
    if block.type not in (BlockType.paragraph, BlockType.title, BlockType.list_item):
        return False, 0.0, {}

    # Pattern 1: Leading number followed by formula/content
    # e.g., "5 I = \operatorname..." or "8 \operatorname..."
    m = _RE_LEADING_NUMBER.match(text)
    if m:
        num = m.group(1)
        rest = m.group(2).strip()
        if 1 <= int(num) <= 99 and len(rest) > 10:
            metadata["detected_number"] = num
            metadata["detection_method"] = "leading_number"
            return True, 0.9, metadata

    # Pattern 2: Title block with Chinese numbering
    if block.type == BlockType.title:
        if _RE_CHINESE_NUMBER.match(text):
            metadata["detection_method"] = "chinese_number_title"
            return True, 0.7, metadata

    # Pattern 3: Paragraph with formula(s) -- question stem
    if block.type == BlockType.paragraph and _has_formula(block):
        text_len = len(inline_text.strip())
        formula_count = sum(1 for i in (block.inline_content or [])
                          if i.type == InlineType.formula)
        metadata["text_length"] = text_len
        metadata["formula_count"] = formula_count

        # High confidence: long text + formulas
        if text_len >= 15 and formula_count >= 1:
            metadata["detection_method"] = "formula_paragraph"
            return True, 0.7, metadata

        # Medium confidence: short text prefix + formulas
        # e.g., "设 ，则 " (text_len=5, formulas=2)
        question_starts = ("设", "已知", "若", "当", "计算", "求", "证明")
        if text_len >= 1 and any(inline_text.strip().startswith(p) for p in question_starts):
            metadata["detection_method"] = "prefix_with_formula"
            return True, 0.65, metadata

        # Lower confidence: pure formula block (no text at all)
        if text_len == 0 and formula_count >= 1:
            metadata["detection_method"] = "pure_formula"
            return True, 0.4, metadata

    # Pattern 4: Substantial text paragraph (no formula) that looks like a question
    # e.g., "I = lim (√x + x5 − √x −x5) ="
    if block.type == BlockType.paragraph and not _has_formula(block):
        stripped = inline_text.strip()
        if len(stripped) >= 15:
            has_math_chars = any(c in stripped for c in "=()[]{}^_+")
            has_eq_or_lim = any(w in stripped.lower() for w in ("lim", "sin", "cos", "ln", "log", "exp"))
            starts_like_q = any(stripped.startswith(p) for p in ("I ", "设", "已知", "求", "证明"))
            if has_math_chars or has_eq_or_lim or starts_like_q:
                metadata["detection_method"] = "text_math_expression"
                return True, 0.5, metadata

    # Pattern 5: Text starting with question-like prefixes (fallback)
    question_prefixes = ("设", "已知", "求", "证明", "计算", "讨论", "判断",
                         "试证", "若", "当", "设函数", "设常数")
    stripped = inline_text.strip()
    for prefix in question_prefixes:
        if stripped.startswith(prefix) and len(stripped) >= 5:
            metadata["detection_method"] = "question_prefix"
            metadata["prefix"] = prefix
            return True, 0.5, metadata

    return False, 0.0, {}

    # Pattern 1: Leading number followed by formula/content
    # e.g., "5 I = \operatorname..." or "8 \operatorname..."
    m = _RE_LEADING_NUMBER.match(text)
    if m:
        num = m.group(1)
        rest = m.group(2).strip()
        # Number should be small (1-99) and followed by substantial content
        if 1 <= int(num) <= 99 and len(rest) > 10:
            metadata["detected_number"] = num
            metadata["detection_method"] = "leading_number"
            return True, 0.9, metadata

    # Pattern 2: Title block that looks like a question header
    if block.type == BlockType.title:
        # "填空" is a section header, not a question
        # But "例1" or "Exercise 1" would be a question
        if _RE_CHINESE_NUMBER.match(text):
            metadata["detection_method"] = "chinese_number_title"
            return True, 0.7, metadata

    # Pattern 3: Substantial paragraph with formula content
    # These are question stems without explicit numbers
    if block.type == BlockType.paragraph and _has_formula(block):
        text_len = len(inline_text.strip())
        formula_count = sum(1 for i in (block.inline_content or [])
                          if i.type == InlineType.formula)

        # Long text with formulas is likely a question stem
        if text_len >= 15 and formula_count >= 1:
            metadata["detection_method"] = "formula_paragraph"
            metadata["text_length"] = text_len
            metadata["formula_count"] = formula_count
            return True, 0.6, metadata

    # Pattern 4: Text starting with question-like prefixes
    question_prefixes = ("设", "已知", "求", "证明", "计算", "讨论", "判断",
                         "试证", "若", "当", "设函数", "设常数")
    stripped = inline_text.strip()
    for prefix in question_prefixes:
        if stripped.startswith(prefix) and len(stripped) > 15:
            metadata["detection_method"] = "question_prefix"
            metadata["prefix"] = prefix
            return True, 0.5, metadata

    return False, 0.0, {}


# ============================================================
# Main detection function
# ============================================================

def detect(
    doc: NormalizedDocument,
    output_path: str | None = None,
) -> AnnotatedDocument:
    """
    Run question detection on a NormalizedDocument.

    Produces an AnnotatedDocument with:
    - question_number: blocks with detected question numbers
    - question_candidate: blocks that are likely question starts
    - noise: blocks that are definitely not question content

    Does NOT modify any blocks in the NormalizedDocument.
    """
    now = datetime.now(timezone.utc).isoformat()
    annotations: list[Annotation] = []
    ann_seq = 0

    def make_prov(method: str) -> Provenance:
        return Provenance(
            source_tool="internal",
            source_version=COMPONENT_VERSION,
            source_raw_id=None,
            source_page=None,
            component=COMPONENT,
            component_version=COMPONENT_VERSION,
            created_at=now,
        )

    def add_annotation(ann_type: str, block_id: str, score: float | None = None,
                       metadata: dict[str, Any] | None = None) -> None:
        nonlocal ann_seq
        ann_seq += 1
        annotations.append(Annotation(
            annotation_id=make_annotation_id(doc.document_id, ann_seq),
            type=ann_type,
            block_ids=[block_id],
            provenance=make_prov(ann_type),
            score=score,
            metadata=metadata or {},
        ))

    # Process each block
    for page in doc.pages:
        for block in page.blocks:
            # Check noise first
            is_noise, noise_reason = _is_noise(block)
            if is_noise:
                add_annotation("noise", block.id, metadata={"reason": noise_reason})
                continue

            # Check question candidate
            is_candidate, score, meta = _is_question_candidate(block)
            if is_candidate:
                # If we detected a number, also add question_number annotation
                if "detected_number" in meta:
                    add_annotation("question_number", block.id,
                                   score=score, metadata=meta)
                add_annotation("question_candidate", block.id,
                               score=score, metadata=meta)

    # Build AnnotatedDocument
    ann_doc = AnnotatedDocument(
        document_id=doc.document_id,
        normalized_version=doc.created_at,
        annotations=annotations,
        schema_version=SCHEMA_VERSION,
        pipeline_version=PIPELINE_VERSION,
        created_at=now,
    )

    # Save if path specified
    if output_path:
        from pathlib import Path
        ann_doc.save(Path(output_path))

    return ann_doc



# ============================================================
# Boundary detection
# ============================================================

def detect_boundaries(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
) -> AnnotatedDocument:
    """
    Add question_boundary annotations based on question_candidate positions.

    For each candidate, the boundary extends from the candidate block
    to just before the next candidate block. Noise blocks within that
    range are excluded from the question's stem blocks.

    Returns a new AnnotatedDocument with additional question_boundary annotations.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Build block lookup: id -> (page_idx, reading_order, block)
    block_order: dict[str, tuple[int, int]] = {}
    for page in doc.pages:
        for block in page.blocks:
            block_order[block.id] = (page.page_number - 1, block.reading_order)

    # Collect candidate and noise block IDs from existing annotations
    candidate_ids: list[str] = []
    noise_ids: set[str] = set()
    candidate_meta: dict[str, dict] = {}
    candidate_scores: dict[str, float] = {}

    for a in ann_doc.annotations:
        bid = a.block_ids[0]
        if a.type == "question_candidate":
            candidate_ids.append(bid)
            candidate_meta[bid] = a.metadata
            if a.score is not None:
                candidate_scores[bid] = a.score
        elif a.type == "noise":
            noise_ids.add(bid)

    # Sort candidates by document position
    candidate_ids.sort(key=lambda bid: block_order.get(bid, (999, 999)))

    # Build flat block list for range lookup
    all_blocks: list[str] = []
    for page in doc.pages:
        for block in page.blocks:
            all_blocks.append(block.id)

    block_idx_map = {bid: i for i, bid in enumerate(all_blocks)}

    # For each candidate, determine its boundary
    new_annotations: list[Annotation] = []
    ann_seq = len(ann_doc.annotations)

    for i, cand_id in enumerate(candidate_ids):
        cand_idx = block_idx_map.get(cand_id)
        if cand_idx is None:
            continue

        # End index: start of next candidate, or end of document
        if i + 1 < len(candidate_ids):
            next_cand_id = candidate_ids[i + 1]
            next_idx = block_idx_map.get(next_cand_id, len(all_blocks))
        else:
            next_idx = len(all_blocks)

        # Collect non-noise blocks in range [cand_idx, next_idx)
        stem_ids = []
        for j in range(cand_idx, next_idx):
            bid = all_blocks[j]
            if bid not in noise_ids:
                stem_ids.append(bid)

        # Create boundary annotation
        ann_seq += 1
        prov = Provenance(
            source_tool="internal",
            source_version=COMPONENT_VERSION,
            source_raw_id=None,
            source_page=None,
            component=COMPONENT,
            component_version=COMPONENT_VERSION,
            created_at=now,
        )

        meta = dict(candidate_meta.get(cand_id, {}))
        meta["stem_count"] = len(stem_ids)
        meta["range_start"] = cand_idx
        meta["range_end"] = next_idx - 1

        new_annotations.append(Annotation(
            annotation_id=make_annotation_id(doc.document_id, ann_seq),
            type="question_boundary",
            block_ids=[cand_id],
            provenance=prov,
            score=candidate_scores.get(cand_id),
            metadata={
                **meta,
                "stem_block_ids": stem_ids,
            },
        ))

    # Return new AnnotatedDocument with boundary annotations added
    return AnnotatedDocument(
        document_id=ann_doc.document_id,
        normalized_version=ann_doc.normalized_version,
        annotations=ann_doc.annotations + new_annotations,
        schema_version=ann_doc.schema_version,
        pipeline_version=ann_doc.pipeline_version,
        created_at=ann_doc.created_at,
    )

# ============================================================
# Summary helper
# ============================================================

def summarize(ann_doc: AnnotatedDocument) -> dict[str, Any]:
    """Return a human-readable summary of detection results."""
    from collections import Counter
    type_counts = Counter(a.type for a in ann_doc.annotations)
    candidates = [a for a in ann_doc.annotations if a.type == "question_candidate"]
    noise = [a for a in ann_doc.annotations if a.type == "noise"]
    numbers = [a for a in ann_doc.annotations if a.type == "question_number"]

    return {
        "total_annotations": len(ann_doc.annotations),
        "type_distribution": dict(type_counts),
        "question_candidates": len(candidates),
        "noise_blocks": len(noise),
        "detected_numbers": len(numbers),
        "candidate_details": [
            {
                "block_id": a.block_ids[0],
                "score": a.score,
                "method": a.metadata.get("detection_method"),
                "number": a.metadata.get("detected_number"),
            }
            for a in candidates
        ],
        "noise_reasons": [
            {"block_id": a.block_ids[0], "reason": a.metadata.get("reason")}
            for a in noise
        ],
    }
