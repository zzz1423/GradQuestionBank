"""Local vision PDF import pipeline for LM Studio-compatible models."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Callable

import pypdfium2 as pdfium
from json_repair import loads as repair_json_loads

from pipeline.enricher import enrich_all
from pipeline.llm.extractor import _get_existing_hierarchy
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.merger import merge_enriched


VISION_SYSTEM_PROMPT = """You extract graduate math exam questions from page images.
Return JSON only, with no Markdown and no explanation.
Preserve formulas in LaTex and extract every visible question, including questions
whose number is missing or unclear in the OCR. Exclude headings, difficulty labels,
score labels, note areas, and answer areas.

Output exactly this structure:
{"questions":[{"question_number":"string or null","content":"full question text"}]}"""


def _parse_questions(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Vision model did not return a JSON object")
    candidate = text[start:end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        data = repair_json_loads(candidate)
    questions = data.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("Vision response questions must be an array")
    return [q for q in questions if isinstance(q, dict) and str(q.get("content", "")).strip()]


def _page_data_url(page: Any, scale: float = 1.5) -> str:
    image = page.render(scale=scale).to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def run_vision_pdf_pipeline(
    pdf_path: str | Path,
    output_base: str | Path,
    llm_config: LLMConfig,
    db_path: str,
    subjects: list[str] | None = None,
    progress_callback: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Extract questions from rendered PDF pages through a local vision model."""
    pdf_path = Path(pdf_path)
    output_base = Path(output_base)
    questions_dir = output_base / "questions"
    output_base.mkdir(parents=True, exist_ok=True)
    questions_dir.mkdir(parents=True, exist_ok=True)
    report = progress_callback or (lambda **_: None)
    client = LLMClient(llm_config)
    document = pdfium.PdfDocument(pdf_path)
    total_pages = len(document)
    extracted: list[dict[str, Any]] = []

    for page_index in range(total_pages):
        page_number = page_index + 1
        image_url = _page_data_url(document[page_index])
        response = client.chat(
            system=VISION_SYSTEM_PROMPT,
            user=[
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": f"Extract all questions on page {page_number}."},
            ],
            temperature=0.1,
            max_tokens=llm_config.max_tokens,
        )
        for question in _parse_questions(response.content):
            extracted.append({
                "question_index": len(extracted),
                "source_pdf": str(pdf_path),
                "source_pages": [page_number],
                "detection": {
                    "method": "local_vision",
                    "score": 1.0,
                    "detected_number": question.get("question_number"),
                },
                "stem_block_ids": [],
                "stem_text": str(question["content"]).strip(),
                "block_metadata": {},
            })
        report(
            step="vision_extract",
            progress=int(45 * page_number / total_pages),
            current_question=page_number,
            total_questions=total_pages,
        )

    for index, question in enumerate(extracted, start=1):
        (questions_dir / f"question_{index:04d}.json").write_text(
            json.dumps(question, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    existing_kps = _get_existing_hierarchy(db_path, subjects=subjects)
    enriched = enrich_all(
        questions_dir,
        config=llm_config,
        existing_kps=existing_kps,
        progress_callback=report,
    )
    import_path = output_base / "import_ready.json"
    merge_enriched(questions_dir, import_path, source_pdf=pdf_path.name)
    return {
        "pdf": str(pdf_path),
        "output": str(output_base),
        "questions": len(extracted),
        "enriched": len(enriched),
        "import_json": str(import_path),
    }
