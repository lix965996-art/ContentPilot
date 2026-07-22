from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Platform = Literal["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"]


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_text: str = Field(min_length=10, max_length=100_000)
    summary: str | None = Field(default=None, max_length=2000)
    topic: str | None = Field(default=None, max_length=100)
    target_audience: str | None = Field(default=None, max_length=150)
    tone: str | None = Field(default="专业自然", max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=20)


class ArticleUpdate(ArticleCreate):
    status: str | None = None


class GenerateRequest(BaseModel):
    article_id: int
    platforms: list[Platform] = Field(min_length=1)
    style: str = "专业自然"
    length: Literal["SHORT", "MEDIUM", "LONG"] = "MEDIUM"
    target_audience: str | None = Field(default=None, max_length=150)
    include_emoji: bool = True
    include_hashtags: bool = True
    preserve_meaning: int = Field(default=90, ge=50, le=100)
    generation_mode: Literal["QUICK", "DEEP"] = "QUICK"
    creative_goal: str = Field(default="知识分享", min_length=1, max_length=80)

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[Platform]) -> list[Platform]:
        return list(dict.fromkeys(value))


class VariantUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_text: str = Field(min_length=1, max_length=100_000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)


class WechatFormatRequest(BaseModel):
    theme: Literal["clean", "brand", "editorial"] = "clean"
    accent_color: str = Field(default="#1677ff", pattern=r"^#[0-9A-Fa-f]{6}$")
    font_size: int = Field(default=16, ge=14, le=20)
    line_height: float = Field(default=1.8, ge=1.4, le=2.2)
    paragraph_spacing: int = Field(default=16, ge=8, le=32)
    first_line_indent: bool = False
    link_footnotes: bool = True


class WechatFormatPreviewRequest(WechatFormatRequest):
    content_text: str = Field(min_length=1, max_length=100_000)


class KeywordRequest(BaseModel):
    article_id: int


class MediaSelectRequest(BaseModel):
    article_id: int
    variant_id: int | None = None
    source: str
    source_id: str | None = None
    image_url: str
    thumbnail_url: str
    photographer_name: str | None = None
    photographer_url: str | None = None
    alt_text: str | None = None
    search_keyword: str | None = None
    usage_type: Literal["COVER", "BODY"] = "BODY"


class RecommendationRequest(BaseModel):
    article_id: int
    variant_id: int | None = None
    platform: Platform
    target_date: date | None = None


class ScheduleCreate(BaseModel):
    article_id: int
    variant_id: int
    account_id: int | None = None
    platform: Platform
    scheduled_at: datetime
    publish_mode: Literal["REAL_API", "DRAFT_ONLY", "MANUAL_CONFIRM"] = "MANUAL_CONFIRM"


class ScheduleUpdate(BaseModel):
    scheduled_at: datetime | None = None
    account_id: int | None = None
    publish_mode: Literal["REAL_API", "DRAFT_ONLY", "MANUAL_CONFIRM"] | None = None


class MetricCreate(BaseModel):
    schedule_id: int
    platform: Platform
    metric_date: date
    impressions: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    collects: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    followers: int = Field(default=0, ge=0)
    group_type: Literal["RECOMMENDED_TIME", "FIXED_TIME"] = "RECOMMENDED_TIME"
    data_source: Literal["REAL", "MANUAL", "IMPORTED", "SIMULATED"] = "MANUAL"


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: Literal["CONTENT_EFFICIENCY", "PUBLISH_TIME"]
    hypothesis: str = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    control_description: str | None = None
    treatment_description: str | None = None
    metrics: dict = Field(default_factory=dict)

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, value: date | None, info):
        start = info.data.get("start_date")
        if value and start and value < start:
            raise ValueError("结束日期不能早于开始日期")
        return value


class ExperimentUpdate(BaseModel):
    name: str | None = None
    hypothesis: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    control_description: str | None = None
    treatment_description: str | None = None
    metrics: dict | None = None
    conclusion: str | None = None


class SettingUpdate(BaseModel):
    value: str = Field(max_length=5000)


class LlmConfigUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    base_url: str = Field(default="", max_length=1000)
    api_key: str = Field(default="", max_length=5000)
    model: str = Field(default="", max_length=100)
    input_price_per_million: float = Field(default=0, ge=0, le=1_000_000)
    output_price_per_million: float = Field(default=0, ge=0, le=1_000_000)
    currency: Literal["CNY", "USD"] = "CNY"

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str, info):
        if not value.startswith(("http://", "https://")):
            raise ValueError("接口地址必须以 http:// 或 https:// 开头")
        return value.rstrip("/")

    @field_validator("provider")
    @classmethod
    def reject_local_mock_provider(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.lower() == "mock":
            raise ValueError("不再支持本地模拟模型，请配置真实的大模型服务")
        return normalized


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,50}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    role: Literal["ADMIN", "OPERATOR", "VIEWER"] = "VIEWER"
