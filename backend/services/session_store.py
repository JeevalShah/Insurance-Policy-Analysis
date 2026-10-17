import uuid
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

@dataclass
class Session:
    session_id: str
    status: str = "created"

class SessionStore:
    def __init__(self, embedder=None):
        self.embedder = embedder
        self.vector_store = None
        self._sessions = {}

    def create(self) -> Session:
        session_id = str(uuid.uuid4())
        new_session = Session(session_id=session_id)
        self._sessions[session_id] = new_session
        return new_session
        
    def require(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id]

    def initialize_store(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        if not self.vector_store:
            self.vector_store = FAISS.from_texts(
                texts=texts,
                embedding=self.embedder,
                metadatas=metadatas
            )
        else:
            self.vector_store.add_texts(texts=texts, metadatas=metadatas)

    def get_session_retriever(self, session_id: str, k: int = 5):
        if not self.vector_store:
            raise ValueError("Vector store is not initialized.")
        return self.vector_store.as_retriever(
            search_kwargs={
                "k": k,
                "filter": {"session_id": session_id}
            }
        )
        
    def clear_session_data(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
        logger.info(f"Session data cleanup requested for {session_id}.")

# Export global instance for the backend to share state
store = SessionStore()