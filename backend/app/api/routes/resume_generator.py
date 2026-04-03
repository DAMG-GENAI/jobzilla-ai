"""
Resume Generator Route

Accept a master resume PDF + job description, then:
1. Parse the PDF into structured ResumeData.
2. Generate an ATS-optimized, 1-page tailored resume via LLM.
3. Compute an ATS compatibility score against the job description.
4. Return the resume as Markdown + PDF (base64) + ATS score.
"""

import base64
import json
import re
from typing import Optional

import google.generativeai as genai
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.nodes.resume_generator import generate_resume
from app.core.config import settings
from app.models import JobListing, ResumeData
from app.services.pdf_utils import markdown_to_pdf
from app.services.resume_parser import extract_text_from_pdf, parse_resume

router = APIRouter()


class ATSScore(BaseModel):
    overall: int                   # 0-100
    keyword_match: int             # % of JD keywords found in resume
    matched_keywords: list[str]
    missing_keywords: list[str]
    feedback: list[str]


class GeminiReview(BaseModel):
    ats_score: int                 # 0-100, Gemini's holistic ATS assessment
    bullet_quality_score: int      # 0-100, strength of action verbs + metrics
    jd_alignment_score: int        # 0-100, semantic match with job description
    strengths: list[str]           # What the resume does well
    weaknesses: list[str]          # Issues found
    suggestions: list[str]         # Specific improvements
    verdict: str                   # "Pass" | "Needs Work" | "Fail"
    skipped: bool = False          # True if Gemini key not configured


class ResumeGeneratorResponse(BaseModel):
    resume_markdown: str
    word_count: int
    assumptions_made: list[str]
    candidate_name: str
    pdf_base64: str
    original_ats_score: ATSScore
    tailored_ats_score: ATSScore
    changes_made: list[str]        # Summary of changes from original
    gemini_review: GeminiReview


# ── ATS scoring ────────────────────────────────────────────────────────────

