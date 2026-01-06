from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Lumina Backend"
    version: str = "0.1.0"
    debug: bool = True

    database_url: Optional[str] = None


settings = Settings()
