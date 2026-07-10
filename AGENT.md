# GradQuestionBank Agent Notes

This file is the single source of truth for agents working on this project.

## Current State (2026-07-10)

The PDF → Question Bank pipeline is **fully functional** with checkpoint/resume, background task tracking, OCR repair, LaTeX auto-fix, and JSON structured output.

Knowledge points now support **tree structure** (parent-child relationships, merge, move).

**Do NOT:**
- Re-introduce `magic-pdf 1.x`, `PDF-Extract-Kit-1.0`, `Detectron2`, `PP-OCRv3`
- Modify Python / CUDA / PyTorch versions without explicit justification
- Put all questions in a single LLM call (does not scale)

**Do:**
- Use `pipeline/pipeline.py` as the main entry point
- Use `-b pipeline` for MinerU CLI
- Process questions individually (per-question LLM calls)
- Preserve intermediate files for debugging

## Environment

- Project: `F:\Temp\CCC\Codex\GradQuestionBank`
- Python: `.venv` (Python 3.12.10)
- MinerU: 3.4.2 (`mineru[all]`)
- PyTorch: 2.10.0+cu128 (CUDA available)
- LLM: qwen/qwen3.5-9b via LM Studio 0.4.19 (http://127.0.0.1:1234/v1)
- LM Studio GUI: "Enable Thinking = Off" (no `/no_think` tag needed)

## Pipeline Architecture

```
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

### Pipeline Usage

```python
from pipeline.pipeline import Pipeline
from pipeline.llm import LLMConfig

pipe = Pipeline(
    pdf_path="1-3.pdf",
    output_base="data/pipeline-output/1-3",
    llm_config=LLMConfig(model="qwen/qwen3.5-9b"),
)
result = pipe.run()           # Full pipeline
result = pipe.run_from("enrich")  # Resume from enrichment step
```

### Output Structure

```
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

## Knowledge Point Canonicalization (Done)

LLM output produces inconsistent KP names. Solution:
- `pipeline/canonical/kp_canonical.py` — normalizer (499 aliases loaded)
- `pipeline/canonical/kp_aliases.json` — alias mapping (别名 -> 标准名)
- Integrated into `merger.py` (merge-time) and `app.py` import endpoint (import-time)
- `data/exam_syllabus/math{1,2,3}.json` — full exam outlines (379 KPs across 5 subjects)
- `database.seed_from_syllabus()` — loads syllabus JSON into DB (idempotent)
