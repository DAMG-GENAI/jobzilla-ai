"""
Match Route

Trigger the agent pipeline for job-resume matching.
"""

import os
import uuid

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from openai import OpenAI
from pinecone import Pinecone

from app.services.resume_parser import parse_resume
from app.services.s3_storage import upload_parsed_resume, upload_resume

# GitHub MCP Server URL
GITHUB_MCP_URL = os.getenv("MCP_GITHUB_SERVER_URL", "http://mcp-github:8001")

router = APIRouter()

# Initialize clients (safe - won't crash if keys are missing)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX_NAME", "killmatch-jobs")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)
except Exception as e:
    print(f"⚠️ Pinecone init failed (will use fallback): {e}")
    pc = None
    index = None

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def get_embedding(text: str) -> list[float]:
    """Get embedding for text using OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],  # Truncate to avoid token limits
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return [0.0] * 1536


def extract_skills_with_llm(text: str, max_skills: int = 10) -> list[str]:
    """
    Extract required skills from job description using LLM.
    This is dynamic - no hardcoded skill list needed.
    """
    if not text or len(text.strip()) < 50:
        return []

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical recruiter. Extract the key technical skills, tools, and technologies required for a job. Return ONLY a comma-separated list of skills, nothing else. Focus on: programming languages, frameworks, tools, cloud platforms, databases, and methodologies.",
                },
                {
                    "role": "user",
                    "content": f"Extract the top {max_skills} required skills from this job description:\n\n{text[:2000]}",
                },
            ],
            temperature=0,
            max_tokens=200,
        )

        skills_text = response.choices[0].message.content.strip()
        # Parse comma-separated list
        skills = [s.strip() for s in skills_text.split(",") if s.strip()]
        return skills[:max_skills]

    except Exception as e:
        print(f"LLM skill extraction failed: {e}")
        return []


@router.post("/match")
async def match_jobs(
    query: str | None = Form(None),
    location: str | None = Form(None),
    level: str | None = Form(None),
    github_username: str | None = Form(None),
    num_results: int = Form(10),
    resume: UploadFile | None = File(None),
):
    """
    Match jobs using semantic search + fields.

    1. Parse resume (if provided)
    2. Create embedding from resume + query
    3. Query Pinecone for semantic matches
    4. Return ranked jobs with skill gaps
    """
    try:
        # 1. Parse Resume
        resume_text = ""
        skills = []

        if resume:
            if not resume.filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400, detail="Only PDF resumes are supported"
                )

            content = await resume.read()

            # Upload to S3 for persistent storage (non-critical, skip on failure)
            user_id = str(uuid.uuid4())[:8]  # Generate temporary user ID
            try:
                s3_result = await upload_resume(
                    user_id=user_id,
                    file_content=content,
                    filename=resume.filename,
                    content_type="application/pdf",
                )
                if s3_result.get("success"):
                    print(f"✅ Resume uploaded to S3: {s3_result.get('s3_key')}")
                else:
                    print(
                        f"⚠️ S3 upload failed (continuing without): {s3_result.get('error', 'Unknown error')}"
                    )
            except Exception as s3_err:
                print(f"⚠️ S3 unavailable (continuing without): {s3_err}")
                s3_result = {"success": False}

            # Use our existing service to parse (returns ResumeData model)
            resume_data = await parse_resume(content)

            # Upload parsed data to S3 as well (non-critical)
            if s3_result.get("success"):
                try:
                    parsed_s3 = await upload_parsed_resume(
                        user_id=user_id,
                        parsed_data=(
                            resume_data.model_dump()
                            if hasattr(resume_data, "model_dump")
                            else {}
                        ),
                    )
                    if parsed_s3.get("success"):
                        print(
                            f"✅ Parsed resume saved to S3: {parsed_s3.get('s3_key')}"
                        )
                except Exception as s3_err:
                    print(f"⚠️ S3 parsed upload failed (continuing): {s3_err}")

            # Extract text for embedding - skills are Skill objects, extract names
            skill_names = [
                s.name if hasattr(s, "name") else str(s)
                for s in (resume_data.skills or [])
            ]
            resume_text = f"{resume_data.summary or ''} {' '.join(skill_names)} "
            for exp in resume_data.experience or []:
                resume_text += f"{exp.title} {exp.company} {exp.description or ''} "

            skills = skill_names  # Use string skill names, not Skill objects

        # 2. Fetch GitHub profile for additional context
        github_context = ""
        if github_username:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{GITHUB_MCP_URL}/tools/get_user_repos",
                        json={"username": github_username},
                    )
                    if response.status_code == 200:
                        github_data = response.json()
                        repos = github_data.get("repos", [])[:5]  # Top 5 repos
                        languages = set()
                        topics = set()
                        for repo in repos:
                            if repo.get("language"):
                                languages.add(repo["language"])
                            topics.update(repo.get("topics", []))

                        github_context = f" GitHub skills: {', '.join(languages)}. "
                        github_context += f"Projects: {', '.join(topics)}. "
                        print(
                            f"✅ GitHub profile fetched for {github_username}: {len(repos)} repos"
                        )
            except Exception as e:
                print(f"⚠️ GitHub fetch failed (continuing without): {e}")

        # 3. Create Embedding Context
        # Combine user query with resume text and GitHub context
        search_context = f"{query or ''} {level or ''} {location or ''}"
        if resume_text:
            search_context += (
                f" Skills: {', '.join(skills[:20])}. Experience: {resume_text[:1000]}"
            )
        if github_context:
            search_context += github_context

        print(f"Generating embedding for context depth: {len(search_context)}")

        # Get embedding vector
        query_vector = get_embedding(search_context)

        # 3. Query Pinecone (with database fallback if Pinecone is unreachable)
        matches = []
        try:
            if index is None:
                raise Exception("Pinecone not initialized")

            search_results = index.query(
                vector=query_vector, top_k=200, include_metadata=True
            )

            # Build matches without LLM calls first (fast)
            all_matches = []
            for match in search_results.matches:
                metadata = match.metadata or {}
                if not metadata.get("title"):
                    continue

                all_matches.append(
                    {
                        "id": str(metadata.get("job_id", match.id)),
                        "title": metadata.get("title", "Unknown Role"),
                        "company": metadata.get("company", "Unknown Company"),
                        "description": metadata.get("description", "") or "",
                        "url": metadata.get("url", ""),
                        "source": metadata.get("source", ""),
                        "match_score": match.score,
                        "recruiter_concerns": [],
                        "coach_highlights": [],
                        "missing_skills": [],
                    }
                )

            # Diversify: max 2 jobs per company
            company_count = {}
            for m in all_matches:
                company = m["company"]
                company_count[company] = company_count.get(company, 0) + 1
                if company_count[company] <= 2:
                    matches.append(m)
                if len(matches) >= num_results:
                    break

            # Now extract skills only for the requested number
            resume_skills_lower = {s.lower() for s in skills if s}
            for m in matches:
                try:
                    full_text = f"{m['title']}\n\n{m['description']}"
                    job_skills = set(extract_skills_with_llm(full_text, max_skills=10))
                    job_skills_lower = {s.lower() for s in job_skills if s}
                    missing = job_skills_lower - resume_skills_lower
                    m["missing_skills"] = [
                        s for s in job_skills if s.lower() in missing
                    ][:5]
                except Exception:
                    pass

            print(f"✅ Pinecone returned {len(matches)} matches")

            # Enrich matches with source_url from DB if missing
            if matches:
                try:
                    from sqlalchemy import create_engine
                    from sqlalchemy import text as sql_text

                    db_url = os.getenv("DATABASE_URL", "")
                    db_url = db_url.replace("+asyncpg", "+psycopg2")
                    engine = create_engine(db_url)
                    missing_url_ids = [m["id"] for m in matches if not m.get("url")]
                    if missing_url_ids:
                        with engine.connect() as conn:
                            result = conn.execute(
                                sql_text(
                                    "SELECT id, source_url, title FROM jobs WHERE id = ANY(:ids)"
                                ),
                                {"ids": missing_url_ids},
                            )
                            url_map = {}
                            for row in result:
                                url_map[str(row[0])] = {
                                    "url": row[1] or "",
                                    "title": row[2] or "",
                                }
                            for m in matches:
                                if m["id"] in url_map:
                                    db_url_val = url_map[m["id"]]["url"]
                                    # Only use real URLs, not generic search pages
                                    if db_url_val and "jobs/search" not in db_url_val:
                                        m["url"] = db_url_val
                                    if url_map[m["id"]]["title"]:
                                        m["title"] = url_map[m["id"]]["title"]
                        print(
                            f"✅ Enriched {len(missing_url_ids)} matches with DB urls"
                        )
                except Exception as enrich_err:
                    print(f"⚠️ URL enrichment failed: {enrich_err}")

        except Exception as pinecone_err:
            print(
                f"⚠️ Pinecone query failed (falling back to database): {pinecone_err}"
            )

            # Fallback: query PostgreSQL database directly
            try:
                from sqlalchemy import create_engine
                from sqlalchemy import text as sql_text

                db_url = os.getenv("DATABASE_URL", "")
                if not db_url:
                    raise ValueError("DATABASE_URL is not set")
                db_url = db_url.replace("+asyncpg", "+psycopg2")
                engine = create_engine(db_url)

                search_terms = (query or "software engineer").split()
                like_clauses = " OR ".join(
                    [
                        f"LOWER(title) LIKE :term{i} OR LOWER(description) LIKE :term{i}"
                        for i in range(len(search_terms))
                    ]
                )
                params = {
                    f"term{i}": f"%{term.lower()}%"
                    for i, term in enumerate(search_terms)
                }

                with engine.connect() as conn:
                    result = conn.execute(
                        sql_text(
                            f"SELECT id, title, company, description, source_platform, source_url FROM jobs WHERE ({like_clauses}) AND is_active = true LIMIT {num_results}"
                        ),
                        params,
                    )

                    for row in result:
                        job_match = {
                            "id": str(row[0]),
                            "title": row[1] or "Unknown Role",
                            "company": row[2] or "Unknown Company",
                            "description": row[3] or "",
                            "url": row[5] or "",
                            "source": row[4] or "Database",
                            "match_score": 0.75,
                            "recruiter_concerns": [],
                            "coach_highlights": [],
                            "missing_skills": [],
                        }
                        matches.append(job_match)

                print(f"✅ Database fallback returned {len(matches)} matches")

            except Exception as db_err:
                print(f"⚠️ Database fallback also failed: {db_err}")

            if not matches:
                print("⚠️ No matches found from Pinecone or database")

        return {
            "matches": matches,
            "count": len(matches),
            "parsed_skills": [s for s in skills if s],
            "resume_summary": resume_text[:3000] if resume_text else "",
        }

    except Exception as e:
        print(f"Error in match_jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
