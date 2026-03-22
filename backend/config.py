from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./meeting_jira.db"
    secret_key: str = "change-this-in-production-use-a-real-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # LLM Provider configuration
    llm_provider: str = "azure_anthropic"  # "anthropic" or "azure_anthropic"
    
    # Azure Anthropic configuration
    azure_anthropic_endpoint: str = ""
    azure_anthropic_api_key: str = ""
    azure_anthropic_model: str = ""

    # Direct Anthropic configuration
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-20250514"

    # Embedding Provider configuration
    embedding_provider: str = "azure_openai"  # "openai" or "azure_openai"
    
    # Azure OpenAI Embeddings configuration
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # Direct OpenAI configuration
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
