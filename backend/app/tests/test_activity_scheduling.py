"""End-to-end coverage for import → activity analysis → recommendation → schedule."""

import io
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

WEEKS = 6


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_history_csv(platform: str = "WEIBO", account: str = "history-account") -> bytes:
    """Synthesise a history export whose best slot is deterministic (hour 20).

    Anchored to a recent Tuesday relative to "now" (instead of a fixed
    calendar date) so the fixed-size dataset always falls inside the default
    90-day activity/recommendation analysis window, regardless of when the
    test suite is executed.
    """
    header = (
        "platform,account_id,content_type,publish_time,views,impressions,"
        "likes,comments,shares,favorites,followers,source_type"
    )
    rows = [header]
    now = datetime.now()
    days_since_tuesday = ((now.weekday() - 1) % 7) or 7
    anchor = (now - timedelta(days=days_since_tuesday)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    base = anchor - timedelta(days=7 * (WEEKS - 1))
    for week in range(WEEKS):
        peak = base + timedelta(days=7 * week)
        rows.append(
            f"{platform},{account},KNOWLEDGE,{peak:%Y-%m-%d %H:%M},"
            "20000,22000,900,180,140,260,50000,ACCOUNT_HISTORY"
        )
        quiet = peak.replace(hour=3) + timedelta(days=2)
        rows.append(
            f"{platform},{account},KNOWLEDGE,{quiet:%Y-%m-%d %H:%M},"
            "18000,21000,40,3,2,6,50000,ACCOUNT_HISTORY"
        )
        noon = peak.replace(hour=12) + timedelta(days=1)
        rows.append(
            f"{platform},{account},NEWS,{noon:%Y-%m-%d %H:%M},"
            "9000,10000,220,30,18,40,50000,ACCOUNT_HISTORY"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def upload(client: TestClient, auth: dict, path: str, payload: bytes, **form: str):
    return client.post(
        path,
        headers=auth,
        files={"file": ("history.csv", io.BytesIO(payload), "text/csv")},
        data=form,
    )


def test_history_import_preview_validates_and_deduplicates(client: TestClient, login_as) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    payload = build_history_csv(platform="X", account="preview-account")
    broken = payload + b"X,preview-account,NEWS,not-a-date,1,1,1,1,1,1,1,ACCOUNT_HISTORY\n"

    preview = upload(client, auth, "/api/activity/history/preview", broken)
    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["mapping"]["publish_time"] == "publish_time"
    assert data["validRows"] == WEEKS * 3
    assert data["errorRows"] == 1
    assert data["errors"][0]["row"] == WEEKS * 3 + 2
    assert data["importableRows"] == WEEKS * 3
    assert len(data["preview"]) <= 20

    imported = upload(
        client, auth, "/api/activity/history/import", payload, default_source_type="ACCOUNT_HISTORY"
    )
    assert imported.status_code == 200
    batch = imported.json()["data"]
    assert batch["successCount"] == WEEKS * 3
    assert batch["duplicateCount"] == 0

    again = upload(client, auth, "/api/activity/history/import", payload)
    assert again.json()["data"]["successCount"] == 0
    assert again.json()["data"]["duplicateCount"] == WEEKS * 3

    summary = client.get("/api/activity/history/summary", headers=auth).json()["data"]
    assert any(item["platform"] == "X" for item in summary["items"])


def test_activity_analysis_and_recommendation_use_imported_history(
    client: TestClient, login_as
) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    upload(
        client,
        auth,
        "/api/activity/history/import",
        build_history_csv(platform="TOUTIAO", account="analysis-account"),
    )

    analysis = client.get(
        "/api/activity/analysis", headers=auth, params={"platform": "TOUTIAO"}
    ).json()["data"]
    assert analysis["sampleCount"] == WEEKS * 3
    assert len(analysis["weekday"]) == 7
    assert len(analysis["hourly"]) == 24
    assert len(analysis["heatmap"]) == 7 * 24
    assert analysis["completeness"]["score"] > 0
    best_hour = max(analysis["hourly"], key=lambda item: item["score"])
    assert best_hour["hour"] == 20
    types = {item["contentType"] for item in analysis["contentTypes"]}
    assert {"KNOWLEDGE", "NEWS"} <= types

    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "活跃度驱动的排期验证",
            "source_text": "这是一篇用于验证活跃度分析与发布时间推荐链路的原创文章，内容足够长。",
            "keywords": ["排期"],
        },
    ).json()["data"]
    # Generate all standard platform variants so this article does not become an
    # incomplete "latest article" for other order-dependent tests sharing the DB.
    client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article["id"],
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"],
        },
    )
    response = client.post(
        "/api/recommendations/publish-time",
        headers=auth,
        json={"article_id": article["id"], "platform": "TOUTIAO", "horizon_days": 7},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["algorithmVersion"] == "hybrid-v2"
    assert data["accountSampleCount"] == WEEKS * 3
    assert data["weights"]["history"] > 0
    assert len(data["alternatives"]) == 2
    assert data["dataSource"]["accountSampleCount"] == WEEKS * 3
    assert data["dataSufficiency"]["level"] in {"LOW", "MEDIUM", "HIGH"}
    assert data["narrative"]
    assert len(data["curve"]) == 24
    assert datetime.fromisoformat(data["recommendedAt"]).hour in (19, 20, 21)


def test_schedule_records_recommendation_basis_and_effect(client: TestClient, login_as) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    upload(
        client,
        auth,
        "/api/activity/history/import",
        build_history_csv(platform="XIAOHONGSHU", account="schedule-account"),
    )
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "推荐时间加入排期",
            "source_text": "这是一篇用于验证推荐时间落地到排期日历的原创文章，内容足够长。",
            "keywords": ["排期"],
        },
    ).json()["data"]
    task = client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article["id"],
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"],
        },
    ).json()["data"]
    task_variants = client.get(f"/api/generation/tasks/{task['taskId']}", headers=auth).json()[
        "data"
    ]["variants"]
    variant = next(item for item in task_variants if item["platform"] == "XIAOHONGSHU")

    recommendation = client.post(
        "/api/recommendations/publish-time",
        headers=auth,
        json={
            "article_id": article["id"],
            "variant_id": variant["id"],
            "platform": "XIAOHONGSHU",
            "horizon_days": 7,
        },
    ).json()["data"]

    created = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article["id"],
            "variant_id": variant["id"],
            "platform": "XIAOHONGSHU",
            "scheduled_at": recommendation["recommendedAt"],
            "publish_mode": "MANUAL_CONFIRM",
            "recommendation_id": recommendation["id"],
            "time_source": "RECOMMENDED",
        },
    )
    assert created.status_code == 200
    schedule = created.json()["data"]
    assert schedule["timeSource"] == "RECOMMENDED"
    assert schedule["usedRecommendedTime"] is True
    assert schedule["timeDeviationMinutes"] == 0
    assert schedule["recommendationSnapshotJson"]["algorithmVersion"] == "hybrid-v2"

    basis = client.get(
        f"/api/schedules/{schedule['id']}/recommendation-basis", headers=auth
    ).json()["data"]
    assert basis["timeSource"] == "RECOMMENDED"
    assert basis["recommendation"]["id"] == recommendation["id"]
    assert basis["slotEvidence"]["platform"] == "XIAOHONGSHU"

    conflict = client.get(
        "/api/schedules/conflict-check",
        headers=auth,
        params={"platform": "XIAOHONGSHU", "scheduled_at": schedule["scheduledAt"]},
    ).json()["data"]
    assert conflict["hasConflict"] is True

    effect = client.get("/api/analytics/recommendation-effect", headers=auth).json()["data"]
    assert effect["adoption"]["withRecommendation"] >= 1
    assert effect["adoption"]["adoptionRate"] > 0
    assert {item["name"] for item in effect["comparison"]} == {"推荐时段", "非推荐时段"}
    assert len(effect["experimentGroups"]) == 2


