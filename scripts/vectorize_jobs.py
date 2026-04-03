#!/usr/bin/env python3
"""
Job Vectorization Script

Embeds all jobs from PostgreSQL into Pinecone for semantic search.
Run this after scraping jobs to enable embedding-based matching.
"""

import os

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

# Load environment variables
load_dotenv("/Applications/demo-pro2/.env")

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX_NAME", "killmatch-jobs")

# Database config - use Docker service name when running in container
DB_HOST = os.getenv("DB_HOST", "killmatch-postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "killmatch")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


def get_embedding(client: OpenAI, text: str) -> list[float]:
    """Get embedding for text using OpenAI."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],  # Truncate to avoid token limits
    )
    return response.data[0].embedding


def main():
    print("🚀 Starting job vectorization...")

    # Initialize clients
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)

    # Connect to database
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    cur = conn.cursor()

    # Get all jobs
    cur.execute("""
        SELECT id, title, company, description, source_platform
        FROM jobs
        WHERE is_active = true
    """)
    jobs = cur.fetchall()
    print(f"📊 Found {len(jobs)} jobs to vectorize")

    # Check what's already in Pinecone
    stats = index.describe_index_stats()
    existing_count = stats.get("total_vector_count", 0)
    print(f"📌 Pinecone already has {existing_count} vectors")

    # Process jobs in batches
    batch_size = 50
    vectorized_count = 0
    skipped_count = 0

    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        vectors_to_upsert = []

        for job_id, title, company, description, source in batch:
            # Create text for embedding
            job_text = f"{title} at {company}. {description or ''}"

            # Generate synthetic job URL from company name
            company_slug = (
                (company or "job").lower().replace(" ", "-").replace(",", "")[:30]
            )
            synthetic_url = f"https://linkedin.com/jobs/search/?keywords={company_slug}"

            try:
                # Get embedding
                embedding = get_embedding(openai_client, job_text)

                # Prepare vector for Pinecone
                vectors_to_upsert.append(
                    {
                        "id": f"job_{job_id}",
                        "values": embedding,
                        "metadata": {
                            "job_id": job_id,
                            "title": title,
                            "company": company,
                            "description": (description or "")[:1000],
                            "url": synthetic_url,
                            "source": source or "LinkedIn",
                        },
                    }
                )
                vectorized_count += 1

            except Exception as e:
                print(f"  ⚠️ Error embedding job {job_id}: {e}")
                skipped_count += 1

        # Upsert batch to Pinecone
        if vectors_to_upsert:
            index.upsert(vectors=vectors_to_upsert)
            print(
                f"  ✅ Batch {i//batch_size + 1}: Upserted {len(vectors_to_upsert)} vectors"
            )

    # Close database connection
    cur.close()
    conn.close()

    # Final stats
    final_stats = index.describe_index_stats()
    print("\n🎉 Vectorization complete!")
    print(f"   - Jobs vectorized: {vectorized_count}")
    print(f"   - Jobs skipped: {skipped_count}")
    print(f"   - Total vectors in Pinecone: {final_stats.get('total_vector_count', 0)}")


if __name__ == "__main__":
    main()
