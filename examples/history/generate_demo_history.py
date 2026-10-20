"""Generate the SIMULATED demo history CSV used to exercise the import wizard.

The output is explicitly synthetic: it exists so the import / cleaning /
analysis pipeline can be demonstrated without any real platform data.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT = Path(__file__).with_name("demo-account-history-SIMULATED.csv")
HEADERS = [
    "platform",
    "account_id",
    "content_type",
    "publish_time",
    "views",
    "impressions",
    "likes",
    "comments",
    "shares",
    "favorites",
    "followers",
    "source_type",
]

PLATFORMS = {
    "WEIBO": {"followers": 48_000, "peak_hours": (12, 18, 20, 21)},
    "XIAOHONGSHU": {"followers": 31_500, "peak_hours": (12, 19, 20, 21, 22)},
    "WECHAT_OFFICIAL": {"followers": 22_800, "peak_hours": (7, 8, 12, 20)},
}
CONTENT_TYPES = ["KNOWLEDGE", "TUTORIAL", "NEWS", "OPINION", "LIFESTYLE"]
# Anchored to "now" (instead of a fixed calendar date) so the generated demo
# data keeps working with the default "last 90 days" analysis window no
# matter when this script is regenerated or the demo is run.
WEEKS = 16
START = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
    weeks=WEEKS
)


def hour_factor(hour: int, peaks: tuple[int, ...]) -> float:
    if hour in peaks:
        return 1.0
    if 7 <= hour <= 23:
        return 0.55
    return 0.18


def weekday_factor(weekday: int) -> float:
    return 1.0 if weekday in (1, 2, 3) else 0.88 if weekday < 5 else 0.72


def main() -> None:
    random.seed(20260803)
    rows: list[dict[str, object]] = []
    for platform, config in PLATFORMS.items():
        followers = config["followers"]
        for week in range(WEEKS):
            for _ in range(4):
                day = START + timedelta(days=7 * week + random.randint(0, 6))
                hour = random.choice(
                    list(config["peak_hours"]) + [9, 10, 14, 15, 16, 17, 23, 2, 5]
                )
                moment = day.replace(hour=hour, minute=random.choice((0, 30)))
                factor = hour_factor(hour, config["peak_hours"]) * weekday_factor(
                    moment.weekday()
                )
                content_type = random.choice(CONTENT_TYPES)
                views = int(followers * random.uniform(0.22, 0.55) * factor)
                impressions = int(views * random.uniform(1.05, 1.4))
                like_rate = random.uniform(0.012, 0.035) * factor
                likes = int(views * like_rate)
                comments = int(likes * random.uniform(0.06, 0.18))
                shares = int(likes * random.uniform(0.04, 0.14))
                favorites = int(likes * random.uniform(0.15, 0.45))
                rows.append(
                    {
                        "platform": platform,
                        "account_id": f"demo-{platform.lower()}",
                        "content_type": content_type,
                        "publish_time": moment.strftime("%Y-%m-%d %H:%M"),
                        "views": views,
                        "impressions": impressions,
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                        "favorites": favorites,
                        "followers": followers,
                        "source_type": "ACCOUNT_HISTORY",
                    }
                )
    rows.sort(key=lambda item: (item["platform"], item["publish_time"]))
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"已生成 {len(rows)} 行演示数据：{OUTPUT}")


if __name__ == "__main__":
    main()
