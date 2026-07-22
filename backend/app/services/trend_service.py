import asyncio
import html
import json
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

BAIDU_URL = "https://top.baidu.com/board?tab=realtime"
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
HEADERS = {"User-Agent": "ContentPilot/1.0 (+https://github.com/lix965996-art/ContentPilot)"}
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CACHE_SECONDS = 300


def parse_baidu_html(raw_html: str, limit: int = 20) -> list[dict[str, Any]]:
    match = re.search(r"<!--s-data:(.*?)-->", raw_html, re.S)
    if not match:
        raise ValueError("百度热榜页面没有返回可识别的榜单数据")
    payload = json.loads(html.unescape(match.group(1)))
    contents: list[dict[str, Any]] = []
    for card in payload.get("data", {}).get("cards", []):
        if card.get("component") == "hotList":
            contents.extend(card.get("content", []))
    fetched_at = datetime.now(UTC).isoformat()
    items = []
    for index, item in enumerate(contents[:limit], start=1):
        title = str(item.get("word") or item.get("query") or "").strip()
        if not title:
            continue
        score = item.get("hotScore")
        url = item.get("rawUrl") or item.get("url") or BAIDU_URL
        items.append(
            {
                "id": f"BAIDU-{index}-{abs(hash(title))}",
                "source": "BAIDU",
                "sourceName": "百度热榜",
                "rank": index,
                "title": title,
                "summary": str(item.get("desc") or "").strip(),
                "url": url,
                "imageUrl": item.get("img") or None,
                "heat": int(score) if str(score).isdigit() else None,
                "heatLabel": f"{score} 热度" if score else "实时上榜",
                "fetchedAt": fetched_at,
                "tags": [str(item.get("hotTag"))] if item.get("hotTag") else [],
            }
        )
    return items


async def fetch_baidu(limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HEADERS) as client:
        response = await client.get(BAIDU_URL)
        response.raise_for_status()
        return parse_baidu_html(response.text, limit)


async def fetch_hacker_news(limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HEADERS) as client:
        top_response = await client.get(HN_TOP_URL)
        top_response.raise_for_status()
        ids = top_response.json()[: min(limit, 20)]
        responses = await asyncio.gather(
            *(client.get(HN_ITEM_URL.format(item_id=item_id)) for item_id in ids),
            return_exceptions=True,
        )
    fetched_at = datetime.now(UTC).isoformat()
    items: list[dict[str, Any]] = []
    for rank, (item_id, response) in enumerate(zip(ids, responses, strict=True), start=1):
        if isinstance(response, BaseException) or response.status_code >= 400:
            continue
        item = response.json() or {}
        if item.get("type") != "story" or not item.get("title"):
            continue
        url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        score = int(item.get("score") or 0)
        comments = int(item.get("descendants") or 0)
        items.append(
            {
                "id": f"HACKER_NEWS-{item_id}",
                "source": "HACKER_NEWS",
                "sourceName": "Hacker News",
                "rank": rank,
                "title": item["title"],
                "summary": f"{score} points · {comments} comments",
                "url": url,
                "imageUrl": None,
                "heat": score,
                "heatLabel": f"{score} points",
                "fetchedAt": fetched_at,
                "tags": ["科技", "国际"],
            }
        )
    return items


async def _cached(source: str, limit: int, refresh: bool) -> list[dict[str, Any]]:
    cached = _cache.get(source)
    if not refresh and cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1][:limit]
    fetcher = fetch_baidu if source == "BAIDU" else fetch_hacker_news
    items = await fetcher(limit)
    _cache[source] = (time.monotonic(), items)
    return items


async def aggregate_trends(
    source: str = "ALL", limit: int = 20, query: str = "", refresh: bool = False
) -> dict[str, Any]:
    sources = ["BAIDU", "HACKER_NEWS"] if source == "ALL" else [source]
    results = await asyncio.gather(
        *(_cached(item, limit, refresh) for item in sources), return_exceptions=True
    )
    items: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    names = {"BAIDU": "百度热榜", "HACKER_NEWS": "Hacker News"}
    for source_name, result in zip(sources, results, strict=True):
        if isinstance(result, BaseException):
            states.append(
                {
                    "source": source_name,
                    "name": names[source_name],
                    "status": "FAILED",
                    "count": 0,
                    "error": str(result),
                }
            )
        else:
            items.extend(result)
            states.append(
                {
                    "source": source_name,
                    "name": names[source_name],
                    "status": "SUCCESS",
                    "count": len(result),
                    "error": None,
                }
            )
    if query:
        keyword = query.casefold()
        items = [
            item for item in items if keyword in (item["title"] + " " + item["summary"]).casefold()
        ]
    return {
        "items": items,
        "sources": states,
        "fetchedAt": datetime.now(UTC).isoformat(),
        "notice": "全部内容来自公开实时榜单；请打开原始来源核验事实后再发布。",
    }
