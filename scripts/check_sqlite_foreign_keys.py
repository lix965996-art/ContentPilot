"""Verify the migrated SQLite schema with foreign keys enabled.

Deleting an article must preserve reusable media assets by setting
``media_asset.article_id`` to NULL, not by cascading the delete.
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, event, text


def main(url: str) -> None:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                "INSERT INTO content_article (title, source_text, status, created_by, keywords_json) "
                "VALUES ('FK 删除行为验证', '用于验证删除原文后素材保留的原文内容', 'DRAFT', 1, '[]')"
            )
        )
        article_id = connection.execute(text("SELECT last_insert_rowid()")).scalar()
        connection.execute(
            text(
                "INSERT INTO media_asset "
                "(article_id, source, image_url, thumbnail_url, usage_type, selected, tags_json, favorite) "
                "VALUES (:article_id, 'LOCAL_UPLOAD', '/uploads/fk.png', '/uploads/fk.png', "
                "'BODY', 0, '[]', 0)"
            ),
            {"article_id": article_id},
        )
        asset_id = connection.execute(text("SELECT last_insert_rowid()")).scalar()
        connection.execute(text("DELETE FROM content_article WHERE id = :id"), {"id": article_id})
        row = connection.execute(
            text("SELECT article_id FROM media_asset WHERE id = :id"), {"id": asset_id}
        ).first()
        violations = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
    assert row is not None, "media asset was deleted with the article"
    assert row[0] is None, "media asset must keep existing with article_id = NULL"
    assert not violations, f"foreign key violations: {violations}"
    print("sqlite foreign key check OK")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sqlite:///./var/tmp/fk-check.db")