# Known technical terms / tools / skills that ATS systems look for.
# We ONLY count these — no generic English words.
_TECH_TERMS = {
    # Languages
    "python", "java", "javascript", "typescript", "golang", "ruby", "scala",
    "rust", "swift", "kotlin", "perl", "bash", "shell", "c++", "c#",
    "html", "html5", "css", "css3", "sass", "less", "php", "r",
    "sql", "nosql", "plsql", "t-sql", "matlab", "lua", "dart", "haskell",
    # Frontend
    "react", "angular", "vue", "vue.js", "next.js", "nuxt", "svelte",
    "redux", "webpack", "vite", "tailwind", "tailwindcss", "bootstrap",
    "jquery", "gatsby", "remix", "astro", "storybook",
    # Backend
    "node.js", "express", "django", "flask", "fastapi", "spring",
    "spring-boot", "rails", "laravel", ".net", "asp.net", "nestjs",
    "gin", "fiber", "actix", "rocket", "sinatra",
    # Data / ML / AI
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "scipy", "matplotlib", "seaborn", "plotly", "jupyter", "notebook",
    "spark", "pyspark", "hadoop", "hive", "flink", "airflow", "dbt",
    "databricks", "snowflake", "bigquery", "redshift", "glue", "emr",
    "sagemaker", "mlflow", "kubeflow", "ray", "dask", "polars",
    "nlp", "llm", "bert", "gpt", "transformer", "rag", "langchain",
    "huggingface", "opencv", "yolo", "cnn", "rnn", "lstm", "gan",
    "machine-learning", "deep-learning", "computer-vision",
    "data-engineering", "data-science", "data-analytics", "etl",
    "feature-engineering", "model-training", "model-deployment",
    # Cloud
    "aws", "azure", "gcp", "heroku", "vercel", "netlify", "digitalocean",
    "lambda", "ec2", "s3", "ecs", "eks", "fargate", "cloudformation",
    "cloudwatch", "iam", "vpc", "route53", "sqs", "sns", "kinesis",
    "step-functions", "api-gateway", "dynamodb", "rds", "aurora",
    "cosmos-db", "blob-storage", "cloud-functions", "pub/sub",
    # DevOps / CI-CD
    "docker", "kubernetes", "k8s", "terraform", "ansible", "puppet",
    "jenkins", "github-actions", "gitlab-ci", "circleci", "travis",
    "ci/cd", "helm", "istio", "argocd", "prometheus", "grafana",
    "datadog", "splunk", "elk", "logstash", "kibana", "nagios",
    "nginx", "apache", "linux", "unix", "centos", "ubuntu",
    # Databases
    "mysql", "postgresql", "postgres", "mongodb", "redis", "elasticsearch",
    "cassandra", "sqlite", "oracle", "mssql", "neo4j", "couchdb",
    "influxdb", "timescaledb", "cockroachdb", "mariadb", "memcached",
    "firebase", "firestore", "supabase", "pinecone", "weaviate", "milvus",
    # Tools
    "git", "github", "gitlab", "bitbucket", "jira", "confluence",
    "postman", "swagger", "openapi", "figma", "slack", "trello",
    "notion", "tableau", "powerbi", "power-bi", "looker", "metabase",
    "excel", "vscode",
    # Messaging / Streaming
    "kafka", "rabbitmq", "celery", "redis-queue", "zeromq", "nats",
    "pulsar", "kinesis", "eventbridge",
    # Testing
    "jest", "mocha", "pytest", "junit", "selenium", "cypress",
    "playwright", "testng", "unittest", "rspec", "phpunit",
    # Concepts (common JD technical terms)
    "api", "rest", "restful", "graphql", "grpc", "websocket",
    "microservices", "monolith", "serverless", "event-driven",
    "oauth", "jwt", "sso", "saml", "ldap",
    "agile", "scrum", "kanban", "devops", "devsecops", "sre",
    "sdlc", "stlc", "tdd", "bdd", "ci/cd",
    "oop", "functional", "design-patterns", "solid", "mvc", "mvvm",
    "crud", "orm", "acid", "cap",
    "data-modeling", "data-warehouse", "data-lake", "data-pipeline",
    "data-visualization", "reporting", "dashboard", "analytics",
    "automation", "scripting", "infrastructure", "monitoring",
    "security", "encryption", "authentication", "authorization",
    "distributed", "scalable", "high-availability", "fault-tolerant",
    "cache", "caching", "load-balancer", "cdn",
    "version-control", "code-review", "pair-programming",
    "full-stack", "frontend", "backend", "fullstack",
}

# Also match these patterns dynamically from the JD
_TECH_PATTERNS = re.compile(
    r"""(?ix)
    [A-Z]{2,6}              # Acronyms: AWS, GCP, SQL, API, ETL
    |[A-Z][a-z]+\.js        # Node.js, Vue.js, Next.js
    |[A-Z][a-z]+(?:DB|ML|AI|QL|MQ)  # MongoDB, GraphQL, RabbitMQ
    """
)


def _extract_keywords(text: str) -> set[str]:
    """Extract ONLY technical/tool keywords from text."""
    text_lower = text.lower()
    
    # 1. Match known tech terms
    keywords = set()
    for term in _TECH_TERMS:
        # Check for the term as a whole word
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text_lower):
            keywords.add(term)
    
    # 2. Match acronyms (2-6 uppercase letters like AWS, GCP, SQL)
    acronyms = re.findall(r'\b([A-Z]{2,6})\b', text)
    for acr in acronyms:
        if len(acr) >= 2 and acr.lower() not in {"the", "and", "for", "are", "you", "our", "may", "can"}:
            keywords.add(acr.lower())
    
    # 3. Match tech-looking terms (with dots, hashes, plusses: C++, C#, Node.js)
    tech_tokens = re.findall(r'\b[A-Za-z][A-Za-z0-9]*[.+#][A-Za-z0-9.]*\b', text)
    for tt in tech_tokens:
        keywords.add(tt.lower())
    
    return keywords


