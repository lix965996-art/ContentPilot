from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.services.schedule_optimization_service import PlatformTarget


def test_platform_target_normalizes_aware_operator_anchors() -> None:
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    expected = aware.astimezone(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)

    target = PlatformTarget(
        platform="WEIBO",
        account_id=None,
        variant_id=None,
        locked_time=aware,
        preferred_time=aware,
        original_best_time=aware,
    )

    assert target.locked_time == expected
    assert target.preferred_time == expected
    assert target.original_best_time == expected
    assert target.locked_time.tzinfo is None
