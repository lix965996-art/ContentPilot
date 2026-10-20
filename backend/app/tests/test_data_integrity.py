"""Regressions for measurement provenance, import contracts and business time."""

import csv
import importlib.util
import io
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, inspect, select
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.api.endpoints.analytics import _save_metric
from app.api.endpoints.experiments import _results
from app.core.exceptions import AppException
from app.db.base import Base
from app.models.business import (
    ContentArticle,
    ContentEmbedding,
    ContentVariant,
    EngagementHistory,
    Experiment,
    ExperimentSample,
    PublishSchedule,
)
from app.schemas.business import MetricCreate
from app.services.activity_estimation_service import build_samples, estimate
from app.services.activity_service import business_now, count_rows, load_rows, parse_publish_time
from app.services.analytics_service import article_engagement, grouped, summarize
from app.services.content_embedding_service import EMBEDDING_VERSION
from app.services.engagement_feedback_service import FEEDBACK_SOURCE_NOTE, sync_schedule_feedback
from app.services.history_import_service import (
    commit_import,
    parse_rows,
)
from app.services.semantic_history_retrieval_service import _scope_embeddings


@pytest.fixture
def isolated_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def schedule(db: Session) -> PublishSchedule:
    article = ContentArticle(
        title="Isolated data regression", source_text="Independent test data", created_by=1
    )
    db.add(article)
    db.flush()
    variant = ContentVariant(
        article_id=article.id,
        platform="WEIBO",
        title=article.title,
        content_text=article.source_text,
    )
    db.add(variant)
    db.flush()
    published_at = business_now() - timedelta(days=1)
    row = PublishSchedule(
        article_id=article.id,
        variant_id=variant.id,
        platform="WEIBO",
        scheduled_at=published_at,
        actual_publish_at=published_at,
        status="PUBLISHED",
        idempotency_key=f"integrity-{article.id}",
        created_by=1,
    )
    db.add(row)
    db.flush()
    return row


def measurement(db, item, *, source="MANUAL", basis="FOLLOWERS", day=0, likes=100):
    payload = MetricCreate(
        schedule_id=item.id,
        platform="WEIBO",
        metric_date=date(2026, 7, 1) + timedelta(days=day),
        impressions=100,
        followers=1000,
        likes=likes,
        metric_basis=basis,
        data_source=source,
    )
    row = _save_metric(db, payload)
    db.add(row)
    db.flush()
    return row


def test_metric_platform_must_match_the_published_schedule(isolated_db):
    item = schedule(isolated_db)
    with pytest.raises(AppException, match="平台与排期平台不匹配"):
        _save_metric(
            isolated_db,
            MetricCreate(
                schedule_id=item.id,
                platform="BLUESKY",
                metric_date=date(2026, 10, 20),
                impressions=100,
                likes=10,
                metric_basis="IMPRESSIONS",
            ),
        )


