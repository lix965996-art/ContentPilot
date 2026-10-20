import base64
import io
import zipfile
from types import SimpleNamespace

import httpcore
import httpx
import pytest
from sqlalchemy import select

from app.api.endpoints import media, schedules
from app.core.exceptions import AppException
from app.core.paths import local_media_path
from app.db.session import SessionLocal
from app.models.business import MediaAsset
from app.services import image_service
from app.services.generation_service import LlmRuntime

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def runtime(provider="openai-compatible", model="image-test"):
    return LlmRuntime(
        provider=provider,
        api_key="isolated-test",
        base_url="https://provider.test/v1",
        model_name=model,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["silicon-url", "openai-url", "openai-base64", "data-url"])
async def test_image_response_protocols_keep_exact_validated_bytes(monkeypatch, shape):
    encoded = base64.b64encode(PNG).decode()
    body = {
        "silicon-url": {"images": [{"url": "https://image.test/result"}]},
        "openai-url": {"data": [{"url": "https://image.test/result"}]},
        "openai-base64": {"data": [{"b64_json": encoded}]},
        "data-url": {"data": [{"url": "data:image/png;base64," + encoded}]},
    }[shape]
    downloads = []

    async def post(*_args):
        return httpx.Response(
            200, request=httpx.Request("POST", "https://provider.test"), json=body
        )

    async def download(url):
        downloads.append(url)
        return ".png", PNG

    monkeypatch.setattr(image_service, "_post_image_request", post)
    monkeypatch.setattr(image_service, "_download_generated_image", download)
    suffix, content, _metadata = await image_service.generate_provider_image(
        runtime(), prompt="test", model="image-test"
    )
    assert (suffix, content) == (".png", PNG)
    assert len(downloads) == (1 if shape.endswith("-url") and shape != "data-url" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"data": []},
        {"data": [{"b64_json": "invalid!"}]},
        {"data": [{"b64_json": base64.b64encode(b"<html>not an image</html>").decode()}]},
        {"images": [{"url": "file:///sensitive.txt"}]},
    ],
)
async def test_invalid_provider_images_are_rejected_without_download(monkeypatch, body):
    async def post(*_args):
        return httpx.Response(
            200, request=httpx.Request("POST", "https://provider.test"), json=body
        )

    async def forbidden(*_args):
        pytest.fail("invalid image must not trigger network download")

    monkeypatch.setattr(image_service, "_post_image_request", post)
    monkeypatch.setattr(image_service, "_download_generated_image", forbidden)
    with pytest.raises(AppException) as error:
        await image_service.generate_provider_image(runtime(), prompt="test", model="image-test")
    assert error.value.code == 50221


@pytest.mark.asyncio
async def test_base64_size_is_checked_before_decoding(monkeypatch):
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 4)
    with pytest.raises(AppException, match="超过大小限制"):
        await image_service._provider_image_content(
            {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
        )


@pytest.mark.parametrize(
    "provider,model,expected",
    [
        ("siliconflow", "Qwen/Qwen-Image", {"image_size": "1664x928"}),
        ("openai", "gpt-image-1", {"size": "1536x1024"}),
        ("openai", "dall-e-3", {"size": "1792x1024"}),
        ("openai-compatible", "custom-image", {"size": "1664x928"}),
    ],
)
def test_provider_size_fields_follow_selected_protocol(provider, model, expected):
    payload = image_service._image_payload(
        runtime(provider, model), "test", model, "1664x928", None
    )
    assert {
        key: value for key, value in payload.items() if key in {"image_size", "size"}
    } == expected


def test_known_image_models_advertise_editing_without_mislabeling_generation_only_models():
    assert image_service.image_model_capabilities("gpt-image-1") == (True, True)
    assert image_service.image_model_capabilities("dall-e-3") == (True, False)
    assert image_service.image_model_capabilities("Qwen/Qwen-Image-Edit-2509") == (False, True)


@pytest.mark.asyncio
async def test_standard_image_edit_uses_multipart_edits_endpoint(monkeypatch, tmp_path):
    image = tmp_path / "source.png"
    image.write_bytes(PNG)
    monkeypatch.setattr(image_service, "local_media_path", lambda *_args, **_kwargs: image)
    captured = []

    async def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        image_service.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    suffix, content, _metadata = await image_service.generate_provider_image(
        runtime("openai", "gpt-image-1"),
        prompt="edit",
        model="gpt-image-1",
        source_asset=SimpleNamespace(image_url="/uploads/media/source.png"),
    )
    assert (suffix, content) == (".png", PNG)
    assert captured[0].url.path == "/v1/images/edits"
    assert captured[0].headers["content-type"].startswith("multipart/form-data;")
    assert PNG in captured[0].content


@pytest.mark.asyncio
async def test_unknown_provider_post_result_is_not_automatically_billed_twice(monkeypatch):
    calls = 0

    async def post(*_args):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("unknown image creation result")

    monkeypatch.setattr(image_service, "_post_image_request", post)
    with pytest.raises(AppException):
        await image_service.generate_provider_image(runtime(), prompt="test", model="image-test")
    assert calls == 1


@pytest.mark.asyncio
async def test_package_download_includes_remote_bytes_and_fails_explicitly_on_missing_image(
    monkeypatch,
):
    row = SimpleNamespace(
        created_by=1,
        platform="XIAOHONGSHU",
        publish_package_json={"images": ["https://image.test/selected.png"]},
    )
    database = SimpleNamespace(get=lambda *_args: row)

    async def download(_url):
        return ".png", PNG

    monkeypatch.setattr(schedules, "_download_generated_image", download)
    response = await schedules.download_publish_package(1, database, SimpleNamespace(id=1))
    content = b"".join([part async for part in response.body_iterator])
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.read("images/01.png") == PNG

    async def failed_download(_url):
        raise AppException(50221, "missing", 502)

    monkeypatch.setattr(schedules, "_download_generated_image", failed_download)
    with pytest.raises(AppException, match="未生成缺图发布包") as error:
        await schedules.download_publish_package(1, database, SimpleNamespace(id=1))
    assert error.value.code == 50223


def test_selected_remote_image_is_durable_local_and_preserves_attribution(
    client, login_as, monkeypatch
):
    async def download(_url):
        return ".png", PNG

    monkeypatch.setattr(media, "_download_generated_image", download)
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    article = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "远程素材本地化", "source_text": "验证联网选图能用于真实平台发布。"},
    ).json()["data"]
    payload = {
        "article_id": article["id"],
        "source": "WIKIMEDIA_COMMONS",
        "source_id": "source-identifier",
        "image_url": "https://image.test/original.jpg",
        "thumbnail_url": "https://image.test/thumb.jpg",
        "photographer_name": "Original author",
        "photographer_url": "https://example.org/author",
        "usage_type": "COVER",
    }
    first = client.post("/api/media/select", headers=auth, json=payload)
    assert first.status_code == 200, first.text
    item = first.json()["data"]
    path = local_media_path(item["imageUrl"])
    assert path and path.read_bytes() == PNG
    assert item["photographerName"] == "Original author"
    assert item["sourceId"] == "source-identifier"
    second = client.post("/api/media/select", headers=auth, json=payload)
    assert second.json()["data"]["id"] == item["id"]
    with SessionLocal() as db:
        assert (
            len(db.scalars(select(MediaAsset).where(MediaAsset.article_id == article["id"])).all())
            == 1
        )


