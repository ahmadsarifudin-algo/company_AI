"""
Knowledge Service — Document ingestion, embedding, and RAG retrieval.

Pipeline: Text → Chunk → Embed (LiteLLM) → Store (pgvector) → Search (cosine similarity)
"""

import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.knowledge import KnowledgeDocument

logger = structlog.get_logger()
settings = get_settings()


class KnowledgeService:
    """Full RAG pipeline: ingest, embed, search, retrieve."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Document Ingestion ───────────────────────

    async def ingest_document(
        self,
        title: str,
        content: str,
        department: str,
        doc_type: str = "general",
        source: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Ingest a document: chunk it, embed chunks, store in pgvector.

        Args:
            title: Document title.
            content: Full text content.
            department: Department scope for retrieval isolation.
            doc_type: Type — sop, policy, decision, report, memo, general.
            source: Original file path or URL.
            metadata: Extra metadata dict.

        Returns:
            Dict with parent_doc_id and number of chunks created.
        """
        parent_doc_id = str(uuid.uuid4())

        # 1. Chunk the content
        chunks = self._chunk_text(content)
        logger.info("chunking_complete", title=title, chunks=len(chunks))

        # 2. Embed all chunks
        embeddings = await self._embed_texts(chunks)
        logger.info("embedding_complete", title=title, vectors=len(embeddings))

        # 3. Store chunks with embeddings
        docs = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc = KnowledgeDocument(
                title=f"{title} [chunk {i + 1}/{len(chunks)}]" if len(chunks) > 1 else title,
                content=chunk,
                department=department,
                doc_type=doc_type,
                source=source,
                chunk_index=i,
                parent_doc_id=parent_doc_id,
                embedding=embedding,
                metadata_json=metadata,
            )
            docs.append(doc)

        self.db.add_all(docs)
        await self.db.flush()

        logger.info(
            "document_ingested",
            title=title,
            parent_doc_id=parent_doc_id,
            chunks=len(docs),
            department=department,
        )

        return {
            "parent_doc_id": parent_doc_id,
            "title": title,
            "chunks_created": len(docs),
            "department": department,
            "doc_type": doc_type,
        }

    # ── Semantic Search ──────────────────────────

    async def search(
        self,
        query: str,
        department: str | None = None,
        doc_type: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search the knowledge base using cosine similarity.

        Args:
            query: Search query text.
            department: Optional department filter.
            doc_type: Optional document type filter.
            top_k: Number of results (default from settings).

        Returns:
            List of dicts with id, title, content, department, score.
        """
        if top_k is None:
            top_k = settings.RAG_TOP_K

        # Embed the query
        query_embedding = await self._embed_single(query)

        # Build the SQL query with pgvector cosine distance
        # pgvector uses <=> for cosine distance (lower = more similar)
        sql = text("""
            SELECT id, title, content, department, doc_type, source,
                   chunk_index, parent_doc_id,
                   1 - (embedding <=> :query_vec::vector) AS similarity
            FROM knowledge_documents
            WHERE embedding IS NOT NULL
            {dept_filter}
            {type_filter}
            ORDER BY embedding <=> :query_vec::vector
            LIMIT :top_k
        """.format(
            dept_filter="AND department = :department" if department else "",
            type_filter="AND doc_type = :doc_type" if doc_type else "",
        ))

        params: dict[str, Any] = {
            "query_vec": str(query_embedding),
            "top_k": top_k,
        }
        if department:
            params["department"] = department
        if doc_type:
            params["doc_type"] = doc_type

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "department": row.department,
                "doc_type": row.doc_type,
                "source": row.source,
                "chunk_index": row.chunk_index,
                "parent_doc_id": row.parent_doc_id,
                "similarity": round(float(row.similarity), 4),
            }
            for row in rows
        ]

    async def get_context_for_task(
        self,
        task_description: str,
        department: str,
        top_k: int | None = None,
    ) -> str:
        """Retrieve formatted RAG context for an agent task.

        Searches the knowledge base and formats results into a context
        string that can be prepended to the agent's messages.

        Args:
            task_description: The task to find context for.
            department: Department scope.
            top_k: Number of context chunks.

        Returns:
            Formatted context string, or empty string if no results.
        """
        results = await self.search(
            query=task_description,
            department=department,
            top_k=top_k,
        )

        if not results:
            return ""

        context_parts = ["## Relevant Knowledge Base Context\n"]
        for i, doc in enumerate(results, 1):
            context_parts.append(
                f"### [{i}] {doc['title']} (similarity: {doc['similarity']})\n"
                f"Type: {doc['doc_type']} | Source: {doc.get('source', 'N/A')}\n\n"
                f"{doc['content']}\n"
            )

        return "\n---\n".join(context_parts)

    # ── Document Management ──────────────────────

    async def list_documents(
        self,
        department: str | None = None,
        doc_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List unique documents (grouped by parent_doc_id).

        Returns one entry per parent document, not per chunk.
        """
        # Get distinct parent docs with their first chunk
        query = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.chunk_index == 0)
        )
        if department:
            query = query.where(KnowledgeDocument.department == department)
        if doc_type:
            query = query.where(KnowledgeDocument.doc_type == doc_type)
        query = query.order_by(KnowledgeDocument.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        docs = result.scalars().all()

        return [
            {
                "parent_doc_id": doc.parent_doc_id,
                "title": doc.title,
                "department": doc.department,
                "doc_type": doc.doc_type,
                "source": doc.source,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]

    async def delete_document(self, parent_doc_id: str) -> int:
        """Delete all chunks of a document by parent_doc_id.

        Returns:
            Number of chunks deleted.
        """
        result = await self.db.execute(
            delete(KnowledgeDocument).where(
                KnowledgeDocument.parent_doc_id == parent_doc_id
            )
        )
        await self.db.flush()
        deleted = result.rowcount  # type: ignore[union-attr]
        logger.info("document_deleted", parent_doc_id=parent_doc_id, chunks=deleted)
        return deleted

    # ── Private: Chunking ────────────────────────

    def _chunk_text(self, text_content: str) -> list[str]:
        """Split text into chunks with overlap.

        Uses a simple word-based chunking strategy. Each chunk targets
        ~CHUNK_SIZE tokens (approximated as words * 1.3).
        """
        words = text_content.split()
        chunk_size_words = int(settings.CHUNK_SIZE / 1.3)  # rough token→word conversion
        overlap_words = int(settings.CHUNK_OVERLAP / 1.3)

        if len(words) <= chunk_size_words:
            return [text_content]

        chunks = []
        start = 0
        while start < len(words):
            end = start + chunk_size_words
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start = end - overlap_words  # overlap with previous chunk

        return chunks

    # ── Private: Embedding ───────────────────────

    async def _embed_single(self, text_content: str) -> list[float]:
        """Embed a single text string via LiteLLM proxy."""
        results = await self._embed_texts([text_content])
        return results[0]

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts via LiteLLM proxy embedding endpoint.

        Uses the configured embedding model (text-embedding-3-small).
        Batches requests to avoid hitting rate limits.
        """
        url = f"{settings.LITELLM_PROXY_URL}/v1/embeddings"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json={
                    "model": settings.EMBEDDING_MODEL,
                    "input": texts,
                },
                headers={
                    "Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result = response.json()

        # Extract embeddings in order
        embeddings = [item["embedding"] for item in result["data"]]
        return embeddings
