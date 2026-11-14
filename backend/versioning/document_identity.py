"""
document_identity.py

Stable document identity management for the Sentra Engine.
Ensures document identity is distinct from transient filenames, file formats,
and document version identity.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Optional, List, Dict, Any


class DocumentType(str, Enum):
    POLICY = "policy"
    REGULATORY = "regulatory"
    UNKNOWN = "unknown"


class AmbiguousDocumentIdentityError(Exception):
    """Raised when document identity cannot be confidently established."""
    pass


@dataclass
class DocumentIdentity:
    """
    Stable identity representation of a document across its lifetime and versions.
    """
    doc_id: str
    doc_type: DocumentType = DocumentType.UNKNOWN
    title: str = ""
    description: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type.value if isinstance(self.doc_type, DocumentType) else str(self.doc_type),
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentIdentity":
        doc_type_raw = data.get("doc_type", "unknown")
        try:
            doc_type = DocumentType(doc_type_raw)
        except ValueError:
            doc_type = DocumentType.UNKNOWN

        return cls(
            doc_id=data["doc_id"],
            doc_type=doc_type,
            title=data.get("title", ""),
            description=data.get("description", ""),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
            aliases=data.get("aliases", []),
        )


# Patterns to scan document header or text for explicit identity markers
_IDENTITY_PATTERNS = [
    re.compile(r'\b(?:Document\s*ID|Doc\s*ID)\s*[:=\-]\s*([A-Za-z0-9_\-\.\/]+)', re.IGNORECASE),
    re.compile(r'\b(?:Policy\s*(?:ID|Number|No\.?))\s*[:=\-]\s*([A-Za-z0-9_\-\.\/]+)', re.IGNORECASE),
    re.compile(r'\b(?:Circular\s*(?:No\.?|Ref|Reference))\s*[:=\-]\s*([A-Za-z0-9_\-\.\/]+)', re.IGNORECASE),
    re.compile(r'\b(?:Ref\s*(?:No\.?|:))\s*([A-Za-z0-9_\-\.\/]{4,})', re.IGNORECASE),
    re.compile(r'\b(?:UIN)\s*[:=\-]\s*([A-Za-z0-9_\-\.\/]+)', re.IGNORECASE),
]

_TITLE_PATTERNS = [
    re.compile(r'^(?:DOCUMENT\s*\d+\s*\n)?([^\n]{5,100})', re.IGNORECASE),
]


def extract_document_identity_from_text(
    text: str,
    doc_type: DocumentType = DocumentType.UNKNOWN
) -> Optional[str]:
    """
    Attempts to extract an explicit document ID from document text (e.g. headers, preamble).
    Returns the extracted ID string or None if not found.
    """
    if not text:
        return None

    # Scan the first 3000 characters where headers / metadata typically reside
    header_sample = text[:3000]

    for pattern in _IDENTITY_PATTERNS:
        match = pattern.search(header_sample)
        if match:
            candidate = match.group(1).strip().strip(".,;")
            if candidate and len(candidate) >= 3:
                return candidate

    return None


extract_document_identity = extract_document_identity_from_text


def resolve_document_identity(
    explicit_doc_id: Optional[str] = None,
    document_text: Optional[str] = None,
    filename: Optional[str] = None,
    doc_type: DocumentType = DocumentType.UNKNOWN,
    registry: Optional[Dict[str, DocumentIdentity]] = None,
    allow_unconfirmed: bool = False,
) -> DocumentIdentity:
    """
    Resolves document identity using a prioritized fallback chain:
    1. Explicitly provided doc_id (trusted primary input).
    2. Explicit metadata ID extracted from document text.
    3. Document registry lookup if filename/alias matches an existing identity.
    4. If none of the above are available:
       - If allow_unconfirmed=True, generates a slug-based identity marked as unconfirmed.
       - Otherwise, raises AmbiguousDocumentIdentityError.
    """
    # 1. Explicit ID provided
    if explicit_doc_id and explicit_doc_id.strip():
        clean_id = explicit_doc_id.strip()
        if registry and clean_id in registry:
            return registry[clean_id]
        return DocumentIdentity(
            doc_id=clean_id,
            doc_type=doc_type,
            title=clean_id,
            metadata={"source": "explicit"},
        )

    # 2. Text inspection
    if document_text:
        extracted_id = extract_document_identity_from_text(document_text, doc_type)
        if extracted_id:
            if registry and extracted_id in registry:
                return registry[extracted_id]
            return DocumentIdentity(
                doc_id=extracted_id,
                doc_type=doc_type,
                title=extracted_id,
                metadata={"source": "extracted_from_text"},
            )

    # 3. Registry lookup via filename / alias
    if filename and registry:
        clean_filename = filename.lower().strip()
        for identity in registry.values():
            if clean_filename in [a.lower() for a in identity.aliases]:
                return identity

    # 4. Fallback or error
    if not allow_unconfirmed:
        raise AmbiguousDocumentIdentityError(
            f"Cannot establish document identity with confidence for file '{filename}'. "
            "Please provide an explicit 'document_id' or confirm document identity."
        )

    # Generated fallback with unconfirmed status
    generated_id = f"DOC_{int(time.time())}"
    if filename:
        slug = re.sub(r'[^a-zA-Z0-9_]', '_', filename.split('.')[0]).strip('_')
        if slug:
            generated_id = f"DOC_{slug}"

    return DocumentIdentity(
        doc_id=generated_id,
        doc_type=doc_type,
        title=filename or generated_id,
        metadata={"source": "generated_unconfirmed", "unconfirmed": True},
        aliases=[filename] if filename else [],
    )
