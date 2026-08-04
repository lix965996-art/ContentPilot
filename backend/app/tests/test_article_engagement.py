def test_article_engagement_summary(client, login_as) -> None:
    login_data = login_as("viewer", "Viewer@123456")
    headers = {"Authorization": f"Bearer {login_data['access_token']}"}

    articles = client.get("/api/articles?page_size=1", headers=headers).json()["data"]["items"]
    assert articles
    article_id = articles[0]["id"]

    response = client.get(f"/api/analytics/articles/{article_id}/engagement", headers=headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["articleId"] == article_id
    assert "hasData" in payload
    assert "platforms" in payload

    batch = client.get(
        f"/api/analytics/articles/engagement?ids={article_id}",
        headers=headers,
    )
    assert batch.status_code == 200
    items = batch.json()["data"]["items"]
    if payload["hasData"]:
        assert items and items[0]["articleId"] == article_id
