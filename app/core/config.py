from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lumina Backend"
    version: str = "0.1.0"
    debug: bool = True


settings = Settings()
