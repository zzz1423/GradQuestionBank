"""Page-by-page PDF pipeline with automatic question import.

Each source page is processed as its own unit: questions on that page are
enriched (with visual recovery when the stem is incomplete), question numbers
are attached, and the page's questions are written to the database before the
pipeline moves on to the next page.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipeline.enricher import enrich_single
from pipeline.import_to_db import import_entries
from pipeline.llm.extractor import _get_existing_hierarchy
from pipeline.llm.llm_client import LLMClient, LLMConfig
from pipeline.merger import build_question_entry
from pipeline.pipeline import Pipeline


def _first_source_page(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pages = data.get("source_pages") or []
        if pages and str(pages[0]).strip().isdigit():
            return int(pages[0])
    except (json.JSONDecodeError, OSError):
        return None
    return None


def run_page_pipeline(
    pdf_path: str | Path,
    output_base: str | Path,
    llm_config: LLMConfig,
    db_path: str | Path,
    mineru_cmd: str | list[str] = "mineru",
    subjects: list[str] | None = None,
    progress_callback: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Run MinerU/split once, then process and import one PDF page at a time."""
    pdf_path = Path(pdf_path)
    output_base = Path(output_base)
    report = progress_callback or (lambda **_: None)

    pipe = Pipeline(
        pdf_path=pdf_path,
        output_base=output_base,
        mineru_cmd=mineru_cmd,
        llm_config=llm_config,
        db_path=db_path,
        subjects=subjects,
        progress_callback=report,
    )
    for step in ("mineru", "normalize", "detect", "llm_split", "split"):
        getattr(pipe, f"_step_{step}")()

    question_files = sorted(pipe.questions_dir.glob("question_*.json"))
    question_files = [
        f for f in question_files
        if ".enriched." not in f.name
        and ".repaired." not in f.name
        and ".error." not in f.name
    ]
    pages = sorted(
        {page for f in question_files if (page := _first_source_page(f)) is not None}
    )
    total_pages = len(pages) or 1

    existing_kps = _get_existing_hierarchy(db_path, subjects=subjects)
    client = LLMClient(llm_config)
    all_entries: list[dict[str, Any]] = []
    imported_total = 0
    skipped_total: list[dict[str, Any]] = []

    for page_index, page in enumerate(pages, 1):
        page_files = [f for f in question_files if _first_source_page(f) == page]
        page_entries: list[dict[str, Any]] = []
        for qpath in page_files:
            enriched_path = enrich_single(
                qpath,
                client,
                existing_kps,
                force=False,
                pdf_path=pdf_path,
            )
            enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
            entry = build_question_entry(enriched, source_pdf=pdf_path.name)
            if entry is not None:
                page_entries.append(entry)
                all_entries.append(entry)

        report(
            step="page_enrich",
            progress=int(30 + 60 * page_index / total_pages),
            current_question=page,
            total_questions=total_pages,
        )

        if page_entries:
            result = import_entries(db_path, page_entries)
            imported_total += result["imported"]
            skipped_total.extend(result["skipped"])

        report(
            step="page_import",
            progress=int(30 + 65 * page_index / total_pages),
            current_question=page,
            total_questions=total_pages,
        )

    import_path = output_base / "import_ready.json"
    import_path.write_text(
        json.dumps(
            {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "pipeline",
                "questions": all_entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "pdf": str(pdf_path),
        "output": str(output_base),
        "questions": len(all_entries),
        "imported": imported_total,
        "skipped_count": len(skipped_total),
        "skipped": skipped_total,
        "import_json": str(import_path),
    }
