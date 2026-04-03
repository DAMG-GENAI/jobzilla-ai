"""
User Data Models

Pydantic models for user profiles and preferences.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.resume import ResumeData


class GitHubProfile(BaseModel):
    """GitHub profile data from MCP server."""

    username: str
    public_repos: int = 0
    followers: int = 0
    following: int = 0

    # Extracted data
    primary_language: str | None = None
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    # Activity
    activity_level: str = "Unknown"  # High, Medium, Low
    recent_commits: int = 0

    # Quality indicators
    avg_repo_quality_score: float = 0


class JobPreferences(BaseModel):
    """User's job search preferences."""

    # Role preferences
    target_roles: list[str] = Field(default_factory=list)
    excluded_roles: list[str] = Field(default_factory=list)

    # Location
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str = "Flexible"  # Remote, On-site, Hybrid, Flexible
    willing_to_relocate: bool = False

    # Compensation
    min_salary: int | None = None
    preferred_currency: str = "USD"

    # Company preferences
    preferred_company_sizes: list[str] = Field(
        default_factory=list
    )  # Startup, Mid-size, Enterprise
    preferred_industries: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)

    # Experience level
    experience_level: str = "Mid"  # Entry, Mid, Senior, Lead, Executive

    # Other
    visa_sponsorship_required: bool = False


class UserProfile(BaseModel):
    """Complete user profile."""

    id: UUID = Field(default_factory=uuid4)

    # Contact
    email: str
    name: str | None = None

    # Profile data
    resume: ResumeData | None = None
    github: GitHubProfile | None = None
    preferences: JobPreferences = Field(default_factory=JobPreferences)

    # Status
    is_active: bool = True
    email_notifications: bool = True

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_match_at: datetime | None = None


class MatchHistory(BaseModel):
    """User's match history entry."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    job_id: str

    # Match result
    score: float
    recommendation: str

    # User feedback
    user_rating: int | None = None  # 1-5 stars
    user_feedback: str | None = None
    applied: bool = False
    applied_at: datetime | None = None

    # Timestamps
    matched_at: datetime = Field(default_factory=datetime.utcnow)
