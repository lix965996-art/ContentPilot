import base64

from fastapi.testclient import TestClient

from app.services.image_service import MEDIA_UPLOAD_DIR

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
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
