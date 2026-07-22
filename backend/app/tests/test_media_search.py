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
