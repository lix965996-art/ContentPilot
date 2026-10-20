"""Platform activity priors: the rule-based 7x24 layer under the recommender.

The prior answers "how active is this platform's audience at weekday W, hour H"
before any of the account's own history is taken into account. It is the layer
that carries a brand-new account through cold start, and the layer the Bayesian
smoothing in ``activity_estimation_service`` shrinks towards when a slot has too
few real samples.

A prior score is built from three independent pieces:

1. ``PLATFORM_HOUR_PEAKS`` - the platform's known intra-day peaks (commute,
   lunch break, prime time).
2. ``OFF_PEAK_BY_HOUR`` - a smooth diurnal baseline for every hour that is not a
   named peak, so 03:00 never scores like 15:00.
3. ``WEEKDAY_FACTORS`` - how each platform's audience moves across the week.
   Work-hour readers (WeChat / Toutiao) drop on weekends, lifestyle feeds
   (Xiaohongshu) peak on weekends, news-like feeds (Weibo / X) stay flat.

On Saturday and Sunday the intra-day shape also moves: the commute peak
disappears and the morning starts roughly an hour later.

All values are published-behaviour rules of thumb, not measurements, so seeded
rows are tagged SIMULATED and operators can override any slot from the UI.
"""

from __future__ import annotations

# Named intra-day peaks per platform, expressed on a 0-100 scale (weekday shape).
PLATFORM_HOUR_PEAKS: dict[str, dict[int, float]] = {
    "WEIBO": {8: 78, 12: 82, 18: 88, 20: 96, 21: 91},
    "X": {8: 80, 12: 86, 17: 82, 20: 94, 22: 88},
    # No Bluesky-specific audience measurements yet; use only the generic
    # SIMULATED diurnal baseline until the user imports actual account history.
    "BLUESKY": {},
    # Federation-wide or instance-specific Mastodon audience measurements have
    # not been imported. This is a generic SIMULATED human rule, not evidence
    # about the connected instance's audience.
    "MASTODON": {},
    "XIAOHONGSHU": {9: 74, 12: 80, 19: 90, 20: 98, 21: 94, 22: 86},
    "WECHAT_OFFICIAL": {7: 83, 8: 90, 12: 76, 18: 82, 20: 88},
    "TOUTIAO": {7: 76, 8: 82, 12: 88, 18: 92, 20: 86, 22: 78},
}

# Baseline for hours that are not a named peak: deep night is genuinely dead,
# the afternoon is mediocre, the evening ramps back up.
OFF_PEAK_BY_HOUR: dict[int, float] = {
    0: 32,
    1: 22,
    2: 16,
    3: 14,
    4: 15,
    5: 20,
    6: 34,
    7: 46,
    8: 54,
    9: 58,
    10: 60,
    11: 62,
    12: 64,
    13: 58,
    14: 55,
    15: 56,
    16: 58,
    17: 63,
    18: 66,
    19: 69,
    20: 71,
    21: 68,
    22: 60,
    23: 46,
}

# Multiplier per weekday, Monday (0) through Sunday (6).
WEEKDAY_FACTORS: dict[str, tuple[float, ...]] = {
    # Read during working hours; the weekend drop is the largest of any platform.
    "WECHAT_OFFICIAL": (1.06, 1.05, 1.04, 1.03, 0.98, 0.84, 0.88),
    "TOUTIAO": (1.04, 1.04, 1.03, 1.02, 1.00, 0.90, 0.93),
    # News-like feeds barely care which day it is.
    "WEIBO": (0.98, 1.00, 1.01, 1.02, 1.03, 1.00, 1.02),
    "X": (0.99, 1.01, 1.02, 1.02, 1.03, 0.97, 0.99),
    # Lifestyle discovery: the weekend is prime time.
    "XIAOHONGSHU": (0.94, 0.96, 0.97, 0.99, 1.06, 1.12, 1.10),
}
DEFAULT_WEEKDAY_FACTORS = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

WEEKEND_DAYS = (5, 6)
# Weekend mornings run late, so a weekday 08:00 peak behaves like 09:00.
WEEKEND_MORNING_SHIFT_HOURS = 1
WEEKEND_SHIFT_UNTIL_HOUR = 12

SEED_SOURCE_DESCRIPTION = "公开活跃时段经验规则（SIMULATED）"


def weekday_factor(platform: str, weekday: int) -> float:
    factors = WEEKDAY_FACTORS.get(platform, DEFAULT_WEEKDAY_FACTORS)
    return factors[weekday % 7]


def default_prior_score(platform: str, weekday: int, hour: int) -> float:
    """Rule-based activity prior for one (platform, weekday, hour) slot."""
    peaks = PLATFORM_HOUR_PEAKS.get(platform, {})
    peak_hour = hour
    if weekday in WEEKEND_DAYS and hour <= WEEKEND_SHIFT_UNTIL_HOUR:
        peak_hour = hour - WEEKEND_MORNING_SHIFT_HOURS
    base = peaks.get(peak_hour, OFF_PEAK_BY_HOUR[hour])
    return round(min(100.0, base * weekday_factor(platform, weekday)), 1)


def prior_platforms() -> tuple[str, ...]:
    return tuple(PLATFORM_HOUR_PEAKS)


def prior_rules(platform: str) -> list[tuple[int, int, float]]:
    """Full 7x24 rule set for one platform as (weekday, hour, score) triples."""
    return [
        (weekday, hour, default_prior_score(platform, weekday, hour))
        for weekday in range(7)
        for hour in range(24)
    ]
