"""
Job Scraping DAG (Tavily API)

Runs every 4 hours to scrape jobs via Tavily, store in PostgreSQL, and embed in Pinecone.
"""

import os
import re
from datetime import datetime, timedelta

from airflow.operators.python import PythonOperator

from airflow import DAG

default_args = {
    "owner": "killmatch",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "job_scraping",
    default_args=default_args,
    description="[DISABLED] Tavily scraper — produces jobs without valid apply URLs. Use job_scrape_ingest_daily (Greenhouse/Lever) instead.",
    schedule_interval=None,  # Disabled: Tavily results lack reliable apply links
    start_date=datetime(2024, 1, 1),
    catchup=False,
    is_paused_upon_creation=True,
    tags=["scraping", "jobs"],
)


def scrape_jobs(**context):
    """Scrape jobs from Tavily via MCP Job Market server."""
    import httpx

    jobs = []
    queries = [
        "Python Developer",
        "Software Engineer",
        "Data Scientist",
        "Machine Learning Engineer",
        "Full Stack Developer",
    ]

    for query in queries:
        try:
            response = httpx.post(
                "http://mcp-jobmarket:8002/tools/search_jobs",
                json={"query": query, "limit": 20},
                timeout=60,
            )
            if response.status_code == 200:
                result = response.json()
                jobs.extend(result.get("jobs", []))
                print(f"Scraped {len(result.get('jobs', []))} jobs for '{query}'")
        except Exception as e:
            print(f"Error scraping {query}: {e}")

    print(f"Total raw results: {len(jobs)}")
    context["ti"].xcom_push(key="raw_jobs", value=jobs)
    return len(jobs)


def validate_and_store(**context):
    """Parse Tavily results, extract real URLs, store in PostgreSQL."""
    from sqlalchemy import create_engine, text

    raw_jobs = context["ti"].xcom_pull(key="raw_jobs")
    if not raw_jobs:
        print("No jobs to process")
        return 0

    # Parse each Tavily result — keep the REAL URL from Tavily
    valid_jobs = []
    seen_urls = set()

    for job in raw_jobs:
        url = (job.get("url") or "").strip()
        title = (job.get("title") or "").strip()
        snippet = (job.get("snippet") or "").strip()
        source = job.get("source", "Unknown")

        # Skip generic search/listing pages (not actual job postings)
        if not url:
            continue
        skip_patterns = [
            "jobs/search",
            "jobs-in-",
            "jobs?",
            "best-",
            "top-",
            "glassdoor.com/Job",
            "linkedin.com/jobs/",
            "indeed.com/jobs",
            "indeed.com/q-",
        ]
        if any(p in url for p in skip_patterns):
            continue

        # Clean up title — Tavily titles often have site names appended
        title = re.split(r"\s*\|\s*|\s*-\s*LinkedIn\s*$|\s*-\s*Indeed\s*$", title)[
            0
        ].strip()
        if not title or len(title) < 5:
            continue

        # Skip aggregate/search result pages by title patterns
        if re.search(
            r"\d{1,3},?\d{3}\+?\s+\w+\s+jobs|jobs in\s|Best\s.*Jobs\s\d{4}",
            title,
            re.IGNORECASE,
        ):
            continue

        # Deduplicate by URL
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Extract company from title if possible (pattern: "Role at Company")
        company = "Unknown"
        if " at " in title:
            parts = title.rsplit(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()

        valid_jobs.append(
            {
                "title": title[:500],
                "company": company[:255],
                "description": snippet[:2000],
                "source_url": url[:1000],
                "source_platform": source[:100],
            }
        )

    print(f"Valid jobs with URLs: {len(valid_jobs)}")

    if not valid_jobs:
        return 0

    # Store in PostgreSQL
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set, skipping store")
        return 0
    db_url = db_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(db_url)

    stored = 0
    skipped = 0
    with engine.begin() as conn:
        for job in valid_jobs:
            try:
                existing = conn.execute(
                    text("SELECT id FROM jobs WHERE source_url = :url"),
                    {"url": job["source_url"]},
                )
                if existing.fetchone():
                    skipped += 1
                    continue

                conn.execute(
                    text("""
                        INSERT INTO jobs (title, company, description, source_url, source_platform, scraped_at, is_active)
                        VALUES (:title, :company, :description, :source_url, :source_platform, :scraped_at, true)
                    """),
                    {
                        **job,
                        "scraped_at": datetime.utcnow(),
                    },
                )
                stored += 1
            except Exception as e:
                print(f"Error storing {job['title']}: {e}")

    print(f"Stored {stored} new jobs, skipped {skipped} existing")
    context["ti"].xcom_push(key="stored_count", value=stored)
    return stored


def embed_new_jobs(**context):
    """Embed newly stored jobs into Pinecone."""
    import psycopg2
    from openai import OpenAI
    from pinecone import Pinecone

    openai_key = os.getenv("OPENAI_API_KEY", "")
    pinecone_key = os.getenv("PINECONE_API_KEY", "")
    index_name = os.getenv("PINECONE_INDEX_NAME", "killmatch-jobs")

    if not openai_key or not pinecone_key:
        print("[embed] Missing API keys, skipping")
        return 0

    client = OpenAI(api_key=openai_key)
    pc = Pinecone(api_key=pinecone_key)
    index = pc.Index(index_name)

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("[embed] DATABASE_URL not set")
        return 0
    db_url = (
        db_url.replace("+asyncpg", "")
        .replace("+psycopg2", "")
        .replace("postgres://", "postgresql://")
    )

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, company, location, description, source_url, source_platform
        FROM jobs
        WHERE embedding_id IS NULL AND is_active = true
        AND source_url IS NOT NULL AND source_url != ''
        AND source_url NOT LIKE '%jobs/search%'
        ORDER BY scraped_at DESC
        LIMIT 500
    """)
    rows = cur.fetchall()

    if not rows:
        print("[embed] No new jobs to embed")
        cur.close()
        conn.close()
        return 0

    print(f"[embed] Embedding {len(rows)} jobs")
    embedded = 0

    for i in range(0, len(rows), 50):
        batch = rows[i : i + 50]
        texts = [f"{r[1]} at {r[2]}. {r[3] or ''}. {(r[4] or '')[:500]}" for r in batch]
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts)

        vectors = []
        for j, row in enumerate(batch):
            vectors.append(
                {
                    "id": str(row[0]),
                    "values": resp.data[j].embedding,
                    "metadata": {
                        "title": row[1] or "",
                        "company": row[2] or "",
                        "location": row[3] or "",
                        "description": (row[4] or "")[:500],
                        "url": row[5] or "",
                        "source": row[6] or "",
                        "job_id": str(row[0]),
                    },
                }
            )

        index.upsert(vectors=vectors)
        ucur = conn.cursor()
        for row in batch:
            ucur.execute(
                "UPDATE jobs SET embedding_id = %s WHERE id = %s",
                (str(row[0]), row[0]),
            )
        conn.commit()
        ucur.close()
        embedded += len(batch)
        print(f"[embed] Batch {i // 50 + 1}: {embedded} embedded")

    cur.close()
    conn.close()
    print(f"[embed] Total: {embedded}")
    return embedded


scrape_task = PythonOperator(
    task_id="scrape_jobs",
    python_callable=scrape_jobs,
    dag=dag,
)

store_task = PythonOperator(
    task_id="validate_and_store",
    python_callable=validate_and_store,
    dag=dag,
)

embed_task = PythonOperator(
    task_id="embed_new_jobs",
    python_callable=embed_new_jobs,
    dag=dag,
)

scrape_task >> store_task >> embed_task
