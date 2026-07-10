"""
TaskManager — background task tracking with JSON persistence.

Decoupled from Flask/FastAPI/CLI. Any frontend can use this to track
pipeline progress. Tasks persist to disk so they survive restarts.

Usage:
    from pipeline.task_manager import TaskManager

    tm = TaskManager()
    task = tm.create_task(pdf_name="1-3.pdf", pdf_path="/path/to/1-3.pdf")

    # Pipeline reports progress via callback
    def on_progress(task_id, **kwargs):
        tm.update_task(task_id, **kwargs)

    # After completion
    tm.update_task(task.task_id, status="completed", progress=100)
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_STATES = ("pending", "running", "completed", "failed", "cancelled")

DEFAULT_TASKS_DIR = Path("data/tasks")


@dataclass
class Task:
    """A single pipeline task."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    pdf_name: str = ""
    pdf_path: str = ""
    output_directory: str = ""
    status: str = "pending"  # pending | running | completed | failed | cancelled
    progress: int = 0  # 0-100
    current_step: str = ""
    current_question: int = 0
    total_questions: int = 0
    start_time: str = ""
    finish_time: str = ""
    elapsed_seconds: float = 0.0
    error_message: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TaskManager:
    """Manages pipeline tasks with JSON-file persistence.

    Thread-safe: all mutations are protected by a lock.
    Each task is persisted as a separate JSON file in tasks_dir.
    """

    def __init__(self, tasks_dir: str | Path | None = None):
        self.tasks_dir = Path(tasks_dir) if tasks_dir else DEFAULT_TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._load_all()

    # ── CRUD ─────────────────────────────────────────────────

    def create_task(
        self,
        pdf_name: str,
        pdf_path: str,
        output_directory: str = "",
    ) -> Task:
        """Create a new task and persist it."""
        task = Task(
            pdf_name=pdf_name,
            pdf_path=pdf_path,
            output_directory=output_directory,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        """List tasks, most recent first."""
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True,
            )
            return tasks[:limit]

    def update_task(self, task_id: str, **kwargs: Any) -> Task | None:
        """Update task fields and persist.

        Accepted kwargs: status, progress, current_step, current_question,
        total_questions, error_message, finish_time, elapsed_seconds,
        output_directory.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            # Auto-timestamp status transitions
            now = datetime.now(timezone.utc).isoformat()
            if kwargs.get("status") == "running" and not task.start_time:
                task.start_time = now
            if kwargs.get("status") in ("completed", "failed", "cancelled"):
                if not task.finish_time:
                    task.finish_time = now
                if task.start_time:
                    try:
                        start = datetime.fromisoformat(task.start_time)
                        finish = datetime.fromisoformat(task.finish_time)
                        task.elapsed_seconds = round(
                            (finish - start).total_seconds(), 1
                        )
                    except Exception:
                        pass

            self._save_task(task)
            return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task (removes JSON file)."""
        with self._lock:
            task = self._tasks.pop(task_id, None)
            if not task:
                return False
            task_file = self.tasks_dir / f"{task_id}.json"
            task_file.unlink(missing_ok=True)
            return True

    # ── Persistence ──────────────────────────────────────────

    def _save_task(self, task: Task) -> None:
        """Persist a single task to disk. Caller must hold _lock."""
        task_file = self.tasks_dir / f"{task.task_id}.json"
        task_file.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_all(self) -> None:
        """Load all tasks from disk on startup."""
        for f in self.tasks_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                task = Task.from_dict(data)
                self._tasks[task.task_id] = task
            except Exception:
                continue

    # ── Convenience ──────────────────────────────────────────

    def make_progress_callback(self, task_id: str):
        """Return a callback suitable for Pipeline(progress_callback=...).

        The callback signature matches what Pipeline expects:
            callback(step=..., progress=..., current_question=..., total_questions=...)
        """

        def _callback(
            step: str = "",
            progress: int = 0,
            current_question: int = 0,
            total_questions: int = 0,
        ) -> None:
            kwargs: dict[str, Any] = {}
            if step:
                kwargs["current_step"] = step
            if progress:
                kwargs["progress"] = progress
            if current_question:
                kwargs["current_question"] = current_question
            if total_questions:
                kwargs["total_questions"] = total_questions
            if kwargs:
                # Also update elapsed_seconds on each callback
                task = self.get_task(task_id)
                if task and task.start_time:
                    try:
                        start = datetime.fromisoformat(task.start_time)
                        kwargs["elapsed_seconds"] = round(
                            (datetime.now(timezone.utc) - start).total_seconds(), 1
                        )
                    except Exception:
                        pass
                self.update_task(task_id, **kwargs)

        return _callback


def run_pipeline_background(
    task_manager: TaskManager,
    task_id: str,
    pipeline_kwargs: dict[str, Any],
) -> None:
    """Run a Pipeline in a background thread, updating the task.

    This is the bridge between TaskManager and Pipeline.
    Call this from a threading.Thread target.

    Args:
        task_manager: The TaskManager instance
        task_id: Task ID to update
        pipeline_kwargs: Kwargs passed to Pipeline.__init__
    """
    from pipeline.pipeline import Pipeline

    task_manager.update_task(task_id, status="running")
    callback = task_manager.make_progress_callback(task_id)

    # Inject progress_callback into pipeline kwargs
    pipeline_kwargs = dict(pipeline_kwargs)
    pipeline_kwargs["progress_callback"] = callback

    try:
        pipe = Pipeline(**pipeline_kwargs)
        result = pipe.run()

        # Verify import_ready.json exists
        import os
        import_ready = os.path.join(result.get("output", ""), "import_ready.json")
        if not os.path.isfile(import_ready):
            task_manager.update_task(
                task_id,
                status="failed",
                error_message="未检测到题目。可能需要调整规则引擎参数或换一个 PDF 格式。",
            )
            return

        task_manager.update_task(
            task_id,
            status="completed",
            progress=100,
            output_directory=result.get("output", ""),
        )
    except Exception as e:
        task_manager.update_task(
            task_id,
            status="failed",
            error_message=traceback.format_exc()[:500],
        )