def test_history_import_rejects_unmapped_required_field(client: TestClient, login_as) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    payload = b"channel,when,likes\nWEIBO,2026-01-06 20:00,10\n"
    response = client.post(
        "/api/activity/history/preview",
        headers=auth,
        files={"file": ("odd.csv", io.BytesIO(payload), "text/csv")},
        data={"mapping": json.dumps({"platform": "channel"})},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 40044
    assert "publish_time" in body["data"]["missingFields"]


def test_viewer_cannot_import_history(client: TestClient, login_as) -> None:
    auth = headers(login_as("viewer", "Viewer@123456")["access_token"])
    response = upload(client, auth, "/api/activity/history/import", build_history_csv())
    assert response.status_code == 403


def test_batch_recommendation_and_schedule(client: TestClient, login_as) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    admin_auth = headers(login_as("admin", "Admin@123456")["access_token"])
    toutiao = client.put(
        "/api/platform-accounts/TOUTIAO",
        headers=admin_auth,
        json={
            "account_name": "批量排期头条号",
            "auth_type": "QR_LOGIN",
            "publish_mode": "BROWSER_PUBLISH",
        },
    )
    assert toutiao.status_code == 200, toutiao.text
    for platform in ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO"):
        upload(
            client,
            auth,
            "/api/activity/history/import",
            build_history_csv(platform=platform, account=f"{platform.lower()}-batch"),
        )

    accounts = {
        row["platform"]: row["id"]
        for row in client.get("/api/platform-accounts", headers=auth).json()["data"]
        if row.get("id")
    }
    assert "TOUTIAO" in accounts
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "跨平台批量推荐排期",
            "source_text": "这是一篇用于验证跨平台批量推荐与批量排期链路的原创文章，内容足够长。",
            "keywords": ["排期"],
        },
    ).json()["data"]
    task = client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article["id"],
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO"],
        },
    ).json()["data"]
    task_variants = client.get(f"/api/generation/tasks/{task['taskId']}", headers=auth).json()[
        "data"
    ]["variants"]
    variant_by_platform = {item["platform"]: item for item in task_variants}

    batch = client.post(
        "/api/recommendations/publish-time/batch",
        headers=auth,
        json={
            "article_id": article["id"],
            "window": "90D",
            "targets": [
                {
                    "platform": platform,
                    "account_id": accounts[platform],
                    "variant_id": variant_by_platform[platform]["id"],
                }
                for platform in ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO")
            ],
        },
    )
    assert batch.status_code == 200
    batch_data = batch.json()["data"]
    assert batch_data["successCount"] == 4
    assert batch_data["failureCount"] == 0
    assert len(batch_data["items"]) == 4
    for item in batch_data["items"]:
        assert item["success"] is True
        assert item["data"]["recommendedAt"]
        assert len(item["data"]["alternatives"]) == 2

    # Batch planning defers live OAuth/login checks; use each platform's real publish mode.
    mode_by_platform = {
        "WEIBO": "REAL_API",
        "XIAOHONGSHU": "MANUAL_CONFIRM",
        "WECHAT_OFFICIAL": "DRAFT_ONLY",
        "TOUTIAO": "BROWSER_PUBLISH",
    }
    schedule_batch = client.post(
        "/api/schedules/batch",
        headers=auth,
        json={
            "article_id": article["id"],
            "idempotency_key": f"batch-test-{article['id']}",
            "items": [
                {
                    "platform": item["platform"],
                    "variant_id": variant_by_platform[item["platform"]]["id"],
                    "account_id": accounts[item["platform"]],
                    "scheduled_at": item["data"]["recommendedAt"],
                    "recommended_at": item["data"]["recommendedAt"],
                    "recommendation_id": item["data"]["id"],
                    "time_source": "RECOMMENDED",
                    "publish_mode": mode_by_platform[item["platform"]],
                }
                for item in batch_data["items"]
            ],
        },
    )
    assert schedule_batch.status_code == 200
    schedule_data = schedule_batch.json()["data"]
    assert schedule_data["successCount"] == 4, schedule_data
    assert len(schedule_data["createdScheduleIds"]) == 4
    assert all(item["success"] for item in schedule_data["items"])


