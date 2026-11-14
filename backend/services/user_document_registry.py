"""
user_document_registry.py

User-scoped document registry for the Sentra Engine.
Maintains reliable document identity, ownership, metadata, and version pointers
per authenticated user.
"""

from contextlib import contextmanager
import logging
import os
import re
import sqlite3
import time
from typing import Optional, List, Dict, Any

from versioning.document_identity import (
    DocumentIdentity,
    DocumentType,
    resolve_document_identity,
    AmbiguousDocumentIdentityError,
)

logger = logging.getLogger(__name__)


class UserDocumentRegistry:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "document_registry.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    current_version INTEGER NOT NULL DEFAULT 1,
                    content_fingerprint TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE(user_id, doc_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_docs_user ON user_documents(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_docs_filename ON user_documents(user_id, filename)")
            conn.commit()

    def register_document(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
        doc_type: str = "policy",
        title: str = "",
        description: str = "",
        content_fingerprint: str = "",
        version_num: int = 1,
    ) -> Dict[str, Any]:
        """Registers a new document or updates existing document metadata under the given user."""
        now = time.time()
        title = title or filename or doc_id
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO user_documents (
                    user_id, doc_id, filename, doc_type, title, description,
                    current_version, content_fingerprint, created_at, updated_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(user_id, doc_id) DO UPDATE SET
                    filename = excluded.filename,
                    doc_type = excluded.doc_type,
                    title = excluded.title,
                    description = excluded.description,
                    current_version = excluded.current_version,
                    content_fingerprint = excluded.content_fingerprint,
                    updated_at = excluded.updated_at,
                    status = 'active'
            """, (
                user_id, doc_id, filename, doc_type, title, description,
                version_num, content_fingerprint, now, now
            ))
            conn.commit()

        return self.get_document(user_id, doc_id)

    def get_document(self, user_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("""
                SELECT user_id, doc_id, filename, doc_type, title, description,
                       current_version, content_fingerprint, created_at, updated_at, status
                FROM user_documents
                WHERE user_id = ? AND doc_id = ?
            """, (user_id, doc_id))
            row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def get_document_by_filename(self, user_id: str, filename: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("""
                SELECT user_id, doc_id, filename, doc_type, title, description,
                       current_version, content_fingerprint, created_at, updated_at, status
                FROM user_documents
                WHERE user_id = ? AND lower(filename) = lower(?) AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id, filename))
            row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_user_documents(self, user_id: str, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            if doc_type:
                cur = conn.execute("""
                    SELECT user_id, doc_id, filename, doc_type, title, description,
                           current_version, content_fingerprint, created_at, updated_at, status
                    FROM user_documents
                    WHERE user_id = ? AND doc_type = ? AND status = 'active'
                    ORDER BY updated_at DESC
                """, (user_id, doc_type))
            else:
                cur = conn.execute("""
                    SELECT user_id, doc_id, filename, doc_type, title, description,
                           current_version, content_fingerprint, created_at, updated_at, status
                    FROM user_documents
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY updated_at DESC
                """, (user_id,))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def update_document_version(
        self,
        user_id: str,
        doc_id: str,
        new_version: int,
        new_fingerprint: str
    ) -> bool:
        now = time.time()
        with self._connection() as conn:
            cur = conn.execute("""
                UPDATE user_documents
                SET current_version = ?, content_fingerprint = ?, updated_at = ?
                WHERE user_id = ? AND doc_id = ?
            """, (new_version, new_fingerprint, now, user_id, doc_id))
            conn.commit()
            return cur.rowcount > 0

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        with self._connection() as conn:
            cur = conn.execute("""
                UPDATE user_documents SET status = 'deleted', updated_at = ?
                WHERE user_id = ? AND doc_id = ?
            """, (time.time(), user_id, doc_id))
            conn.commit()
            return cur.rowcount > 0

    def resolve_user_document_identity(
        self,
        user_id: str,
        explicit_doc_id: Optional[str] = None,
        filename: Optional[str] = None,
        document_text: Optional[str] = None,
        doc_type: str = "policy",
        allow_unconfirmed: bool = False,
    ) -> DocumentIdentity:
        """
        Resolves document identity within the user's isolated document universe.
        Builds a user-specific identity registry from their registered documents.
        """
        user_docs = self.list_user_documents(user_id)
        registry: Dict[str, DocumentIdentity] = {}
        for d in user_docs:
            d_type = DocumentType.POLICY if d["doc_type"] == "policy" else DocumentType.REGULATORY
            registry[d["doc_id"]] = DocumentIdentity(
                doc_id=d["doc_id"],
                doc_type=d_type,
                title=d["title"],
                aliases=[d["filename"]] if d.get("filename") else [],
                metadata={"current_version": d["current_version"]}
            )

        doc_type_enum = DocumentType.POLICY if doc_type == "policy" else DocumentType.REGULATORY

        return resolve_document_identity(
            explicit_doc_id=explicit_doc_id,
            document_text=document_text,
            filename=filename,
            doc_type=doc_type_enum,
            registry=registry,
            allow_unconfirmed=allow_unconfirmed,
        )


document_registry = UserDocumentRegistry()
