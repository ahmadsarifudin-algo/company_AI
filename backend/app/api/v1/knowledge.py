"""
Knowledge API — Document ingestion, search, listing, and deletion.

Endpoints:
    POST   /knowledge/ingest      — Ingest a document (chunk + embed + store)
    POST   /knowledge/search      — Semantic search via pgvector
    GET    /knowledge/documents    — List documents (filter by dept/type)
    DELETE /knowledge/{doc_id}     — Delete a document and all its chunks
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.knowledge import (
    DeleteResponse,
    DocumentListResponse,
    DocumentSummary,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.knowledge_service import KnowledgeService

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Ingest ──────────────────────────────────────

@knowledge_router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    request: IngestRequest,
    db: DbSession,
    user: CurrentUser,
) -> IngestResponse:
    """Ingest a document into the knowledge base.

    The document is automatically chunked, embedded, and stored
    with pgvector for semantic retrieval.
    """
    service = KnowledgeService(db)
    result = await service.ingest_document(
        title=request.title,
        content=request.content,
        department=request.department,
        doc_type=request.doc_type,
        source=request.source,
        metadata=request.metadata,
    )
    await db.commit()
    return IngestResponse(**result)


# ── Search ──────────────────────────────────────

@knowledge_router.post("/search", response_model=SearchResponse)
async def search_knowledge(
    request: SearchRequest,
    db: DbSession,
    user: CurrentUser,
) -> SearchResponse:
    """Semantic search across the knowledge base.

    Uses cosine similarity on pgvector embeddings to find
    the most relevant document chunks.
    """
    service = KnowledgeService(db)
    results = await service.search(
        query=request.query,
        department=request.department,
        doc_type=request.doc_type,
        top_k=request.top_k,
    )
    return SearchResponse(
        query=request.query,
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )


# ── List Documents ──────────────────────────────

@knowledge_router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    db: DbSession,
    user: CurrentUser,
    department: str | None = Query(None),
    doc_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> DocumentListResponse:
    """List documents in the knowledge base.

    Returns one entry per parent document (not per chunk).
    Filter by department and/or document type.
    """
    service = KnowledgeService(db)
    docs = await service.list_documents(
        department=department,
        doc_type=doc_type,
        limit=limit,
    )
    return DocumentListResponse(
        documents=[DocumentSummary(**d) for d in docs],
        total=len(docs),
    )


# ── Delete Document ─────────────────────────────

@knowledge_router.delete("/{doc_id}", response_model=DeleteResponse)
async def delete_document(
    doc_id: str,
    db: DbSession,
    user: CurrentUser,
) -> DeleteResponse:
    """Delete a document and all its chunks from the knowledge base."""
    service = KnowledgeService(db)
    deleted = await service.delete_document(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.commit()
    return DeleteResponse(parent_doc_id=doc_id, chunks_deleted=deleted)