def compute_ats_score(resume_text: str, job_description: str, job_title: str = "") -> ATSScore:
    """Compute ATS compatibility score."""
    if not job_description.strip():
        return ATSScore(
            overall=0, keyword_match=0,
            matched_keywords=[], missing_keywords=[],
            feedback=["No job description provided — ATS score requires a job description."],
        )

    jd_keywords = _extract_keywords(job_description + " " + job_title)
    resume_lower = resume_text.lower()

    matched = sorted([kw for kw in jd_keywords if kw in resume_lower])
    missing = sorted([kw for kw in jd_keywords if kw not in resume_lower])

    kw_pct = int(len(matched) / max(len(jd_keywords), 1) * 100)

    # Structural bonuses
    structural_bonus = 0
    if re.search(r"(?i)(experience|work history)", resume_text):
        structural_bonus += 5
    if re.search(r"(?i)(education)", resume_text):
        structural_bonus += 5
    if re.search(r"(?i)(skills?)", resume_text):
        structural_bonus += 5
    if re.search(r"(?i)(projects?)", resume_text):
        structural_bonus += 3

    overall = min(100, kw_pct + structural_bonus)

    feedback: list[str] = []
    if overall >= 80:
        feedback.append("✅ Excellent keyword alignment with the job description.")
    elif overall >= 60:
        feedback.append("⚠️ Good alignment but some key terms are missing.")
    else:
        feedback.append("❌ Low keyword coverage — consider adding more role-specific terms.")

    if missing[:5]:
        feedback.append(f"Missing terms to consider: {', '.join(missing[:8])}.")

    if overall >= 75:
        feedback.append("✅ Resume is likely to pass ATS filters.")
    elif overall >= 55:
        feedback.append("⚠️ Resume may be filtered by strict ATS systems.")
    else:
        feedback.append("❌ Resume needs significant tailoring to pass ATS scanners.")

    return ATSScore(
        overall=overall, keyword_match=kw_pct,
        matched_keywords=matched[:20], missing_keywords=missing[:15],
        feedback=feedback,
    )


# ── Gemini Verification ────────────────────────────────────────────────────

async def verify_with_gemini(resume_markdown: str, job_description: str, job_title: str) -> GeminiReview:
    """Use Gemini to holistically verify the generated resume quality."""
    if not settings.gemini_api_key:
        return GeminiReview(
            ats_score=0, bullet_quality_score=0, jd_alignment_score=0,
            strengths=[], weaknesses=[], suggestions=[],
            verdict="Skipped", skipped=True,
        )

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""You are an expert ATS analyst and senior technical recruiter. Evaluate the resume below against the job description and return ONLY a JSON object — no markdown, no explanation.

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description[:1500] if job_description.strip() else "Not provided"}

RESUME:
{resume_markdown[:3000]}

Return this exact JSON structure:
{{
  "ats_score": <0-100 holistic ATS pass likelihood>,
  "bullet_quality_score": <0-100 strength of action verbs and quantified metrics>,
  "jd_alignment_score": <0-100 semantic alignment with job description>,
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"],
  "suggestions": ["<specific fix 1>", "<specific fix 2>", "<specific fix 3>"],
  "verdict": "<Pass|Needs Work|Fail>"
}}

