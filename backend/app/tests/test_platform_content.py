import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.core.credentials import encrypt_secret
from app.publishers.official import WeiboPublisher
from app.services.platform_content import (
    build_weibo_status,
    build_x_post,
    build_xiaohongshu_package,
    normalize_topics,
    validate_platform_publish,
    x_weighted_length,
)


def test_weibo_status_uses_hook_as_first_line_and_formats_topics() -> None:
    status = build_weibo_status(
        "先说结论",
        "这是正文。",
        ["#内容运营#", " 内容 运营 ", "#内容运营#"],
    )
    assert status == "先说结论\n\n这是正文。\n\n#内容运营#"


def test_weibo_status_does_not_duplicate_existing_hook() -> None:
    status = build_weibo_status("先说结论", "先说结论\n正文", [])
    assert status == "先说结论\n正文"


def test_x_post_uses_plain_hashtags_and_weighted_length() -> None:
    post = build_x_post("先说结论", "这是正文。", ["#AI#", "内容运营"])
    assert post == "先说结论\n\n这是正文。\n\n#AI #内容运营"
    assert x_weighted_length("abc") == 3
    assert x_weighted_length("中文") == 4
    assert x_weighted_length("https://example.com/a/very/long/path") == 23


def test_x_preflight_rejects_more_than_280_weighted_characters() -> None:
    errors = validate_platform_publish(
        platform="X",
        title="",
        content="中" * 141,
        hashtags=[],
        images=[],
    )
    assert errors == ["X 帖子合计 282 个加权字符，最多允许 280 个"]


def test_xiaohongshu_package_separates_topics_and_uses_first_image_as_cover() -> None:
    package = build_xiaohongshu_package(
        title="二十字以内的标题",
        content="正文",
        hashtags=["#效率", " 工作流 "],
        images=["cover.jpg", "body.jpg"],
    )
    assert package["topics"] == ["效率", "工作流"]
    assert package["hashtags"] == ["#效率", "#工作流"]
    assert package["coverImage"] == "cover.jpg"
    assert package["coverImageIndex"] == 0
    assert package["imageOrder"] == [0, 1]


def test_xiaohongshu_package_rejects_overlong_title() -> None:
    with pytest.raises(ValueError, match="最多 20"):
        build_xiaohongshu_package(
            title="超过二十个字符的小红书标题需要在保存或发布之前被明确拒绝",
            content="正文",
            hashtags=[],
            images=[],
        )


def test_xiaohongshu_package_rejects_overlong_content() -> None:
    with pytest.raises(ValueError, match="最多 1000"):
        build_xiaohongshu_package(
            title="合规标题",
            content="正文" * 501,
            hashtags=[],
            images=["cover.jpg"],
        )


def test_platform_preflight_matches_xiaohongshu_publish_contract() -> None:
    errors = validate_platform_publish(
        platform="XIAOHONGSHU",
        title="合规标题",
        content="正文" * 501,
        hashtags=[],
        images=[],
    )
    assert "小红书正文最多 1000 个字符" in errors
    assert "小红书发布至少需要 1 张图片" in errors


def test_platform_preflight_rejects_overlong_weibo_with_image() -> None:
    errors = validate_platform_publish(
        platform="WEIBO",
        title="首句",
        content="正文" * 80,
        hashtags=["话题"],
        images=["cover.jpg"],
    )
    assert errors
    assert "140" in errors[0]


def test_weibo_text_publish_uses_update_endpoint_and_longtext(monkeypatch) -> None:
    captured: dict = {}

    async def fake_post(_client, url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={"idstr": "123", "user": {"idstr": "456"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    publisher = WeiboPublisher.__new__(WeiboPublisher)
    publisher.db = None
    publisher.account = SimpleNamespace(access_token_encrypted=encrypt_secret("token"))
    publisher.config = {"operation_ip": "8.8.8.8"}

    result = asyncio.run(
        publisher.publish(
            {
                "title": "",
                "content": "正文" * 80,
                "hashtags": [],
                "images": [],
            }
        )
    )

    assert result.success is True
    assert result.status == "PUBLISHED"
    assert captured["url"].endswith("/2/statuses/update.json")
    assert captured["data"]["rip"] == "8.8.8.8"
    assert captured["data"]["is_longtext"] == 1
    assert captured["files"] is None


def test_normalize_topics_removes_markers_and_duplicates() -> None:
    assert normalize_topics(["#话题#", " 话题 ", "#另一个"]) == ["话题", "另一个"]
