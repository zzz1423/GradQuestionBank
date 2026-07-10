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
from pathlib import Path
from typing import Any

from pipeline.llm.models import QuestionCollection
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.llm.prompt import get_system_prompt, build_combined_prompt
from pipeline.llm.validator import extract_and_validate_with_retry
from pipeline.llm.schemas import load_schema

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = LLMConfig(
    api_url="http://127.0.0.1:1234/v1/chat/completions",
    model="qwen/qwen3.5-9b",
    temperature=0.1,
    max_tokens=4000,
    timeout=120,
)


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
        f"Return the JSON now."
    )


def enrich_single(
    question_path: Path,
    client: LLMClient,
    existing_kps: str = "",
    force: bool = False,
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
            "source_page": enriched_question.source_page,
        },
        "content": enriched_question.content,
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
    config = config or DEFAULT_CONFIG
    client = LLMClient(config)

    # Find all question files (not enriched ones)
    question_files = sorted(questions_dir.glob("question_*.json"))
    question_files = [f for f in question_files if ".enriched." not in f.name and ".repaired." not in f.name]

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
            epath = enrich_single(qpath, client, existing_kps, force=force)
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
