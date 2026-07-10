"""
Prompt builder for LLM structured output.

Centralizes all prompt construction logic.
The prompts are designed to be model-agnostic — they work with any
OpenAI-compatible API (LM Studio, Ollama, OpenAI, vLLM, etc.).

Prompt design principles:
1. Explicit JSON-only output instructions (no markdown, no explanation)
2. Schema is described in natural language, not as raw JSON Schema
   (so it works with models that don't support structured output)
3. Business context (existing knowledge points) is injected dynamically
4. Questions are presented with their extracted text, not raw block IDs
"""
from __future__ import annotations

from typing import Any


# ============================================================
# System prompt for combined extraction (questions + KPs in one pass)
# ============================================================

_SYSTEM_COMBINED = """You are a math exam question analyzer. Given OCR-extracted text from a math exam PDF, extract all questions and classify their knowledge points.

STRICT OUTPUT RULES:
1. Return ONLY valid JSON. Nothing else.
2. Do NOT output Markdown code fences (no ```json).
3. Do NOT output explanations, comments, or reasoning.
4. Do NOT output any text before or after the JSON.
5. The JSON MUST conform exactly to the schema described below.

OUTPUT SCHEMA:
{
  "questions": [
    {
      "content": "string — the question text in LaTeX. Preserve the original OCR output exactly. Do NOT modify, correct, or rewrite any text or formula.",
      "question_type": "string — one of: choice, fill_blank, true_false, short_answer, calculation, proof, comprehensive, unknown",
      "subject_name": "string — subject name, e.g. '高等数学', '线性代数'",
      "knowledge_points": [
        {
          "name": "string — knowledge point name, e.g. '函数极限'",
          "chapter": "string — chapter name, e.g. '极限'",
          "role": "string — 'primary' or 'secondary'",
          "weight": 0.0 to 1.0 — relevance weight, primary typically 0.7-1.0, secondary 0.1-0.5
        }
      ],
      "source_page": integer or null — page number in the source PDF (1-based)
    }
  ]
}

RULES:
- Every question MUST have at least one knowledge_point with role="primary".
- Include 1-3 knowledge_points per question.
- Use standard Chinese math education terminology for knowledge point and chapter names.
- content must be the ORIGINAL OCR text, including all LaTeX notation. Never modify it.
- If a question number is visible (e.g. "5", "8"), extract it but do NOT prepend it to content."""


# ============================================================
# System prompt for question classification only (Layer 4)
# ============================================================

_SYSTEM_CLASSIFY = """You are a math exam question classifier. Given a list of question candidates detected by a rule engine, confirm which are real questions and classify them.

STRICT OUTPUT RULES:
1. Return ONLY valid JSON. Nothing else.
2. Do NOT output Markdown code fences.
3. Do NOT output explanations, comments, or reasoning.
4. The JSON MUST conform exactly to the schema described below.

OUTPUT SCHEMA:
{
  "questions": [
    {
      "content": "string — the question text in LaTeX, preserved exactly from input",
      "question_type": "string — one of: choice, fill_blank, true_false, short_answer, calculation, proof, comprehensive, unknown",
      "subject_name": "string — subject name",
      "knowledge_points": [
        {
          "name": "string",
          "chapter": "string",
          "role": "string — 'primary' or 'secondary'",
          "weight": 0.0 to 1.0
        }
      ],
      "source_page": integer or null
    }
  ]
}

RULES:
- Skip candidates that are NOT real questions (noise, headers, metadata).
- Every confirmed question MUST have at least one primary knowledge_point.
- Preserve the original OCR text exactly in content."""


# ============================================================
# User prompt builders
# ============================================================

def build_combined_prompt(
    questions: list[dict[str, Any]],
    existing_kps: str = "",
) -> str:
    """Build user prompt for combined question + KP extraction.

    Args:
        questions: List of dicts with keys: index, number, type, text, page
        existing_kps: Existing knowledge point hierarchy text (optional context)
    """
    lines = [
        "Extract all questions and their knowledge points from the OCR text below.",
        "",
    ]

    if existing_kps:
        lines.append("EXISTING KNOWLEDGE POINT HIERARCHY (for reference):")
        lines.append(existing_kps)
        lines.append("")

    lines.append("QUESTIONS:")
    lines.append("")

    for q in questions:
        num = f" (#{q['number']})" if q.get("number") else ""
        page = f" [Page {q['page']}]" if q.get("page") else ""
        lines.append(f"--- Question {q['index']}{num}{page} ---")
        lines.append(f"Type hint: {q.get('type', 'unknown')}")
        lines.append(f"Text: {q['text']}")
        lines.append("")

    lines.append("Return the JSON now.")
    return "\n".join(lines)


def build_classify_prompt(
    questions: list[dict[str, Any]],
    existing_kps: str = "",
) -> str:
    """Build user prompt for question classification + KP extraction.

    Args:
        questions: List of dicts with keys: index, number, type, text, page
        existing_kps: Existing knowledge point hierarchy text (optional context)
    """
    lines = [
        "Analyze each question candidate below. Confirm which are real questions,",
        "classify them, and extract their knowledge points.",
        "",
    ]

    if existing_kps:
        lines.append("EXISTING KNOWLEDGE POINT HIERARCHY (for reference):")
        lines.append(existing_kps)
        lines.append("")

    lines.append("CANDIDATES:")
    lines.append("")

    for q in questions:
        num = f" (#{q['number']})" if q.get("number") else ""
        page = f" [Page {q['page']}]" if q.get("page") else ""
        lines.append(f"Candidate {q['index']}{num}{page}:")
        lines.append(f"  Type hint: {q.get('type', 'unknown')}")
        lines.append(f"  Text: {q['text']}")
        lines.append("")

    lines.append("Return the JSON now.")
    return "\n".join(lines)


# ============================================================
# System prompt selector
# ============================================================

def get_system_prompt(mode: str = "combined") -> str:
    """Return the appropriate system prompt.

    Args:
        mode: "combined" for full extraction, "classify" for classification only
    """
    if mode == "classify":
        return _SYSTEM_CLASSIFY
    return _SYSTEM_COMBINED
