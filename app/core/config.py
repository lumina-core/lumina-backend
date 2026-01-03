from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Lumina Backend"
    version: str = "0.1.0"
    debug: bool = True

    database_url: str


settings = Settings()
