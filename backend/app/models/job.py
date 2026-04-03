"""
Job Data Models

Pydantic models for job listings and matching.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SalaryRange(BaseModel):
    """Salary range for a job."""

    min_salary: int | None = None
    max_salary: int | None = None
    currency: str = "USD"
    period: str = "yearly"  # yearly, monthly, hourly


class JobListing(BaseModel):
    """Job listing data structure."""

    id: str
    title: str
    company: str
    location: str
    description: str

    # Requirements
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    education_requirement: str | None = None

    # Details
    job_type: str = "Full-time"  # Full-time, Part-time, Contract, Internship
    experience_level: str = "Mid"  # Entry, Mid, Senior, Lead, Executive
    remote_policy: str = "On-site"  # On-site, Remote, Hybrid

    # Compensation
    salary: SalaryRange | None = None
    benefits: list[str] = Field(default_factory=list)

    # Source
    source_url: str | None = None
    source_platform: str | None = None  # LinkedIn, Indeed, etc.
    posted_date: datetime | None = None
    scraped_at: datetime | None = None

    # Metadata
    company_size: str | None = None
    industry: str | None = None
    department: str | None = None


class MatchScore(BaseModel):
    """Detailed match score breakdown."""

    overall_score: float = Field(ge=0, le=100)

    # Component scores
    skills_match: float = Field(ge=0, le=100)
    experience_match: float = Field(ge=0, le=100)
    education_match: float = Field(ge=0, le=100)
    culture_fit: float = Field(ge=0, le=100)

    # Agent scores
    recruiter_score: float = Field(
        ge=0, le=100, description="Score from recruiter (lower = more concerns)"
    )
    coach_score: float = Field(
        ge=0, le=100, description="Score from coach (higher = more strengths)"
    )
    judge_score: float = Field(ge=0, le=100, description="Final score from judge")

    # Confidence
    confidence: float = Field(ge=0, le=1, description="Confidence in the score")


class SkillGap(BaseModel):
    """Identified skill gap with recommendation."""

    skill_name: str
    importance: str = "Medium"  # Critical, High, Medium, Low
    description: str
    learning_resources: list[str] = Field(default_factory=list)
    estimated_time_to_learn: str | None = None  # e.g., "2-4 weeks"


class JobMatch(BaseModel):
    """Complete job match result."""

    job: JobListing
    score: MatchScore

    # Analysis
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[SkillGap] = Field(default_factory=list)

    # Agent outputs
    recruiter_concerns: list[str] = Field(default_factory=list)
    coach_highlights: list[str] = Field(default_factory=list)
    judge_reasoning: str | None = None

    # Recommendations
    improvement_suggestions: list[str] = Field(default_factory=list)
    interview_tips: list[str] = Field(default_factory=list)

    # Metadata
    matched_at: datetime = Field(default_factory=datetime.utcnow)
