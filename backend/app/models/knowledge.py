"""KnowledgeDocument model — RAG knowledge base with pgvector embeddings."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class KnowledgeDocument(Base, TimestampMixin):
    """A chunk of knowledge stored with its vector embedding.

    Documents are chunked during ingestion. Each row represents one chunk,
    linked to its parent via parent_doc_id. Embeddings use OpenAI's
    text-embedding-3-small (1536 dimensions) via LiteLLM proxy.
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general"
    )  # sop, policy, decision, report, memo, general
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    embedding = mapped_column(Vector(1536), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<KnowledgeDocument {self.title[:40]} ({self.department}/{self.doc_type})>"
