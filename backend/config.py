from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./meeting_jira.db"
    secret_key: str = "change-this-in-production-use-a-real-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Azure Anthropic configuration
    azure_anthropic_endpoint: str = ""
    azure_anthropic_api_key: str = ""
    azure_anthropic_model: str = ""

    # Azure OpenAI Embeddings configuration
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
