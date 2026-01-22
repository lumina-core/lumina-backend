from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Lumina Backend"
    version: str = "0.1.0"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/lumina.db"

    # JWT 配置
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24小时
    jwt_refresh_token_expire_days: int = 7  # 7天

    # 邮箱配置 (163邮箱)
    smtp_host: str = "smtp.163.com"
    smtp_port: int = 465
    smtp_user: str = ""  # 你的163邮箱
    smtp_password: str = ""  # 163邮箱授权码
    smtp_from_name: str = "Lumina"

    # 验证码配置
    verification_code_expire_minutes: int = 10

    # 邀请裂变奖励配置
    invite_reward_inviter: int = 500  # 邀请人奖励积分
    invite_reward_invitee: int = 200  # 被邀请人奖励积分

    # 前端地址（用于生成邀请链接）
    frontend_url: str = "https://lumina.ai"


settings = Settings()
