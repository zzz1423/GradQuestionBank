# GradQuestionBank Agent Notes

This file is the single source of truth for agents working on this project.

## Current State (2026-09-08 v2.9)

The PDF → Question Bank pipeline has checkpoint/resume, background task tracking, OCR repair, LaTeX auto-fix, and JSON structured output. PDF import is unified around the selected LLM route (local LM Studio or online API), processes page by page, and auto-imports completed questions with source page and question number. Missing stems trigger visual recovery using the original PDF page image through the currently selected route.

Knowledge points support tree structure (parent-child, merge, move) and LLM deduplication (/dedup). Question management, five-level practice records, weighted weakness statistics, filtered export, batch source/delete, question-number search/sort, and KaTeX rendering in question details are implemented.

**Do NOT:**
- Re-introduce `magic-pdf 1.x`, `PDF-Extract-Kit-1.0`, `Detectron2`, `PP-OCRv3`
- Modify Python / CUDA / PyTorch versions without explicit justification
- Put all questions in a single LLM call (does not scale)

**Do:**
- Use `pipeline/pipeline.py` as the main entry point
- Page-by-page auto-import is handled by `pipeline/page_pipeline.py`
- Use `-b pipeline` for MinerU CLI
- Process questions individually (per-question LLM calls)
- Preserve intermediate files for debugging

## Environment

- Project: `E:\Temp\CCC\Codex\GradQuestionBank`
- Python: `.venv` (Python 3.12.10)
- MinerU: 3.4.2 (`mineru[all]`)
- PyTorch: 2.10.0+cu128 (CUDA available)
- LLM: DeepSeek `deepseek-v4-flash` via chat completions for PDF extraction; LM Studio remains available for local fallback
- Use chat mode for structured extraction. Reasoner mode is reserved for future analysis tasks, not the import pipeline.
- PDF import uses the selected route from Settings: local LM Studio (`qwen/qwen3.5-9b`) or an online API. There is no separate full-document vision mode in the UI; visual input is used only for missing-stem recovery on the affected page.

## Pipeline Architecture

```text
PDF
 ↓ MinerU CLI (-b pipeline)
Raw (content_list_v2.json) (content_list_v2.json, model.json)
 ↓ pipeline/converters/mineru_v2.py
NormalizedDocument (pipeline/schema.py)
 ↓ pipeline/detectors/rule_engine.py
AnnotatedDocument (noise + candidates + boundaries)
 ↓ pipeline/splitter_llm.py (LLM fine-split + noise filter + LaTeX fix)
llm_split_result.json (clean question list)
 ↓ pipeline/splitter.py
questions/question_0001.json ... question_NNNN.json
 ↓ pipeline/ocr_repair.py (OCR error repair using LLM)
questions/question_0001.repaired.json ...
 ↓ pipeline/enricher.py (uses repaired_text, per-question LLM, checkpoint)
questions/question_0001.enriched.json ...
 ↓ pipeline/merger.py
import_ready.json → /api/import

Page-by-page mode (`pipeline/page_pipeline.py`) runs MinerU/split once, then enriches and imports each page before moving to the next.
```

### LLM Splitter (splitter_llm.py)
Sits between rule engine and splitter. Uses LLM to:
- Split multi-question blocks into individual questions
- Filter noise that rule engine missed (answer areas, difficulty markers, notes)
- Identify questions the rule engine overlooked
- Falls back to rule engine output if LLM fails

### Key Files

