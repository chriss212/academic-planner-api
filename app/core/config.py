from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    anthropic_api_key: str
    ai_model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"

settings = Settings()