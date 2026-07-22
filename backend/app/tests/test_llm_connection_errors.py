import httpx

from app.schemas.business import LlmConfigUpdate
from app.services.llm_config_service import _connection_error_message, _model_query_params


def response(status: int, code: str = "") -> httpx.Response:
    return httpx.Response(
        status,
        request=httpx.Request("GET", "https://api.example.test/v1/models"),
        json={
            "error": {
                "code": code,
                "message": "Incorrect API key provided: sk-secret-must-not-leak",
            }
        },
    )


def test_connection_error_explains_invalid_key_without_reflecting_secret() -> None:
    message = _connection_error_message(response(401, "invalid_api_key"))

    assert "API Key 无效" in message
    assert "sk-secret" not in message


def test_connection_error_distinguishes_quota_from_rate_limit() -> None:
    assert "额度不足" in _connection_error_message(response(429, "insufficient_quota"))
    assert "请求过于频繁" in _connection_error_message(response(429, "rate_limit_exceeded"))


def test_llm_config_trims_accidental_api_key_whitespace() -> None:
    payload = LlmConfigUpdate(
        provider="openai",
        base_url="https://api.openai.com/v1/",
        api_key="  example-key\n",
    )

    assert payload.api_key == "example-key"
    assert payload.base_url == "https://api.openai.com/v1"


def test_siliconflow_model_query_only_returns_chat_models() -> None:
    assert _model_query_params("siliconflow") == {"type": "text", "sub_type": "chat"}
    assert _model_query_params("openai-compatible") is None
