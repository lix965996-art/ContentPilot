"""Import form options must agree with the parser before the first upload."""

import io

import pytest

from app.services.history_import_service import SOURCE_TYPE_CHOICES


@pytest.mark.parametrize("source_type", ["RESEARCH_DATASET", "YOUTUBE_PUBLIC_SAMPLE"])
def test_history_field_options_and_preview_use_valid_input_sources(
    client, login_as, source_type
) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    metadata = client.get("/api/activity/history/fields", headers=headers).json()["data"]
    assert {item["value"] for item in metadata["sourceTypes"]} == set(SOURCE_TYPE_CHOICES)
    assert "MIXED" not in SOURCE_TYPE_CHOICES
    assert "PUBLIC_DATASET" not in SOURCE_TYPE_CHOICES
    assert "YOUTUBE_PUBLIC" not in SOURCE_TYPE_CHOICES
    raw = b"platform,publish_time,likes\nYOUTUBE,2025-01-01 12:00,10\n"
    response = client.post(
        "/api/activity/history/preview",
        headers=headers,
        files={"file": ("history.csv", io.BytesIO(raw), "text/csv")},
        data={"default_source_type": source_type},
    )
    assert response.status_code == 200
    preview = response.json()["data"]
    assert preview["importableRows"] == 1
    assert preview["sourceTypes"] == metadata["sourceTypes"]
    assert preview["preview"][0]["sourceType"] == source_type
