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
    length: str = "MEDIUM"
    include_emoji: bool = True
    include_hashtags: bool = True
    preserve_meaning: int = Field(default=90, ge=50, le=100)


class VariantUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_text: str = Field(min_length=1, max_length=100_000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)


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
    publish_mode: Literal["MOCK", "MANUAL"] = "MANUAL"


class ScheduleUpdate(BaseModel):
    scheduled_at: datetime | None = None
    publish_mode: Literal["MOCK", "MANUAL"] | None = None


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


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,50}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    role: Literal["ADMIN", "OPERATOR", "VIEWER"] = "VIEWER"
