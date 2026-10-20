from app.api.endpoints.schedules import _forwarded_public_ip


def test_direct_public_address_is_used_as_is() -> None:
    assert _forwarded_public_ip("8.8.8.8", "1.1.1.1", "") == "8.8.8.8"


def test_private_reverse_proxy_uses_forwarded_headers() -> None:
    assert _forwarded_public_ip("172.18.0.2", "1.1.1.1", "10.0.0.5, 9.9.9.9") == "1.1.1.1"


def test_non_ip_direct_host_is_rejected() -> None:
    assert _forwarded_public_ip("testclient", "1.1.1.1", "") == ""
