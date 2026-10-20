import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.business import ContentArticle, ContentVariant
from app.models.user import User


def test_content_library_pages_and_batches_platforms(client, login_as):
    auth = {"Authorization": f"Bearer {login_as('operator', 'Operator@123456')['access_token']}"}
    marker = f"library-{uuid.uuid4().hex}"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "operator"))
        articles = [
            ContentArticle(
                title=f"{marker}-{i:02d}", source_text="分页回归测试正文", created_by=user.id
            )
            for i in range(23)
        ]
        db.add_all(articles)
        db.flush()
        ids = [row.id for row in articles]
        db.add_all(
            [
                ContentVariant(
                    article_id=ids[-1],
                    platform="WEIBO",
                    version_no=i,
                    title="重复平台版本",
                    content_text="平台标记需要去重",
                )
                for i in (1, 2)
            ]
        )
        db.commit()
    try:
        first = client.get("/api/articles", params={"keyword": marker}, headers=auth).json()["data"]
        second = client.get(
            "/api/articles", params={"keyword": marker, "page": 2}, headers=auth
        ).json()["data"]
        assert first["total"] == second["total"] == 23
        assert len(first["items"]) == 20 and len(second["items"]) == 3
        assert {row["id"] for row in first["items"]}.isdisjoint(
            row["id"] for row in second["items"]
        )
        newest = next(row for row in first["items"] if row["id"] == ids[-1])
        assert newest["platforms"] == ["WEIBO"]
        assert newest["variantCount"] == 2
        old = client.get(f"/api/articles/{ids[0]}", headers=auth)
        assert old.status_code == 200 and old.json()["data"]["title"] == f"{marker}-00"
        filtered = client.get(
            "/api/articles", params={"keyword": marker, "platform": "WEIBO"}, headers=auth
        ).json()["data"]
        assert filtered["total"] == 1
    finally:
        with SessionLocal() as db:
            for article in db.scalars(select(ContentArticle).where(ContentArticle.id.in_(ids))):
                db.delete(article)
            db.commit()
