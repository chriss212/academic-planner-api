from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    openai_max_output_tokens: int = 4096

    # Precios del modelo en USD por 1M de tokens (por defecto gpt-4o-mini).
    openai_price_input_per_1m: float = 0.15
    openai_price_output_per_1m: float = 0.60

    frontend_origin: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
