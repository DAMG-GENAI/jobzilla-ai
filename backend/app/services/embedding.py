"""
Embedding Service

Generate embeddings using OpenAI for semantic search.
"""

from openai import AsyncOpenAI

from app.core.config import settings


async def get_embedding(text: str) -> list[float]:
    """
    Generate embedding for a single text.

    Uses OpenAI's text-embedding-3-small model.
    """
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured")

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )

    return response.data[0].embedding


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    Batches requests for efficiency.
    """
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured")

    if not texts:
        return []

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # OpenAI allows batching up to ~8000 tokens
    # We'll send in batches of 100 texts
    all_embeddings = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]

        response = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=batch,
        )

        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    """
    import math

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)
