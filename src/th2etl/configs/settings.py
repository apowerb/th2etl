from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """ETL settings, loaded from environment variables or a .env file."""

    # Database connection settings
    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str = "secret"
    database_schema: str | None = None
    database_ssl_mode: str | None = None
    
    # Directory for pipeline run outputs
    pipelines_logs_dir: Path | None = None
    
    api_key: str
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_dsn(self) -> str:
        if self.database_url:
            return self.database_url

        ssl = f"?sslmode={self.database_ssl_mode}" if self.database_ssl_mode else ""
        return (
            f"postgresql://{self.database_user}:{self.database_password}@"
            f"{self.database_host}:{self.database_port}/{self.database_name}{ssl}"
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()