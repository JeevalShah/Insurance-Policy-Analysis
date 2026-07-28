import os
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config

@dataclass
class SessionState:
    session_id: str
    session_dir: str
    status: str = "created"           # created -> ingesting -> ready -> analyzing -> analyzed -> error
    error: Optional[str] = None

    policy_clauses: List[Dict[str, Any]] = field(default_factory=list)
    regulation_clauses: List[Dict[str, Any]] = field(default_factory=list)

    index: Any = None                 # faiss.Index
    embedder: Any = None              # embeddings.embedder.PolicyEmbedder

    analysis_result: Optional[List[Dict[str, Any]]] = None
    
    # Stores the conversational memory
    chat_history: List[Dict[str, str]] = field(default_factory=list)

    def add_chat_message(self, role: str, content: str):
        """Helper to append a message to the memory."""
        self.chat_history.append({"role": role, "content": content})

    def get_recent_chat_history(self, limit: int = 6) -> List[Dict[str, str]]:
        """Returns only the most recent N messages to prevent context window overflow."""
        return self.chat_history[-limit:] if self.chat_history else []


class SessionStore:
    """Thread-safe in-memory registry of active analysis sessions."""

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def create(self) -> SessionState:
        session_id = uuid.uuid4().hex[:12]
        session_dir = os.path.join(config.SESSIONS_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(os.path.join(session_dir, "raw"), exist_ok=True)

        state = SessionState(session_id=session_id, session_dir=session_dir)
        with self._lock:
            self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> SessionState:
        state = self.get(session_id)
        if state is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        return state


# Single process-wide store.
store = SessionStore()