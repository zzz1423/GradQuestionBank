"""
Pydantic models for LLM-based question splitting.

The LLM receives raw page text and identifies:
- Individual question boundaries
- Noise to filter out
- Question numbers and page references
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SplitQuestion(BaseModel):
    """A single question identified by the LLM splitter."""

    question_number: Optional[str] = Field(
        None,
        description="Question number if visible, e.g. '1', '5', '(3)'. Null if not numbered.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The full question text, including all formulas in LaTeX notation. "
                    "Preserve the original OCR text exactly — do not modify or correct.",
    )
    page: Optional[int] = Field(
        None,
        ge=1,
        description="Page number in the source PDF (1-based). Null if uncertain.",
    )
    is_noise: bool = Field(
        False,
        description="True if this block is NOT a real question (e.g., answer area, "
                    "difficulty marker, notes, headers, category labels).",
    )
    noise_reason: Optional[str] = Field(
        None,
        description="If is_noise=True, explain why (e.g., 'answer area', 'difficulty marker').",
    )


class SplitResult(BaseModel):
    """Top-level LLM response for the question splitter."""

    questions: list[SplitQuestion] = Field(
        ...,
        description="List of identified questions. Include noise items with is_noise=True "
                    "so the caller can log what was filtered.",
    )
