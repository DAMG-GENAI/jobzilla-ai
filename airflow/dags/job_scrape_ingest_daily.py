"""
Daily Airflow DAG: scrape jobs (Greenhouse + Lever) and ingest into Postgres.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from airflow.operators.python import PythonOperator

from airflow import DAG

default_args = {
    "owner": "jobzilla",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    dag_id="job_scrape_ingest_daily",
    default_args=default_args,
    description="Daily scrape from Greenhouse/Lever and idempotent Postgres ingest",
    schedule_interval="0 6 * * *",  # Daily at 06:00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["jobs", "scraping", "postgres"],
)


DEFAULT_SEEDS = [
    "https://boards.greenhouse.io/speechify",
    "https://jobs.lever.co/explodingkittens",
]
DEFAULT_MAX_SEEDS = 500


def _html_to_text(html: str | None) -> str:
    from bs4 import BeautifulSoup

    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _humanize_name(raw: str) -> str:
    return (
        re.sub(r"\s{2,}", " ", raw.replace("-", " ").replace("_", " ")).strip().title()
    )


def _get_seed_urls() -> list[str]:
    max_seeds = int(os.getenv("JOB_SCRAPE_MAX_SEEDS", str(DEFAULT_MAX_SEEDS)))
    value = os.getenv("JOB_SCRAPE_SEEDS", "")
    if value.strip():
        cleaned = [seed.strip() for seed in value.split(",") if seed.strip()]
        return cleaned[:max_seeds]
    return DEFAULT_SEEDS[:max_seeds]


def _extract_greenhouse_board_token(seed_url: str) -> str | None:
    parsed = urlparse(seed_url)
    query = parse_qs(parsed.query)
    if query.get("for"):
        return query["for"][0]

    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower().startswith("boards-api.greenhouse.io"):
        try:
            idx = parts.index("boards")
            return parts[idx + 1]
        except (ValueError, IndexError):
            return None
    return parts[0] if parts else None


def _extract_lever_site_token(seed_url: str) -> str | None:
    parsed = urlparse(seed_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower().startswith("api.lever.co"):
        if len(parts) >= 3 and parts[0] == "v0" and parts[1] == "postings":
            return parts[2]
        return None
    return parts[0] if parts else None


def _fetch_greenhouse_jobs(session: Any, seed_url: str) -> list[dict[str, Any]]:
    board = _extract_greenhouse_board_token(seed_url)
    if not board:
        print(f"[greenhouse] Could not parse board token from seed: {seed_url}")
        return []
    response = session.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    scraped_at = datetime.utcnow().isoformat()
    jobs: list[dict[str, Any]] = []
    for job in data.get("jobs", []):
        source_url = job.get("absolute_url") or job.get("url")
        if not source_url:
            continue
        location_obj = job.get("location") or {}
        location = (
            location_obj.get("name")
            if isinstance(location_obj, dict)
            else str(location_obj or "")
        )
        company = (
            job.get("company")
            or job.get("company_name")
            or data.get("name")
            or _humanize_name(board)
        )
        jobs.append(
            {
                "title": (job.get("title") or "").strip(),
                "company": company,
                "location": location or None,
                "description": _html_to_text(job.get("content") or ""),
                "source_url": source_url,
                "source_platform": "greenhouse",
                "scraped_at": scraped_at,
            }
        )
    print(f"[greenhouse] {board}: scraped {len(jobs)} jobs")
    return jobs


def _fetch_lever_jobs(session: Any, seed_url: str) -> list[dict[str, Any]]:
    site = _extract_lever_site_token(seed_url)
    if not site:
        print(f"[lever] Could not parse site token from seed: {seed_url}")
        return []
    response = session.get(
        f"https://api.lever.co/v0/postings/{site}?mode=json", timeout=30
    )
    response.raise_for_status()
    postings = response.json()

    scraped_at = datetime.utcnow().isoformat()
    jobs: list[dict[str, Any]] = []
    for posting in postings:
        source_url = posting.get("hostedUrl") or posting.get("applyUrl")
        if not source_url:
            continue
        categories = posting.get("categories") or {}
        description_chunks: list[str] = []
        if posting.get("description"):
            description_chunks.append(posting["description"])
        if posting.get("descriptionPlain"):
            description_chunks.append(posting["descriptionPlain"])
        if isinstance(posting.get("lists"), list):
            for section in posting["lists"]:
                content = section.get("content") if isinstance(section, dict) else ""
                if content:
                    description_chunks.append(content)
        jobs.append(
            {
                "title": (posting.get("text") or "").strip(),
                "company": posting.get("company") or _humanize_name(site),
                "location": categories.get("location"),
                "description": _html_to_text("\n".join(description_chunks)),
                "source_url": source_url,
                "source_platform": "lever",
                "scraped_at": scraped_at,
            }
        )
    print(f"[lever] {site}: scraped {len(jobs)} jobs")
    return jobs


def _scrape_all_jobs() -> list[dict[str, Any]]:
    import requests

    seeds = _get_seed_urls()
    print(f"[scrape_all_jobs] Using {len(seeds)} seed(s)")
    all_jobs: list[dict[str, Any]] = []
    seen: set[str] = set()

    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "jobzilla-airflow-scraper/1.0", "Accept": "application/json"}
        )
        for seed in seeds:
            netloc = urlparse(seed).netloc.lower()
            try:
                if "greenhouse" in netloc:
                    jobs = _fetch_greenhouse_jobs(session, seed)
                elif "lever.co" in netloc:
                    jobs = _fetch_lever_jobs(session, seed)
                else:
                    print(f"[scrape_all_jobs] Unsupported seed, skipping: {seed}")
                    continue
            except Exception as exc:
                print(f"[scrape_all_jobs] Error scraping seed '{seed}': {exc}")
                continue

            for job in jobs:
                source_url = (job.get("source_url") or "").strip()
                if source_url and source_url not in seen:
                    seen.add(source_url)
                    all_jobs.append(job)

    print(f"[scrape_all_jobs] Total unique jobs scraped: {len(all_jobs)}")
    return all_jobs


def _parse_scraped_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    return datetime.utcnow()


def _get_conn_string() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return (
            url.replace("+asyncpg", "")
            .replace("+psycopg2", "")
            .replace("postgres://", "postgresql://")
        )

    host = os.getenv("DB_HOST", os.getenv("PGHOST", "localhost"))
    port = os.getenv("DB_PORT", os.getenv("PGPORT", "5432"))
    name = os.getenv("DB_NAME", os.getenv("PGDATABASE", "killmatch"))
    user = os.getenv("DB_USER", os.getenv("PGUSER", "postgres"))
    password = os.getenv("DB_PASSWORD", os.getenv("PGPASSWORD", "postgres"))
    return f"dbname={name} user={user} password={password} host={host} port={port}"


def _upsert_jobs(jobs: list[dict[str, Any]]) -> dict[str, int]:
    import psycopg2

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in jobs:
        source_url = (job.get("source_url") or "").strip()
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        deduped.append(
            {
                "title": (
                    (job.get("title") or "Untitled Role").strip() or "Untitled Role"
                )[:500],
                "company": (
                    (job.get("company") or "Unknown Company").strip()
                    or "Unknown Company"
                )[:255],
                "location": (
                    str(job.get("location")).strip()[:255]
                    if job.get("location")
                    else None
                ),
                "description": job.get("description") or "",
                "source_url": source_url[:1000],
                "source_platform": (
                    (job.get("source_platform") or "unknown").strip() or "unknown"
                )[:100],
                "scraped_at": _parse_scraped_at(job.get("scraped_at")),
            }
        )

    if not deduped:
        print("[upsert_jobs] No valid jobs to ingest.")
        return {"inserted": 0, "updated": 0}

    upsert_sql = """
        INSERT INTO jobs (
            title, company, location, description, source_url, source_platform, scraped_at, is_active
        )
        VALUES (
            %(title)s, %(company)s, %(location)s, %(description)s, %(source_url)s, %(source_platform)s, %(scraped_at)s, true
        )
        ON CONFLICT (source_url)
        DO UPDATE SET
            title = EXCLUDED.title,
            company = EXCLUDED.company,
            location = EXCLUDED.location,
            description = EXCLUDED.description,
            source_platform = EXCLUDED.source_platform,
            scraped_at = EXCLUDED.scraped_at,
            is_active = true
        RETURNING (xmax = 0) AS inserted;
    """

    inserted = 0
    updated = 0
    conn = psycopg2.connect(_get_conn_string())
    try:
        with conn, conn.cursor() as cur:
            for job in deduped:
                cur.execute(upsert_sql, job)
                if bool(cur.fetchone()[0]):
                    inserted += 1
                else:
                    updated += 1
    finally:
        conn.close()

    print(
        f"[upsert_jobs] input={len(jobs)} normalized={len(deduped)} inserted={inserted} updated={updated}"
    )
    return {"inserted": inserted, "updated": updated}


def scrape_jobs_task(**context) -> int:
    jobs = _scrape_all_jobs()
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", context["run_id"])
    output_path = Path(f"/tmp/job_scrape_{run_id}.json")
    output_path.write_text(json.dumps(jobs), encoding="utf-8")
    context["ti"].xcom_push(key="scraped_jobs_path", value=str(output_path))
    print(f"[scrape_jobs_task] Number of jobs scraped: {len(jobs)}")
    print(f"[scrape_jobs_task] Wrote scrape payload: {output_path}")
    return len(jobs)


def ingest_jobs_task(**context) -> int:
    payload_path = context["ti"].xcom_pull(
        task_ids="scrape_jobs", key="scraped_jobs_path"
    )
    if not payload_path:
        raise ValueError("Missing scraped_jobs_path in XCom")
    jobs = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    print(f"[ingest_jobs_task] Number of jobs received from scrape task: {len(jobs)}")
    stats = _upsert_jobs(jobs)
    print(
        f"[ingest_jobs_task] inserted={stats.get('inserted', 0)} updated={stats.get('updated', 0)}"
    )
    return int(stats.get("inserted", 0)) + int(stats.get("updated", 0))


scrape_jobs = PythonOperator(
    task_id="scrape_jobs",
    python_callable=scrape_jobs_task,
    dag=dag,
)

ingest_jobs = PythonOperator(
    task_id="ingest_jobs",
    python_callable=ingest_jobs_task,
    dag=dag,
)

scrape_jobs >> ingest_jobs

# Local test commands:
# export JOB_SCRAPE_SEEDS="https://boards.greenhouse.io/openai,https://jobs.lever.co/figma"
# export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/killmatch"
# python scripts/scrape_jobs_bs_only.py
# python scripts/ingest_jobs_to_db.py
# airflow dags test job_scrape_ingest_daily 2026-02-19
