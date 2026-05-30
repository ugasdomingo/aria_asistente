from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TraceRecorder:
    chat_id: str
    workflow: str
    events: list[dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def add(self, event_type: str, **payload) -> None:
        self.events.append({"type": event_type, "at": time.time(), **payload})

    def finish(self, status: str, final_text: str = "") -> None:
        self.add("finish", status=status, final_chars=len(final_text))
        path = os.getenv("ARIA_TRACE_FILE", ".aria_traces.jsonl").strip()
        if not path:
            return
        record = {
            "chat_id": self.chat_id,
            "workflow": self.workflow,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 3),
            "events": self.events,
        }
        try:
            Path(path).write_text("", encoding="utf-8") if not Path(path).exists() else None
            with Path(path).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"ARIA trace disabled: {exc}")