| File | Purpose |
|------|---------|
| `pipeline/pipeline.py` | Pipeline orchestrator (run / run_from / checkpoint) |
| `pipeline/splitter_llm.py` | LLM-based question splitter + noise filter + LaTeX fix |
| `pipeline/splitter.py` | Split AnnotatedDocument into per-question files |
| `pipeline/ocr_repair.py` | OCR error repair using LLM (post-split, pre-enrich) |
| `pipeline/latex_fix.py` | Bare LaTeX command detection + $ delimiters |
| `pipeline/llm/split_models.py` | Pydantic models for LLM splitter output |
| `pipeline/llm/schemas/` | JSON schemas for structured output (json_schema mode) |
| `pipeline/task_manager.py` | Background task tracking with JSON persistence |
| `pipeline/enricher.py` | Per-question LLM enrichment with checkpoint/resume |
| `pipeline/merger.py` | Merge enriched files into import-ready JSON |
| `pipeline/page_pipeline.py` | Page-by-page pipeline with automatic DB import |
| `pipeline/import_to_db.py` | Direct SQLite import for pipeline entries |
| `pipeline/canonical/kp_canonical.py` | KP name normalizer (499 aliases) |
| `pipeline/canonical/kp_aliases.json` | Alias mapping: 别名 -> 标准名 |
| `data/exam_syllabus/math{1,2,3}.json` | Full exam outlines (379 KPs) |
| `data/exam_syllabus/computer408.json` | 408 大纲 (4 subjects, 339 KPs) |
| `pipeline/schema.py` | DOM dataclasses (NormalizedDocument, AnnotatedDocument, etc.) |
| `pipeline/converters/mineru_v2.py` | MinerU v2 → NormalizedDocument |
| `pipeline/detectors/rule_engine.py` | Question detection + boundary detection |
| `pipeline/llm/models.py` | Pydantic models (QuestionCollection, Question, KnowledgePoint) |
| `pipeline/llm/prompt.py` | Prompt builder (strict JSON-only instructions) |
| `pipeline/llm/llm_client.py` | Generic OpenAI-compatible LLM client |
| `pipeline/llm/validator.py` | JSON extraction + Pydantic validation + auto-retry |
| `pipeline/llm/extractor.py` | Legacy single-call entry point (use pipeline.py instead) |
| `pipeline/canonical/kp_canonical.py` | KP name normalizer (499 aliases) |
| `pipeline/canonical/kp_aliases.json` | Alias mapping: 别名 -> 标准名 |
| `data/exam_syllabus/math{1,2,3}.json` | 数一/数二/数三 完整大纲 |
| `data/exam_syllabus/computer408.json` | 408 大纲 (4 subjects, 339 KPs) |
| `pipeline/task_manager.py` | Background task tracking with JSON persistence |
| `data/tasks/*.json` | Persisted task files |
| `pipeline/renderers/markdown.py` | NormalizedDocument → Markdown (for verification) |
| `docs/schema/document_object_model.md` | Full DOM schema spec |
| `pipeline/canonical/kp_dedup.py` | LLM-based KP deduplication |
| `pipeline/vision_pdf.py` | Legacy full-page vision extractor (not exposed in UI) |
| `frontend/src/pages/Exams.tsx` | Exam management page |
| `frontend/src/pages/DedupReview.tsx` | KP dedup review page |
| `frontend/src/components/LatexContent.tsx` | KaTeX content renderer |

### Pipeline Usage

```python
from pipeline.pipeline import Pipeline
from pipeline.llm import LLMConfig

pipe = Pipeline(
    pdf_path="1-3.pdf",
    output_base="data/pipeline-output/1-3",
    llm_config=LLMConfig(model="deepseek-v4-flash"),
)
result = pipe.run()           # Full pipeline
result = pipe.run_from("enrich")  # Resume from enrichment step
```

### Output Structure

```text
data/pipeline-output/<doc>/
├── raw/                     # MinerU output
├── normalized.json          # Layer 2
├── annotations.json         # Layer 3
├── questions/               # Per-question files
│   ├── question_0001.json
│   ├── question_0001.enriched.json
│   └── ...
├── import_ready.json        # Final merged output
└── pipeline_state.json      # Checkpoint state
```

## LLM Notes

- LM Studio 0.4.19 with "Enable Thinking = Off" disables reasoning via GUI
- No need for `/no_think` tag or `chat_template_kwargs`
- `max_tokens=4000` is sufficient when thinking is off
- Response time: ~2-3s per question (single call)
- Total for 8 questions: ~20s

## Known Issues

- Turbomind/Blackwell acceleration broken (`no kernel image`), use `-b pipeline`
- Old `.venv` backups in project root (can be removed once stable)
- Node.js is not on PATH by default; use `C:\Users\Hear\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin` before `pnpm build`.
- DeepSeek API must be reachable before running the full PDF pipeline.
- Local vision extraction requires Thinking disabled in LM Studio. With Thinking enabled, Qwen can spend its output budget in `reasoning_content` before returning JSON.

## Knowledge Point Deduplication (Done)

LLM-based duplicate detection for existing KPs in the database:
- pipeline/canonical/kp_dedup.py — dedup module (sends KP batches to LLM)
- /api/kps/dedup — API endpoint (POST, runs analysis)
- /api/kps/dedup/apply — API endpoint (POST, adds aliases)
- /dedup — frontend review page (accept/reject suggestions)
- Always uses local LM Studio (not cloud APIs)

## Knowledge Point Canonicalization (Done)

LLM output produces inconsistent KP names. Solution:
- `pipeline/canonical/kp_canonical.py` — normalizer (499 aliases loaded)
- `pipeline/canonical/kp_aliases.json` — alias mapping (别名 -> 标准名)
- Integrated into `merger.py` (merge-time) and `app.py` import endpoint (import-time)
- `data/exam_syllabus/math{1,2,3}.json` — full exam outlines (379 KPs across 5 subjects)
- `database.seed_from_syllabus()` — loads syllabus JSON into DB (idempotent)
