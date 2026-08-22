"""Conversation memory (spec section 38): keeps recent turns per session so
follow-up questions ("which ones were about pricing?") carry context.
In-memory for V1."""

import threading
import uuid


class SessionStore:
    def __init__(self, max_turns: int = 20):
        self._sessions: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self._max_turns = max_turns

    def get_or_create(self, session_id: str | None) -> tuple[str, list[dict]]:
        with self._lock:
            if session_id and session_id in self._sessions:
                return session_id, list(self._sessions[session_id])
            new_id = session_id or str(uuid.uuid4())
            self._sessions.setdefault(new_id, [])
            return new_id, list(self._sessions[new_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            history = self._sessions.setdefault(session_id, [])
            history.append({"role": role, "content": content})
            del history[: -self._max_turns]
