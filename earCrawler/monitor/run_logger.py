"""Run logger capturing structured step telemetry for observability (B.36)."""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class StepRecord:
    name: str
    status: str
    duration: float
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class RunRecord:
    run_id: str
    started: float
    finished: Optional[float] = None
    status: str = "running"
    input_hash: Optional[str] = None
    steps: List[StepRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "run_id": self.run_id,
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)),
            "finished": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.finished))
                if self.finished
                else None
            ),
            "status": self.status,
            "input_hash": self.input_hash,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "duration": round(step.duration, 4),
                    "metadata": step.metadata,
                }
                for step in self.steps
            ],
        }


@contextmanager
def run_logger(
    path: Path, *, run_id: str | None = None, input_hash: str | None = None
) -> RunRecord:
    record = RunRecord(
        run_id=run_id or uuid.uuid4().hex, started=time.time(), input_hash=input_hash
    )
    try:
        yield record
        record.status = "ok"
    except Exception:
        record.status = "failed"
        raise
    finally:
        record.finished = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


@contextmanager
def log_step(run: RunRecord, name: str, *, metadata: Dict[str, str] | None = None):
    start = time.time()
    step_metadata = metadata or {}
    try:
        yield step_metadata
        status = "ok"
    except Exception:
        status = "failed"
        raise
    finally:
        run.steps.append(
            StepRecord(
                name=name,
                status=status,
                duration=time.time() - start,
                metadata=step_metadata,
            )
        )
