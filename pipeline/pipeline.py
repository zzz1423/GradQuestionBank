"""
Pipeline Orchestrator — manages the full PDF → JSON flow.

Each step produces intermediate files that are preserved for:
- Checkpoint/resume (skip completed steps)
- Debugging (inspect intermediate results)
- Cache-friendly re-runs (only re-process affected steps)

Usage:
    from pipeline.pipeline import Pipeline

    pipe = Pipeline("1-3.pdf", output_base="data/pipeline-output/1-3")
    result = pipe.run()  # runs all steps
    # or
    result = pipe.run_from("split")  # resume from a specific step
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.schema import NormalizedDocument, AnnotatedDocument
from pipeline.converters.mineru_v2 import convert as mineru_convert
from pipeline.detectors.rule_engine import detect, detect_boundaries
from pipeline.splitter import split_questions
from pipeline.splitter_llm import split_with_llm
from pipeline.ocr_repair import repair_all_questions
from pipeline.enricher import enrich_all
from pipeline.merger import merge_enriched
from pipeline.llm.llm_client import LLMConfig
from pipeline.llm.extractor import _get_existing_hierarchy

logger = logging.getLogger(__name__)

STEPS = ["mineru", "normalize", "detect", "llm_split", "split", "ocr_repair", "enrich", "merge"]


@dataclass
class PipelineState:
    """Tracks pipeline execution state for checkpoint/resume."""
    current_step: str = ""
    completed_steps: list[str] = field(default_factory=list)
    question_count: int = 0
    enriched_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "question_count": self.question_count,
            "enriched_count": self.enriched_count,
            "error_count": self.error_count,
        }

    @classmethod
    def load(cls, path: Path) -> PipelineState:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                current_step=data.get("current_step", ""),
                completed_steps=data.get("completed_steps", []),
                question_count=data.get("question_count", 0),
                enriched_count=data.get("enriched_count", 0),
                error_count=data.get("error_count", 0),
            )
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2),
            encoding="utf-8",
        )


class Pipeline:
    """Full PDF → JSON pipeline with checkpoint/resume.

    Directory structure:
        output_base/
            raw/                  # MinerU output
            normalized.json       # Layer 2
            annotations.json      # Layer 3
            questions/            # Split question files
                question_0001.json
                question_0001.enriched.json
                ...
            import_ready.json     # Final merged output
            pipeline_state.json   # Checkpoint state
    """

    def __init__(
        self,
        pdf_path: str | Path,
        output_base: str | Path,
        mineru_cmd: str = "mineru",
        llm_config: LLMConfig | None = None,
        db_path: str = "data/grad.db",
        subjects: list[str] | None = None,
        progress_callback: Any | None = None,
    ):
        self.pdf_path = Path(pdf_path)
        self.output_base = Path(output_base)
        self.mineru_cmd = mineru_cmd
        self.llm_config = llm_config
        self.db_path = db_path
        self.subjects = subjects
        self.progress_callback = progress_callback or (lambda **kw: None)

        # Derived paths
        self.raw_dir = self.output_base / "raw"
        self.normalized_path = self.output_base / "normalized.json"
        self.annotations_path = self.output_base / "annotations.json"
        self.questions_dir = self.output_base / "questions"
        self.import_path = self.output_base / "import_ready.json"
        self.state_path = self.output_base / "pipeline_state.json"

        self.state = PipelineState.load(self.state_path)

    def _report(self, **kwargs: Any) -> None:
        """Report progress to callback."""
        try:
            self.progress_callback(**kwargs)
        except Exception:
            logger.debug("Progress callback error", exc_info=True)

    def run(self) -> dict[str, Any]:
        """Run the full pipeline from start to finish (with checkpoint/resume)."""
        return self.run_from("mineru")

    def run_from(self, start_step: str) -> dict[str, Any]:
        """Run pipeline from a specific step onwards.

        Args:
            start_step: Step to start from (mineru/normalize/detect/split/enrich/merge)

        Returns:
            Summary dict with results
        """
        if start_step not in STEPS:
            raise ValueError(f"Invalid start_step '{start_step}'. Valid steps: {STEPS}")
        start_idx = STEPS.index(start_step)
        steps_to_run = STEPS[start_idx:]

        logger.info(f"Pipeline starting from step '{start_step}' for {self.pdf_path.name}")

        for step in steps_to_run:
            if step in self.state.completed_steps:
                logger.info(f"Skipping '{step}' (already completed)")
                # Still report progress so the user sees what's happening
                step_idx = STEPS.index(step)
                progress = int(100 * step_idx / len(STEPS))
                self._report(step=step, progress=max(progress, 1))
                continue

            self.state.current_step = step
            self.state.save(self.state_path)

            logger.info(f"Running step: {step}")

            try:
                handler = getattr(self, f"_step_{step}")
                handler()
                self.state.completed_steps.append(step)
                self.state.save(self.state_path)
                logger.info(f"Step '{step}' completed")

            except Exception as e:
                logger.error(f"Step '{step}' failed: {e}")
                self.state.save(self.state_path)
                raise

        return {
            "pdf": str(self.pdf_path),
            "output": str(self.output_base),
            "questions": self.state.question_count,
            "enriched": self.state.enriched_count,
            "import_json": str(self.import_path),
            "state": self.state.to_dict(),
        }

    # ============================================================
    # Step handlers
    # ============================================================

    def _step_mineru(self) -> None:
        """Step 1: Run MinerU CLI to extract PDF content."""
        mineru_output = self.raw_dir / self.pdf_path.stem

        # Check if already done
        v2_file = mineru_output / "auto" / f"{self.pdf_path.stem}_content_list_v2.json"
        if v2_file.exists():
            # Validate: check if output has usable content
            if self._mineru_output_has_content(v2_file):
                logger.info(f"MinerU output already exists: {v2_file}")
                return
            else:
                logger.warning("MinerU output exists but has no usable content, retrying")
                import shutil
                shutil.rmtree(mineru_output, ignore_errors=True)

        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # First attempt: default settings
        cmd = [
            self.mineru_cmd,
            "-p", str(self.pdf_path),
            "-o", str(self.raw_dir),
            "-b", "pipeline",
        ]

        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"MinerU failed (exit {result.returncode}):\n{result.stderr}"
            )

        logger.info(f"MinerU output: {v2_file}")

        # Retry with --table False if output is mostly empty tables
        if v2_file.exists() and not self._mineru_output_has_content(v2_file):
            logger.warning("MinerU output has no usable text, retrying with -m ocr")
            import shutil
            shutil.rmtree(mineru_output, ignore_errors=True)

            cmd_retry = cmd + ["-m", "ocr"]
            logger.info(f"Running (retry): {' '.join(cmd_retry)}")
            result = subprocess.run(
                cmd_retry,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"MinerU retry failed (exit {result.returncode}):\n{result.stderr}"
                )

            # -m ocr outputs to ocr/ directory; move to auto/ for consistency
            ocr_dir = mineru_output / "ocr"
            auto_dir = mineru_output / "auto"
            if ocr_dir.exists() and not auto_dir.exists():
                ocr_dir.rename(auto_dir)
                logger.info(f"Moved OCR output from ocr/ to auto/")
            elif ocr_dir.exists() and auto_dir.exists():
                # Merge: copy missing files from ocr/ to auto/
                for f in ocr_dir.iterdir():
                    dest = auto_dir / f.name
                    if not dest.exists():
                        import shutil
                        shutil.copy2(f, dest)

            logger.info(f"MinerU retry output: {v2_file}")

    def _mineru_output_has_content(self, v2_file: Path) -> bool:
        """Check if MinerU output has usable text blocks.

        Requires at least 2 paragraph blocks with real text content.
        A single title (like a page header) is not enough.
        """
        try:
            import json
            raw = json.loads(v2_file.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw and isinstance(raw[0], list):
                items = raw[0]
            elif isinstance(raw, list):
                items = raw
            else:
                return False

            paragraph_count = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                bt = item.get("type", "")
                if bt == "paragraph":
                    content = item.get("content", {})
                    if isinstance(content, dict):
                        for key, val in content.items():
                            if key.endswith("_content") and isinstance(val, list):
                                for part in val:
                                    if isinstance(part, dict) and part.get("type") == "text":
                                        if part.get("content", "").strip():
                                            paragraph_count += 1
            return paragraph_count >= 2
        except Exception:
            return False
    def _step_normalize(self) -> None:
        """Step 2: Convert MinerU output to NormalizedDocument."""
        if self.normalized_path.exists():
            logger.info("NormalizedDocument already exists")
            return

        stem = self.pdf_path.stem
        v2_file = self.raw_dir / stem / "auto" / f"{stem}_content_list_v2.json"
        model_file = self.raw_dir / stem / "auto" / f"{stem}_model.json"

        if not v2_file.exists():
            raise FileNotFoundError(f"MinerU output not found: {v2_file}")

        doc = mineru_convert(
            v2_file,
            model_file if model_file.exists() else None,
            output_dir=self.output_base,
            source_pdf_path=str(self.pdf_path),
        )

        logger.info(f"NormalizedDocument: {len(doc.pages)} pages, "
                    f"{sum(len(p.blocks) for p in doc.pages)} blocks")

        self._report(step="normalize", progress=15)
    def _step_detect(self) -> None:
        """Step 3: Run rule engine to detect question boundaries."""
        if self.annotations_path.exists():
            logger.info("AnnotatedDocument already exists")
            return

        doc = NormalizedDocument.load(self.normalized_path)

        # Detect candidates
        ann_doc = detect(doc)

        # Detect boundaries
        ann_doc = detect_boundaries(doc, ann_doc)

        # Save
        ann_doc.save(self.annotations_path)

        candidates = sum(1 for a in ann_doc.annotations if a.type == "question_candidate")
        logger.info(f"Detected {candidates} question candidates")

        self._report(step="detect", progress=25)

    def _step_llm_split(self) -> None:
        """Step 3.5: Use LLM to refine question splitting and filter noise."""
        llm_split_path = self.output_base / "llm_split_result.json"

        if llm_split_path.exists():
            logger.info("LLM split result already exists")
            return

        doc = NormalizedDocument.load(self.normalized_path)
        ann_doc = AnnotatedDocument.load(self.annotations_path)

        config = self.llm_config or LLMConfig()
        questions = split_with_llm(
            doc=doc,
            ann_doc=ann_doc,
            config=config,
            output_dir=self.output_base,
        )

        if not questions:
            raise RuntimeError(
                "LLM splitter returned no questions. "
                "Check if the PDF has readable content."
            )

        logger.info(f"LLM identified {len(questions)} questions")
        self._report(step="llm_split", progress=28)

    def _step_split(self) -> None:
        """Step 4: Split document into individual question files.

        Uses LLM split result if available, otherwise falls back to rule engine.
        """
        import json as _json
        llm_split_path = self.output_base / "llm_split_result.json"

        if llm_split_path.exists():
            # Use LLM-refined questions
            llm_data = _json.loads(llm_split_path.read_text(encoding="utf-8"))
            questions = llm_data.get("questions", [])

            if not questions:
                raise RuntimeError("LLM split result has no questions")

            self.questions_dir.mkdir(parents=True, exist_ok=True)
            created_files = []

            for idx, q in enumerate(questions):
                question_data = {
                    "question_index": idx,
                    "source_pdf": str(self.pdf_path),
                    "source_pages": [q.get("page", 1)],
                    "detection": {
                        "method": "llm_split",
                        "score": 1.0,
                        "detected_number": q.get("question_number"),
                    },
                    "stem_block_ids": [],
                    "stem_text": q["content"],
                    "block_metadata": {},
                }

                filename = f"question_{idx + 1:04d}.json"
                filepath = self.questions_dir / filename
                filepath.write_text(
                    _json.dumps(question_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                created_files.append(filepath)

            self.state.question_count = len(created_files)
            logger.info(f"Split {len(created_files)} questions from LLM result")

        else:
            # Fallback: use rule engine output
            doc = NormalizedDocument.load(self.normalized_path)
            ann_doc = AnnotatedDocument.load(self.annotations_path)

            files = split_questions(doc, ann_doc, self.questions_dir)
            self.state.question_count = len(files)

            logger.info(f"Split into {len(files)} question files (rule engine fallback)")

        self._report(step="split", progress=30)

    def _step_ocr_repair(self) -> None:
        """Step 5: Repair OCR errors in question text using LLM."""
        config = self.llm_config or LLMConfig()

        repaired_files = repair_all_questions(
            self.questions_dir,
            config=config,
            progress_callback=self._report,
        )

        logger.info(f"OCR repair: {len(repaired_files)} questions processed")

    def _step_enrich(self) -> None:
        """Step 6: Enrich each question with LLM (with checkpoint/resume)."""
        existing_kps = _get_existing_hierarchy(self.db_path, subjects=self.subjects)
        config = self.llm_config or LLMConfig()

        enriched_files = enrich_all(
            self.questions_dir,
            config=config,
            existing_kps=existing_kps,
            progress_callback=self._report,
        )

        self.state.enriched_count = len(enriched_files)

        # Count errors
        error_files = list(self.questions_dir.glob("question_*.error.json"))
        self.state.error_count = len(error_files)

        logger.info(f"Enriched: {len(enriched_files)}, Errors: {len(error_files)}")

    def _step_merge(self) -> None:
        """Step 7: Merge all enriched files into import-ready JSON."""
        data = merge_enriched(
            self.questions_dir,
            self.import_path,
            source_pdf=self.pdf_path.name,
        )

        logger.info(f"Merged {len(data.get('questions', []))} questions → {self.import_path}")
        self._report(step="merge", progress=100)
