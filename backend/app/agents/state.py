"""
Agent State Definition

TypedDict defining the state that flows through the LangGraph pipeline.
"""

from typing import Any, TypedDict

from app.models import (
    Argument,
    DebateRound,
    GitHubProfile,
    JobListing,
    ResumeData,
    SkillGap,
    Verdict,
)


class AgentState(TypedDict, total=False):
    """
    State that flows through the LangGraph agent pipeline.

    Each node in the graph can read from and write to this state.
    """

    # =========================================================================
    # Input Data
    # =========================================================================
    resume_data: ResumeData
    job_data: JobListing
    github_profile: GitHubProfile | None

    # =========================================================================
    # Parsed Profile (from profile_parser node)
    # =========================================================================
    parsed_skills: list[str]
    parsed_experience_summary: str
    parsed_strengths: list[str]
    total_years_experience: float

    # =========================================================================
    # Debate State
    # =========================================================================
    # Current debate round
    current_round: int

    # Recruiter outputs (concerns/weaknesses)
    recruiter_arguments: list[Argument]
    recruiter_score: float  # 0-100, lower = more concerns

    # Coach outputs (strengths/positives)
    coach_arguments: list[Argument]
    coach_score: float  # 0-100, higher = more strengths

    # All debate rounds
    debate_rounds: list[DebateRound]

    # =========================================================================
    # Judge Decision
    # =========================================================================
    score_difference: float  # Absolute difference between recruiter and coach
    should_redebate: bool
    final_verdict: Verdict | None

    # =========================================================================
    # Output Generation
    # =========================================================================
    skill_gaps: list[SkillGap]
    cover_letter: str | None
    generated_resume: str | None
    improvement_suggestions: list[str]

    # =========================================================================
    # Metadata
    # =========================================================================
    error: str | None
    processing_started_at: str
    tokens_used: int
    messages: list[dict[str, Any]]  # For debugging/logging
