"""
API Client

Wrapper for backend API calls.
"""

from typing import Any

import httpx

# Default backend URL - can be overridden
BACKEND_URL = "http://localhost:8000"


class APIClient:
    """Client for KillMatch backend API."""

    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def health_check(self) -> dict[str, Any]:
        """Check if backend is healthy."""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    async def create_profile(
        self,
        email: str,
        name: str | None = None,
        github_username: str | None = None,
        resume_content: bytes | None = None,
    ) -> dict[str, Any]:
        """Create a user profile."""
        data = {"email": email}
        if name:
            data["name"] = name
        if github_username:
            data["github_username"] = github_username

        files = {}
        if resume_content:
            files["resume"] = ("resume.pdf", resume_content, "application/pdf")

        response = await self.client.post(
            f"{self.base_url}/api/v1/profile",
            data=data,
            files=files if files else None,
        )
        response.raise_for_status()
        return response.json()

    async def match_jobs(
        self,
        resume_data: dict[str, Any],
        job_search_query: str | None = None,
        job: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the matching pipeline."""
        payload = {
            "resume": resume_data,
        }
        if job_search_query:
            payload["job_search_query"] = job_search_query
        if job:
            payload["job"] = job

        response = await self.client.post(
            f"{self.base_url}/api/v1/match",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def generate_cover_letter(
        self,
        resume_data: dict[str, Any],
        job: dict[str, Any],
        tone: str = "professional",
        recruiter_concerns: list[str] = None,
        coach_highlights: list[str] = None,
    ) -> dict[str, Any]:
        """Generate a cover letter."""
        payload = {
            "resume": resume_data,
            "job": job,
            "tone": tone,
            "recruiter_concerns": recruiter_concerns or [],
            "coach_highlights": coach_highlights or [],
        }

        response = await self.client.post(
            f"{self.base_url}/api/v1/cover-letter",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def get_analytics(self, user_id: str) -> dict[str, Any]:
        """Get user analytics."""
        response = await self.client.get(f"{self.base_url}/api/v1/analytics/{user_id}")
        response.raise_for_status()
        return response.json()

    async def get_recommendations(self, user_id: str) -> dict[str, Any]:
        """Get headhunter recommendations."""
        response = await self.client.get(f"{self.base_url}/api/v1/headhunter/{user_id}")
        response.raise_for_status()
        return response.json()


def get_sync_client(base_url: str = BACKEND_URL) -> httpx.Client:
    """Get a synchronous client for use in Streamlit."""
    return httpx.Client(base_url=base_url, timeout=60.0)
