"""
Agent Data Models

Pydantic models for the multi-agent debate system.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """Roles in the agent debate system."""

    PROFILE_PARSER = "profile_parser"
    RECRUITER = "recruiter"
    COACH = "coach"
    JUDGE = "judge"
    SKILL_GAP = "skill_gap"
    COVER_WRITER = "cover_writer"
    RESUME_GENERATOR = "resume_generator"
    IMPROVEMENT = "improvement"


class AgentMessage(BaseModel):
    """Message from an agent."""

    role: AgentRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Argument(BaseModel):
    """Single argument in a debate."""

    point: str
    evidence: str | None = None
    strength: str = "Medium"  # Strong, Medium, Weak
    category: str | None = None  # Skills, Experience, Culture, etc.


class DebateRound(BaseModel):
    """A round of debate between recruiter and coach."""

    round_number: int

    # Recruiter's arguments (concerns/weaknesses)
    recruiter_arguments: list[Argument] = Field(default_factory=list)
    recruiter_score: float = Field(ge=0, le=100)

    # Coach's arguments (strengths/positives)
    coach_arguments: list[Argument] = Field(default_factory=list)
    coach_score: float = Field(ge=0, le=100)

    # Score difference triggers redebate if > threshold
    score_difference: float = 0

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VerdictReasoning(BaseModel):
    """Detailed reasoning for the judge's verdict."""

    key_strengths: list[str] = Field(default_factory=list)
    key_concerns: list[str] = Field(default_factory=list)
    deciding_factors: list[str] = Field(default_factory=list)
    recommendation: str  # "Strong Match", "Good Match", "Possible Match", "Weak Match", "Not Recommended"


class Verdict(BaseModel):
    """Judge's final verdict on the match."""

    final_score: float = Field(ge=0, le=100)
    recommendation: str
    reasoning: VerdictReasoning
    confidence: float = Field(ge=0, le=1)

    # Which agent "won" the debate
    favored_agent: AgentRole | None = None

    # Actionable items
    must_address: list[str] = Field(
        default_factory=list, description="Critical issues to address"
    )
    nice_to_have: list[str] = Field(
        default_factory=list, description="Optional improvements"
    )

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentPipelineResult(BaseModel):
    """Complete result from the agent pipeline."""

    # Input summary
    resume_summary: str
    job_summary: str
    github_summary: str | None = None

    # Debate
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    total_rounds: int = 0

    # Verdict
    verdict: Verdict

    # Outputs
    skill_gaps: list[dict[str, Any]] = Field(default_factory=list)
    cover_letter: str | None = None
    generated_resume: str | None = None
    improvement_suggestions: list[str] = Field(default_factory=list)

    # Metadata
    processing_time_seconds: float = 0
    tokens_used: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
