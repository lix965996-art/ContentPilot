from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

Platform = Literal["WEIBO", "WECHAT_OFFICIAL", "XIAOHONGSHU"]
AccountStatus = Literal[
    "NOT_CONFIGURED",
    "CONNECTING",
    "CONNECTED",
    "TOKEN_EXPIRED",
    "INVALID",
    "DISABLED",
    "MANUAL_ONLY",
]
PublishMode = Literal["REAL_API", "DRAFT_ONLY", "SUBMIT_PUBLISH", "MANUAL_CONFIRM"]


class PlatformAccountUpsert(BaseModel):
    account_name: str = Field(min_length=1, max_length=100)
    auth_type: Literal["NONE", "OAUTH2", "APP_SECRET"] = "NONE"
    publish_mode: PublishMode
    app_id: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    app_secret: str | None = Field(default=None, max_length=1000)
    access_token: str | None = Field(default=None, max_length=4000)
    refresh_token: str | None = Field(default=None, max_length=4000)
    token_expires_at: datetime | None = None
    redirect_uri: HttpUrl | None = None
    default_author: str | None = Field(default=None, max_length=100)
    default_cover_media_id: str | None = Field(default=None, max_length=255)
    default_cover_url: HttpUrl | None = None
    allow_submit_publish: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_platform_mode(self) -> "PlatformAccountUpsert":
        if self.publish_mode == "REAL_API" and not (self.client_id or self.app_id):
            raise ValueError("真实 API 模式必须配置 App ID 或 Client ID")
        return self


class WeiboOAuthStart(BaseModel):
    redirect_uri: HttpUrl


class ManualConfirmRequest(BaseModel):
    published_url: HttpUrl | None = None


class PublisherResultSchema(BaseModel):
    success: bool
    platform: Platform
    mode: str
    status: str
    external_id: str = ""
    published_url: str = ""
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""
    suggested_action: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
