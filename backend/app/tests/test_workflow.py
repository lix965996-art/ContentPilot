from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.publishers.official import WeiboPublisher


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_complete_content_to_publish_flow(client: TestClient, login_as, monkeypatch) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    created = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "完整业务链路验证",
            "source_text": (
                "这是一篇用于验证内容生成、时间推荐、排期和真实发布适配器完整流程的原创文章。"
                "所有结果都应保存在测试数据库中。"
            ),
            "topic": "系统验证",
            "target_audience": "校园新媒体团队",
            "tone": "专业自然",
            "keywords": ["测试", "内容运营"],
        },
    )
    assert created.status_code == 200
    article_id = created.json()["data"]["id"]

    generated = client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article_id,
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"],
            "preserve_meaning": 90,
        },
    )
    assert generated.status_code == 200
    task_id = generated.json()["data"]["taskId"]
    task = client.get(f"/api/generation/tasks/{task_id}", headers=auth).json()["data"]
    assert task["status"] == "SUCCESS"
    assert len(task["variants"]) == 3
    variant = task["variants"][0]

    recommendation = client.post(
        "/api/recommendations/publish-time",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant["id"],
            "platform": variant["platform"],
        },
    )
    assert recommendation.status_code == 200
    assert recommendation.json()["data"]["algorithmVersion"] == "weighted-v1"

    scheduled_at = (datetime.now() + timedelta(days=3)).isoformat(timespec="seconds")
    accounts = client.get("/api/platform-accounts", headers=auth).json()["data"]
    account_id = next(item["id"] for item in accounts if item["platform"] == variant["platform"])
    configured = client.put(
        "/api/platform-accounts/WEIBO",
        headers=auth,
        json={
            "account_name": "真实接口测试微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "test-client-id",
            "app_secret": "test-client-secret",
            "access_token": "test-access-token",
        },
    )
    assert configured.status_code == 200
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        account.status = "CONNECTED"
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()

    async def official_publish(_self, _request):
        return PublishResult(
            True,
            "WEIBO",
            "REAL_API",
            "SUCCESS",
            external_id="official-weibo-status-id",
            published_url="https://weibo.com/test/official-weibo-status-id",
            detail={"real": True},
        )

    monkeypatch.setattr(WeiboPublisher, "publish", official_publish)
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant["id"],
            "platform": variant["platform"],
            "account_id": account_id,
            "scheduled_at": scheduled_at,
            "publish_mode": "REAL_API",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "SUCCESS"

    repeated = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert repeated.status_code == 200
    assert repeated.json()["data"]["status"] == "SUCCESS"


def test_wechat_variant_can_preview_and_save_formatting(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    articles = client.get("/api/articles?page_size=100", headers=auth).json()["data"]["items"]
    article_id = articles[0]["id"]
    variants = client.get(f"/api/articles/{article_id}/variants", headers=auth).json()["data"]
    variant = next(item for item in variants if item["platform"] == "WECHAT_OFFICIAL")
    profile = {
        "theme": "editorial",
        "accent_color": "#9a6b3f",
        "font_size": 17,
        "line_height": 1.9,
        "paragraph_spacing": 18,
        "first_line_indent": True,
        "link_footnotes": True,
    }

    themes = client.get("/api/formatting/wechat/profiles", headers=auth)
    assert themes.status_code == 200
    assert len(themes.json()["data"]) == 3

    preview = client.post(
        "/api/formatting/wechat/preview",
        headers=auth,
        json={"content_text": variant["contentText"], **profile},
    )
    assert preview.status_code == 200
    assert 'data-contentpilot-format="wechat-editorial"' in preview.json()["data"]["contentHtml"]

    saved = client.put(f"/api/variants/{variant['id']}/format", headers=auth, json=profile)
    assert saved.status_code == 200
    assert saved.json()["data"]["formatProfileJson"]["theme"] == "editorial"
    assert "border-bottom:2px" in saved.json()["data"]["contentHtml"]


def test_analytics_and_experiment_endpoints(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    schedules = client.get("/api/schedules", headers=auth).json()["data"]
    schedule = schedules[0]
    response = client.post(
        "/api/analytics/manual",
        headers=auth,
        json={
            "schedule_id": schedule["id"],
            "platform": schedule["platform"],
            "metric_date": (datetime.now() + timedelta(days=1)).date().isoformat(),
            "impressions": 1000,
            "likes": 80,
            "comments": 10,
            "collects": 20,
            "shares": 10,
            "followers": 3000,
            "group_type": "RECOMMENDED_TIME",
            "data_source": "MANUAL",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["engagementTotal"] == 120
    assert client.get("/api/analytics/overview", headers=auth).json()["data"]["sampleCount"] > 0

    experiment = client.post(
        "/api/experiments",
        headers=auth,
        json={
            "name": "接口实验验证",
            "type": "PUBLISH_TIME",
            "hypothesis": "推荐时间提高互动率",
            "control_description": "固定时间",
            "treatment_description": "推荐时间",
            "metrics": {"engagementRate": "互动率"},
        },
    )
    assert experiment.status_code == 200
    experiment_id = experiment.json()["data"]["id"]
    assert client.post(f"/api/experiments/{experiment_id}/start", headers=auth).status_code == 200
    assert client.post(f"/api/experiments/{experiment_id}/finish", headers=auth).status_code == 200


def test_viewer_cannot_mutate_content(client: TestClient, login_as) -> None:
    token = login_as("viewer", "Viewer@123456")["access_token"]
    response = client.post(
        "/api/articles",
        headers=headers(token),
        json={"title": "越权", "source_text": "查看者不应该能够创建或修改任何内容数据。"},
    )
    assert response.status_code == 403


def test_secret_setting_is_masked(client: TestClient, login_as) -> None:
    token = login_as("admin", "Admin@123456")["access_token"]
    auth = headers(token)
    updated = client.put(
        "/api/settings/llm.api_key",
        headers=auth,
        json={"value": "local-secret-key-for-test"},
    )
    assert updated.status_code == 200
    rows = client.get("/api/settings", headers=auth).json()["data"]
    secret = next(item for item in rows if item["settingKey"] == "llm.api_key")
    assert secret["settingValue"] == "••••••••"


def test_model_service_configuration_and_usage(client: TestClient, login_as, monkeypatch) -> None:
    token = login_as("admin", "Admin@123456")["access_token"]
    auth = headers(token)
    payload = {
        "provider": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "real-provider-test-key",
        "model": "Qwen/Qwen3-8B",
        "input_price_per_million": 2.5,
        "output_price_per_million": 10,
        "currency": "CNY",
    }
    saved = client.put("/api/settings/model-service", headers=auth, json=payload)
    assert saved.status_code == 200
    assert saved.json()["data"]["model"] == "Qwen/Qwen3-8B"

    async def official_models(_self, url, **_kwargs):
        return httpx.Response(
            200,
            json={"data": [{"id": "Qwen/Qwen3-8B"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", official_models)

    tested = client.post("/api/settings/model-service/test", headers=auth, json=payload)
    assert tested.status_code == 200
    assert tested.json()["data"]["connected"] is True
    assert tested.json()["data"]["models"] == ["Qwen/Qwen3-8B"]

    usage = client.get("/api/settings/model-service/usage?days=30", headers=auth)
    assert usage.status_code == 200
    assert usage.json()["data"]["totalTokens"] >= 0
    assert usage.json()["data"]["currency"] == "CNY"


def test_operator_cannot_manage_model_service(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    response = client.get("/api/settings/model-service", headers=headers(token))
    assert response.status_code == 403