def test_failed_remote_selection_does_not_replace_existing_cover(client, login_as, monkeypatch):
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    article = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "保留原有封面", "source_text": "失败的新图片不能取代当前封面。"},
    ).json()["data"]
    old = client.post(
        "/api/media/upload",
        headers=auth,
        data={"article_id": article["id"], "usage_type": "COVER"},
        files={"file": ("cover.png", PNG, "image/png")},
    ).json()["data"]

    async def failed(_url):
        raise AppException(50221, "远程图片下载失败", 502)

    monkeypatch.setattr(media, "_download_generated_image", failed)
    response = client.post(
        "/api/media/select",
        headers=auth,
        json={
            "article_id": article["id"],
            "source": "TEST",
            "image_url": "https://image.test/missing.png",
            "thumbnail_url": "https://image.test/missing.png",
            "usage_type": "COVER",
        },
    )
    assert response.status_code == 502
    rows = client.get(f"/api/articles/{article['id']}/media", headers=auth).json()["data"]
    assert next(row for row in rows if row["id"] == old["id"])["selected"] is True


def test_private_selected_image_is_blocked_before_any_connection(client, login_as, monkeypatch):
    async def forbidden(*_args, **_kwargs):
        pytest.fail("selecting a private image must not create a connection")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", forbidden)
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    article = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "阻止内网素材", "source_text": "不得通过图片选择访问内网服务。"},
    ).json()["data"]
    response = client.post(
        "/api/media/select",
        headers=auth,
        json={
            "article_id": article["id"],
            "source": "TEST",
            "image_url": "http://127.0.0.1/private.png",
            "thumbnail_url": "http://127.0.0.1/private.png",
            "usage_type": "COVER",
        },
    )
    assert response.status_code == 502
    assert "内网" in response.json()["message"]


def test_upload_rejects_html_disguised_as_png(client, login_as):
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    response = client.post(
        "/api/media/upload",
        headers=auth,
        files={"file": ("fake.png", b"<html>not an image</html>", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 40042


def test_attaching_historical_remote_asset_localizes_without_changing_library_source(
    client, login_as, monkeypatch
):
    async def download(_url):
        return ".png", PNG

    monkeypatch.setattr(media, "_download_generated_image", download)
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    article = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "旧远程素材", "source_text": "历史素材用于文章时必须本地化且保留来源。"},
    ).json()["data"]
    with SessionLocal() as db:
        source = MediaAsset(
            source="WIKIMEDIA_COMMONS",
            source_id="historical-source",
            image_url="https://image.test/library.png",
            thumbnail_url="https://image.test/thumb.png",
            photographer_name="Historical author",
            usage_type="BODY",
            selected=False,
        )
        db.add(source)
        db.commit()
        source_id = source.id
    response = client.post(
        f"/api/media/{source_id}/attach",
        headers=auth,
        json={"article_id": article["id"], "usage_type": "BODY"},
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]
    path = local_media_path(item["imageUrl"])
    assert path and path.read_bytes() == PNG
    assert item["photographerName"] == "Historical author"
    with SessionLocal() as db:
        assert db.get(MediaAsset, source_id).image_url == "https://image.test/library.png"
