"""
Resume Data Models

Pydantic models for resume/CV data structures.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class SkillCategory(StrEnum):
    """Categories for different types of skills."""

    PROGRAMMING = "Programming"
    FRAMEWORK = "Framework"
    TOOL = "Tool"
    SOFT_SKILL = "Soft Skill"
    OTHER = "Other"


class Skill(BaseModel):
    """Individual skill with optional proficiency level."""

    name: str
    category: SkillCategory | None = None
    proficiency: str | None = None  # e.g., "Expert", "Intermediate", "Beginner"
    years_of_experience: float | None = None


class Experience(BaseModel):
    """Work experience entry."""

    company: str
    title: str
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None  # None if current
    is_current: bool = False
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """Education entry."""

    institution: str
    degree: str
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    gpa: float | None = None
    honors: list[str] = Field(default_factory=list)


class Project(BaseModel):
    """Project entry (personal or professional)."""

    name: str
    description: str | None = None
    url: str | None = None
    technologies: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    """Professional certification."""

    name: str
    issuer: str
    date_obtained: date | None = None
    expiration_date: date | None = None
    credential_id: str | None = None
    url: str | None = None


class Publication(BaseModel):
    """Publication entry (paper, article, etc.)."""

    title: str
    publisher: str | None = None
    date_published: date | None = None
    url: str | None = None
    description: str | None = None


class Achievement(BaseModel):
    """Award or achievement entry."""

    title: str
    issuer: str | None = None
    date_received: date | None = None
    description: str | None = None


class ResumeData(BaseModel):
    """Complete resume/CV data structure."""

    # Basic Info
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

    # Summary
    summary: str | None = None

    # Core Sections
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)

    # Additional
    languages: list[str] = Field(default_factory=list)  # Spoken languages
    interests: list[str] = Field(default_factory=list)

    # Computed fields
    total_years_experience: float | None = None
    primary_role: str | None = None

    def get_all_technologies(self) -> list[str]:
        """Get all unique technologies mentioned."""
        techs = set()
        for exp in self.experience:
            techs.update(exp.technologies)
        for proj in self.projects:
            techs.update(proj.technologies)
        for skill in self.skills:
            if skill.category in [
                SkillCategory.PROGRAMMING,
                SkillCategory.FRAMEWORK,
                SkillCategory.TOOL,
            ]:
                techs.add(skill.name)
        return sorted(techs)
