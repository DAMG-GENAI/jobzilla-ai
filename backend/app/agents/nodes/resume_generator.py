"""
Resume Generator Node

Generates ATS-optimized, 1-page resumes tailored for graduate students.
"""

from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

from app.agents.prompts.resume_generator_prompt import RESUME_GENERATOR_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.core.config import settings
from app.models import JobListing, ResumeData


async def resume_generator_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node that generates a tailored resume.

    Uses insights from the debate pipeline (parsed skills, experience
    summary, skill gaps) to produce a better-targeted resume.
    """
    resume = state["resume_data"]
    job = state["job_data"]

    # Leverage parsed data from earlier nodes if available
    target_role = job.title if job else None

    result = await generate_resume(
        resume=resume,
        job=job,
        target_role=target_role,
    )

    return {
        "generated_resume": result.get("resume_markdown", ""),
        "messages": state.get("messages", []) + [
            {"role": "resume_generator", "content": "Generated tailored resume"}
        ],
    }


async def generate_resume(
    resume: ResumeData,
    job: Optional[JobListing] = None,
    target_role: Optional[str] = None,
    raw_resume_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an ATS-optimized resume using LLM.

    This function is also called directly by the resume generator API endpoint.
    """
    target_role = target_role or job.title if job else "Software Engineer"

    # Build structured user prompt from ResumeData fields
    prompt = _build_user_prompt(resume, job, target_role, raw_resume_text)

    resume_markdown = ""
    assumptions_made: List[str] = []

    if settings.openai_api_key:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.6,  # Balanced: creative but consistent
        )

        response = await llm.ainvoke([
            {"role": "system", "content": RESUME_GENERATOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        raw = response.content

        # Split out "Assumptions Made" section if the LLM included one
        if "## Assumptions Made" in raw:
            parts = raw.split("## Assumptions Made", 1)
            resume_markdown = parts[0].strip()
            assumptions_text = parts[1].strip()
            assumptions_made = [
                line.lstrip("- ").strip()
                for line in assumptions_text.splitlines()
                if line.strip() and line.strip() != "---"
            ]
        elif "**Assumptions Made**" in raw:
            parts = raw.split("**Assumptions Made**", 1)
            resume_markdown = parts[0].strip()
            assumptions_text = parts[1].strip()
            assumptions_made = [
                line.lstrip("- ").strip()
                for line in assumptions_text.splitlines()
                if line.strip() and line.strip() != "---"
            ]
        else:
            resume_markdown = raw.strip()
    else:
        # Fallback template when no API key is configured
        resume_markdown = _build_fallback_resume(resume, target_role, raw_resume_text)
        assumptions_made = ["Generated using fallback template — configure OpenAI API key for AI-powered generation"]

    word_count = len(resume_markdown.split())

    return {
        "resume_markdown": resume_markdown,
        "assumptions_made": assumptions_made,
        "word_count": word_count,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_user_prompt(
    resume: ResumeData,
    job: Optional[JobListing],
    target_role: str,
    raw_resume_text: Optional[str] = None,
) -> str:
    """Build the user-facing prompt from structured ResumeData."""

    sections: List[str] = []

    # 1. Contact info
    sections.append("## Candidate Information")
    sections.append(f"**Full Name:** {resume.name}")
    if resume.email:
        sections.append(f"**Email:** {resume.email}")
    if resume.phone:
        sections.append(f"**Phone:** {resume.phone}")
    if resume.location:
        sections.append(f"**Location:** {resume.location}")
    if resume.linkedin_url:
        sections.append(f"**LinkedIn:** {resume.linkedin_url}")
    if resume.github_url:
        sections.append(f"**GitHub:** {resume.github_url}")
    if resume.portfolio_url:
        sections.append(f"**Portfolio:** {resume.portfolio_url}")

    # 2. Target role
    sections.append(f"\n**Target Role:** {target_role}")

    # 3. Summary
    if resume.summary:
        sections.append(f"\n## Summary\n{resume.summary}")

    # 4. Education
    if resume.education:
        sections.append("\n## Education")
        for edu in resume.education:
            gpa_str = f" | GPA: {edu.gpa}/4.0" if edu.gpa and edu.gpa >= 3.5 else ""
            date_range = ""
            if edu.start_date:
                date_range = f" | {edu.start_date.strftime('%b %Y')}"
            if edu.end_date:
                date_range += f" – {edu.end_date.strftime('%b %Y')}"
            sections.append(
                f"- {edu.degree}, {edu.field_of_study or 'N/A'} | "
                f"{edu.institution}{date_range}{gpa_str}"
            )
            if edu.honors:
                sections.append(f"  Honors: {', '.join(edu.honors)}")

    # 5. Skills
    if resume.skills:
        sections.append("\n## Skills")
        by_cat: Dict[str, List[str]] = {}
        for s in resume.skills:
            cat = s.category.value if hasattr(s.category, "value") else (s.category or "Other")
            by_cat.setdefault(cat, []).append(s.name)
        for cat, names in by_cat.items():
            sections.append(f"- **{cat}:** {', '.join(names)}")

    # 6. Projects
    if resume.projects:
        sections.append("\n## Projects")
        for proj in resume.projects:
            tech = ", ".join(proj.technologies) if proj.technologies else "N/A"
            sections.append(f"- **{proj.name}** | {tech}")
            if proj.description:
                sections.append(f"  {proj.description}")
            for hl in proj.highlights:
                sections.append(f"  - {hl}")

    # 7. Experience
    if resume.experience:
        sections.append("\n## Work Experience / Internships")
        for exp in resume.experience:
            date_range = ""
            if exp.start_date:
                date_range = f" | {exp.start_date.strftime('%b %Y')}"
            if exp.end_date:
                date_range += f" – {exp.end_date.strftime('%b %Y')}"
            elif exp.is_current:
                date_range += " – Present"
            sections.append(
                f"- **{exp.title}** | {exp.company}"
                f"{f' | {exp.location}' if exp.location else ''}{date_range}"
            )
            for hl in exp.highlights:
                sections.append(f"  - {hl}")

    # 8. Certifications
    if resume.certifications:
        sections.append("\n## Certifications")
        for cert in resume.certifications:
            date_str = f" | {cert.date_obtained.strftime('%b %Y')}" if cert.date_obtained else ""
            sections.append(f"- **{cert.name}** | {cert.issuer}{date_str}")

    # 8.5 Publications
    if resume.publications:
        sections.append("\n## Publications")
        for pub in resume.publications:
            date_str = f" | {pub.date_published.strftime('%b %Y')}" if pub.date_published else ""
            sections.append(f"- **{pub.title}** | {pub.publisher or 'Independent'}{date_str}")

    # 8.6 Achievements
    if resume.achievements:
        sections.append("\n## Achievements / Awards")
        for ach in resume.achievements:
            date_str = f" | {ach.date_received.strftime('%b %Y')}" if ach.date_received else ""
            sections.append(f"- **{ach.title}** | {ach.issuer or 'Independent'}{date_str}")

    # 9. Job context (optional, for tailoring)
    if job:
        sections.append("\n## Target Job Context")
        sections.append(f"**Title:** {job.title}")
        sections.append(f"**Company:** {job.company}")
        sections.append(f"**Description:** {job.description[:800]}")
        if job.required_skills:
            sections.append(f"**Required Skills:** {', '.join(job.required_skills)}")
        if job.preferred_skills:
            sections.append(f"**Preferred Skills:** {', '.join(job.preferred_skills)}")

        # Explicit ATS keyword optimization instruction
        import re as _re
        _jd_stop = {
            "and","or","the","a","an","in","on","at","to","for","of","with","is","are",
            "be","we","you","our","your","will","have","has","that","this","as","by",
            "from","it","who","what","how","not","can","all","also","must","very",
            "such","than","about","any","into","then","them","their","more","would",
            "could","should","been","being","were","was","other","some","just",
            "these","those","each","every","using","used","able","well","work",
            "working","including","ability","academic","activities","another",
            "approach","applying","across","along","among","around","based",
            "become","before","between","both","bring","build","building","business",
            "come","company","complex","contribute","create","current","day",
            "demonstrate","develop","developing","different","drive","during",
            "effort","enable","end","ensure","environment","established","even",
            "experience","experienced","first","follow","found","full","generate",
            "get","give","good","great","grow","growth","help","high","highly",
            "ideal","identify","impact","implement","important","improve","include",
            "increase","information","internal","involve","join","keep","key",
            "know","knowledge","large","last","lead","learn","level","like","long",
            "look","looking","maintain","make","making","manage","many","may",
            "meet","multiple","need","new","next","offer","open","opportunity",
            "over","own","part","participate","perform","play","plus","position",
            "possible","practice","prefer","preferred","problem","process",
            "product","professional","provide","range","related","require",
            "required","requirement","requirements","responsible","result",
            "role","run","see","seek","seeking","serve","set","show","significant",
            "solve","solving","specific","start","still","strong","success",
            "successful","support","take","team","teams","through","time",
            "together","top","track","turn","understand","understanding","upon",
            "value","want","way","while","within","without","world","write",
            "writing","year","years","ready","quickly","often","best",
            "one","two","three","four","five","six","several",
        }
        jd_words = set(_re.findall(r"[a-zA-Z][a-zA-Z0-9+#._/-]{3,}", job.description))
        jd_kws = sorted([w for w in jd_words if w.lower() not in _jd_stop and len(w) >= 4])[:40]
        if jd_kws:
            sections.append(
                f"\n> **ATS OPTIMIZATION — CRITICAL RULES**:\n"
                f"> 1. Your **Technical Skills** section MUST list these technologies/tools from the JD: "
                f"{', '.join(jd_kws[:20])}\n"
                f"> 2. Your **Projects** bullet points MUST naturally weave in these terms where relevant.\n"
                f"> 3. Your **Experience** bullets MUST use the same terminology as the JD.\n"
                f"> 4. Add skill categories that match the JD (e.g., Cloud, DevOps, ML/AI, Data).\n"
                f"> 5. Target: **75%+ keyword coverage**. This is mandatory.\n"
                f"> All JD keywords to include: {', '.join(jd_kws)}"
            )

    # Add raw resume text so LLM can recover any data the parser missed
    if raw_resume_text and raw_resume_text.strip():
        sections.append("\n## Full Resume Text (use this to extract any missing sections)")
        sections.append("```")
        sections.append(raw_resume_text[:2500])  # tighter cap to save tokens
        sections.append("```")
        sections.append(
            "\n> IMPORTANT: The structured data above may be incomplete. "
            "Use the Full Resume Text above to extract Experience, Education, Projects, "
            "Certifications and any other sections that are missing from the structured data. "
            "Generate ALL standard resume sections."
        )

    # ── Section priority hint when JD is present ──
    if job:
        sections.append(
            "\n> **SECTION PRIORITY**: "
            "Reorder your projects so the most JD-relevant project comes first. "
            "Within each Experience role, put the most JD-relevant bullet first. "
            "In Technical Skills, list the most JD-relevant technologies first in each row."
        )

    # ── Final instruction with word budget reminder ──
    sections.append(
        "\n---"
        "\n## GENERATE NOW"
        "\nProduce the resume following EVERY rule in the system prompt."
        "\n\n**Word budget reminder:**"
        "\n- Total: ≤ 650 words, ≤ 55 non-blank lines"
        "\n- Education: ≤ 80 words | Experience: ≤ 200 words | Projects: ≤ 180 words"
        "\n- Skills: ≤ 80 words | Pub/Certs: ≤ 50 words"
        "\n- Every bullet: 120–180 characters, starts with strong action verb, ends with metric"
        "\n- Use |||RIGHT||| for dates and |||TAB||| for skills. These are MANDATORY."
        "\n\nStart output with `# ` followed by the candidate's full name. No preamble."
    )

    return "\n".join(sections)


def _build_fallback_resume(
    resume: ResumeData,
    target_role: str,
    raw_resume_text: Optional[str] = None,
) -> str:
    """Build a Markdown resume from structured data + raw text fallback."""

    lines: List[str] = []

    # Contact
    lines.append(f"# {resume.name}")
    contact_parts = [p for p in [resume.location, resume.phone, resume.email] if p]
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    link_parts = [p for p in [resume.linkedin_url, resume.github_url, resume.portfolio_url] if p]
    if link_parts:
        lines.append(" | ".join(link_parts))
    lines.append("")

    # Check if structured data is sparse
    has_experience = bool(resume.experience)
    has_education = bool(resume.education)
    has_projects = bool(resume.projects)

    # If structured data is mostly empty but we have raw text,
    # use the raw text as the resume content directly (cleaned up)
    if not has_experience and not has_projects and raw_resume_text and len(raw_resume_text) > 200:
        # The raw text IS the resume — just present it with basic formatting
        lines.append("")

        # Try to extract sections from raw text
        import re
        raw = raw_resume_text

        # Common section headers to detect
        section_patterns = [
            (r'(?i)\b(education)\b', '## Education'),
            (r'(?i)\b(experience|work\s*history|employment)\b', '## Experience'),
            (r'(?i)\b(projects?)\b', '## Projects'),
            (r'(?i)\b(publications?\s*(?:&|and)?\s*certifications?|certifications?|publications?)\b', '## Publication & Certifications'),
            (r'(?i)\b(technical\s*skills?|skills?)\b', '## Technical Skills'),
        ]

        # Split raw text into lines and try to identify sections
        raw_lines = raw.split('\n')
        current_section = None
        for rline in raw_lines:
            rline_stripped = rline.strip()
            if not rline_stripped:
                lines.append("")
                continue

            # Check if this line is a section header
            is_header = False
            for pattern, header in section_patterns:
                # A section header is typically a short line that matches a pattern
                if re.match(r'^' + pattern + r'\s*$', rline_stripped, re.IGNORECASE) or \
                   (len(rline_stripped) < 40 and re.search(pattern, rline_stripped)):
                    lines.append(header)
                    current_section = header
                    is_header = True
                    break

            if is_header:
                continue

            # Regular content line
            if rline_stripped.startswith(('•', '·', '-', '*', '–')):
                # Bullet point
                bullet_text = re.sub(r'^[•·\-*–]\s*', '', rline_stripped)
                lines.append(f"- {bullet_text}")
            else:
                lines.append(rline_stripped)

        return "\n".join(lines)

    # ── Standard structured data path ──

    # Summary
    if resume.summary:
        lines.append("## Summary")
        lines.append(resume.summary)
        lines.append("")

    # Education
    if resume.education:
        lines.append("## Education")
        for edu in resume.education:
            gpa = f" | GPA: {edu.gpa}/4.0" if edu.gpa and edu.gpa >= 3.5 else ""
            date_range = ""
            if edu.start_date:
                date_range = f"{edu.start_date.strftime('%b %Y')}"
            if edu.end_date:
                date_range += f" - {edu.end_date.strftime('%b %Y')}"
            lines.append(f"**{edu.institution}** |||RIGHT||| {date_range}")
            lines.append(f"{edu.degree}, {edu.field_of_study or ''}{gpa}")
        lines.append("")

    # Experience
    if resume.experience:
        lines.append("## Experience")
        for exp in resume.experience:
            date_range = ""
            if exp.start_date:
                date_range = f"{exp.start_date.strftime('%b %Y')}"
            if exp.end_date:
                date_range += f" - {exp.end_date.strftime('%b %Y')}"
            elif exp.is_current:
                date_range += " - Present"
            lines.append(f"**{exp.company}** |||RIGHT||| {date_range}")
            lines.append(f"*{exp.title}*")
            for hl in exp.highlights:
                lines.append(f"- {hl}")
        lines.append("")

    # Skills
    if resume.skills:
        lines.append("## Technical Skills")
        by_cat: Dict[str, List[str]] = {}
        for s in resume.skills:
            cat = s.category.value if hasattr(s.category, "value") else (s.category or "Other")
            by_cat.setdefault(cat, []).append(s.name)
        for cat, names in by_cat.items():
            lines.append(f"**{cat}** |||TAB||| {', '.join(names)}")
        lines.append("")

    # Projects
    if resume.projects:
        lines.append("## Projects")
        for proj in resume.projects:
            tech = ", ".join(proj.technologies) if proj.technologies else ""
            lines.append(f"**{proj.name}** | {tech}")
            if proj.description:
                lines.append(f"- {proj.description}")
            for hl in proj.highlights:
                lines.append(f"- {hl}")
        lines.append("")

    # Certifications
    if resume.certifications:
        lines.append("## Publication & Certifications")
        for cert in resume.certifications:
            lines.append(f"**{cert.name}** | {cert.issuer}")
        lines.append("")

    return "\n".join(lines)

