from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ContentArticle(TimestampMixin, Base):
    __tablename__ = "content_article"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    keywords_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), index=True)
    variants: Mapped[list[ContentVariant]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ContentVariant(TimestampMixin, Base):
    __tablename__ = "content_variant"
    __table_args__ = (
        UniqueConstraint("article_id", "platform", "version_no", name="uq_variant_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("content_article.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(30), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    content_text: Mapped[str] = mapped_column(Text)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags_json: Mapped[list] = mapped_column(JSON, default=list)
    emoji_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    model_name: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    generation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    manual_edit_ratio: Mapped[float] = mapped_column(Float, default=0)
    review_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    review_detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    original_generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    article: Mapped[ContentArticle] = relationship(back_populates="variants")


class MediaAsset(Base):
    __tablename__ = "media_asset"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("content_article.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_variant.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str] = mapped_column(String(1000))
    thumbnail_url: Mapped[str] = mapped_column(String(1000))
    photographer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photographer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(String(100), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(30), default="BODY")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PlatformAccount(TimestampMixin, Base):
    __tablename__ = "platform_account"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_platform_account_user"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("sys_user.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    account_name: Mapped[str] = mapped_column(String(100))
    auth_type: Mapped[str] = mapped_column(String(30), default="NONE")
    publish_mode: Mapped[str] = mapped_column(String(30), default="MANUAL")
    app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="NOT_CONFIGURED")
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_logs: Mapped[list[PlatformAuthLog]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class PlatformAuthLog(Base):
    __tablename__ = "platform_auth_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_account_id: Mapped[int] = mapped_column(
        ForeignKey("platform_account.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500), default="")
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    account: Mapped[PlatformAccount] = relationship(back_populates="auth_logs")


class ActivityPrior(Base):
    __tablename__ = "activity_prior"
    __table_args__ = (
        UniqueConstraint("platform", "day_of_week", "hour_of_day", name="uq_activity_prior_slot"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    base_score: Mapped[float] = mapped_column(Float)
    source_description: Mapped[str] = mapped_column(String(255), default="人工维护的发布时间规则")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AccountActivityStat(Base):
    __tablename__ = "account_activity_stat"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("platform_account.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(30))
    day_of_week: Mapped[int] = mapped_column(Integer)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_impressions: Mapped[float] = mapped_column(Float, default=0)
    avg_engagement_rate: Mapped[float] = mapped_column(Float, default=0)
    avg_likes: Mapped[float] = mapped_column(Float, default=0)
    avg_comments: Mapped[float] = mapped_column(Float, default=0)
    avg_collects: Mapped[float] = mapped_column(Float, default=0)
    avg_shares: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PublishRecommendation(Base):
    __tablename__ = "publish_recommendation"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("content_article.id", ondelete="CASCADE"))
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_variant.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(30))
    recommended_at: Mapped[datetime] = mapped_column(DateTime)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(20))
    reason_json: Mapped[list] = mapped_column(JSON, default=list)
    alternative_times_json: Mapped[list] = mapped_column(JSON, default=list)
    algorithm_version: Mapped[str] = mapped_column(String(30), default="weighted-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PublishSchedule(TimestampMixin, Base):
    __tablename__ = "publish_schedule"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("content_article.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[int] = mapped_column(ForeignKey("content_variant.id", ondelete="CASCADE"))
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_account.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(30), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    publish_mode: Mapped[str] = mapped_column(String(30), default="MANUAL")
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retry_count: Mapped[int] = mapped_column(Integer, default=3)
    actual_publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    publish_package_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    logs: Mapped[list[PublishLog]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class PublishLog(Base):
    __tablename__ = "publish_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(50))
    request_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    schedule: Mapped[PublishSchedule] = relationship(back_populates="logs")


class EngagementMetric(TimestampMixin, Base):
    __tablename__ = "engagement_metric"
    __table_args__ = (
        UniqueConstraint("schedule_id", "metric_date", "data_source", name="uq_metric_source_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(30), index=True)
    metric_date: Mapped[date] = mapped_column(Date)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    collects: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    engagement_total: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0)
    group_type: Mapped[str] = mapped_column(String(30), default="RECOMMENDED_TIME")
    data_source: Mapped[str] = mapped_column(String(30), default="MANUAL")


class Experiment(TimestampMixin, Base):
    __tablename__ = "experiment"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50))
    hypothesis: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    samples: Mapped[list[ExperimentSample]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentSample(Base):
    __tablename__ = "experiment_sample"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiment.id", ondelete="CASCADE"), index=True
    )
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="SET NULL"), nullable=True
    )
    group_type: Mapped[str] = mapped_column(String(30))
    sample_label: Mapped[str] = mapped_column(String(255))
    metric_value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    experiment: Mapped[Experiment] = relationship(back_populates="samples")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    module: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class GenerationTask(TimestampMixin, Base):
    __tablename__ = "generation_task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("content_article.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    platforms_json: Mapped[list] = mapped_column(JSON, default=list)
    result_variant_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), default="")
    provider: Mapped[str] = mapped_column(String(50), default="")
    prompt_version: Mapped[str] = mapped_column(String(30), default="")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    platform_status_json: Mapped[dict] = mapped_column(JSON, default=dict)
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_setting"
    id: Mapped[int] = mapped_column(primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(100), unique=True)
    setting_value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
