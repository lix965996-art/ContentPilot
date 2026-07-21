from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_complete_content_to_publish_flow(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    created = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "完整业务链路验证",
            "source_text": (
                "这是一篇用于验证内容生成、时间推荐、排期和模拟发布完整流程的原创文章。"
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
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant["id"],
            "platform": variant["platform"],
            "scheduled_at": scheduled_at,
            "publish_mode": "MOCK",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "MOCK_SUCCESS"

    repeated = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert repeated.status_code == 200
    assert repeated.json()["data"]["status"] == "MOCK_SUCCESS"


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
