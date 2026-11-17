"""
One-shot local data loader: create tables -> scrape -> upsert to Postgres -> embed to Pinecone.

Mirrors the Airflow DAG `job_scrape_ingest_daily` (scrape >> ingest >> embed) so the
demo can be bootstrapped without running Airflow.

Usage (from repo root, with .env loaded and Postgres on localhost:5432):
    set -a; source .env; set +a
    export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/killmatch
    .venv/bin/python scripts/load_demo_data.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import psycopg2  # noqa: E402
from ingest_jobs_to_db import upsert_jobs  # noqa: E402
from openai import OpenAI  # noqa: E402
from pinecone import Pinecone  # noqa: E402
from scrape_jobs_bs_only import _html_to_text, scrape_all_jobs  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

DEFAULT_SEEDS = ",".join(
    [
        "https://boards.greenhouse.io/stripe",
        "https://boards.greenhouse.io/databricks",
        "https://boards.greenhouse.io/datadog",
        "https://boards.greenhouse.io/airbnb",
    ]
)


def create_tables(db_url: str) -> None:
    # Importing app.db builds the app's async engine, which needs an async driver URL.
    os.environ["DATABASE_URL"] = db_url.replace("+psycopg2", "+asyncpg")
    try:
        from app.db.models import Base
    finally:
        os.environ["DATABASE_URL"] = db_url

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    print(f"[tables] ensured: {', '.join(Base.metadata.tables)}")


def clean(text: str | None) -> str:
    # Greenhouse returns HTML-escaped HTML; one pass unescapes, the second strips tags.
    return _html_to_text(_html_to_text(text or ""))


def embed_jobs(db_url: str) -> int:
    client = OpenAI()
    index = Pinecone().Index(os.getenv("PINECONE_INDEX_NAME", "killmatch-jobs"))
    namespace = os.getenv("PINECONE_NAMESPACE") or None

    conn = psycopg2.connect(db_url.replace("+psycopg2", ""))
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, company, location, description, source_url, source_platform
        FROM jobs WHERE embedding_id IS NULL AND is_active = true
        ORDER BY scraped_at DESC
    """)
    rows = cur.fetchall()
    print(f"[embed] {len(rows)} jobs to embed (namespace={namespace})")

    done = 0
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        texts = [
            f"{r[1]} at {r[2]}. {r[3] or ''}. {(r[4] or '')[:1500]}" for r in batch
        ]
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
        vectors = [
            {
                "id": str(r[0]),
                "values": resp.data[j].embedding,
                "metadata": {
                    "job_id": str(r[0]),
                    "title": r[1] or "",
                    "company": r[2] or "",
                    "location": r[3] or "",
                    "description": (r[4] or "")[:1500],
                    "url": r[5] or "",
                    "source": r[6] or "",
                },
            }
            for j, r in enumerate(batch)
        ]
        index.upsert(vectors=vectors, namespace=namespace)
        cur.executemany(
            "UPDATE jobs SET embedding_id = %s WHERE id = %s",
            [(str(r[0]), r[0]) for r in batch],
        )
        conn.commit()
        done += len(batch)
        print(f"[embed] {done}/{len(rows)}")
    conn.close()
    return done


def main() -> None:
    db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg2")
    os.environ["DATABASE_URL"] = db_url
    os.environ.setdefault("JOB_SCRAPE_SEEDS", DEFAULT_SEEDS)

    create_tables(db_url)
    jobs = scrape_all_jobs()
    for job in jobs:
        job["description"] = clean(job.get("description"))
    print(f"[ingest] {upsert_jobs(jobs)}")
    if "--skip-embed" not in sys.argv:
        embed_jobs(db_url)


if __name__ == "__main__":
    main()
