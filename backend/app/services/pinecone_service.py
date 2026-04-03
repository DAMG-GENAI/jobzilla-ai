"""
Pinecone Service

Vector database operations for job storage and similarity search.
"""

from typing import Any

from pinecone import Pinecone

from app.core.config import settings
from app.services.embedding import get_embedding


class PineconeService:
    """Service for Pinecone vector database operations."""

    def __init__(self):
        if not settings.pinecone_api_key:
            raise ValueError("Pinecone API key not configured")

        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name
        self._index = None

    @property
    def index(self):
        """Get or create the index connection."""
        if self._index is None:
            self._index = self.pc.Index(self.index_name)
        return self._index

    async def upsert_job(
        self,
        job_id: str,
        job_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Upsert a job listing into the vector database.

        Args:
            job_id: Unique identifier for the job
            job_text: Text to embed (title + description + skills)
            metadata: Job metadata (title, company, location, etc.)
        """
        # Generate embedding
        embedding = await get_embedding(job_text)

        # Upsert to Pinecone
        self.index.upsert(
            vectors=[
                {
                    "id": job_id,
                    "values": embedding,
                    "metadata": metadata,
                }
            ]
        )

    async def upsert_jobs_batch(
        self,
        jobs: list[dict[str, Any]],
    ) -> int:
        """
        Batch upsert multiple jobs.

        Args:
            jobs: List of dicts with id, text, and metadata

        Returns:
            Number of jobs upserted
        """
        from app.services.embedding import get_embeddings

        # Generate all embeddings
        texts = [job["text"] for job in jobs]
        embeddings = await get_embeddings(texts)

        # Build vectors
        vectors = [
            {
                "id": job["id"],
                "values": embeddings[i],
                "metadata": job["metadata"],
            }
            for i, job in enumerate(jobs)
        ]

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            self.index.upsert(vectors=batch)

        return len(jobs)

    async def search_jobs(
        self,
        query: str,
        top_k: int = 10,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar jobs using semantic search.

        Args:
            query: Search query text
            top_k: Number of results to return
            filter: Optional metadata filter

        Returns:
            List of matching jobs with scores
        """
        # Generate query embedding
        query_embedding = await get_embedding(query)

        # Search Pinecone
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filter,
        )

        # Format results
        jobs = []
        for match in results.get("matches", []):
            jobs.append(
                {
                    "id": match["id"],
                    "score": match["score"],
                    **match.get("metadata", {}),
                }
            )

        return jobs

    async def delete_job(self, job_id: str) -> None:
        """Delete a job from the index."""
        self.index.delete(ids=[job_id])

    async def get_index_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        return self.index.describe_index_stats()


# Singleton instance
_pinecone_service: PineconeService | None = None


def get_pinecone_service() -> PineconeService:
    """Get or create Pinecone service instance."""
    global _pinecone_service
    if _pinecone_service is None:
        _pinecone_service = PineconeService()
    return _pinecone_service