def test_manual_and_csv_metrics_reject_mismatched_platform_without_losing_valid_rows(
    client, login_as
):
    from app.api.endpoints.analytics import HEADERS
    from app.db.session import SessionLocal

    auth = {"Authorization": f"Bearer {login_as('operator', 'Operator@123456')['access_token']}"}
    with SessionLocal() as db:
        item = schedule(db)
        db.commit()
        schedule_id, article_id = item.id, item.article_id
    invalid = {
        "schedule_id": schedule_id,
        "platform": "BLUESKY",
        "metric_date": "2026-10-20",
        "group_type": "RECOMMENDED_TIME",
        "impressions": 100,
        "likes": 10,
        "comments": 0,
        "collects": 0,
        "shares": 0,
        "followers": 0,
        "metric_basis": "IMPRESSIONS",
        "data_source": "MANUAL",
    }
    response = client.post("/api/analytics/manual", headers=auth, json=invalid)
    assert response.status_code == 400
    assert "平台与排期平台不匹配" in response.json()["message"]

    csv_data = io.StringIO()
    writer = csv.DictWriter(csv_data, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerow(invalid)
    writer.writerow({**invalid, "platform": "WEIBO", "data_source": "IMPORTED"})
    imported = client.post(
        "/api/analytics/import",
        headers=auth,
        files={"file": ("metrics.csv", csv_data.getvalue().encode(), "text/csv")},
    )
    assert imported.status_code == 200
    result = imported.json()["data"]
    assert result["successCount"] == 1 and result["errorCount"] == 1
    assert result["errors"][0]["row"] == 2
    assert "平台与排期平台不匹配" in result["errors"][0]["message"]
    detail = client.get(f"/api/analytics/articles/{article_id}/engagement", headers=auth)
    assert detail.json()["data"]["platforms"][0]["platform"] == "WEIBO"
    with SessionLocal() as db:
        from app.models.business import EngagementMetric

        metrics = db.scalars(
            select(EngagementMetric).where(EngagementMetric.schedule_id == schedule_id)
        ).all()
        assert len(metrics) == 1 and metrics[0].platform == "WEIBO"


def history(
    db,
    *,
    source="ACCOUNT_HISTORY",
    provenance=None,
    row_hash="history",
    basis="IMPRESSIONS",
    note=None,
    platform="WEIBO",
):
    moment = business_now() - timedelta(days=2)
    row = EngagementHistory(
        platform=platform,
        account_ref="sample-video",
        publish_time=moment,
        day_of_week=moment.weekday(),
        hour_of_day=moment.hour,
        views=1000,
        impressions=1000,
        likes=100,
        comments=2,
        shares=3,
        followers=1000,
        engagement_total=105,
        engagement_rate=0.105,
        engagement_score=50,
        metric_detail_json={
            "metricBasis": basis,
            "reach": 1000,
            "dataSource": provenance or "IMPORTED",
            "title": "content",
        },
        source_type=source,
        source_note=note,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row


def test_downloaded_history_template_can_be_imported_and_stays_simulated(client, login_as):
    auth = {"Authorization": f"Bearer {login_as('operator', 'Operator@123456')['access_token']}"}
    downloaded = client.get("/api/activity/history/template", headers=auth)
    assert downloaded.status_code == 200
    files = {
        "file": (
            "template.xlsx",
            downloaded.content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    preview = client.post("/api/activity/history/preview", headers=auth, files=files)
    assert preview.status_code == 200, preview.text
    row = preview.json()["data"]["preview"][0]
    assert row["sourceType"] == "SIMULATED"
    assert row["publishTime"] == "2026-07-01T20:00:00"
    assert row["likes"] == 320 and row["metricBasis"] == "IMPRESSIONS"
    assert preview.json()["data"]["validRows"] == 1
    imported = client.post("/api/activity/history/import", headers=auth, files=files)
    assert imported.status_code == 200, imported.text
    assert imported.json()["data"]["successCount"] == 1
    assert imported.json()["data"]["sourceType"] == "SIMULATED"


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-01T16:00:00Z",
        "2026-07-02T00:00:00+08:00",
        datetime(2026, 7, 1, 16, tzinfo=UTC),
        datetime(2026, 7, 2, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_same_instant_uses_the_same_business_weekday_and_hour(value):
    parsed = parse_publish_time(value)
    assert parsed == datetime(2026, 7, 2)
    records = [{"platform": "WEIBO", "publish_time": value, "likes": 100, "impressions": 1000}]
    imported = parse_rows(records, {key: key for key in records[0]})["rows"][0]
    assert (imported["dayOfWeek"], imported["hourOfDay"]) == (3, 0)


def test_followers_basis_survives_persistence_feedback_and_all_summaries(isolated_db):
    db = isolated_db
    item = schedule(db)
    measured = measurement(db, item)
    db.expire(measured)
    assert measured.metric_basis == "FOLLOWERS" and measured.engagement_rate == 0.1
    feedback = sync_schedule_feedback(db, item.id)
    assert feedback.engagement_rate == 0.1
    assert feedback.metric_detail_json["metricBasis"] == "FOLLOWERS"
    assert feedback.metric_detail_json["reach"] == 1000
    for result in [
        summarize(db),
        grouped(db, "platform")[0],
        article_engagement(db, item.article_id)["totals"],
    ]:
        assert result["engagementRate"] == 10
        assert result["metricBasis"] == "FOLLOWERS" and result["rateAvailable"]
    sample = build_samples([feedback], {}, now=business_now())[0]
    assert sample.engagement_rate == 0.1


def test_simulation_cannot_create_or_overwrite_genuine_feedback(isolated_db):
    db = isolated_db
    item = schedule(db)
    measurement(db, item, source="SIMULATED")
    assert sync_schedule_feedback(db, item.id) is None
    measurement(db, item, source="MANUAL", day=1)
    row = sync_schedule_feedback(db, item.id)
    assert row.source_type == "ACCOUNT_HISTORY" and row.likes == 100
    measurement(db, item, source="SIMULATED", day=2, likes=900)
    assert sync_schedule_feedback(db, item.id).likes == 100
    real = summarize(db)
    assert real["sampleCount"] == 1 and real["engagementRate"] == 10
    assert real["excludedSimulatedCount"] == 2
    demo = summarize(db, data_scope="SIMULATED")
    assert demo["sampleCount"] == 2 and demo["simulatedCount"] == 2
    assert summarize(db, data_scope="ALL")["engagementRate"] is None


def test_unknown_or_mixed_basis_is_visible_without_a_guessed_rate(isolated_db):
    db = isolated_db
    item = schedule(db)
    measurement(db, item, basis="UNKNOWN")
    assert sync_schedule_feedback(db, item.id) is None
    unknown = summarize(db)
    assert unknown["engagementRate"] is None and not unknown["rateAvailable"]
    assert unknown["unknownBasisCount"] == 1 and unknown["sampleCount"] == 1
    measurement(db, item, basis="FOLLOWERS", day=1)
    mixed = summarize(db)
    assert mixed["metricBasis"] == "MIXED" and mixed["engagementRate"] is None
    assert (
        next(item for item in mixed["byBasis"] if item["metricBasis"] == "FOLLOWERS")[
            "engagementRate"
        ]
        == 10
    )
    measurement(db, item, basis="IMPRESSIONS", day=2)
    assert len(summarize(db)["byBasis"]) == 3


def test_simulation_and_legacy_simulation_are_absent_from_retrieval_and_estimation(isolated_db):
    db = isolated_db
    real = history(db, row_hash="real")
    fake = history(db, source="SIMULATED", row_hash="fake")
    contaminated = history(db, provenance="SIMULATED", row_hash="legacy-fake")
    for row in (real, fake, contaminated):
        db.add(
            ContentEmbedding(
                ref_type="HISTORY",
                content_id=row.id,
                platform=row.platform,
                embedding_model="test",
                embedding_version=EMBEDDING_VERSION,
                vector_json=[1.0, 0.0],
                text_hash=row.row_hash,
            )
        )
    db.flush()
    assert count_rows(db) == 1
    assert count_rows(db, include_simulated=True) == 3
    vectors, _ = _scope_embeddings(db, platform="WEIBO", account_id=None, exclude_article_id=None)
    assert [vector.content_id for vector in vectors] == [real.id]
    baseline = estimate(db, platform="WEIBO", account_id=None, similarity_by_row={real.id: 1.0})
    polluted = estimate(
        db,
        platform="WEIBO",
        account_id=None,
        similarity_by_row={real.id: 1.0, fake.id: 1.0, contaminated.id: 1.0},
    )
    assert baseline == polluted
    assert [
        sample.row_id
        for sample in build_samples([real, fake, contaminated], {}, now=business_now())
    ] == [real.id]


def test_real_import_is_not_deduplicated_against_demo_and_batch_scope_is_accurate(isolated_db):
    db = isolated_db
    records = [
        {
            "platform": "WEIBO",
            "account_id": "fixture",
            "publish_time": "2026-07-01 20:00",
            "likes": 100,
            "impressions": 1000,
            "source_type": "SIMULATED",
        }
    ]
    mapping = {key: key for key in records[0]}
    first = commit_import(
        db,
        filename="demo.csv",
        headers=list(mapping),
        records=records,
        mapping=mapping,
        user_id=None,
    )
    assert first.source_type == "SIMULATED" and first.success_count == 1
    records[0]["source_type"] = "ACCOUNT_HISTORY"
    second = commit_import(
        db,
        filename="real.csv",
        headers=list(mapping),
        records=records,
        mapping=mapping,
        user_id=None,
    )
    assert second.source_type == "ACCOUNT_HISTORY" and second.success_count == 1
    assert count_rows(db) == 1 and len(load_rows(db, include_simulated=True)) == 2


def test_experiments_keep_unknown_and_simulated_observations_separate():
    experiment = Experiment(
        samples=[
            ExperimentSample(
                group_type="CONTROL",
                metric_value_json={
                    "dataSource": "MANUAL",
                    "metricBasis": "FOLLOWERS",
                    "engagementRate": 10,
                },
            ),
            ExperimentSample(
                group_type="CONTROL",
                metric_value_json={
                    "dataSource": "SIMULATED",
                    "metricBasis": "FOLLOWERS",
                    "engagementRate": 90,
                },
            ),
            ExperimentSample(
                group_type="CONTROL",
                metric_value_json={"dataSource": "IMPORTED", "engagementRate": 100},
            ),
        ]
    )
    real = _results(experiment)["CONTROL"]
    assert real["excludedSimulatedCount"] == 1 and real["unknownBasisCount"] == 1
    assert real["engagementRate"] is None
    assert (
        next(item for item in real["byBasis"] if item["metricBasis"] == "FOLLOWERS")[
            "engagementRate"
        ]
        == 10
    )
    assert _results(experiment, "SIMULATED")["CONTROL"]["engagementRate"] == 90


def test_migration_preserves_counters_and_only_backfills_proven_provenance():
    engine = create_engine("sqlite://")
    old = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(old)
    old.tables["engagement_metric"]._columns.remove(old.tables["engagement_metric"].c.metric_basis)
    old.create_all(engine)
    with Session(engine) as db:
        real = history(db, row_hash="real-migrate")
        proven = history(db, provenance="SIMULATED", row_hash="fake-migrate")
        guessed = history(db, note="demo-like filename is not proof", row_hash="unknown-migrate")
        feedback = history(db, note=FEEDBACK_SOURCE_NOTE, row_hash="feedback-migrate")
        feedback.metric_detail_json = dict(feedback.metric_detail_json, scheduleId=99)
        public = history(
            db,
            platform="YOUTUBE",
            source="YOUTUBE_PUBLIC_SAMPLE",
            basis="VIEWS",
            row_hash="public-migrate",
        )
        experiment = Experiment(
            name="Migration proof", type="PUBLISH_TIME", hypothesis="test", created_by=1
        )
        db.add(experiment)
        db.flush()
        experiment.samples.append(
            ExperimentSample(
                group_type="CONTROL",
                sample_label="public proof",
                metric_value_json={
                    "dataSource": "YOUTUBE_PUBLIC_SAMPLE",
                    "videoId": public.account_ref,
                    "views": public.views,
                    "likes": public.likes,
                    "comments": public.comments,
                    "shares": public.shares,
                    "engagementRate": 10.5,
                },
            )
        )
        ids = (real.id, proven.id, guessed.id, feedback.id)
        db.commit()
    path = Path(__file__).resolve().parents[2] / "alembic/versions/20261011_0015_data_integrity.py"
    spec = importlib.util.spec_from_file_location("data_integrity_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert "metric_basis" in {
            column["name"] for column in inspect(connection).get_columns("engagement_metric")
        }
    with Session(engine) as db:
        real, proven, guessed, feedback = [db.get(EngagementHistory, row_id) for row_id in ids]
        assert real.source_type == guessed.source_type == "ACCOUNT_HISTORY"
        assert proven.source_type == "SIMULATED" and proven.likes == 100
        assert feedback.metric_detail_json["metricBasis"] == "UNKNOWN"
        sample = db.scalar(select(ExperimentSample))
        assert sample.metric_value_json["metricBasis"] == "VIEWS"
        assert sample.metric_value_json["engagementRate"] == 10.5
    engine.dispose()
