from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ContentPilot"
    app_env: str = "dev"
    app_timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api"

    database_url: str = "mysql+pymysql://root:123456@127.0.0.1:3306/socialflow?charset=utf8mb4"
    sqlite_fallback_url: str = "sqlite:///./socialflow.db"

    jwt_secret: str = Field(default="change-this-secret", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    jwt_refresh_expire_days: int = 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    app_demo_mode: bool = False
    allow_registration: bool = True
    admin_initial_password: str = ""
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 60
    unsplash_access_key: str = ""
    media_fallback_enabled: bool = False
    publish_mode: str = "manual"
    platform_credential_key: str = ""
    weibo_api_base_url: str = "https://api.weibo.com"
    weibo_upload_api_base_url: str = "https://upload.api.weibo.com"
    x_api_base_url: str = "https://api.x.com"
    x_oauth_authorize_url: str = "https://x.com/i/oauth2/authorize"
    x_oauth_token_url: str = "https://api.x.com/2/oauth2/token"
    wechat_api_base_url: str = "https://api.weixin.qq.com"
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_browser_publishing_enabled: bool = True
    wechat_browser_headless: bool = True
    wechat_browser_profile_root: str = ""
    xhs_mcp_base_url: str = "http://127.0.0.1:18060/mcp"
    xhs_mcp_binary_path: str = ""
    experimental_browser_publishing_enabled: bool = False
    toutiao_browser_publishing_enabled: bool = True
    toutiao_browser_headless: bool = True
    toutiao_browser_profile_root: str = ""
    wechatsync_cli_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
