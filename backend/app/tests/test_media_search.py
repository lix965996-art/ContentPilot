import httpx
import pytest

from app.services.media_search_service import search_wikimedia_commons


@pytest.mark.asyncio
async def test_wikimedia_search_returns_real_network_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "commons.wikimedia.org"
        assert request.url.params["generator"] == "search"
        assert request.url.params["gsrnamespace"] == "6"
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "File:Urban heat island.png",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/full.png",
                                    "thumburl": "https://upload.wikimedia.org/thumb.png",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Urban_heat_island.png",
                                    "extmetadata": {
                                        "ImageDescription": {"value": "<b>Urban heat island</b>"},
                                        "Artist": {"value": "Example Author"},
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                        "LicenseUrl": {
                                            "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                                        },
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )

    items = await search_wikimedia_commons("高温城市", transport=httpx.MockTransport(handler))

    assert items == [
        {
            "id": "commons-42",
            "imageUrl": "https://upload.wikimedia.org/full.png",
            "thumbnailUrl": "https://upload.wikimedia.org/thumb.png",
            "source": "WIKIMEDIA_COMMONS",
            "photographerName": "Example Author",
            "photographerUrl": "https://commons.wikimedia.org/wiki/File:Urban_heat_island.png",
            "altText": "Urban heat island",
            "searchKeyword": "高温城市",
            "licenseName": "CC BY-SA 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        }
    ]


@pytest.mark.asyncio
async def test_wikimedia_search_optimizes_a_long_chinese_topic_after_no_results() -> None:
    queries: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["gsrsearch"]
        queries.append(query)
        if len(queries) == 1:
            return httpx.Response(200, json={"query": {"pages": []}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 7,
                            "title": "File:Weather station.jpg",
                            "imageinfo": [{"url": "https://upload.wikimedia.org/weather.jpg"}],
                        }
                    ]
                }
            },
        )

    items = await search_wikimedia_commons(
        "今年国家级气象站出现首个50°C，高温影响城市运行",
        transport=httpx.MockTransport(handler),
    )

    assert queries == [
        "今年国家级气象站出现首个50°C，高温影响城市运行",
        "extreme heat weather station city 50°C",
    ]
    assert items[0]["source"] == "WIKIMEDIA_COMMONS"
