"""
OCR Repair Layer - post-processes OCR text using LLM.

Sits between question splitting and enrichment.
Fixes OCR errors, restores missing math symbols, using context.

Does NOT solve the problem or add information not implied by context.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.llm.validator import extract_and_validate_with_retry
from pipeline.llm.schemas import load_schema
from pipeline.latex_fix import normalize_latex_in_text
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Pydantic model for repair output
class RepairOutput(BaseModel):
    """Output from OCR repair LLM call."""
    repaired_text: str = Field(..., description="The repaired question text")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence in the repair")
    changes_made: str = Field("", description="Brief description of what was fixed")


class RepairResult:
    """Result of OCR repair for a single question."""
    def __init__(self, repaired_text: str, confidence: float = 1.0, changes_made: str = ""):
        self.repaired_text = repaired_text
        self.confidence = confidence
        self.changes_made = changes_made


_REPAIR_SYSTEM_PROMPT = """You are an OCR post-processor for Chinese math exam questions.

Given OCR-extracted text that may contain errors, fix the text while preserving the original meaning.

STRICT RULES:
1. Fix OCR garbled characters (e.g., random symbols replacing Chinese characters likeΙθ->设, Τς->则)
2. Restore clearly missing mathematical symbols and notation
3. Preserve the original LaTeX formulas exactly - do NOT modify them
4. Do NOT solve the problem or add answers
5. Do NOT add information that is not clearly implied by context
6. If you cannot determine what the original text was, keep the garbled text as-is

OUTPUT SCHEMA:
{
  "repaired_text": "string - the repaired question text",
  "confidence": 0.0 to 1.0,
  "changes_made": "brief description of what was fixed"
}

EXAMPLE:
Input: "160Ιθ $f(x)=x^2$,Τς divgrads) .."
Output: {"repaired_text": "设 $f(x)=x^2$,则 $\\\\operatorname{div}(\\\\operatorname{grad} f)$", "confidence": 0.7, "changes_made": "Fixed garbled Chinese, restored div/grad"}"""


def repair_question_text(
    stem_text: str,
    block_metadata: dict[str, Any],
    client: LLMClient,
    neighbors_text: str = "",
) -> RepairResult:
    """Repair OCR errors in a single question's text."""
    # Build block type context
    block_info = []
    for bid, meta in block_metadata.items():
        btype = meta.get("type", "unknown")
        block_info.append(f"Block {bid}: type={btype}")
    block_context = "; ".join(block_info) if block_info else "No metadata"

    user_prompt = (
        f"Fix OCR errors in this math exam question.\n\n"
        f"BLOCK TYPES: {block_context}\n\n"
        f"ORIGINAL TEXT: {stem_text}\n\n"
    )

    if neighbors_text:
        user_prompt += f"NEIGHBORING QUESTIONS (for context):\n{neighbors_text}\n\n"

    user_prompt += "Return the repaired JSON now."

    try:
        # Use a simple dict schema for repair output
        repair_schema = {
            "name": "RepairOutput",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "repaired_text": {"type": "string", "minLength": 1},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "changes_made": {"type": "string"}
                },
                "required": ["repaired_text", "confidence", "changes_made"]
            }
        }

        response = client.chat(
            system=_REPAIR_SYSTEM_PROMPT,
            user=user_prompt,
            json_schema=repair_schema,
        )

        # Parse the response
        json_text = response.content.strip()
        # Strip markdown fences if present
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            json_text = "\n".join(lines).strip()

        data = json.loads(json_text)
        repaired = data.get("repaired_text", stem_text)
        repaired = normalize_latex_in_text(repaired)

        return RepairResult(
            repaired_text=repaired,
            confidence=data.get("confidence", 0.5),
            changes_made=data.get("changes_made", ""),
        )

    except Exception as e:
        logger.warning(f"OCR repair failed: {e}")

    # Fallback: return original text with basic LaTeX fix
    return RepairResult(
        repaired_text=normalize_latex_in_text(stem_text),
        confidence=0.5,
        changes_made="LLM repair failed, applied basic LaTeX fix",
    )


def repair_all_questions(
    questions_dir: Path | str,
    config: LLMConfig | None = None,
    force: bool = False,
    progress_callback: Any | None = None,
) -> list[Path]:
    """Repair OCR errors in all question files.

    Creates question_XXXX.repaired.json alongside original files.
    """
    questions_dir = Path(questions_dir)
    config = config or LLMConfig()
    client = LLMClient(config)

    # Find question files (not enriched or repaired)
    question_files = sorted(questions_dir.glob("question_*.json"))
    question_files = [
        f for f in question_files
        if ".enriched." not in f.name and ".repaired." not in f.name
    ]

    if not question_files:
        logger.warning(f"No question files found in {questions_dir}")
        return []

    already_done = sum(
        1 for f in question_files
        if f.with_suffix(".repaired.json").exists() and not force
    )

    total = len(question_files)
    logger.info(f"OCR repairing {total} questions ({already_done} already done)")

    repaired_files: list[Path] = []

    # Pre-load all question texts for neighbor context (avoids re-reading)
    _question_text_cache: dict[Path, str] = {}
    for qf in question_files:
        try:
            qd = json.loads(qf.read_text(encoding="utf-8"))
            _question_text_cache[qf] = qd.get("stem_text", "")
        except Exception:
            _question_text_cache[qf] = ""

    for i, qpath in enumerate(question_files, 1):
        repaired_path = qpath.with_suffix(".repaired.json")

        if repaired_path.exists() and not force:
            logger.debug(f"Skipping {qpath.name} (already repaired)")
            repaired_files.append(repaired_path)
            continue

        question_data = json.loads(qpath.read_text(encoding="utf-8"))
        stem_text = question_data.get("stem_text", "")
        block_metadata = question_data.get("block_metadata", {})

        # Get neighboring questions for context (from cache)
        context_parts = []
        for other_q, other_text in _question_text_cache.items():
            if other_q == qpath:
                continue
            if other_text:
                context_parts.append(other_text[:200])
        neighbors_text = "\n".join(context_parts[:3])

        # Repair
        result = repair_question_text(
            stem_text=stem_text,
            block_metadata=block_metadata,
            client=client,
            neighbors_text=neighbors_text,
        )

        # Save repaired file
        repaired_data = {
            **question_data,
            "repaired_text": result.repaired_text,
            "repair_info": {
                "original_text": stem_text,
                "confidence": result.confidence,
                "changes_made": result.changes_made,
            },
        }

        repaired_path.write_text(
            json.dumps(repaired_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        repaired_files.append(repaired_path)

        if progress_callback:
            try:
                progress_callback(
                    step="ocr_repair",
                    progress=25 + int(5 * i / total),
                    current_question=i,
                    total_questions=total,
                )
            except Exception:
                pass

        if i % 10 == 0 or i == total:
            logger.info(f"OCR repair progress: {i}/{total}")

    logger.info(f"OCR repair complete: {len(repaired_files)} questions")
    return repaired_files
