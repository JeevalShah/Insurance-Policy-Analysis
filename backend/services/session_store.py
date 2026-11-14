import uuid
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Session:
    session_id: str
    status: str = "created"
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

class SessionStore:
    def __init__(self, embedder=None):
        self.embedder = embedder
        self.vector_store = None
        self._sessions: Dict[str, Session] = {}

    def create(self, user_id: Optional[str] = None) -> Session:
        session_id = str(uuid.uuid4())
        new_session = Session(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = new_session
        return new_session
        
    def require(self, session_id: str, user_id: Optional[str] = None) -> Session:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        session = self._sessions[session_id]
        if user_id and session.user_id and session.user_id != user_id:
            raise PermissionError(f"Access denied: session {session_id} belongs to a different user.")
        return session

    def get_user_sessions(self, user_id: str) -> List[Session]:
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def initialize_store(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        from langchain_community.vectorstores import FAISS
        if not self.vector_store:
            self.vector_store = FAISS.from_texts(
                texts=texts,
                embedding=self.embedder,
                metadatas=metadatas
            )
        else:
            self.vector_store.add_texts(texts=texts, metadatas=metadatas)

    def get_session_retriever(self, session_id: str, user_id: Optional[str] = None, k: int = 5):
        if not self.vector_store:
            raise ValueError("Vector store is not initialized.")
        search_filter = {"session_id": session_id}
        if user_id:
            search_filter["user_id"] = user_id
        return self.vector_store.as_retriever(
            search_kwargs={
                "k": k,
                "filter": search_filter
            }
        )
        
    def clear_session_data(self, session_id: str, user_id: Optional[str] = None):
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if user_id and session.user_id and session.user_id != user_id:
                raise PermissionError("Access denied: cannot clear session belonging to another user.")
            del self._sessions[session_id]
        logger.info(f"Session data cleanup completed for {session_id}.")

# Export global instance for the backend to share state
store = SessionStore()
