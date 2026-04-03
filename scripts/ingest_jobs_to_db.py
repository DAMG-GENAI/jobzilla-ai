"""
Insert/upsert scraped jobs into Postgres in an idempotent way.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import psycopg2


def _get_db_conn_string() -> str:
    """
    Build a Postgres connection string from existing project env vars.
    Priority:
    1) DATABASE_URL
    2) DB_* vars used in repo
    3) Standard PG* vars
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return (
            database_url.replace("+asyncpg", "").replace("+psycopg2", "").replace("postgres://", "postgresql://")
        )

    host = os.getenv("DB_HOST", os.getenv("PGHOST", "localhost"))
    port = os.getenv("DB_PORT", os.getenv("PGPORT", "5432"))
    name = os.getenv("DB_NAME", os.getenv("PGDATABASE", "killmatch"))
    user = os.getenv("DB_USER", os.getenv("PGUSER", "postgres"))
    password = os.getenv("DB_PASSWORD", os.getenv("PGPASSWORD", "postgres"))

    return f"dbname={name} user={user} password={password} host={host} port={port}"


def _parse_scraped_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if not value:
        return datetime.utcnow()

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return datetime.utcnow()

    return datetime.utcnow()


def _normalize_jobs(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    dropped = 0

    for job in jobs:
        source_url = (job.get("source_url") or "").strip()
        if not source_url or source_url in seen:
            dropped += 1
            continue
        seen.add(source_url)

        title = (job.get("title") or "Untitled Role").strip()[:500]
        company = (job.get("company") or "Unknown Company").strip()[:255]
        location = (job.get("location") or None)
        platform = (job.get("source_platform") or "unknown").strip()[:100]

        if not title:
            title = "Untitled Role"
        if not company:
            company = "Unknown Company"
        if location is not None:
            location = str(location).strip()[:255] or None
        if not platform:
            platform = "unknown"

        normalized.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "description": (job.get("description") or ""),
                "source_url": source_url[:1000],
                "source_platform": platform,
                "scraped_at": _parse_scraped_at(job.get("scraped_at")),
            }
        )

    return normalized, dropped


def _chunks(values: list[str], chunk_size: int = 500) -> list[list[str]]:
    return [values[i : i + chunk_size] for i in range(0, len(values), chunk_size)]


def upsert_jobs(jobs: list[dict[str, Any]]) -> dict[str, int]:
    """
    Upsert jobs by source_url.
    Falls back to insert-only dedupe if source_url unique constraint is unavailable.
    """
    normalized_jobs, dropped_count = _normalize_jobs(jobs)
    if not normalized_jobs:
        print("[upsert_jobs] No valid jobs to ingest.")
        return {
            "input": len(jobs),
            "normalized": 0,
            "dropped": dropped_count,
            "inserted": 0,
            "updated": 0,
        }

    conn_string = _get_db_conn_string()
    conn = psycopg2.connect(conn_string)

    inserted = 0
    updated = 0

    upsert_sql = """
        INSERT INTO jobs (
            title,
            company,
            location,
            description,
            source_url,
            source_platform,
            scraped_at,
            is_active
        )
        VALUES (
            %(title)s,
            %(company)s,
            %(location)s,
            %(description)s,
            %(source_url)s,
            %(source_platform)s,
            %(scraped_at)s,
            true
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

    fallback_insert_sql = """
        INSERT INTO jobs (
            title,
            company,
            location,
            description,
            source_url,
            source_platform,
            scraped_at,
            is_active
        )
        VALUES (
            %(title)s,
            %(company)s,
            %(location)s,
            %(description)s,
            %(source_url)s,
            %(source_platform)s,
            %(scraped_at)s,
            true
        );
    """

    try:
        with conn, conn.cursor() as cur:
            try:
                for job in normalized_jobs:
                    cur.execute(upsert_sql, job)
                    was_inserted = bool(cur.fetchone()[0])
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
            except Exception as upsert_error:
                message = str(upsert_error).lower()
                requires_fallback = "no unique or exclusion constraint matching the on conflict specification" in message
                if not requires_fallback:
                    raise

                print(
                    "[upsert_jobs] source_url upsert constraint unavailable, "
                    "falling back to code-level dedupe insert."
                )
                conn.rollback()

                with conn, conn.cursor() as fallback_cur:
                    urls = [job["source_url"] for job in normalized_jobs]
                    existing_urls: set[str] = set()
                    for batch in _chunks(urls):
                        fallback_cur.execute(
                            "SELECT source_url FROM jobs WHERE source_url = ANY(%s)",
                            (batch,),
                        )
                        existing_urls.update(row[0] for row in fallback_cur.fetchall() if row[0])

                    new_jobs = [job for job in normalized_jobs if job["source_url"] not in existing_urls]
                    for job in new_jobs:
                        fallback_cur.execute(fallback_insert_sql, job)

                    inserted = len(new_jobs)
                    updated = 0
    finally:
        conn.close()

    print(
        f"[upsert_jobs] input={len(jobs)} normalized={len(normalized_jobs)} "
        f"dropped={dropped_count} inserted={inserted} updated={updated}"
    )
    return {
        "input": len(jobs),
        "normalized": len(normalized_jobs),
        "dropped": dropped_count,
        "inserted": inserted,
        "updated": updated,
    }


def main() -> None:
    # Local convenience runner: scrape then ingest.
    from scrape_jobs_bs_only import scrape_all_jobs

    jobs = scrape_all_jobs()
    stats = upsert_jobs(jobs)
    print(f"[main] Final ingest stats: {stats}")


if __name__ == "__main__":
    main()

# Local test commands:
# export JOB_SCRAPE_SEEDS="https://boards.greenhouse.io/openai,https://jobs.lever.co/figma"
# export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/killmatch"
# python scripts/ingest_jobs_to_db.py
