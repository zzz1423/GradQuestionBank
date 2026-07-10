"""
Math Question Bank - Document Object Model (Schema v1.0.0)

Immutable data structures for the entire PDF -> Question pipeline.
Every layer produces new data; no layer modifies previous data.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ============================================================
# Constants
# ============================================================

SCHEMA_VERSION = "1.0.0"
PIPELINE_VERSION = "0.1.0"


# ============================================================
# Enums
# ============================================================

class BlockType(str, Enum):
    title = "title"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    figure = "figure"
    caption = "caption"
    formula_block = "formula_block"
    equation_interline = "equation_interline"
    page_header = "page_header"
    page_footer = "page_footer"
    page_number = "page_number"
    aside = "aside"
    code_block = "code_block"
    unknown = "unknown"


class InlineType(str, Enum):
    text = "text"
    formula = "formula"
    image = "image"
    unknown = "unknown"


class QuestionType(str, Enum):
    choice = "choice"
    fill_blank = "fill_blank"
    true_false = "true_false"
    short_answer = "short_answer"
    calculation = "calculation"
    proof = "proof"
    comprehensive = "comprehensive"
    unknown = "unknown"


# ============================================================
# Provenance
# ============================================================

@dataclass
class Provenance:
    """Traceability info attached to every produced object."""
    source_tool: str
    source_version: str
    source_raw_id: str | None
    source_page: int | None
    component: str
    component_version: str
    model: str | None = None
    prompt_version: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, d: dict | Provenance) -> Provenance:
        if isinstance(d, cls):
            return d
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in fields},
                   **{k: None for k in fields - d.keys()
                      if k in ('source_raw_id', 'source_page', 'model', 'prompt_version')})


# ============================================================
# Core Types
# ============================================================

@dataclass
class BBox:
    """Bounding box: [x1, y1, x2, y2] in points."""
    x1: float
    y1: float
    x2: float
    y2: float

    def to_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    @classmethod
    def from_list(cls, lst: list[float]) -> BBox:
        return cls(x1=lst[0], y1=lst[1], x2=lst[2], y2=lst[3])

    @classmethod
    def from_dict(cls, v) -> BBox:
        if isinstance(v, cls):
            return v
        if isinstance(v, list) and len(v) >= 4:
            return cls.from_list(v)
        if isinstance(v, dict):
            return cls(x1=v.get("x1", 0), y1=v.get("y1", 0),
                       x2=v.get("x2", 0), y2=v.get("y2", 0))
        return cls(0, 0, 0, 0)


@dataclass
class Inline:
    """Inline element within a paragraph or title."""
    type: InlineType
    content: str
    confidence: float | None = None

    @classmethod
    def from_dict(cls, d: dict | Inline) -> Inline:
        if isinstance(d, cls):
            return d
        return cls(
            type=InlineType(d.get("type", "unknown")),
            content=d.get("content", ""),
            confidence=d.get("confidence"),
        )


@dataclass
class ImageAsset:
    """Global image asset referenced by Blocks."""
    image_id: str
    path: str
    mime_type: str
    source: Provenance
    width: int | None = None
    height: int | None = None
    ocr_text: str | None = None

    @classmethod
    def from_dict(cls, d: dict | ImageAsset) -> ImageAsset:
        if isinstance(d, cls):
            return d
        return cls(
            image_id=d.get("image_id", ""),
            path=d.get("path", ""),
            mime_type=d.get("mime_type", "image/png"),
            source=Provenance.from_dict(d.get("source", {})),
            width=d.get("width"),
            height=d.get("height"),
            ocr_text=d.get("ocr_text"),
        )


# ============================================================
# Block
# ============================================================

@dataclass
class Block:
    """A content block on a page. Immutable after creation."""
    id: str
    page: int
    type: BlockType
    bbox: BBox
    reading_order: int
    source: Provenance
    confidence: float | None = None
    polygon: list[list[float]] | None = None

    # Title fields
    title_content: list[Inline] | None = None
    level: int | None = None

    # Paragraph / list_item fields
    inline_content: list[Inline] | None = None

    # Formula fields
    latex: str | None = None
    math_type: str | None = None
    image_ref: str | None = None

    # Figure / table fields
    caption: list[Inline] | None = None

    # Page header / footer / page_number fields
    text: str | None = None

    @classmethod
    def from_dict(cls, d: dict | Block) -> Block:
        if isinstance(d, cls):
            return d
        kwargs: dict[str, Any] = {}
        kwargs["id"] = d.get("id", "")
        kwargs["page"] = d.get("page", 0)
        kwargs["type"] = BlockType(d.get("type", "unknown"))
        kwargs["bbox"] = BBox.from_dict(d.get("bbox", [0, 0, 0, 0]))
        kwargs["reading_order"] = d.get("reading_order", 0)
        kwargs["source"] = Provenance.from_dict(d.get("source", {}))
        if "confidence" in d and d["confidence"] is not None:
            kwargs["confidence"] = d["confidence"]
        if "polygon" in d and d["polygon"] is not None:
            kwargs["polygon"] = d["polygon"]
        if "title_content" in d and d["title_content"] is not None:
            kwargs["title_content"] = [Inline.from_dict(i) for i in d["title_content"]]
        if "level" in d and d["level"] is not None:
            kwargs["level"] = d["level"]
        if "inline_content" in d and d["inline_content"] is not None:
            kwargs["inline_content"] = [Inline.from_dict(i) for i in d["inline_content"]]
        for scalar in ("latex", "math_type", "image_ref", "text"):
            if scalar in d and d[scalar] is not None:
                kwargs[scalar] = d[scalar]
        if "caption" in d and d["caption"] is not None:
            kwargs["caption"] = [Inline.from_dict(i) for i in d["caption"]]
        return cls(**kwargs)


# ============================================================
# Page
# ============================================================

@dataclass
class Page:
    """A single page in the document."""
    page_number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict | Page) -> Page:
        if isinstance(d, cls):
            return d
        return cls(
            page_number=d.get("page_number", 0),
            width=d.get("width", 595.0),
            height=d.get("height", 841.0),
            blocks=[Block.from_dict(b) for b in d.get("blocks", [])],
        )


# ============================================================
# NormalizedDocument
# ============================================================

@dataclass
class NormalizedDocument:
    """
    The unified DOM. Immutable after creation.
    This is the output of the Normalization layer.
    """
    document_id: str
    source_path: str
    tool: str
    tool_version: str
    tool_raw_dir: str
    pages: list[Page] = field(default_factory=list)
    images: list[ImageAsset] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    pipeline_version: str = PIPELINE_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self, cls=_DataclassEncoder, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> NormalizedDocument:
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict | NormalizedDocument) -> NormalizedDocument:
        if isinstance(d, cls):
            return d
        return cls(
            document_id=d.get("document_id", ""),
            source_path=d.get("source_path", ""),
            tool=d.get("tool", ""),
            tool_version=d.get("tool_version", ""),
            tool_raw_dir=d.get("tool_raw_dir", ""),
            pages=[Page.from_dict(p) for p in d.get("pages", [])],
            images=[ImageAsset.from_dict(i) for i in d.get("images", [])],
            metadata=d.get("metadata", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            pipeline_version=d.get("pipeline_version", PIPELINE_VERSION),
            created_at=d.get("created_at", ""),
        )


# ============================================================
# Annotation
# ============================================================

@dataclass
class Annotation:
    """A single annotation added by Question Detection or LLM."""
    annotation_id: str
    type: str
    block_ids: list[str]
    provenance: Provenance
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict | Annotation) -> Annotation:
        if isinstance(d, cls):
            return d
        return cls(
            annotation_id=d.get("annotation_id", ""),
            type=d.get("type", ""),
            block_ids=d.get("block_ids", []),
            provenance=Provenance.from_dict(d.get("provenance", {})),
            score=d.get("score"),
            metadata=d.get("metadata", {}),
        )


# ============================================================
# AnnotatedDocument
# ============================================================

@dataclass
class AnnotatedDocument:
    """Annotations layer. Does not modify Blocks."""
    document_id: str
    normalized_version: str
    annotations: list[Annotation] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    pipeline_version: str = PIPELINE_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self, cls=_DataclassEncoder, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> AnnotatedDocument:
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict | AnnotatedDocument) -> AnnotatedDocument:
        if isinstance(d, cls):
            return d
        return cls(
            document_id=d.get("document_id", ""),
            normalized_version=d.get("normalized_version", ""),
            annotations=[Annotation.from_dict(a) for a in d.get("annotations", [])],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            pipeline_version=d.get("pipeline_version", PIPELINE_VERSION),
            created_at=d.get("created_at", ""),
        )


# ============================================================
# Question / SubQuestion
# ============================================================

@dataclass
class SubQuestion:
    """A sub-question within a multi-part question."""
    sub_id: str
    label: str
    block_ids: list[str]

    @classmethod
    def from_dict(cls, d: dict | SubQuestion) -> SubQuestion:
        if isinstance(d, cls):
            return d
        return cls(
            sub_id=d.get("sub_id", ""),
            label=d.get("label", ""),
            block_ids=d.get("block_ids", []),
        )


@dataclass
class Question:
    """A single question. References blocks, never copies text."""
    question_id: str
    type: QuestionType
    stem_block_ids: list[str]
    provenance: Provenance
    number: str | None = None
    answer_block_ids: list[str] = field(default_factory=list)
    sub_questions: list[SubQuestion] | None = None
    source_annotation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict | Question) -> Question:
        if isinstance(d, cls):
            return d
        sq = d.get("sub_questions")
        return cls(
            question_id=d.get("question_id", ""),
            type=QuestionType(d.get("type", "unknown")),
            stem_block_ids=d.get("stem_block_ids", []),
            provenance=Provenance.from_dict(d.get("provenance", {})),
            number=d.get("number"),
            answer_block_ids=d.get("answer_block_ids", []),
            sub_questions=[SubQuestion.from_dict(s) for s in sq] if sq else None,
            source_annotation_id=d.get("source_annotation_id"),
            metadata=d.get("metadata", {}),
        )


# ============================================================
# QuestionSet
# ============================================================

@dataclass
class QuestionSet:
    """Final structured questions. Output of the LLM layer."""
    set_id: str
    document_id: str
    source_pdf: str
    questions: list[Question] = field(default_factory=list)
    provenance: Provenance | None = None
    schema_version: str = SCHEMA_VERSION
    pipeline_version: str = PIPELINE_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self, cls=_DataclassEncoder, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> QuestionSet:
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict | QuestionSet) -> QuestionSet:
        if isinstance(d, cls):
            return d
        prov = d.get("provenance")
        return cls(
            set_id=d.get("set_id", ""),
            document_id=d.get("document_id", ""),
            source_pdf=d.get("source_pdf", ""),
            questions=[Question.from_dict(q) for q in d.get("questions", [])],
            provenance=Provenance.from_dict(prov) if prov else None,
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            pipeline_version=d.get("pipeline_version", PIPELINE_VERSION),
            created_at=d.get("created_at", ""),
        )


# ============================================================
# ID Generation
# ============================================================

def make_document_id(source_path: str) -> str:
    """Generate a deterministic document_id from source file path and size."""
    p = Path(source_path)
    content = f"{p.name}:{p.stat().st_size}"
    h = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"{p.stem}_{h}"


def make_block_id(document_id: str, seq: int) -> str:
    return f"{document_id}_b{seq:05d}"


def make_image_id(document_id: str, seq: int) -> str:
    return f"{document_id}_img{seq:04d}"


def make_annotation_id(document_id: str, seq: int) -> str:
    return f"{document_id}_ann{seq:05d}"


def make_question_id(document_id: str, seq: int) -> str:
    return f"{document_id}_q{seq:04d}"


def make_set_id(document_id: str, seq: int) -> str:
    return f"{document_id}_qs{seq:03d}"


# ============================================================
# JSON Serialization
# ============================================================

class _DataclassEncoder(json.JSONEncoder):
    """Serialize dataclasses, enums, and BBox to JSON."""
    def default(self, o: Any) -> Any:
        # BBox must come before generic dataclass check (BBox is also a dataclass)
        if isinstance(o, BBox):
            return o.to_list()
        if isinstance(o, Enum):
            return o.value
        if hasattr(o, "__dataclass_fields__"):
            d = {}
            for fname in o.__dataclass_fields__:
                val = getattr(o, fname)
                if val is not None:
                    d[fname] = val
            return d
        return super().default(o)
