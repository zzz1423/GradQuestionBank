"""
LLM-based Question Splitter — fine-grained question identification.

Sits between the rule engine (Layer 3) and the splitter (Layer 4).
The rule engine provides coarse candidates; this module uses LLM to:
1. Confirm which candidates are real questions
2. Split multi-question blocks into individual questions
3. Filter noise that the rule engine missed
4. Identify questions the rule engine overlooked

Input:  NormalizedDocument + AnnotatedDocument (from rule engine)
Output: Refined list of clean questions with text and metadata

Design:
- Processes one page at a time (keeps context window manageable)
- Preserves original block text for traceability
- Falls back to rule engine output if LLM fails
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pipeline.schema import NormalizedDocument, AnnotatedDocument, InlineType
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.llm.split_models import SplitResult, SplitQuestion
from pipeline.llm.validator import extract_and_validate_with_retry
from pipeline.latex_fix import normalize_latex_in_text
from pipeline.llm.schemas import load_schema

logger = logging.getLogger(__name__)

# System prompt for the LLM splitter
_SPLITTER_SYSTEM_PROMPT = """You are a math exam question splitter and noise filter.

Given OCR-extracted text from a math exam PDF page, identify ALL individual questions and filter out noise.

STRICT OUTPUT RULES:
1. Return ONLY valid JSON. Nothing else.
2. Do NOT output Markdown code fences (no ```json).
3. Do NOT output explanations, comments, or reasoning.
4. Do NOT output any text before or after the JSON.

OUTPUT SCHEMA:
{
  "questions": [
    {
      "question_number": "string or null — question number if visible (e.g. '1', '5', '(3)')",
      "content": "string — the FULL question text in LaTeX. Preserve original OCR exactly.",
      "page": "integer or null — page number (1-based)",
      "is_noise": false,
      "noise_reason": null
    }
  ]
}

RULES:
- Each question must be a COMPLETE, standalone item. Do NOT split a single question into parts.
- If a block contains MULTIPLE questions (e.g., numbered items 1-5 in one block), split them into separate entries.
- Mark non-question content as noise (is_noise=true):
  * Answer areas (答题区, 答案区)
  * Difficulty markers (难度★, 难度★★)
  * Target scores (目标分135)
  * Notes areas (笔记区)
  * Category labels (计算, 概念, 证明) — UNLESS they are part of the question text
  * Answer harvest templates (答题收获, 核心结论, 易错细节)
  * Page numbers, headers, footers
  * Empty or meaningless content
  - LaTeX FORMATTING (CRITICAL):
    * Wrap ALL math expressions in $ delimiters (inline math: $...$).
    * If OCR text has bare LaTeX commands without $, ADD the $ delimiters.
    * Preserve the original LaTeX notation - only add $ delimiters, do not rewrite formulas.
    * Already-delimited math ($...$ or $$...$$) should be kept as-is.
  - Preserve ALL mathematical notation exactly as it appears in the OCR output.
- If a question number is visible (e.g., "5 I = ..."), extract it into question_number.
- Questions may span multiple lines/blocks — combine them into a single question entry."""


def _extract_page_text(doc: NormalizedDocument, page_number: int) -> str:
    """Extract all text from a single page as a formatted string."""
    lines = []

    for page in doc.pages:
        if page.page_number != page_number:
            continue

        for block in page.blocks:
            parts = []

            # Title content
            if block.title_content:
                title_text = "".join(
                    i.content for i in block.title_content
                )
                parts.append(f"[Title] {title_text}")

            # Inline content
            if block.inline_content:
                for item in block.inline_content:
                    if item.type == InlineType.text:
                        parts.append(item.content)
                    elif item.type == InlineType.formula:
                        parts.append(f"${item.content}$")

            # Plain text
            if block.text and not block.inline_content:
                parts.append(block.text)

            # LaTeX
            if block.latex and not block.inline_content:
                parts.append(f"${block.latex}$")

            if parts:
                block_text = " ".join(parts).strip()
                if block_text:
                    lines.append(block_text)

    return "\n".join(lines)


def _extract_candidate_text(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
) -> dict[int, str]:
    """Extract text for each page that has candidates.

    Returns dict of page_number -> page text.
    """
    # Find pages with candidates
    candidate_pages: set[int] = set()
    block_to_page: dict[str, int] = {}

    for page in doc.pages:
        for block in page.blocks:
            block_to_page[block.id] = page.page_number

    for ann in ann_doc.annotations:
        if ann.type in ("question_candidate", "noise"):
            for bid in ann.block_ids:
                if bid in block_to_page:
                    candidate_pages.add(block_to_page[bid])

    # Extract text for each page
    page_texts: dict[int, str] = {}
    for page_num in sorted(candidate_pages):
        page_texts[page_num] = _extract_page_text(doc, page_num)

    return page_texts


def split_with_llm(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
    config: LLMConfig | None = None,
    output_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Use LLM to split and clean questions from the document.

    Args:
        doc: NormalizedDocument (Layer 2 output)
        ann_doc: AnnotatedDocument (Layer 3 output)
        config: LLM configuration
        output_dir: Optional directory to save LLM splitter output for debugging

    Returns:
        List of question dicts with keys: question_number, content, page, source_block_ids
    """
    config = config or LLMConfig()
    client = LLMClient(config)

    # Extract text per page
    page_texts = _extract_candidate_text(doc, ann_doc)

    if not page_texts:
        logger.warning("No pages with candidates found")
        return []

    all_questions: list[dict[str, Any]] = []
    all_noise: list[dict[str, Any]] = []

    for page_num, page_text in sorted(page_texts.items()):
        if not page_text.strip():
            logger.warning(f"Page {page_num} has no text content")
            continue

        logger.info(f"LLM splitting page {page_num} ({len(page_text)} chars)")

        try:
            questions, noise = _split_page(client, page_text, page_num)
            all_questions.extend(questions)
            all_noise.extend(noise)
            logger.info(
                f"Page {page_num}: {len(questions)} questions, {len(noise)} noise items"
            )
        except Exception as e:
            logger.error(f"LLM split failed for page {page_num}: {e}")
            # Fall back to rule engine candidates for this page
            fallback = _fallback_to_rule_engine(doc, ann_doc, page_num)
            all_questions.extend(fallback)
            logger.info(f"Page {page_num}: fell back to {len(fallback)} rule engine candidates")

    # Save debug output if requested
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        debug_path = output_dir / "llm_split_result.json"
        debug_path.write_text(
            json.dumps(
                {"questions": all_questions, "noise": all_noise},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(f"Saved LLM split result to {debug_path}")

    logger.info(
        f"LLM split complete: {len(all_questions)} questions, "
        f"{len(all_noise)} noise items filtered"
    )

    return all_questions


def _split_page(
    client: LLMClient,
    page_text: str,
    page_num: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a single page's text into questions using LLM.

    Returns:
        Tuple of (questions, noise_items)
    """
    user_prompt = (
        f"Page {page_num} of a math exam PDF. "
        f"Identify all individual questions and filter noise.\n\n"
        f"PAGE TEXT:\n{page_text}\n\n"
        f"Return the JSON now."
    )

    result = extract_and_validate_with_retry(
        client=client,
        system_prompt=_SPLITTER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model_class=SplitResult,
        max_retries=2,
        json_schema=load_schema("split_result"),
    )

    questions = []
    noise = []

    for sq in result.questions:
        entry = {
            "question_number": sq.question_number,
            "content": sq.content,
            "page": page_num,
        }

        if sq.is_noise:
            noise.append({
                **entry,
                "noise_reason": sq.noise_reason or "filtered by LLM",
            })
        else:
            questions.append(entry)

    # Apply LaTeX normalization to all questions
    for q in questions:
        q["content"] = normalize_latex_in_text(q["content"])

    return questions, noise


def _fallback_to_rule_engine(
    doc: NormalizedDocument,
    ann_doc: AnnotatedDocument,
    page_num: int,
) -> list[dict[str, Any]]:
    """Fall back to rule engine candidates when LLM fails.

    Extracts candidate text from the rule engine output for the given page.
    """
    block_text_lookup: dict[str, str] = {}
    block_page_lookup: dict[str, int] = {}

    for page in doc.pages:
        for block in page.blocks:
            block_page_lookup[block.id] = page.page_number
            parts = []
            if block.text:
                parts.append(block.text)
            if block.title_content:
                parts.append("".join(i.content for i in block.title_content))
            if block.inline_content:
                for item in block.inline_content:
                    if item.type == InlineType.text:
                        parts.append(item.content)
                    elif item.type == InlineType.formula:
                        parts.append(f"${item.content}$")
            if block.latex and not block.inline_content:
                parts.append(f"${block.latex}$")
            block_text_lookup[block.id] = " ".join(parts).strip()

    questions = []
    for ann in ann_doc.annotations:
        if ann.type != "question_candidate":
            continue

        # Check if this candidate is on the target page
        cand_page = block_page_lookup.get(ann.block_ids[0])
        if cand_page != page_num:
            continue

        # Get boundary block IDs if available
        stem_ids = ann.block_ids
        for boundary in ann_doc.annotations:
            if (boundary.type == "question_boundary"
                    and boundary.block_ids[0] == ann.block_ids[0]):
                stem_ids = boundary.metadata.get("stem_block_ids", ann.block_ids)
                break

        # Build text from stem blocks
        text_parts = []
        for bid in stem_ids:
            t = block_text_lookup.get(bid, "")
            if t:
                text_parts.append(t)

        if text_parts:
            raw_text = " ".join(text_parts)
            questions.append({
                "question_number": ann.metadata.get("detected_number"),
                "content": normalize_latex_in_text(raw_text),
                "page": cand_page,
            })

    return questions
