from functools import lru_cache
from pathlib import Path
from pydantic import Field
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
    th2etl_output_dir: Path | None = None
    
    # JWT settings for token generation
    encrypt_key: str | None = Field(None, description="Secret key for signing JWT tokens")
    jwt_algorithm: str = Field("HS256", description="Algorithm used for JWT encoding")
    jwt_expiry_minutes: int = Field(60, description="Token expiry time in minutes")

    # Logging configuration
    log_dir: Path | None = Field(None, description="Directory to store log files.")
    log_level: str = Field("INFO", description="Global log level (DEBUG, INFO, WARNING, ERROR).")
    log_levels: str | None = Field(None, description="Fine-grained log levels (e.g., 'th2etl.scheduler:INFO,th2etl:WARNING').")

    # Base URL of the apowerb API the ADK blocs call. The seed reads it to
    # build each bloc's config, and it differs per deployment
    # (api-agent-dev / api-agent / api-scei).
    #
    # Declared here rather than left to the environment because pydantic reads
    # EVERY key of the .env file and this model forbids extras: an undeclared
    # ADK_BASE_URL in .env makes the whole service refuse to start, which on
    # 2026-08-07 left a production instance that would not have survived its
    # next restart.
    adk_base_url: str | None = Field(
        None, description="Base URL of the apowerb API used by ADK blocs."
    )

    api_key: str

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