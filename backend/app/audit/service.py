"""Audit trail (spec section 37): every question, plan, approval decision,
execution, and answer gets a record. V1 writes JSON lines to a local file
(gitignored) and keeps a bounded in-memory tail; swap for durable storage
later. Never stores anything in the company clientintel database.
"""

import json
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("audit")

# Single-user V1 — replaced by real authenticated identity when auth lands.
LOCAL_USER_ID = "local-dev"


class AuditService:
    def __init__(self, log_path: str = "audit.log", memory_size: int = 1000):
        self._path = Path(log_path)
        self._recent: deque[dict] = deque(maxlen=memory_size)
        self._lock = threading.Lock()

    def log(
        self,
        event: str,
        *,
        session_id: str | None = None,
        question: str | None = None,
        plan_id: str | None = None,
        generated_sql: list[str] | None = None,
        human_action: str | None = None,
        row_count: int | None = None,
        status: str | None = None,
        error: str | None = None,
    ) -> dict:
        record = {
            "id": str(uuid.uuid4()),
            "event": event,
            "user_id": LOCAL_USER_ID,
            "session_id": session_id,
            "question": question,
            "plan_id": plan_id,
            "generated_sql": generated_sql,
            "human_action": human_action,
            "row_count": row_count,
            "status": status,
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        record = {k: v for k, v in record.items() if v is not None}
        with self._lock:
            self._recent.append(record)
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as e:
                logger.error("Could not write audit record to %s: %s", self._path, e)
        return record

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._recent)[-limit:]
