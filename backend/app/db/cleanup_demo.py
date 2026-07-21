"""Remove only the built-in demonstration business records.

Authentication users, roles, settings and any user-created article whose title is not
part of the built-in seed set are preserved. Run after taking a database backup.
"""

from sqlalchemy import delete, select

from app.db.seed import ARTICLE_SEEDS
from app.db.session import SessionLocal
from app.models.business import (
    ActivityPrior,
    ContentArticle,
    Experiment,
    PlatformAccount,
    SystemSetting,
)


def cleanup() -> dict[str, int]:
    removed: dict[str, int] = {}
    with SessionLocal() as db:
        article_titles = [item[0] for item in ARTICLE_SEEDS]
        article_ids = list(
            db.scalars(select(ContentArticle.id).where(ContentArticle.title.in_(article_titles)))
        )
        result = db.execute(delete(ContentArticle).where(ContentArticle.id.in_(article_ids)))
        removed["articles"] = result.rowcount or 0

        result = db.execute(
            delete(ActivityPrior).where(ActivityPrior.source_description.contains("SIMULATED"))
        )
        removed["activity_priors"] = result.rowcount or 0

        result = db.execute(
            delete(PlatformAccount).where(PlatformAccount.account_name.contains("演示"))
        )
        removed["platform_accounts"] = result.rowcount or 0

        # The initial two experiments are the only experiments created by the seed routine.
        seeded_experiments = ["AI 辅助内容适配效率实验", "推荐时间与固定时间对比实验"]
        result = db.execute(delete(Experiment).where(Experiment.name.in_(seeded_experiments)))
        removed["experiments"] = result.rowcount or 0

        for key, old_value, new_value in (
            ("llm.provider", "mock", "openai-compatible"),
            ("publish.mode", "mock", "manual"),
        ):
            row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
            if row and row.setting_value.lower() == old_value:
                row.setting_value = new_value
        db.commit()
    return removed


if __name__ == "__main__":
    print(cleanup())