def test_activity_prior_covers_every_weekday_and_hour(client: TestClient, login_as) -> None:
    """The rule table must be a real 7x24 grid, not one weekday copied around."""
    auth = headers(login_as("admin", "Admin@123456")["access_token"])
    rows = client.get("/api/activity/platform-priors?platform=WEIBO", headers=auth)
    assert rows.status_code == 200, rows.text
    slots = {(row["dayOfWeek"], row["hourOfDay"]) for row in rows.json()["data"]}
    assert slots == {(weekday, hour) for weekday in range(7) for hour in range(24)}


def test_activity_prior_differs_across_the_week() -> None:
    from app.services.activity_prior_service import default_prior_score

    # Lifestyle discovery peaks at the weekend, work-hour reading collapses.
    assert default_prior_score("XIAOHONGSHU", 5, 20) > default_prior_score("XIAOHONGSHU", 0, 20)
    assert default_prior_score("WECHAT_OFFICIAL", 5, 8) < default_prior_score(
        "WECHAT_OFFICIAL", 0, 8
    )
    # The weekday commute peak shifts an hour later once nobody commutes.
    assert default_prior_score("WECHAT_OFFICIAL", 5, 9) > default_prior_score(
        "WECHAT_OFFICIAL", 5, 7
    )


def test_off_peak_prior_follows_a_diurnal_curve() -> None:
    """Hours without a named peak still have to rank sensibly against each other."""
    from app.services.activity_prior_service import default_prior_score

    deep_night = default_prior_score("WEIBO", 2, 3)
    mid_afternoon = default_prior_score("WEIBO", 2, 15)
    early_evening = default_prior_score("WEIBO", 2, 19)
    assert deep_night < mid_afternoon < early_evening
