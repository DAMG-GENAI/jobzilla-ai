import json
import os
from typing import Any

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_skill_roadmap(
    resume_text: str, job_descriptions: list[str], github_context: str = ""
) -> list[dict[str, Any]]:
    """Generate roadmap using LLM."""
    if not job_descriptions:
        return []

    jobs_text = "\\n\\n".join(
        [f"Job {i+1}: {desc[:500]}..." for i, desc in enumerate(job_descriptions[:3])]
    )

    prompt = f"Analyze skills gap for resume: {resume_text[:1000]} vs jobs: {jobs_text}. Return valid JSON array of objects with keys: skill, priority, reason, time_estimate, resource."

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return (
            data.get("roadmap", [])
            if "roadmap" in data
            else (
                list(data.values())[0]
                if isinstance(list(data.values())[0], list)
                else []
            )
        )
    except Exception as e:
        print(f"Error: {e}")
        return []
