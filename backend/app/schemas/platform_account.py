from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, IPvAnyAddress, field_validator, model_validator

from app.core.mastodon import normalize_instance_url

Platform = Literal["WEIBO", "WECHAT_OFFICIAL", "XIAOHONGSHU", "TOUTIAO", "X", "BLUESKY", "MASTODON"]
AccountStatus = Literal[
    "NOT_CONFIGURED",
    "CONNECTING",
    "CONNECTED",
    "TOKEN_EXPIRED",
    "INVALID",
    "DISABLED",
    "MANUAL_ONLY",
    "READY",
    "LOGIN_REQUIRED",
]
PublishMode = Literal[
    "REAL_API",
    "DRAFT_ONLY",
    "SUBMIT_PUBLISH",
    "MANUAL_CONFIRM",
    "CDP_PUBLISH",
    "MCP_PUBLISH",
    "BROWSER_PUBLISH",
    "BROWSER_DRAFT",
]


class PlatformAccountUpsert(BaseModel):
    account_name: str = Field(min_length=1, max_length=100)
    auth_type: Literal[
        "NONE", "OAUTH2", "APP_SECRET", "APP_PASSWORD", "ACCESS_TOKEN", "QR_LOGIN"
    ] = "NONE"
    publish_mode: PublishMode
    app_id: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    app_secret: str | None = Field(default=None, max_length=1000)
    identifier: str | None = Field(default=None, max_length=253)
    app_password: str | None = Field(default=None, max_length=1000)
    instance_url: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, max_length=4000)
    refresh_token: str | None = Field(default=None, max_length=4000)
    token_expires_at: datetime | None = None
    redirect_uri: HttpUrl | None = None
    operation_ip: IPvAnyAddress | None = None
    default_author: str | None = Field(default=None, max_length=100)
    default_cover_media_id: str | None = Field(default=None, max_length=255)
    default_cover_url: HttpUrl | None = None
    allow_submit_publish: bool = False
    allow_public_publish: bool = False
    enabled: bool = True

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        identifier = value.strip().removeprefix("@")
        if not identifier or any(character.isspace() for character in identifier):
            raise ValueError("账号标识不能为空或包含空白字符")
        return identifier.lower() if not identifier.startswith("did:") else identifier

    @field_validator("app_password")
    @classmethod
    def normalize_app_password(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("access_token")
    @classmethod
    def normalize_access_token(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("instance_url")
    @classmethod
    def validate_instance_url(cls, value: str | None) -> str | None:
        return normalize_instance_url(value) if value is not None else None

    @model_validator(mode="after")
    def validate_platform_mode(self) -> "PlatformAccountUpsert":
        if self.auth_type == "APP_PASSWORD" and not self.identifier:
            raise ValueError("应用密码模式必须配置账号标识")
        if self.auth_type == "ACCESS_TOKEN" and not self.instance_url:
            raise ValueError("访问令牌模式必须配置 Mastodon 服务器网址")
        if (
            self.publish_mode == "REAL_API"
            and self.auth_type not in {"APP_PASSWORD", "ACCESS_TOKEN"}
            and not (self.client_id or self.app_id)
        ):
            raise ValueError("真实 API 模式必须配置 App ID 或 Client ID")
        if self.operation_ip and not self.operation_ip.is_global:
            raise ValueError("发布操作 IP 必须是可路由的公网 IPv4 或 IPv6 地址")
        return self


class WeiboOAuthStart(BaseModel):
    redirect_uri: HttpUrl


class XOAuthStart(BaseModel):
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
