"""Validated, durable reply targets for operator-created publishing threads."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import MediaAsset, PublishSchedule

THREAD_FIELD = "thread"
THREAD_DEFINITION_FIELD = "threadDefinition"
THREAD_REPLY_FIELD = "threadReply"
_POST_URI = re.compile(r"at://did:[^/\s]+/app\.bsky\.feed\.post/[234567a-z]{13}")


@dataclass(frozen=True)
class ThreadContext:
    index: int
    count: int
    root: PublishSchedule | None = None
    parent: PublishSchedule | None = None

    @property
    def is_reply(self) -> bool:
        return self.index > 1

    def targets(self) -> dict[str, str] | None:
        if self.root is None or self.parent is None:
            return None
        if self.root.platform == "BLUESKY":
            return {
                "rootUri": str(self.root.external_id),
                "parentUri": str(self.parent.external_id),
            }
        return {"inReplyToId": str(self.parent.external_id)}


def _invalid(message: str = "串帖上下文无效，请核对原任务后处理") -> AppException:
    return AppException(40919, message, 409)


def _positive_int(value: Any) -> TypeGuard[int]:
    return type(value) is int and value > 0


def _descriptor(schedule: PublishSchedule) -> dict[str, Any]:
    package = schedule.publish_package_json or {}
    value = package.get(THREAD_FIELD)
    if not isinstance(value, dict):
        raise _invalid()
    index, count = value.get("partIndex"), value.get("partCount")
    if not (_positive_int(index) and _positive_int(count) and 1 <= index <= count <= 20):
        raise _invalid()
    allowed = {"partIndex", "partCount"}
    if index > 1:
        allowed |= {"rootScheduleId", "parentScheduleId"}
        if not all(_positive_int(value.get(key)) for key in allowed - {"partIndex", "partCount"}):
            raise _invalid()
    if set(value) != allowed:
        raise _invalid()
    frozen = package.get(THREAD_DEFINITION_FIELD)
    if frozen is not None and frozen != value:
        raise _invalid("串帖任务已尝试发布，不能更换顺序或回复目标")
    return value


def _published_peer(current: PublishSchedule, peer: PublishSchedule | None) -> PublishSchedule:
    if peer is None or peer.id == current.id:
        raise _invalid()
    if any(
        getattr(current, field) != getattr(peer, field)
        for field in ("article_id", "platform", "account_id", "created_by", "publish_mode")
    ):
        raise _invalid("串帖只能回复同文章、平台、账号和操作者的真实发布任务")
    if peer.status != "PUBLISHED" or peer.result_mode != "REAL_API" or not peer.external_id:
        raise _invalid("串帖前一段尚未确认真实发布，已停止后续发布")
    parsed = urlsplit(peer.published_url or "")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or not parsed.path.rstrip("/").endswith(f"/{peer.external_id.rsplit('/', 1)[-1]}")
    ):
        raise _invalid("串帖前一段没有有效的真实平台回执")
    if current.platform == "BLUESKY":
        if not _POST_URI.fullmatch(peer.external_id) or parsed.hostname != "bsky.app":
            raise _invalid()
    elif not re.fullmatch(r"[0-9]+", peer.external_id):
        raise _invalid()
    return peer


def validate_thread_context(db: Session, schedule: PublishSchedule) -> ThreadContext | None:
    package = schedule.publish_package_json or {}
    if THREAD_FIELD not in package:
        if THREAD_REPLY_FIELD in package or THREAD_DEFINITION_FIELD in package:
            raise _invalid("串帖任务的持久化上下文丢失，不能自动重发")
        return None
    if schedule.platform not in {"BLUESKY", "MASTODON"} or schedule.publish_mode != "REAL_API":
        raise _invalid()
    if schedule.account_id is None:
        raise _invalid()
    descriptor = _descriptor(schedule)
    index, count = descriptor["partIndex"], descriptor["partCount"]
    if index == 1:
        if package.get(THREAD_REPLY_FIELD) is not None:
            raise _invalid()
        return ThreadContext(index, count)
    root = _published_peer(
        schedule, db.get(PublishSchedule, descriptor["rootScheduleId"], populate_existing=True)
    )
    if _descriptor(root) != {"partIndex": 1, "partCount": count}:
        raise _invalid()
    parent = _published_peer(
        schedule, db.get(PublishSchedule, descriptor["parentScheduleId"], populate_existing=True)
    )
    cursor = parent
    for expected in range(index - 1, 0, -1):
        previous = _descriptor(cursor)
        if previous["partIndex"] != expected or previous["partCount"] != count:
            raise _invalid("串帖分段顺序不连续，已停止后续发布")
        if expected == 1:
            if cursor.id != root.id:
                raise _invalid()
        else:
            if previous["rootScheduleId"] != root.id:
                raise _invalid()
            cursor = _published_peer(
                schedule,
                db.get(PublishSchedule, previous["parentScheduleId"], populate_existing=True),
            )
    return ThreadContext(index, count, root, parent)


def freeze_thread_definition(db: Session, schedule: PublishSchedule) -> None:
    package = dict(schedule.publish_package_json or {})
    descriptor = _descriptor(schedule)
    package[THREAD_DEFINITION_FIELD] = dict(descriptor)
    schedule.publish_package_json = package
    db.commit()


def prepare_thread_publish(
    db: Session, schedule: PublishSchedule
) -> tuple[ThreadContext | None, dict[str, str] | None]:
    context = validate_thread_context(db, schedule)
    if context is None:
        return None, None
    if context.is_reply and (schedule.publish_package_json or {}).get("imageDescriptions") not in (
        None,
        [],
    ):
        raise _invalid("串帖后续分段不能复用首段配图")
    freeze_thread_definition(db, schedule)
    return context, context.targets()


def filter_thread_assets(
    context: ThreadContext | None, assets: Sequence[MediaAsset]
) -> list[MediaAsset]:
    return [] if context is not None and context.is_reply else list(assets)


def freeze_thread_reply(db: Session, schedule: PublishSchedule, reply: dict) -> dict:
    """Persist the exact remote reply reference before a write, or reject changes."""
    package = dict(schedule.publish_package_json or {})
    frozen = package.get(THREAD_REPLY_FIELD)
    if frozen is not None and frozen != reply:
        raise _invalid("串帖回复目标或版本已变化，不能重发到其他位置")
    package[THREAD_REPLY_FIELD] = reply
    schedule.publish_package_json = package
    db.commit()
    return reply


def thread_request_context(
    db: Session, account_id: int, platform: str, request: dict
) -> tuple[PublishSchedule | None, ThreadContext | None]:
    schedule_id = request.get("schedule_id")
    schedule = db.get(PublishSchedule, schedule_id) if _positive_int(schedule_id) else None
    if request.get("thread_reply") is None and (
        schedule is None or THREAD_FIELD not in (schedule.publish_package_json or {})
    ):
        return None, None
    if (
        schedule is None
        or schedule.account_id != account_id
        or schedule.platform != platform
        or schedule.idempotency_key != request.get("idempotency_key")
    ):
        raise _invalid("串帖发布需要绑定原账号和原排期任务")
    context = validate_thread_context(db, schedule)
    if context is None or request.get("thread_reply") != context.targets():
        raise _invalid("串帖请求与已审核排期的回复目标不一致")
    freeze_thread_definition(db, schedule)
    return schedule, context
