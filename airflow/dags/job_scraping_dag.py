"""
Job Scraping DAG

Runs every 4 hours to scrape jobs, validate, embed, and store in Pinecone.
"""

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
    description="Scrape jobs from multiple sources and store in Pinecone",
    schedule_interval="0 */4 * * *",  # Every 4 hours
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["scraping", "jobs"],
)


def scrape_jobs(**context):
    """Scrape jobs from multiple sources."""
    import httpx

    jobs = []

    # Job search queries to run
    queries = [
        "Python Developer",
        "Software Engineer",
        "Data Scientist",
        "Machine Learning Engineer",
        "Full Stack Developer",
    ]

    # Scrape from MCP Job Market server (PORT 8002!)
    for query in queries:
        try:
            response = httpx.post(
                "http://mcp-jobmarket:8002/tools/search_jobs",  # Fixed port!
                json={"query": query, "limit": 20},
                timeout=60,
            )
            if response.status_code == 200:
                result = response.json()
                jobs.extend(result.get("jobs", []))
                print(f"Scraped {len(result.get('jobs', []))} jobs for '{query}'")
        except Exception as e:
            print(f"Error scraping {query}: {e}")

    print(f"Total jobs scraped: {len(jobs)}")

    # Store in XCom for next task
    context["ti"].xcom_push(key="raw_jobs", value=jobs)

    return len(jobs)


def validate_jobs(**context):
    """Parse and validate jobs from raw snippets."""
    import re

    raw_jobs = context["ti"].xcom_pull(key="raw_jobs")

    parsed_jobs = []
    seen = set()

    for job in raw_jobs:
        source = job.get("source", "Unknown")
        url = job.get("url", "")
        snippet = job.get("snippet", "")

        # Try to extract individual job listings from snippet
        # Pattern: "### Job Title\n\n#### Company Name"
        job_matches = re.findall(r"###\s+([^\n]+)\n\n\s*####\s+([^\n]+)", snippet)

        for title, company in job_matches:
            title = title.strip()
            company = company.strip()

            # Skip duplicates
            key = f"{title}:{company}"
            if key in seen:
                continue
            seen.add(key)

            # Create job entry
            parsed_jobs.append(
                {
                    "title": title,
                    "company": company,
                    "source_url": url,
                    "source_platform": source,
                    "description": f"Position at {company}. Found via {source}.",
                }
            )

    print(f"Parsed {len(parsed_jobs)} unique jobs from {len(raw_jobs)} raw results")
    context["ti"].xcom_push(key="valid_jobs", value=parsed_jobs)

    return len(parsed_jobs)


def embed_and_store(**context):
    """Store jobs directly in PostgreSQL."""
    import os
    from datetime import datetime

    from sqlalchemy import create_engine, text

    valid_jobs = context["ti"].xcom_pull(key="valid_jobs")

    if not valid_jobs:
        print("No jobs to store")
        return 0

    # Connect to database
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@postgres:5432/killmatch",
    )
    # Replace async driver with sync driver for Airflow
    db_url = db_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(db_url)

    stored_count = 0
    skipped_count = 0

    with engine.begin() as conn:  # Use begin() for auto-commit
        for job in valid_jobs:
            try:
                # Check if job already exists by title + company
                result = conn.execute(
                    text(
                        "SELECT id FROM jobs WHERE title = :title AND company = :company"
                    ),
                    {"title": job["title"], "company": job["company"]},
                )
                if result.fetchone():
                    skipped_count += 1
                    continue  # Skip existing

                # Insert new job (without source_url to avoid unique constraint)
                conn.execute(
                    text("""
                        INSERT INTO jobs (title, company, source_platform, description, scraped_at, is_active)
                        VALUES (:title, :company, :source_platform, :description, :scraped_at, true)
                    """),
                    {
                        "title": job["title"],
                        "company": job["company"],
                        "source_platform": job.get("source_platform", ""),
                        "description": job.get("description", ""),
                        "scraped_at": datetime.utcnow(),
                    },
                )
                stored_count += 1
            except Exception as e:
                print(f"Error storing job {job.get('title')}: {e}")

    print(f"Stored {stored_count} new jobs, skipped {skipped_count} existing")
    return stored_count


scrape_task = PythonOperator(
    task_id="scrape_jobs",
    python_callable=scrape_jobs,
    dag=dag,
)

validate_task = PythonOperator(
    task_id="validate_jobs",
    python_callable=validate_jobs,
    dag=dag,
)

store_task = PythonOperator(
    task_id="embed_and_store",
    python_callable=embed_and_store,
    dag=dag,
)

# Define task dependencies
scrape_task >> validate_task >> store_task
