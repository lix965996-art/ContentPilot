import html
import re
from typing import Any

import httpx

WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
SEARCH_TIMEOUT_SECONDS = 15
USER_AGENT = "ContentPilot/1.0 (online image search)"

VISUAL_QUERY_TRANSLATIONS = {
    "人工智能": "artificial intelligence",
    "AI": "artificial intelligence",
    "高温": "extreme heat",
    "热浪": "heat wave",
    "气象": "weather station",
    "城市": "city",
    "气候": "climate change",
    "科技": "technology",
    "数据": "data analytics",
    "内容": "digital content",
    "社交媒体": "social media",
    "营销": "marketing",
    "教育": "education",
    "医疗": "healthcare",
    "经济": "economy",
    "环境": "environment",
    "旅行": "travel",
    "文化": "culture",
    "团队": "teamwork",
}


def _plain_text(value: str | None, fallback: str = "") -> str:
    if not value:
        return fallback
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split()) or fallback


def _search_candidates(keyword: str) -> list[str]:
    candidates = [keyword]
    translated = list(
        dict.fromkeys(
            english
            for chinese, english in VISUAL_QUERY_TRANSLATIONS.items()
            if chinese.lower() in keyword.lower()
        )
    )
    ascii_terms = re.findall(r"[A-Za-z0-9]+(?:[°℃][CF])?", keyword)
    optimized = " ".join([*translated[:4], *ascii_terms[:2]]).strip()
    if optimized and optimized.lower() != keyword.lower():
        candidates.append(optimized)
    return candidates


async def search_wikimedia_commons(
    keyword: str,
    *,
    limit: int = 15,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Search real, reusable media from Wikimedia Commons without an API key."""
    async with httpx.AsyncClient(
        timeout=SEARCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    ) as client:
        for search_query in _search_candidates(keyword):
            response = await client.get(
                WIKIMEDIA_API_URL,
                params={
                    "action": "query",
                    "format": "json",
                    "formatversion": 2,
                    "generator": "search",
                    "gsrsearch": search_query,
                    "gsrnamespace": 6,
                    "gsrlimit": limit,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 960,
                },
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", [])
            items: list[dict[str, Any]] = []
            for page in pages:
                image_info = (page.get("imageinfo") or [{}])[0]
                image_url = image_info.get("url")
                if not image_url:
                    continue
                metadata = image_info.get("extmetadata") or {}
                title = str(page.get("title") or "").removeprefix("File:")
                description = _plain_text(
                    (metadata.get("ImageDescription") or {}).get("value"), title or keyword
                )
                artist = _plain_text(
                    (metadata.get("Artist") or {}).get("value"), "Wikimedia Commons"
                )
                license_name = _plain_text(
                    (metadata.get("LicenseShortName") or {}).get("value"), "请查看原始授权"
                )
                items.append(
                    {
                        "id": f"commons-{page.get('pageid')}",
                        "imageUrl": image_url,
                        "thumbnailUrl": image_info.get("thumburl") or image_url,
                        "source": "WIKIMEDIA_COMMONS",
                        "photographerName": artist[:120],
                        "photographerUrl": image_info.get("descriptionurl"),
                        "altText": description[:500],
                        "searchKeyword": keyword,
                        "licenseName": license_name,
                        "licenseUrl": (metadata.get("LicenseUrl") or {}).get("value"),
                    }
                )
            if items:
                return items
    return []


async def search_unsplash(
    keyword: str,
    access_key: str,
    *,
    page: int = 1,
    limit: int = 15,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, transport=transport) as client:
        response = await client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": keyword, "page": page, "per_page": limit},
            headers={"Authorization": f"Client-ID {access_key}"},
        )
        response.raise_for_status()
    return [
        {
            "id": f"unsplash-{item['id']}",
            "imageUrl": item["urls"]["regular"],
            "thumbnailUrl": item["urls"]["small"],
            "source": "UNSPLASH",
            "photographerName": item["user"]["name"],
            "photographerUrl": item["user"]["links"]["html"],
            "altText": item.get("alt_description") or keyword,
            "searchKeyword": keyword,
            "licenseName": "Unsplash License",
            "licenseUrl": "https://unsplash.com/license",
        }
        for item in response.json().get("results", [])
    ]
