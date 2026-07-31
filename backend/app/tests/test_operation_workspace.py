from fastapi.testclient import TestClient


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_research_library_crud(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    created = client.post(
        "/api/research-items",
        headers=auth,
        json={
            "title": "可复用的研究选题",
            "summary": "来自公开来源的摘要",
            "url": "https://example.com/research-source",
            "source": "MANUAL",
            "source_id": "research-test-1",
            "topic_cluster": "内容运营",
            "tags": ["研究", "创作"],
        },
    )
    assert created.status_code == 200
    item_id = created.json()["data"]["id"]

    listed = client.get("/api/research-items?query=研究选题", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["tags"] == ["研究", "创作"]

    updated = client.put(
        f"/api/research-items/{item_id}",
        headers=auth,
        json={"status": "READY", "notes": "发布前核验原始数据"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "READY"

    archived = client.delete(f"/api/research-items/{item_id}", headers=auth)
    assert archived.status_code == 200
    listed = client.get("/api/research-items", headers=auth)
    assert all(item["id"] != item_id for item in listed.json()["data"])


def test_global_media_metadata_and_attach(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    uploaded = client.post(
        "/api/media/upload",
        headers=auth,
        data={"usage_type": "BODY"},
        files={"file": ("library-test.png", b"not-a-real-image", "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["data"]["id"]
    assert uploaded.json()["data"]["articleId"] is None

    updated = client.put(
        f"/api/media/{asset_id}",
        headers=auth,
        json={
            "title": "品牌素材",
            "collection": "品牌图库",
            "tags": ["品牌", "封面"],
            "favorite": True,
            "license_type": "内部授权",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["collection"] == "品牌图库"

    assets = client.get("/api/media/assets?query=品牌素材", headers=auth)
    assert assets.status_code == 200
    assert assets.json()["data"]["items"][0]["favorite"] is True

    articles = client.get("/api/articles?page_size=100", headers=auth).json()["data"]["items"]
    article_id = articles[0]["id"]
    attached = client.post(
        f"/api/media/{asset_id}/attach",
        headers=auth,
        json={"article_id": article_id, "usage_type": "COVER"},
    )
    assert attached.status_code == 200
    assert attached.json()["data"]["articleId"] == article_id
    attached_id = attached.json()["data"]["id"]

    detached = client.post(f"/api/media/{attached_id}/detach", headers=auth)
    assert detached.status_code == 200
    assert detached.json()["data"]["selected"] is False

    article_media = client.get(f"/api/articles/{article_id}/media", headers=auth)
    detached_row = next(item for item in article_media.json()["data"] if item["id"] == attached_id)
    assert detached_row["selected"] is False
    global_assets = client.get("/api/media/assets?query=品牌素材", headers=auth)
    assert any(item["id"] == asset_id for item in global_assets.json()["data"]["items"])


def test_operation_runs_and_schedule_backlog(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "运行中心与待排期测试",
            "source_text": "这是一段用于验证统一运行记录和日历待排期内容池的真实测试正文。",
            "topic": "系统验证",
            "keywords": ["运行中心"],
        },
    ).json()["data"]
    generated = client.post(
        "/api/generation/content",
        headers=auth,
        json={"article_id": article["id"], "platforms": ["WEIBO"]},
    )
    assert generated.status_code == 200
    task_id = generated.json()["data"]["taskId"]
    task = client.get(f"/api/generation/tasks/{task_id}", headers=auth).json()["data"]
    variant_id = task["variants"][0]["id"]
    assert client.post(f"/api/variants/{variant_id}/approve", headers=auth).status_code == 200

    runs = client.get("/api/operation-runs?run_type=GENERATION", headers=auth)
    assert runs.status_code == 200
    run = next(item for item in runs.json()["data"]["items"] if item["sourceId"] == task_id)
    assert run["type"] == "GENERATION"
    assert run["steps"][0]["name"] == "WEIBO"

    backlog = client.get("/api/schedules/backlog", headers=auth)
    assert backlog.status_code == 200
    assert any(item["variantId"] == variant_id for item in backlog.json()["data"])