Scoring guide:
- ats_score >= 80 → Pass, 55-79 → Needs Work, <55 → Fail
- bullet_quality_score: penalize vague verbs (worked on, helped, assisted), missing metrics
- jd_alignment_score: semantic match, not just keyword count"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        data = json.loads(raw)

        return GeminiReview(
            ats_score=int(data.get("ats_score", 0)),
            bullet_quality_score=int(data.get("bullet_quality_score", 0)),
            jd_alignment_score=int(data.get("jd_alignment_score", 0)),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            suggestions=data.get("suggestions", []),
            verdict=data.get("verdict", "Needs Work"),
            skipped=False,
        )

    except Exception as e:
        print(f"⚠️ Gemini verification failed: {e}")
        return GeminiReview(
            ats_score=0, bullet_quality_score=0, jd_alignment_score=0,
            strengths=[], weaknesses=[],
            suggestions=[f"Gemini verification unavailable: {str(e)}"],
            verdict="Skipped", skipped=True,
        )


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/resume-generator", response_model=ResumeGeneratorResponse)
async def create_resume_from_pdf(
    resume: UploadFile = File(..., description="Master resume PDF"),
    job_description: str = Form(""),
    job_title: str = Form("Software Engineer"),
    job_company: str = Form(""),
    target_role: str = Form(""),
):
    """
    Generate an ATS-optimized, 1-page tailored resume.
    Returns both original and tailored ATS scores.
    """
    if not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

    try:
        pdf_bytes = await resume.read()
        raw_text = extract_text_from_pdf(pdf_bytes)
        resume_data: ResumeData = await parse_resume(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse resume PDF: {e}")

    # ── ATS score for the ORIGINAL resume ──
    original_ats = compute_ats_score(raw_text, job_description, job_title)

    # Build job context
    job: Optional[JobListing] = None
    if job_description.strip() or job_title.strip():
        job = JobListing(
            id="user-provided",
            title=job_title or target_role or "Software Engineer",
            company=job_company or "Target Company",
            description=job_description or f"{job_title} position.",
            required_skills=[],
            preferred_skills=[],
            location="",
            job_type="Full-time",
            remote_policy="",
        )

    effective_role = target_role or (job.title if job else "") or "Software Engineer"

    # ── Generate + retry loop to hit 75% ATS ──
    ATS_TARGET = 75
    MAX_RETRIES = 2
    resume_markdown = ""
    tailored_ats = ATSScore(overall=0, keyword_match=0, matched_keywords=[], missing_keywords=[], feedback=[])
    result: dict = {}

    for attempt in range(1 + MAX_RETRIES):
        try:
            extra_instructions = ""
            if attempt > 0 and tailored_ats.missing_keywords:
                missing_kws = ", ".join(tailored_ats.missing_keywords[:20])
                extra_instructions = (
                    f"\n\n⚠️ IMPORTANT: The previous version scored {tailored_ats.overall}% ATS. "
                    f"You MUST incorporate these missing keywords naturally into the resume: {missing_kws}. "
                    f"Weave them into bullet points, skills, or project descriptions. "
                    f"Target ATS score: {ATS_TARGET}%+."
                )

            result = await generate_resume(
                resume=resume_data,
                job=job,
                target_role=effective_role,
                raw_resume_text=(raw_text or "") + extra_instructions,
            )
        except Exception as e:
            if attempt == 0:
                raise HTTPException(status_code=500, detail=f"Resume generation failed: {e}")
            break  # Use best attempt so far

        resume_markdown = result["resume_markdown"]
        tailored_ats = compute_ats_score(resume_markdown, job_description, job_title)

        print(f"📊 Attempt {attempt + 1}: ATS score = {tailored_ats.overall}%")

        if tailored_ats.overall >= ATS_TARGET:
            break  # Target reached

    # ── Smart keyword injection: categorize and merge into skill lines ──
    if tailored_ats.overall < ATS_TARGET and tailored_ats.missing_keywords:
        missing = tailored_ats.missing_keywords
        print(f"⚙️ Smartly injecting {len(missing)} missing keywords into resume")

        # Auto-categorize keywords by pattern matching
        _CATEGORY_PATTERNS = {
            "Languages": {"python", "java", "javascript", "typescript", "golang", "ruby",
                          "scala", "rust", "swift", "kotlin", "perl", "bash", "shell",
                          "html", "html5", "css", "css3", "c++", "c#"},
            "Frameworks & Libraries": {"react", "angular", "vue", "django", "flask", "fastapi",
                                        "spring", "express", "node.js", "next.js", "tensorflow",
                                        "pytorch", "pandas", "numpy", "scipy", "keras", "spark",
                                        "hadoop", "flink", "airflow", "dbt", "streamlit",
                                        "bootstrap", "tailwind", "redux", ".net"},
            "Cloud & DevOps": {"aws", "azure", "gcp", "docker", "kubernetes", "terraform",
                               "jenkins", "github", "gitlab", "ci/cd", "heroku", "vercel",
                               "cloudformation", "lambda", "s3", "ec2", "ecs", "fargate",
                               "sagemaker", "databricks", "snowflake", "redshift"},
            "Databases": {"mysql", "postgresql", "postgres", "mongodb", "redis", "elasticsearch",
                          "dynamodb", "cassandra", "sqlite", "oracle", "mssql", "neo4j",
                          "firebase", "supabase", "pinecone", "bigquery"},
            "Tools & Platforms": {"git", "jira", "confluence", "postman", "swagger",
                                   "linux", "unix", "nginx", "grafana", "prometheus",
                                   "kafka", "rabbitmq", "celery", "tableau", "powerbi",
                                   "figma", "slack"},
            "Data & ML": {"machine_learning", "deep_learning", "nlp", "computer_vision",
                          "etl", "data_pipeline", "analytics", "visualization",
                          "regression", "classification", "clustering", "neural",
                          "llm", "transformer", "bert", "gpt", "rag"},
            "Methodologies": {"agile", "scrum", "kanban", "sdlc", "stlc", "devops",
                              "microservices", "rest", "graphql", "api", "oauth",
                              "testing", "automation", "ci/cd"},
        }

        # Classify each missing keyword
        categorized: dict[str, list[str]] = {}
        uncategorized: list[str] = []

        for kw in missing:
            placed = False
            for cat, patterns in _CATEGORY_PATTERNS.items():
                if kw.lower() in patterns or any(p in kw.lower() for p in patterns):
                    categorized.setdefault(cat, []).append(kw)
                    placed = True
                    break
            if not placed:
                uncategorized.append(kw)

        # Find the skills section and merge
        skills_header = None
        if "## Technical Skills" in resume_markdown:
            skills_header = "## Technical Skills"
        elif "## Skills" in resume_markdown:
            skills_header = "## Skills"

        new_skill_lines: list[str] = []
        for cat, kws in categorized.items():
            new_skill_lines.append(f"**{cat}** |||TAB||| {', '.join(kws)}")
        if uncategorized:
            new_skill_lines.append(f"**Other Tools** |||TAB||| {', '.join(uncategorized)}")

        if skills_header and new_skill_lines:
            parts = resume_markdown.split(skills_header, 1)
            after = parts[1]

            # Find existing skill lines and the end of skill section
            lines = after.split("\n")
            insert_idx = 0
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("## ") and idx > 0:
                    break
                if stripped and ("|||TAB|||" in stripped or stripped.startswith("**")):
                    insert_idx = idx + 1  # insert after last skill line

            # Merge: try to append to existing categories or add new lines
            existing_text = after.lower()
            lines_to_add = []
            for sl in new_skill_lines:
                # Extract category name
                cat_name = sl.split("**")[1].lower() if "**" in sl else ""
                # Check if this category already exists
                if cat_name and cat_name in existing_text:
                    # Find the matching line and append keywords
                    for idx, line in enumerate(lines):
                        if cat_name in line.lower() and "|||TAB|||" in line:
                            kws_part = sl.split("|||TAB|||")[1].strip()
                            lines[idx] = line.rstrip() + ", " + kws_part
                            break
                    else:
                        lines_to_add.append(sl)
                else:
                    lines_to_add.append(sl)

            # Insert new category lines
            if lines_to_add:
                for line_to_add in reversed(lines_to_add):
                    lines.insert(insert_idx, line_to_add)

            resume_markdown = parts[0] + skills_header + "\n".join(lines)
        elif new_skill_lines:
            resume_markdown += "\n\n## Technical Skills\n" + "\n".join(new_skill_lines) + "\n"

        # Recompute score after smart injection
        tailored_ats = compute_ats_score(resume_markdown, job_description, job_title)
        print(f"📊 After smart injection: ATS score = {tailored_ats.overall}%")

    # ── Compute changes from original ──
    changes_made = _compute_changes(raw_text, resume_markdown, original_ats, tailored_ats)

    # ── Gemini verification ──
    gemini_review = await verify_with_gemini(resume_markdown, job_description, job_title)
    print(f"🤖 Gemini verdict: {gemini_review.verdict} | ATS: {gemini_review.ats_score}% | Bullets: {gemini_review.bullet_quality_score}% | JD fit: {gemini_review.jd_alignment_score}%")

    # Convert to PDF
    try:
        out_pdf = markdown_to_pdf(resume_markdown)
        pdf_b64 = base64.b64encode(out_pdf).decode("utf-8")
    except Exception as e:
        print(f"⚠️ PDF generation failed: {e}")
        pdf_b64 = ""

    return ResumeGeneratorResponse(
        resume_markdown=resume_markdown,
        word_count=result.get("word_count", len(resume_markdown.split())),
        assumptions_made=result.get("assumptions_made", []),
        candidate_name=resume_data.name,
        pdf_base64=pdf_b64,
        original_ats_score=original_ats,
        tailored_ats_score=tailored_ats,
        changes_made=changes_made,
        gemini_review=gemini_review,
    )


def _compute_changes(
    original_text: str,
    tailored_md: str,
    original_ats: ATSScore,
    tailored_ats: ATSScore,
) -> list[str]:
    """Compute a human-readable list of changes made during tailoring."""
    changes: list[str] = []
    orig_lower = original_text.lower()
    tail_lower = tailored_md.lower()

    # 1. Skills added
    orig_kws = _extract_keywords(original_text)
    tail_kws = _extract_keywords(tailored_md)
    added_skills = sorted(tail_kws - orig_kws)
    removed_skills = sorted(orig_kws - tail_kws)
    if added_skills:
        changes.append(f"🆕 **Skills/Keywords Added:** {', '.join(added_skills)}")
    if removed_skills:
        changes.append(f"➖ **Skills/Keywords Removed:** {', '.join(removed_skills)}")

    # 2. Sections comparison
    orig_sections = set(re.findall(r'(?i)(?:education|experience|projects?|skills|certifications?|publications?)', orig_lower))
    tail_sections = set(re.findall(r'(?i)(?:education|experience|projects?|skills|certifications?|publications?)', tail_lower))
    new_sections = tail_sections - orig_sections
    if new_sections:
        changes.append(f"📋 **Sections Added:** {', '.join(s.title() for s in new_sections)}")

    # 3. ATS score change
    delta = tailored_ats.overall - original_ats.overall
    if delta > 0:
        changes.append(f"📈 **ATS Score:** {original_ats.overall}% → {tailored_ats.overall}% (+{delta}%)")
    elif delta < 0:
        changes.append(f"📉 **ATS Score:** {original_ats.overall}% → {tailored_ats.overall}% ({delta}%)")
    else:
        changes.append(f"↔️ **ATS Score:** unchanged at {tailored_ats.overall}%")

    # 4. Keyword match improvement
    kw_delta = tailored_ats.keyword_match - original_ats.keyword_match
    if kw_delta > 0:
        changes.append(f"🔑 **Keyword Coverage:** {original_ats.keyword_match}% → {tailored_ats.keyword_match}% (+{kw_delta}%)")

    # 5. Bullet point enhancements
    orig_bullets = len(re.findall(r'^[-•*]\s', original_text, re.MULTILINE))
    tail_bullets = len(re.findall(r'^[-•*]\s', tailored_md, re.MULTILINE))
    if tail_bullets > orig_bullets:
        changes.append(f"✏️ **Bullet Points:** {orig_bullets} → {tail_bullets} (added {tail_bullets - orig_bullets} action-driven bullets)")
    elif tail_bullets < orig_bullets:
        changes.append(f"✏️ **Bullet Points:** {orig_bullets} → {tail_bullets} (condensed for 1-page fit)")

    # 6. Word count
    orig_words = len(original_text.split())
    tail_words = len(tailored_md.split())
    changes.append(f"📝 **Word Count:** {orig_words} → {tail_words} words")

    if not changes:
        changes.append("No significant changes detected.")

    return changes

