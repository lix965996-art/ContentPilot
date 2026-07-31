from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def normalize_topic(value: Any) -> str:
    """Return the platform topic name without presentation markers."""
    return re.sub(r"[\s#]+", "", str(value or "")).strip()


def normalize_topics(values: Iterable[Any] | None, *, limit: int = 10) -> list[str]:
    topics: list[str] = []
    for value in values or []:
        topic = normalize_topic(value)
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) >= limit:
            break
    return topics


def build_weibo_status(title: str, content: str, hashtags: Iterable[Any] | None) -> str:
    """Build the exact Weibo status shown in the product preview.

    Weibo has no independent article-title field for a normal status, so the
    editor's "title" is treated as the first-line hook. Topics are rendered in
    Weibo's ``#话题#`` notation only at the publishing boundary.
    """
    hook = (title or "").strip()
    body = (content or "").strip()
    parts: list[str] = []
    if hook and not body.startswith(hook):
        parts.append(hook)
    if body:
        parts.append(body)
    topics = " ".join(f"#{topic}#" for topic in normalize_topics(hashtags))
    if topics:
        parts.append(topics)
    return "\n\n".join(parts)


_X_URL_PATTERN = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)
_X_SINGLE_WEIGHT_RANGES = (
    (0, 4351),
    (8192, 8205),
    (8208, 8223),
    (8242, 8247),
)


def x_weighted_length(value: str) -> int:
    """Return a conservative X-compatible weighted character count.

    X transforms every HTTP(S) URL to a fixed-length t.co URL. Most Latin
    characters count as one unit while CJK characters and most emoji count as
    two. Complex emoji sequences can be accepted more generously by X, so the
    server remains deliberately conservative before a real public post.
    """

    def plain_weight(text: str) -> int:
        return sum(
            1 if any(start <= ord(char) <= end for start, end in _X_SINGLE_WEIGHT_RANGES) else 2
            for char in text
        )

    total = 0
    offset = 0
    for match in _X_URL_PATTERN.finditer(value):
        total += plain_weight(value[offset : match.start()])
        total += 23
        offset = match.end()
    return total + plain_weight(value[offset:])


def build_x_post(title: str, content: str, hashtags: Iterable[Any] | None) -> str:
    """Build the exact text sent to X's official ``POST /2/tweets`` endpoint."""
    hook = (title or "").strip()
    body = (content or "").strip()
    parts: list[str] = []
    if hook and not body.startswith(hook):
        parts.append(hook)
    if body:
        parts.append(body)
    topics = " ".join(f"#{topic}" for topic in normalize_topics(hashtags, limit=4))
    if topics:
        parts.append(topics)
    return "\n\n".join(parts)


def build_xiaohongshu_package(
    *,
    title: str,
    content: str,
    hashtags: Iterable[Any] | None,
    images: Iterable[str] | None,
) -> dict[str, Any]:
    """Build a stable, manual-delivery package matching the XHS adapter fields."""
    normalized_title = (title or "").strip()
    normalized_content = (content or "").strip()
    if len(normalized_title) > 20:
        raise ValueError("小红书标题最多 20 个字符")
    if len(normalized_content) > 1000:
        raise ValueError("小红书正文最多 1000 个字符")
    image_list = [str(image).strip() for image in images or [] if str(image).strip()]
    topics = normalize_topics(hashtags)
    return {
        "title": normalized_title,
        "content": normalized_content,
        "topics": topics,
        # hashtags is retained for backwards-compatible package consumers.
        "hashtags": [f"#{topic}" for topic in topics],
        "images": image_list,
        "coverImage": image_list[0] if image_list else "",
        "coverImageIndex": 0 if image_list else None,
        "imageOrder": list(range(len(image_list))),
        "visibility": "public",
    }


def validate_platform_publish(
    *,
    platform: str,
    title: str,
    content: str,
    hashtags: Iterable[Any] | None,
    images: Iterable[str] | None,
) -> list[str]:
    """Validate the payload that will actually cross a platform boundary."""
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()
    image_list = [str(image).strip() for image in images or [] if str(image).strip()]
    errors: list[str] = []

    if not clean_content:
        errors.append("正文不能为空")

    if platform == "WEIBO":
        status = build_weibo_status(clean_title, clean_content, hashtags)
        if image_list and len(status) > 140:
            errors.append(f"图文微博合计 {len(status)} 个字符，官方单图发布接口最多支持 140 个字符")
    elif platform == "X":
        post = build_x_post(clean_title, clean_content, hashtags)
        weighted_length = x_weighted_length(post)
        if weighted_length > 280:
            errors.append(f"X 帖子合计 {weighted_length} 个加权字符，最多允许 280 个")
    elif platform == "XIAOHONGSHU":
        if not clean_title:
            errors.append("小红书标题不能为空")
        elif len(clean_title) > 20:
            errors.append("小红书标题最多 20 个字符")
        if len(clean_content) > 1000:
            errors.append("小红书正文最多 1000 个字符")
        if not image_list:
            errors.append("小红书发布至少需要 1 张图片")
    elif platform == "WECHAT_OFFICIAL":
        if not clean_title:
            errors.append("微信公众号标题不能为空")
        elif len(clean_title) > 64:
            errors.append("微信公众号标题最多 64 个字符")

    return errors
