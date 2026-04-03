"""
Database Models

SQLAlchemy models for PostgreSQL database.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# =============================================================================
# User Models
# =============================================================================


class User(Base):
    """User account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))
    github_username = Column(String(100))
    linkedin_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    resumes = relationship("Resume", back_populates="user")
    job_matches = relationship("JobMatch", back_populates="user")
    cover_letters = relationship("CoverLetter", back_populates="user")


class Resume(Base):
    """Stored resume information."""

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # S3 Storage
    s3_key_raw = Column(String(500))  # Original PDF
    s3_key_parsed = Column(String(500))  # Parsed JSON

    # Parsed Data (cached)
    name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    location = Column(String(255))
    summary = Column(Text)
    skills = Column(JSON)  # List of skills
    experience = Column(JSON)  # List of experience objects
    education = Column(JSON)  # List of education objects
    total_years_experience = Column(Float)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_primary = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="resumes")


# =============================================================================
# Job Models
# =============================================================================


class Job(Base):
    """Job listing."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Core Info
    title = Column(String(500), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255))
    job_type = Column(String(50))  # full-time, part-time, contract
    remote_type = Column(String(50))  # remote, hybrid, on-site

    # Description
    description = Column(Text)
    requirements = Column(JSON)  # List of requirements
    responsibilities = Column(JSON)  # List of responsibilities
    benefits = Column(JSON)  # List of benefits

    # Compensation
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    salary_currency = Column(String(10), default="USD")

    # Skills
    required_skills = Column(JSON)  # List of required skills
    preferred_skills = Column(JSON)  # List of nice-to-have skills
    experience_level = Column(String(50))  # entry, mid, senior, lead
    years_experience_min = Column(Integer)
    years_experience_max = Column(Integer)

    # Source
    source_url = Column(String(1000), unique=True)
    source_platform = Column(String(100))  # linkedin, indeed, etc.

    # Vector Embedding
    embedding_id = Column(String(100))  # Pinecone vector ID

    # Status
    is_active = Column(Boolean, default=True)
    posted_at = Column(DateTime)
    expires_at = Column(DateTime)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    matches = relationship("JobMatch", back_populates="job")


class JobMatch(Base):
    """Match between user and job."""

    __tablename__ = "job_matches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)

    # Match Scores
    overall_score = Column(Float, nullable=False)  # 0-100
    skill_match_score = Column(Float)
    experience_match_score = Column(Float)

    # AI Debate Results
    recruiter_score = Column(Float)  # Recruiter agent score
    coach_score = Column(Float)  # Coach agent score
    judge_verdict = Column(String(50))  # hire, reject, maybe
    debate_summary = Column(Text)

    # User Actions
    is_saved = Column(Boolean, default=False)
    is_applied = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    user_rating = Column(Integer)  # 1-5 stars

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="job_matches")
    job = relationship("Job", back_populates="matches")


# =============================================================================
# Cover Letter Models
# =============================================================================


class CoverLetter(Base):
    """Generated cover letter."""

    __tablename__ = "cover_letters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"))

    # Content
    content = Column(Text, nullable=False)
    s3_key = Column(String(500))

    # Generation Info
    model_used = Column(String(100))
    prompt_version = Column(String(50))

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="cover_letters")


# =============================================================================
# Analytics Models
# =============================================================================


class SkillTrend(Base):
    """Skill demand trends over time."""

    __tablename__ = "skill_trends"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False, index=True)

    # Metrics
    job_count = Column(Integer)  # Jobs mentioning this skill
    demand_score = Column(Float)  # 0-100
    growth_rate = Column(Float)  # % change from last period
    avg_salary = Column(Integer)

    # Time period
    period_start = Column(DateTime)
    period_end = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
