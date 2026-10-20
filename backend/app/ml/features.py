"""Training-only text vocabulary and strictly as-of account history features."""

from __future__ import annotations

import bisect
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta

VERSION = "prepublication-v1"
BASE_NAMES = [
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "weekend",
    "text_length",
    "title_length",
    "hashtag_count",
    "url_count",
    "image_count",
    "has_question",
    "language",
    "mature_history_7d",
    "mature_history_30d",
    "history_log_mean",
    "days_since_mature_post",
    "cold_start",
    "video_duration",
    "content_category",
]
EXPLANATIONS = {
    "hour_sin": "候选发布时间",
    "hour_cos": "候选发布时间",
    "weekday_sin": "星期",
    "weekday_cos": "星期",
    "weekend": "周末",
    "text_length": "正文长度",
    "title_length": "标题长度",
    "hashtag_count": "话题数量",
    "url_count": "链接数量",
    "image_count": "图片数量",
    "has_question": "提问表达",
    "language": "语言",
    "mature_history_7d": "近7天成熟历史支持",
    "mature_history_30d": "近30天成熟历史支持",
    "history_log_mean": "既有历史互动",
    "days_since_mature_post": "最近成熟历史间隔",
    "cold_start": "冷启动",
    "video_duration": "视频时长",
    "content_category": "内容类别",
}


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("数据集时间必须携带 UTC 偏移")
    from datetime import UTC

    return result.astimezone(UTC)


def tokens(text: str) -> list[str]:
    normal = unicodedata.normalize("NFKC", text.lower())[:12000]
    words = re.findall(r"[a-z0-9]{2,30}", normal)
    chars = "".join(re.findall(r"[\u4e00-\u9fff]", normal))
    return words + [chars[i : i + 2] for i in range(min(4000, len(chars) - 1))]


def fit_schema(train: list[dict], *, semantic: bool = False, max_terms: int = 64) -> dict:
    frequencies: Counter = Counter()
    if semantic:
        for row in train:
            frequencies.update(set(tokens(row.get("title", "") + " " + row["text"])))
    vocabulary = sorted(frequencies, key=lambda term: (-frequencies[term], term))[:max_terms]
    return {
        "version": VERSION,
        "vocabulary": vocabulary,
        "idf": [math.log((1 + len(train)) / (1 + frequencies[t])) + 1 for t in vocabulary],
        "names": BASE_NAMES + [f"text_{i}" for i in range(len(vocabulary))],
        "textMode": "TRAIN_ONLY_TFIDF" if semantic else "STRUCTURE_ONLY",
        "categories": sorted({str(row.get("category", "")) for row in train}),
    }


class HistoryIndex:
    def __init__(self, rows: list[dict]):
        self.accounts: dict[str, list[tuple[datetime, datetime, dict]]] = defaultdict(list)
        for row in rows:
            if not row.get("account_known", True) or not row.get("observed_at"):
                continue
            self.accounts[row["account"]].append(
                (
                    timestamp(row["published_at"]),
                    timestamp(row["observed_at"]),
                    row,
                )
            )
        for history in self.accounts.values():
            history.sort(key=lambda item: item[0])
        self.times = {
            account: [item[0] for item in rows] for account, rows in self.accounts.items()
        }

    def previous(self, account: str, decision: datetime) -> list[tuple[datetime, datetime, dict]]:
        times = self.times.get(account, [])
        history = self.accounts.get(account, [])
        start = bisect.bisect_left(times, decision - timedelta(days=30))
        end = bisect.bisect_left(times, decision)
        return [item for item in history[start:end] if item[1] <= decision]


def vector(
    row: dict,
    schema: dict,
    index: HistoryIndex,
    *,
    candidate: datetime | None = None,
    decision: datetime | None = None,
) -> list[float]:
    if schema.get("version") != VERSION:
        raise ValueError("不支持的特征版本")
    published = candidate or timestamp(row["published_at"])
    asof = decision or timestamp(row["decision_at"])
    past = index.previous(row["account"], asof)
    seven = sum(p > asof - timedelta(days=7) for p, _, _ in past)
    log_mean = (
        sum(math.log1p(item["interactions"]) for _, _, item in past) / len(past) if past else 0
    )
    hours = published.hour + published.minute / 60
    weekday = published.weekday()
    text = row.get("text", "")
    result = [
        math.sin(2 * math.pi * hours / 24),
        math.cos(2 * math.pi * hours / 24),
        math.sin(2 * math.pi * weekday / 7),
        math.cos(2 * math.pi * weekday / 7),
        float(weekday >= 5),
        math.log1p(len(text)),
        math.log1p(len(row.get("title", ""))),
        float(len(row.get("hashtags", []))),
        float(len(re.findall(r"https?://", text))),
        float(row.get("image_count", 0)),
        float("?" in text or "？" in text),
        float(row.get("language") == "zh"),
        math.log1p(seven),
        math.log1p(len(past)),
        log_mean,
        min(30.0, (asof - past[-1][0]).total_seconds() / 86400) if past else 30.0,
        float(not past),
    ]
    counts = Counter(tokens(row.get("title", "") + " " + text))
    category = str(row.get("category", ""))
    categories = schema.get("categories", [])
    result.extend(
        [
            math.log1p(float(row.get("duration", 0))),
            float(categories.index(category) + 1) if category in categories else 0.0,
        ]
    )
    tfidf = [
        (1 + math.log(counts[term])) * idf if counts[term] else 0.0
        for term, idf in zip(schema["vocabulary"], schema["idf"], strict=True)
    ]
    norm = math.sqrt(sum(value**2 for value in tfidf)) or 1
    result.extend(value / norm for value in tfidf)
    if len(result) != len(schema["names"]) or not all(math.isfinite(v) for v in result):
        raise ValueError("特征维度或数值无效")
    return result
