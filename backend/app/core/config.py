"""
Application Configuration

Load settings from environment variables using Pydantic Settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "KillMatch API"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # CORS
    cors_origins: list[str] = ["http://localhost:8501", "http://localhost:3000"]

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_environment: str = "us-east-1"
    pinecone_index_name: str = "killmatch-jobs"

    # GitHub
    github_token: str = ""

    # Gemini
    gemini_api_key: str = ""

    # Tavily
    tavily_api_key: str = ""

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/killmatch"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MCP Servers
    mcp_github_server_url: str = "http://localhost:8001"
    mcp_jobmarket_server_url: str = "http://localhost:8002"

    # Agent Configuration
    max_debate_rounds: int = 3
    redebate_threshold: float = 0.30  # Redebate if score difference > 30%


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
