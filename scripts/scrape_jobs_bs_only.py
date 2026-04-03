"""
Scrape jobs from Greenhouse and Lever using requests + BeautifulSoup only.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_SEEDS = [
    "https://boards.greenhouse.io/openai",
    "https://boards.greenhouse.io/stripe",
    "https://jobs.lever.co/figma",
    "https://jobs.lever.co/netflix",
]
DEFAULT_MAX_SEEDS = 500


def _html_to_text(html: str | None) -> str:
    """Convert HTML to readable text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _humanize_name(raw: str) -> str:
    """Convert token-like names to a readable company name."""
    return re.sub(r"\s{2,}", " ", raw.replace("-", " ").replace("_", " ")).strip().title()


def _get_seed_urls(seed_urls: list[str] | None = None) -> list[str]:
    max_seeds = int(os.getenv("JOB_SCRAPE_MAX_SEEDS", str(DEFAULT_MAX_SEEDS)))
    if seed_urls:
        cleaned = [seed.strip() for seed in seed_urls if seed and seed.strip()]
        return cleaned[:max_seeds]

    env_value = os.getenv("JOB_SCRAPE_SEEDS", "")
    if env_value.strip():
        cleaned = [seed.strip() for seed in env_value.split(",") if seed.strip()]
        return cleaned[:max_seeds]

    return DEFAULT_SEEDS[:max_seeds]


def _detect_platform(seed_url: str) -> str:
    netloc = urlparse(seed_url).netloc.lower()
    if "greenhouse" in netloc:
        return "greenhouse"
    if "lever.co" in netloc:
        return "lever"
    return "unknown"


def _extract_greenhouse_board_token(seed_url: str) -> str | None:
    parsed = urlparse(seed_url)
    query = parse_qs(parsed.query)
    if query.get("for"):
        return query["for"][0]

    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower().startswith("boards-api.greenhouse.io"):
        # /v1/boards/<board>/jobs
        try:
            boards_index = parts.index("boards")
            return parts[boards_index + 1]
        except (ValueError, IndexError):
            return None

    if parts:
        return parts[0]
    return None


def _extract_lever_site_token(seed_url: str) -> str | None:
    parsed = urlparse(seed_url)
    parts = [part for part in parsed.path.split("/") if part]

    if parsed.netloc.lower().startswith("api.lever.co"):
        # /v0/postings/<site>
        if len(parts) >= 3 and parts[0] == "v0" and parts[1] == "postings":
            return parts[2]
        return None

    if parts:
        return parts[0]
    return None


def _fetch_greenhouse_jobs(session: requests.Session, seed_url: str) -> list[dict[str, Any]]:
    board = _extract_greenhouse_board_token(seed_url)
    if not board:
        print(f"[greenhouse] Could not parse board token from seed: {seed_url}")
        return []

    endpoint = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    response = session.get(endpoint, timeout=30)
    response.raise_for_status()
    data = response.json()

    scraped_at = datetime.utcnow().isoformat()
    jobs: list[dict[str, Any]] = []
    for job in data.get("jobs", []):
        source_url = job.get("absolute_url") or job.get("url")
        if not source_url:
            continue

        location_obj = job.get("location") or {}
        if isinstance(location_obj, dict):
            location = location_obj.get("name")
        else:
            location = str(location_obj) if location_obj else None

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
                "location": location,
                "description": _html_to_text(job.get("content") or ""),
                "source_url": source_url,
                "source_platform": "greenhouse",
                "scraped_at": scraped_at,
            }
        )

    print(f"[greenhouse] {board}: scraped {len(jobs)} jobs")
    return jobs


def _fetch_lever_jobs(session: requests.Session, seed_url: str) -> list[dict[str, Any]]:
    site = _extract_lever_site_token(seed_url)
    if not site:
        print(f"[lever] Could not parse site token from seed: {seed_url}")
        return []

    endpoint = f"https://api.lever.co/v0/postings/{site}?mode=json"
    response = session.get(endpoint, timeout=30)
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

        description = _html_to_text("\n".join(description_chunks))
        company = posting.get("company") or _humanize_name(site)

        jobs.append(
            {
                "title": (posting.get("text") or "").strip(),
                "company": company,
                "location": categories.get("location"),
                "description": description,
                "source_url": source_url,
                "source_platform": "lever",
                "scraped_at": scraped_at,
            }
        )

    print(f"[lever] {site}: scraped {len(jobs)} jobs")
    return jobs


def scrape_all_jobs(seed_urls: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Scrape jobs from Greenhouse and Lever boards.

    Returns a list of normalized job dictionaries.
    """
    seeds = _get_seed_urls(seed_urls)
    print(f"[scrape_all_jobs] Using {len(seeds)} seed(s)")

    all_jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": "jobzilla-airflow-scraper/1.0",
                "Accept": "application/json",
            }
        )

        for seed in seeds:
            platform = _detect_platform(seed)
            try:
                if platform == "greenhouse":
                    jobs = _fetch_greenhouse_jobs(session, seed)
                elif platform == "lever":
                    jobs = _fetch_lever_jobs(session, seed)
                else:
                    print(f"[scrape_all_jobs] Unsupported seed, skipping: {seed}")
                    continue
            except Exception as exc:
                print(f"[scrape_all_jobs] Error scraping seed '{seed}': {exc}")
                continue

            for job in jobs:
                source_url = (job.get("source_url") or "").strip()
                if not source_url or source_url in seen_urls:
                    continue
                seen_urls.add(source_url)
                all_jobs.append(job)

    print(f"[scrape_all_jobs] Total unique jobs scraped: {len(all_jobs)}")
    return all_jobs


if __name__ == "__main__":
    jobs = scrape_all_jobs()
    print(f"[main] Scraped {len(jobs)} jobs")

# Local test commands:
# export JOB_SCRAPE_SEEDS="https://boards.greenhouse.io/openai,https://jobs.lever.co/figma"
# export JOB_SCRAPE_MAX_SEEDS="500"
# python scripts/scrape_jobs_bs_only.py
