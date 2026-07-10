"""
Pydantic data models for LLM structured output.

These models define the CONTRACT between the LLM and the application.
They contain ONLY business data — no database IDs, no internal references.

All models are designed to be extensible: add new Optional fields freely
without breaking existing prompts or parsers.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# Enums
# ============================================================

class KPRole(str, Enum):
    """Role of a knowledge point relative to a question."""
    primary = "primary"
    secondary = "secondary"


class QuestionType(str, Enum):
    """Question type classification."""
    choice = "choice"
    fill_blank = "fill_blank"
    true_false = "true_false"
    short_answer = "short_answer"
    calculation = "calculation"
    proof = "proof"
    comprehensive = "comprehensive"
    unknown = "unknown"


# ============================================================
# Knowledge Point
# ============================================================

class KnowledgePoint(BaseModel):
    """A single knowledge point associated with a question.

    Contains ONLY business data. Database IDs are assigned by the import layer.
    """
    name: str = Field(
        ...,
        min_length=1,
        description="Knowledge point name, e.g. '函数极限', '等价无穷小'. "
                    "Use standard Chinese math education terminology.",
    )
    chapter: str = Field(
        ...,
        min_length=1,
        description="Chapter name, e.g. '极限', '一元函数微分学'.",
    )
    role: KPRole = Field(
        ...,
        description="'primary' if this is the main topic of the question, "
                    "'secondary' if it's a related/supporting topic.",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance weight between 0 and 1. "
                    "Primary typically 0.7-1.0, secondary 0.1-0.5.",
    )

    # ---- Extensible: add more fields below as needed ----
    # difficulty_hint: Optional[str] = Field(None, description="...")
    # textbook_section: Optional[str] = Field(None, description="...")


# ============================================================
# Question
# ============================================================

class Question(BaseModel):
    """A single extracted question with its knowledge points.

    Contains ONLY the business data needed for import.
    Database IDs, mastery_level, etc. are assigned by the import layer.
    """
    content: str = Field(
        ...,
        min_length=1,
        description="The question text in LaTeX format. "
                    "Preserve the original OCR output exactly — do not modify or correct.",
    )
    question_type: QuestionType = Field(
        default=QuestionType.unknown,
        description="Question type classification.",
    )
    subject_name: str = Field(
        ...,
        min_length=1,
        description="Subject name, e.g. '高等数学', '线性代数', '概率论'.",
    )
    knowledge_points: list[KnowledgePoint] = Field(
        ...,
        min_length=1,
        description="List of knowledge points (1-3 per question). "
                    "At least one primary knowledge point is required.",
    )
    source_page: Optional[int] = Field(
        None,
        ge=1,
        description="Page number in the source PDF where this question appears.",
    )

    # ---- Extensible: add more fields below as needed ----
    # number: Optional[str] = Field(None, description="Question number if detected, e.g. '5', '8'")
    # difficulty: Optional[str] = Field(None, description="Difficulty level: easy/medium/hard")
    # answer: Optional[str] = Field(None, description="Answer text if available")
    # explanation: Optional[str] = Field(None, description="Solution explanation")
    # options: Optional[list[str]] = Field(None, description="Options for choice questions (A/B/C/D)")
    # year: Optional[int] = Field(None, description="Exam year if known")
    # image_references: Optional[list[str]] = Field(None, description="Paths to related images")
    # formula_list: Optional[list[str]] = Field(None, description="Key formulas in LaTeX")

    @field_validator("knowledge_points")
    @classmethod
    def must_have_primary_kp(cls, v: list[KnowledgePoint]) -> list[KnowledgePoint]:
        if not any(kp.role == KPRole.primary for kp in v):
            raise ValueError("At least one knowledge_point with role='primary' is required")
        return v


# ============================================================
# Question Collection (top-level response)
# ============================================================

class QuestionCollection(BaseModel):
    """Top-level LLM response: a collection of extracted questions.

    This is the root model that the LLM must return.
    """
    questions: list[Question] = Field(
        ...,
        min_length=1,
        description="List of extracted questions.",
    )

    # ---- Extensible: add metadata fields below as needed ----
    # source_info: Optional[dict] = Field(None, description="PDF metadata")
    # extraction_notes: Optional[str] = Field(None, description="LLM notes about the extraction")
