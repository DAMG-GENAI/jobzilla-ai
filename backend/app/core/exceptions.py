"""
Custom Exception Classes

Define application-specific exceptions for clear error handling.
"""

from typing import Any


class KillMatchException(Exception):
    """Base exception for KillMatch application."""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ProfileParsingError(KillMatchException):
    """Error parsing resume or GitHub profile."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "PROFILE_PARSING_ERROR", details)


class JobSearchError(KillMatchException):
    """Error searching for jobs."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "JOB_SEARCH_ERROR", details)


class AgentExecutionError(KillMatchException):
    """Error during agent pipeline execution."""

    def __init__(
        self, message: str, agent_name: str, details: dict[str, Any] | None = None
    ):
        details = details or {}
        details["agent_name"] = agent_name
        super().__init__(message, "AGENT_EXECUTION_ERROR", details)


class MCPConnectionError(KillMatchException):
    """Error connecting to MCP server."""

    def __init__(
        self, message: str, server_name: str, details: dict[str, Any] | None = None
    ):
        details = details or {}
        details["server_name"] = server_name
        super().__init__(message, "MCP_CONNECTION_ERROR", details)


class EmbeddingError(KillMatchException):
    """Error generating embeddings."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "EMBEDDING_ERROR", details)


class DatabaseError(KillMatchException):
    """Database operation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "DATABASE_ERROR", details)
