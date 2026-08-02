import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.services.generation_service import LlmRuntime
from app.services.image_service import MEDIA_UPLOAD_DIR, generate_provider_image

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_image_provider_400_is_retried_and_recovers(monkeypatch) -> None:
    calls = 0

    async def fake_post(_runtime, _payload):
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", "https://api.example.com/images/generations")
        if calls == 1:
            return httpx.Response(
                400,
                request=request,
                json={"message": "temporary image validation failure"},
            )
        return httpx.Response(
            200,
            request=request,
            json={"images": [{"url": "https://example.com/generated.png"}], "seed": 7},
        )

    async def fake_download(_url):
        return ".png", PNG_BYTES

    monkeypatch.setattr("app.services.image_service._post_image_request", fake_post)
    monkeypatch.setattr("app.services.image_service._download_generated_image", fake_download)
    result = await generate_provider_image(
        LlmRuntime(
            provider="siliconflow",
            api_key="test-key",
            base_url="https://api.example.com",
            model_name="Qwen/Qwen-Image",
        ),
        prompt="生成一张简洁的科技插画",
        model="Qwen/Qwen-Image",
        image_size="1328x1328",
    )

    assert calls == 2
    assert result[0] == ".png"
    assert result[2]["seed"] == 7


@pytest.mark.asyncio
async def test_repeated_provider_400_returns_readable_error(monkeypatch) -> None:
    async def fake_post(_runtime, _payload):
        return httpx.Response(
            400,
            request=httpx.Request("POST", "https://api.example.com/images/generations"),
            json={"message": "bad request with internal provider details"},
        )

    monkeypatch.setattr("app.services.image_service._post_image_request", fake_post)
    with pytest.raises(AppException, match="图片生成服务连续两次拒绝"):
        await generate_provider_image(
            LlmRuntime(
                provider="siliconflow",
                api_key="test-key",
                base_url="https://api.example.com",
                model_name="Qwen/Qwen-Image",
            ),
            prompt="生成一张简洁的科技插画",
            model="Qwen/Qwen-Image",
            image_size="1328x1328",
        )


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_real_image_model_flow_and_transform(client: TestClient, login_as, monkeypatch) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "智能配图测试",
            "source_text": "这是一篇用于验证真实图片生成与图片改造工作流的文章内容。",
        },
    ).json()["data"]

    async def fake_models(_runtime):
        return ["Qwen/Qwen-Image", "Qwen/Qwen-Image-Edit-2509"]

    async def fake_generate(_runtime, **_kwargs):
        return ".png", PNG_BYTES, {"seed": 42, "inference": 1.2}

    monkeypatch.setattr("app.api.endpoints.media.list_image_models", fake_models)
    monkeypatch.setattr("app.api.endpoints.media.generate_provider_image", fake_generate)

    models = client.get("/api/media/image-models", headers=auth)
    assert models.status_code == 200
    assert models.json()["data"]["textToImage"] == ["Qwen/Qwen-Image"]

    generated = client.post(
        "/api/media/generate",
        headers=auth,
        json={
            "article_id": article["id"],
            "prompt": "专业编辑风格的城市高温主题插画，不要文字和水印",
            "model": "Qwen/Qwen-Image",
            "image_size": "1328x1328",
            "usage_type": "COVER",
        },
    )
    assert generated.status_code == 200
    generated_data = generated.json()["data"]
    assert generated_data["source"] == "AI_GENERATED"
    assert generated_data["imageUrl"].endswith(".png")

    transformed = client.post(
        "/api/media/transform",
        headers=auth,
        json={
            "article_id": article["id"],
            "asset_id": generated_data["id"],
            "prompt": "保留城市主体，改成清爽蓝色编辑插画风格，不要文字",
            "model": "Qwen/Qwen-Image-Edit-2509",
            "usage_type": "COVER",
        },
    )
    assert transformed.status_code == 200
    transformed_data = transformed.json()["data"]
    assert transformed_data["source"] == "AI_TRANSFORMED"

    for filename in (generated_data["sourceId"], transformed_data["sourceId"]):
        path = MEDIA_UPLOAD_DIR / filename
        if path.exists():
            path.unlink()


def test_external_image_can_be_detached_and_reselected_with_long_attribution(
    client: TestClient, login_as
) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "外部配图重复选择测试",
            "source_text": "验证长作者署名不会阻断图片添加，并支持移除后重新选择。",
        },
    ).json()["data"]
    image_url = "https://upload.wikimedia.org/example/reselect-image.jpg"
    payload = {
        "article_id": article["id"],
        "source": "WIKIMEDIA_COMMONS",
        "source_id": "commons-long-attribution",
        "image_url": image_url,
        "thumbnail_url": image_url,
        "photographer_name": "作者姓名" * 40,
        "photographer_url": "https://commons.wikimedia.org/wiki/File:example.jpg",
        "alt_text": "可重复选择的测试配图",
        "search_keyword": "测试",
        "usage_type": "BODY",
    }

    selected = client.post("/api/media/select", headers=auth, json=payload)
    assert selected.status_code == 200
    selected_data = selected.json()["data"]
    assert len(selected_data["photographerName"]) == 100

    detached = client.post(f"/api/media/{selected_data['id']}/detach", headers=auth)
    assert detached.status_code == 200
    assert detached.json()["data"]["selected"] is False

    reselected = client.post("/api/media/select", headers=auth, json=payload)
    assert reselected.status_code == 200
    assert reselected.json()["data"]["id"] == selected_data["id"]
    assert reselected.json()["data"]["selected"] is True
    rows = client.get(f"/api/articles/{article['id']}/media", headers=auth).json()["data"]
    assert sum(item["imageUrl"] == image_url for item in rows) == 1


def test_selected_body_image_can_replace_cover_without_losing_old_cover(
    client: TestClient, login_as
) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "封面切换测试",
            "source_text": "验证新封面生效后，旧封面仍作为正文图片保留。",
        },
    ).json()["data"]

    def select_image(name: str, usage_type: str) -> dict:
        response = client.post(
            "/api/media/select",
            headers=auth,
            json={
                "article_id": article["id"],
                "source": "WIKIMEDIA_COMMONS",
                "source_id": name,
                "image_url": f"https://example.com/{name}.jpg",
                "thumbnail_url": f"https://example.com/{name}.jpg",
                "alt_text": name,
                "usage_type": usage_type,
            },
        )
        assert response.status_code == 200
        return response.json()["data"]

    old_cover = select_image("old-cover", "COVER")
    new_cover = select_image("new-cover", "BODY")

    changed = client.post(f"/api/media/{new_cover['id']}/set-cover", headers=auth)
    assert changed.status_code == 200
    assert changed.json()["data"]["usageType"] == "COVER"
    assert changed.json()["data"]["selected"] is True

    rows = client.get(f"/api/articles/{article['id']}/media", headers=auth).json()["data"]
    old_row = next(item for item in rows if item["id"] == old_cover["id"])
    new_row = next(item for item in rows if item["id"] == new_cover["id"])
    assert old_row["usageType"] == "BODY"
    assert old_row["selected"] is True
    assert new_row["usageType"] == "COVER"
