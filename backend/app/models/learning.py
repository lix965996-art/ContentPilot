"""Immutable publishing evidence and durable, read-only measurement jobs."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UTC_TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")


class PublishedContentSnapshot(Base):
    __tablename__ = "published_content_snapshot"

    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(30))
    account_ref: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    content_json: Mapped[dict] = mapped_column(JSON)
    feature_available_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP)
    published_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP, server_default=func.now())


class MetricCollectionTask(Base):
    __tablename__ = "metric_collection_task"
    __table_args__ = (
        UniqueConstraint("schedule_id", "window_seconds", "request_key", name="uq_metric_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="CASCADE"), index=True
    )
    window_seconds: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    due_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claim_expires_at: Mapped[datetime | None] = mapped_column(UTC_TIMESTAMP, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTC_TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP, server_default=func.now())


class EngagementObservation(Base):
    __tablename__ = "engagement_observation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("metric_collection_task.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("publish_schedule.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(30), index=True)
    account_ref: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))
    observed_at: Mapped[datetime] = mapped_column(UTC_TIMESTAMP, index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTC_TIMESTAMP, nullable=True)
    age_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    window_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reposts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="ACCOUNT_API")
    adapter_version: Mapped[str] = mapped_column(String(30), default="counts-v1")
    __table_args__ = (UniqueConstraint("task_id", "attempt", name="uq_observation_attempt"),)
