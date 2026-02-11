"""Pydantic schemas for Knowledge API — ingestion, search, and document listing."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Requests ────────────────────────────────────

class IngestRequest(BaseModel):
    """Request to ingest a document into the knowledge base."""

    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    department: str = Field(min_length=1, max_length=50)
    doc_type: str = Field(default="general", max_length=50)
    source: str | None = None
    metadata: dict | None = None


class SearchRequest(BaseModel):
    """Request to search the knowledge base."""

    query: str = Field(min_length=1)
    department: str | None = None
    doc_type: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


# ── Responses ───────────────────────────────────

class IngestResponse(BaseModel):
    """Response after ingesting a document."""

    parent_doc_id: str
    title: str
    chunks_created: int
    department: str
    doc_type: str


class SearchResult(BaseModel):
    """A single search result with similarity score."""

    id: str
    title: str
    content: str
    department: str
    doc_type: str
    source: str | None
    chunk_index: int
    parent_doc_id: str | None
    similarity: float


class SearchResponse(BaseModel):
    """Response for knowledge search."""

    query: str
    results: list[SearchResult]
    total: int


class DocumentSummary(BaseModel):
    """Summary of a document (not individual chunks)."""

    parent_doc_id: str | None
    title: str
    department: str
    doc_type: str
    source: str | None
    created_at: datetime | None


class DocumentListResponse(BaseModel):
    """Response for listing documents."""

    documents: list[DocumentSummary]
    total: int


class DeleteResponse(BaseModel):
    """Response after deleting a document."""

    parent_doc_id: str
    chunks_deleted: int
