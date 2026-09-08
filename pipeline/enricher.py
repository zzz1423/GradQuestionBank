"""
Question Enricher — per-question LLM enrichment with checkpoint/resume.

Processes each question file individually:
1. Read question_0001.json
2. Send to LLM for knowledge point extraction
3. Write question_0001.enriched.json
4. Move to next question

Features:
- Checkpoint/resume: skips already-enriched files
- Per-question retry: only retries failed questions
- Progress logging: shows N/M completed
- Future: supports parallel processing with ThreadPoolExecutor
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pipeline.llm.models import QuestionCollection
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.llm.prompt import get_system_prompt, build_combined_prompt
from pipeline.llm.validator import extract_and_validate, extract_and_validate_with_retry
from pipeline.llm.schemas import load_schema

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = LLMConfig(
    api_url="http://127.0.0.1:1234/v1/chat/completions",
    model="qwen/qwen3.5-9b",
    temperature=0.1,
    max_tokens=4000,
    timeout=120,
)


class _VisualQuestionExtraction(BaseModel):
    content: str = Field(..., min_length=1, description="Complete question text in LaTeX.")
    question_number: str | None = Field(
        None,
        description="Question number shown in the PDF page, or null when invisible.",
    )


VISUAL_RECOVERY_SYSTEM_PROMPT = """你是考研数学题复核助手。
原 PDF 页面图片中有一道题，OCR 得到的题干缺失或不完整。
请只看这张页面图片，把这道题的完整题干转写为 LaTeX 格式。
只返回 JSON，不要 Markdown，不要解释，不要补写答案：
{"content": "完整题目内容", "question_number": "题号或 null"}"""


def _is_question_content_complete(text: str) -> bool:
    """Minimal completeness check: content exists and is not just a label."""
    content = (text or "").strip()
    if not content:
        return False
    if len(content) < 8:
        return False
    if re.fullmatch(r"(?:第\s*)?\d{1,4}\s*[\.．、]?\s*(?:题)?", content):
        return False
    return True


def _extract_question_number(text: str) -> str | None:
    """Extract the leading question number from extracted text when visible."""
    content = (text or "").strip().lstrip("\ufeff")
    match = re.match(r"^(?:第\s*)?(\d{1,4})\s*[\.、．)）]?", content)
    if match:
        return match.group(1)
    return None


def _page_data_urls(pdf_path: Path, pages: list[int], scale: float = 1.5) -> list[str]:
    """Render PDF pages to JPEG data URLs for vision-capable LLM routes."""
    import base64
    import io

    import pypdfium2 as pdfium

    urls: list[str] = []
    with pdfium.PdfDocument(pdf_path) as document:
        for page_number in pages:
            if page_number < 1 or page_number > len(document):
                continue
            image = document[page_number - 1].render(scale=scale).to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=88)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            urls.append(f"data:image/jpeg;base64,{encoded}")
    return urls


def _recover_question_with_vision(
    question_data: dict[str, Any],
    client: LLMClient,
    pdf_path: Path,
) -> tuple[str, str | None]:
    """Re-extract an incomplete question from its original PDF page image."""
    pages = [
        int(p)
        for p in (question_data.get("source_pages") or [])
        if str(p).strip().isdigit()
    ]
    if not pages:
        raise ValueError("题目缺少来源页码，无法进行视觉复判")

    image_urls = _page_data_urls(pdf_path, pages)
    if not image_urls:
        raise ValueError(f"无法渲染 PDF 页面：{', '.join(str(p) for p in pages)}")

    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"题目位于 PDF 第 {', '.join(str(p) for p in pages)} 页。"
                "请根据页面图片复现该题的完整题干。"
            ),
        }
    ]
    for url in image_urls:
        user_content.append({"type": "image_url", "image_url": {"url": url}})
    user_content.append({"type": "text", "text": "返回 JSON 格式的完整题干。"})

    response = client.chat(
        system=VISUAL_RECOVERY_SYSTEM_PROMPT,
        user=user_content,
        max_tokens=min(client.config.max_tokens, 8192),
    )
    parsed = extract_and_validate(response, _VisualQuestionExtraction)
    content = parsed.content.strip()
    if not content:
        raise ValueError("视觉复判返回空题干")
    return content, parsed.question_number


def _build_single_question_prompt(question_data: dict[str, Any]) -> str:
    """Build a prompt for a single question.

    Uses repaired_text if available (from OCR repair step),
    otherwise falls back to stem_text.
    """
    q = question_data
    num = f" (#{q['detection']['detected_number']})" if q["detection"].get("detected_number") else ""
    pages = ", ".join(str(p) for p in q.get("source_pages", []))
    page_str = f" [Page {pages}]" if pages else ""

    # Use repaired_text if available, otherwise stem_text
    text = q.get("repaired_text") or q.get("stem_text", "")

    return (
        f"Extract knowledge points for this math exam question.\n\n"
        f"Question{num}{page_str}:\n"
        f"Type hint: {q['detection'].get('method', 'unknown')}\n"
        f"Text: {text}\n\n"
        f"If the PDF shows a question number for this question, include it as "
        f"question_number; otherwise use null.\n\n"
        f"Return the JSON now."
    )


def enrich_single(
    question_path: Path,
    client: LLMClient,
    existing_kps: str = "",
    force: bool = False,
    pdf_path: Path | None = None,
) -> Path:
    """Enrich a single question file.

    Args:
        question_path: Path to question_XXXX.json
        client: LLM client
        existing_kps: Existing KP hierarchy text
        force: If True, re-process even if enriched file exists

    Returns:
        Path to the enriched file
    """
    enriched_path = question_path.with_suffix(".enriched.json")

    # Skip if already enriched (checkpoint/resume)
    if enriched_path.exists() and not force:
        logger.debug(f"Skipping {question_path.name} (already enriched)")
        return enriched_path

    # Load question data
    question_data = json.loads(question_path.read_text(encoding="utf-8"))

    # Re-check incomplete OCR through the original page image before enriching.
    source_text = question_data.get("repaired_text") or question_data.get("stem_text", "")
    visual_retry: dict[str, Any] = {}
    needs_review = False
    review_note = ""
    if not _is_question_content_complete(source_text):
        if pdf_path is not None:
            pages = [
                int(p)
                for p in (question_data.get("source_pages") or [])
                if str(p).strip().isdigit()
            ]
            try:
                visual_text, visual_question_number = _recover_question_with_vision(
                    question_data, client, pdf_path
                )
                question_data["repaired_text"] = visual_text
                visual_retry = {
                    "status": "recovered",
                    "pages": pages,
                    "content": visual_text,
                    "question_number": visual_question_number,
                }
                logger.info(
                    "Visual recovery succeeded for %s (%s)",
                    question_path.name,
                    pages,
                )
            except Exception as e:
                visual_retry = {
                    "status": "failed",
                    "pages": pages,
                    "error": str(e)[:300],
                }
                needs_review = True
                review_note = f"视觉复判失败：{e}"
                logger.warning("Visual recovery failed for %s: %s", question_path.name, e)
        else:
            needs_review = True
            review_note = "题干不完整且未提供原 PDF，无法视觉复判"

    # Build prompts
    system_prompt = get_system_prompt(mode="combined")
    user_prompt = _build_single_question_prompt(question_data)

    if existing_kps:
        user_prompt = (
            f"EXISTING KNOWLEDGE POINT HIERARCHY (for reference):\n"
            f"{existing_kps}\n\n"
            f"{user_prompt}"
        )

    # Call LLM with retry
    result = extract_and_validate_with_retry(
        client=client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_class=QuestionCollection,
        max_retries=2,
        json_schema=load_schema("question_collection"),
    )

    # Extract the single question from result
    if not result.questions:
        raise ValueError(f"LLM returned no questions for {question_path.name}")

    enriched_question = result.questions[0]
    source_pages = [
        int(p) for p in (question_data.get("source_pages") or [])
        if str(p).strip().isdigit()
    ]
    source_page = enriched_question.source_page or (source_pages[0] if source_pages else None)
    detected_number = question_data.get("detection", {}).get("detected_number")
    visual_question_number = (
        visual_retry.get("question_number")
        if visual_retry.get("status") == "recovered"
        else None
    )
    question_number = (
        enriched_question.question_number
        or visual_question_number
        or _extract_question_number(source_text)
        or detected_number
        or str((question_data.get("question_index", 0) or 0) + 1)
    )

    # Build enriched data
    enriched_data = {
        **question_data,
        "enrichment": {
            "question_type": enriched_question.question_type.value,
            "subject_name": enriched_question.subject_name,
            "knowledge_points": [
                {
                    "name": kp.name,
                    "chapter": kp.chapter,
                    "role": kp.role.value,
                    "weight": kp.weight,
                }
                for kp in enriched_question.knowledge_points
            ],
            "source_page": source_page,
            "source_pages": source_pages,
            "question_number": question_number,
            "needs_review": needs_review,
            "review_note": review_note,
            "visual_retry": visual_retry,
        },
        "content": enriched_question.content,
        "source_page": source_page,
        "source_pages": source_pages,
        "question_number": question_number,
        "needs_review": needs_review,
        "review_note": review_note,
    }

    # Write enriched file
    enriched_path.write_text(
        json.dumps(enriched_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return enriched_path


def enrich_all(
    questions_dir: Path | str,
    config: LLMConfig | None = None,
    existing_kps: str = "",
    force: bool = False,
    progress_callback: Any | None = None,
    pdf_path: Path | str | None = None,
) -> list[Path]:
    """Enrich all question files in a directory.

    Args:
        questions_dir: Directory containing question_XXXX.json files
        config: LLM configuration
        existing_kps: Existing KP hierarchy text
        force: If True, re-process all files even if enriched

    Returns:
        List of paths to enriched files
    """
    questions_dir = Path(questions_dir)
    pdf_path = Path(pdf_path) if pdf_path else None
    config = config or DEFAULT_CONFIG
    client = LLMClient(config)

    # Find all question files (not enriched ones)
    question_files = sorted(questions_dir.glob("question_*.json"))
    question_files = [
        f for f in question_files
        if ".enriched." not in f.name
        and ".repaired." not in f.name
        and ".error." not in f.name
    ]

    if not question_files:
        logger.warning(f"No question files found in {questions_dir}")
        return []

    # Count already enriched (for progress)
    already_done = sum(1 for f in question_files
                       if f.with_suffix(".enriched.json").exists() and not force)

    total = len(question_files)
    logger.info(f"Enriching {total} questions ({already_done} already done)")

    enriched_files: list[Path] = []
    errors: list[dict[str, str]] = []

    for i, qpath in enumerate(question_files, 1):
        try:
            epath = enrich_single(
                qpath,
                client,
                existing_kps,
                force=force,
                pdf_path=pdf_path,
            )
            enriched_files.append(epath)


            # Report progress (30-90% range for enrich step)
            if progress_callback:
                pct = 30 + int(60 * i / total)
                try:
                    progress_callback(
                        step="enrich",
                        progress=pct,
                        current_question=i,
                        total_questions=total,
                    )
                except Exception:
                    pass

            # Progress log every 10 questions or on last
            if i % 10 == 0 or i == total:
                logger.info(f"Progress: {i}/{total} enriched")

        except Exception as e:
            error_info = {
                "file": qpath.name,
                "error": str(e),
            }
            errors.append(error_info)
            logger.error(f"Failed to enrich {qpath.name}: {e}")

            # Write error file for debugging
            error_path = qpath.with_suffix(".error.json")
            error_path.write_text(
                json.dumps(error_info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    logger.info(
        f"Enrichment complete: {len(enriched_files)}/{total} succeeded, "
        f"{len(errors)} failed"
    )

    if errors:
        logger.warning(f"Failed files: {[e['file'] for e in errors]}")

    return enriched_files
