"""
Analytics Route

Real analytics from Cloud SQL database.
"""

import os
from collections import Counter
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import create_engine, text

router = APIRouter()


def _get_engine():
    db_url = os.getenv("DATABASE_URL", "")
    db_url = db_url.replace("+asyncpg", "+psycopg2")
    return create_engine(db_url)


@router.get("/analytics/system")
async def get_system_metrics():
    """Real system-wide analytics from the database."""
    engine = _get_engine()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    with engine.connect() as conn:
        # Total jobs
        total_jobs = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE is_active = true")
        ).scalar()

        # Jobs added today
        jobs_today = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE scraped_at >= :today"),
            {"today": today_start},
        ).scalar()

        # Jobs by source platform
        source_rows = conn.execute(
            text(
                "SELECT COALESCE(source_platform, 'Unknown'), COUNT(*) "
                "FROM jobs WHERE is_active = true "
                "GROUP BY source_platform ORDER BY COUNT(*) DESC"
            )
        ).fetchall()
        jobs_by_source = {row[0]: row[1] for row in source_rows}

        # Total users
        total_users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()

        # Top hiring companies
        company_rows = conn.execute(
            text(
                "SELECT company, COUNT(*) as cnt FROM jobs "
                "WHERE is_active = true AND company IS NOT NULL "
                "GROUP BY company ORDER BY cnt DESC LIMIT 10"
            )
        ).fetchall()
        top_companies = [row[0] for row in company_rows]

        # Most common job titles (cleaned)
        title_rows = conn.execute(
            text(
                "SELECT title FROM jobs WHERE is_active = true "
                "ORDER BY scraped_at DESC LIMIT 1000"
            )
        ).fetchall()
        title_keywords = Counter()
        for row in title_rows:
            title = row[0] or ""
            for keyword in [
                "Software Engineer",
                "Data Scientist",
                "Machine Learning",
                "Product Manager",
                "Data Engineer",
                "Frontend",
                "Backend",
                "Full Stack",
                "DevOps",
                "AI Engineer",
            ]:
                if keyword.lower() in title.lower():
                    title_keywords[keyword] += 1
        top_titles = [k for k, _ in title_keywords.most_common(5)]

        # Most in-demand skills from job descriptions
        skill_rows = conn.execute(
            text(
                "SELECT description FROM jobs WHERE is_active = true "
                "AND description IS NOT NULL AND description != '' "
                "ORDER BY scraped_at DESC LIMIT 500"
            )
        ).fetchall()
        import re

        skill_counter = Counter()
        safe_skills = [
            "Python",
            "SQL",
            "AWS",
            "Docker",
            "Kubernetes",
            "React",
            "TypeScript",
            "Java",
            "TensorFlow",
            "PyTorch",
            "Spark",
            "Airflow",
            "PostgreSQL",
            "MongoDB",
            "Redis",
            "Machine Learning",
            "NLP",
            "Kafka",
            "CI/CD",
        ]
        boundary_skills = {"Go": r"\bgo\b(?:lang)?", "REST": r"\bREST\s?(?:ful|API)\b"}
        for row in skill_rows:
            desc = (row[0] or "").lower()
            for skill in safe_skills:
                if skill.lower() in desc:
                    skill_counter[skill] += 1
            for skill_name, pattern in boundary_skills.items():
                if re.search(pattern, row[0] or "", re.IGNORECASE):
                    skill_counter[skill_name] += 1
        top_skills = [k for k, _ in skill_counter.most_common(10)]

        # Jobs with embeddings (searchable)
        embedded_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM jobs WHERE embedding_id IS NOT NULL AND is_active = true"
            )
        ).scalar()

    return {
        "generated_at": now.isoformat(),
        "total_users": total_users or 0,
        "total_jobs_indexed": total_jobs or 0,
        "jobs_added_today": jobs_today or 0,
        "jobs_searchable": embedded_count or 0,
        "jobs_by_source": jobs_by_source,
        "top_hiring_companies": top_companies,
        "most_common_job_titles": top_titles,
        "most_in_demand_skills": top_skills,
    }


@router.get("/analytics/skills/trends")
async def get_skill_trends(skills: str | None = None):
    """Real skill demand trends from job descriptions."""
    engine = _get_engine()

    with engine.connect() as conn:
        # Get recent job descriptions
        rows = conn.execute(
            text(
                "SELECT title, description, scraped_at FROM jobs "
                "WHERE is_active = true AND description IS NOT NULL "
                "ORDER BY scraped_at DESC LIMIT 1000"
            )
        ).fetchall()

    skill_list = (
        skills.split(",")
        if skills
        else [
            "Python",
            "SQL",
            "AWS",
            "Docker",
            "Kubernetes",
            "React",
            "TypeScript",
            "Java",
            "Go",
            "TensorFlow",
        ]
    )

    trends = []
    for skill in skill_list:
        skill_clean = skill.strip()
        count = sum(
            1
            for r in rows
            if skill_clean.lower() in ((r[1] or "") + " " + (r[0] or "")).lower()
        )
        pct = round((count / len(rows)) * 100, 1) if rows else 0

        if pct >= 15:
            demand = "Very High"
        elif pct >= 8:
            demand = "High"
        elif pct >= 3:
            demand = "Medium"
        else:
            demand = "Low"

        trends.append(
            {
                "skill": skill_clean,
                "mentions": count,
                "percentage": pct,
                "demand": demand,
            }
        )

    trends.sort(key=lambda x: x["mentions"], reverse=True)

    return {
        "total_jobs_analyzed": len(rows),
        "skills": trends,
    }


@router.get("/analytics/{user_id}")
async def get_user_analytics(user_id: str):
    """Real user analytics from the database."""
    engine = _get_engine()

    with engine.connect() as conn:
        # Get user
        user = conn.execute(
            text("SELECT id, name, email FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()

        # Get user's matches
        matches = conn.execute(
            text(
                "SELECT overall_score, skill_match_score, experience_match_score, "
                "debate_summary, created_at FROM job_matches "
                "WHERE user_id = :uid ORDER BY created_at DESC"
            ),
            {"uid": user_id},
        ).fetchall()

        # Get user's resumes
        resume_count = conn.execute(
            text("SELECT COUNT(*) FROM resumes WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar()

        # Get user's cover letters
        cover_letter_count = conn.execute(
            text("SELECT COUNT(*) FROM cover_letters WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar()

    total = len(matches)
    scores = [m[0] for m in matches if m[0] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    best_score = round(max(scores), 1) if scores else 0

    return {
        "user_id": user_id,
        "user_name": user[1] if user else "Unknown",
        "generated_at": datetime.utcnow().isoformat(),
        "total_jobs_analyzed": total,
        "avg_match_score": avg_score,
        "best_match_score": best_score,
        "resumes_uploaded": resume_count or 0,
        "cover_letters_generated": cover_letter_count or 0,
    }
