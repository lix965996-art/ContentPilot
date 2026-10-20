"""Shared recommendation constants used by scoring and analysis."""

from app.services.activity_prior_service import PLATFORM_HOUR_PEAKS

ALGORITHM_VERSION = "hybrid-v2"
LEGACY_ALGORITHM_VERSION = "weighted-v1"

DEFAULT_PEAKS = PLATFORM_HOUR_PEAKS

SLOT_MINUTES = (0, 30)
# Sample count at which the account history reaches half of its maximum weight.
HISTORY_HALF_LIFE = 20.0
MAX_HISTORY_WEIGHT = 0.60
# Schedules on the same platform closer than this are treated as a hard conflict.
CONFLICT_MINUTES = 30
# Same-account posts closer than this trigger a "posting too densely" warning.
DENSITY_MINUTES = 120
ACTIVE_SCHEDULE_STATUSES = ("PENDING", "RUNNING", "WAITING_MANUAL_CONFIRM")
