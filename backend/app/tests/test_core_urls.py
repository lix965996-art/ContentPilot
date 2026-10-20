import asyncio
import socket
import ssl
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from app.core import urls


def _validate(value: str, **kwargs) -> str:
    return asyncio.run(urls.ensure_public_http_url(value, **kwargs))


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError):
        _validate("file:///etc/passwd")


def test_rejects_loopback_literal() -> None:
    with pytest.raises(ValueError):
        _validate("http://127.0.0.1/image.png")


def test_rejects_private_dns_result(monkeypatch) -> None:
    monkeypatch.setattr(
        urls.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    )
    with pytest.raises(ValueError):
        _validate("https://example.com/image.png")


def test_accepts_public_dns_result(monkeypatch) -> None:
    monkeypatch.setattr(
        urls.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    assert _validate("https://example.com/image.png") == "https://example.com/image.png"


class WireStream(httpcore.AsyncNetworkStream):
    """Exercise real HTTP core serialization/parsing without external sockets."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.writes = []
        self.tls = []
        self.reads = 0
        self.closed = False

    async def read(self, max_bytes, timeout=None):
        self.reads += 1
        return self.responses.pop(0) if self.responses else b""

    async def write(self, buffer, timeout=None):
        self.writes.append(buffer)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls.append((server_hostname, ssl_context))
        return self

    async def aclose(self):
        self.closed = True


def _wire_image(body=b"image"):
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\nConnection: close\r\n\r\n"
        + body
    )


def _public_dns(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


@pytest.mark.asyncio
async def test_fetch_connects_verified_numeric_ip_without_second_dns(monkeypatch):
    lookups = []
    connections = []
    stream = WireStream([_wire_image()])

    def rebinding_dns(host, *_args, **_kwargs):
        lookups.append(host)
        ip = "8.8.8.8" if len(lookups) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

    async def connect(_self, host, port, **_kwargs):
        # An unpinned implementation would resolve this hostname a second time
        # and reach loopback. The real connection backend must get an IP only.
        connections.append((host, port))
        assert host == "8.8.8.8"
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", rebinding_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    result = await urls.fetch_public_image("http://images.example.org/test.png")
    assert result.content == b"image"
    assert lookups == ["images.example.org"]
    assert connections == [("8.8.8.8", 80)]
    assert b"Host: images.example.org\r\n" in b"".join(stream.writes)


@pytest.mark.asyncio
async def test_rebinding_cannot_hit_local_secret_server(monkeypatch):
    """Real local sockets: public-IP route is safe; a second DNS route is a trap."""
    hits = {"image": 0, "secret": 0}
    original_connect = httpcore.AnyIOBackend.connect_tcp

    async def respond(reader, writer, kind):
        await reader.readuntil(b"\r\n\r\n")
        hits[kind] += 1
        writer.write(_wire_image(b"safe" if kind == "image" else b"secret"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    image_server = await asyncio.start_server(lambda r, w: respond(r, w, "image"), "127.0.0.1", 0)
    secret_server = await asyncio.start_server(lambda r, w: respond(r, w, "secret"), "127.0.0.1", 0)
    image_port = image_server.sockets[0].getsockname()[1]
    secret_port = secret_server.sockets[0].getsockname()[1]
    dns_calls = []

    def dns(host, *_args, **_kwargs):
        dns_calls.append(host)
        ip = "8.8.8.8" if len(dns_calls) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

    async def connect(backend, host, port, **kwargs):
        # Only in this isolated test, route the approved public IP to the image
        # fixture. An unsafe hostname connection would instead hit the trap.
        target_port = image_port if host == "8.8.8.8" else secret_port
        return await original_connect(backend, "127.0.0.1", target_port, **kwargs)

    monkeypatch.setattr(urls.socket, "getaddrinfo", dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    try:
        result = await urls.fetch_public_image("http://rebind.example.org/image.png")
        assert result.content == b"safe"
        assert hits == {"image": 1, "secret": 0}
        assert dns_calls == ["rebind.example.org"]
    finally:
        image_server.close()
        secret_server.close()
        await image_server.wait_closed()
        await secret_server.wait_closed()


@pytest.mark.asyncio
async def test_mastodon_rebinding_between_preflight_and_connection_cannot_send_token(monkeypatch):
    from app.core.credentials import encrypt_json, encrypt_secret
    from app.publishers.mastodon import MastodonPublisher

    calls = []

    def dns(host, *_args, **_kwargs):
        calls.append(host)
        ip = "8.8.8.8" if len(calls) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    async def forbidden(*_args, **_kwargs):
        pytest.fail("a rebound Mastodon origin must not open a socket or send the token")

    monkeypatch.setattr(urls.socket, "getaddrinfo", dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", forbidden)
    account = SimpleNamespace(
        credentials_encrypted=encrypt_json({"instance_url": "https://mastodon.example.org"}),
        access_token_encrypted=encrypt_secret("isolated-test-token"),
    )
    with pytest.raises(ValueError, match="内网"):
        await MastodonPublisher(None, account)._request(
            "GET", "/api/v1/accounts/verify_credentials"
        )
    assert calls == ["mastodon.example.org", "mastodon.example.org"]


@pytest.mark.asyncio
async def test_https_preserves_original_sni_host_and_certificate_checks(monkeypatch):
    stream = WireStream([_wire_image()])

    async def connect(_self, host, port, **_kwargs):
        assert host == "8.8.8.8" and port == 443
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    async with httpx.AsyncClient(transport=urls.PublicHTTPTransport(), trust_env=False) as client:
        response = await client.get(
            "https://images.example.org/test.png",
            extensions={"sni_hostname": "wrong.example.org"},
        )
    assert response.content == b"image"
    assert stream.tls[0][0] == "images.example.org"
    context = stream.tls[0][1]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert b"Host: images.example.org\r\n" in b"".join(stream.writes)


@pytest.mark.asyncio
async def test_redirect_private_dns_is_rejected_before_connect(monkeypatch):
    connections = []
    stream = WireStream(
        [
            b"HTTP/1.1 302 Found\r\nLocation: https://private.example.org/image.png\r\n"
            b"Content-Length: 0\r\nConnection: close\r\n\r\n"
        ]
    )

    def dns(host, *_args, **_kwargs):
        ip = "192.168.1.20" if host == "private.example.org" else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    async def connect(_self, host, port, **_kwargs):
        connections.append(host)
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    with pytest.raises(ValueError, match="内网"):
        await urls.fetch_public_image("https://images.example.org/image.png")
    assert connections == ["8.8.8.8"]


@pytest.mark.asyncio
async def test_stream_limit_aborts_without_reading_entire_image(monkeypatch):
    stream = WireStream(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nTransfer-Encoding: chunked\r\n\r\n",
            b"4\r\n1234\r\n",
            b"4\r\n5678\r\n",
            b"4\r\n9012\r\n",
            b"0\r\n\r\n",
        ]
    )

    async def connect(*_args, **_kwargs):
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    with pytest.raises(ValueError, match="图片不能超过"):
        await urls.fetch_public_image("https://images.example.org/image.png", max_bytes=5)
    assert stream.reads == 3
    assert stream.closed and len(stream.responses) == 2


@pytest.mark.asyncio
async def test_content_length_limit_rejects_before_body(monkeypatch):
    stream = WireStream(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 10000000\r\n\r\n",
            b"not-read",
        ]
    )

    async def connect(*_args, **_kwargs):
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    with pytest.raises(ValueError, match="图片不能超过"):
        await urls.fetch_public_image("https://images.example.org/image.png", max_bytes=100)
    assert stream.reads == 1 and stream.closed


@pytest.mark.asyncio
async def test_unexpected_compressed_response_is_rejected_before_decompression(monkeypatch):
    stream = WireStream(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Encoding: gzip\r\n"
            b"Content-Length: 100\r\n\r\n",
            b"unread-compressed-body",
        ]
    )

    async def connect(*_args, **_kwargs):
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    with pytest.raises(ValueError, match="压缩传输"):
        await urls.fetch_public_image("https://images.example.org/image.png")
    assert stream.reads == 1 and stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_proxy_connect_targets_numeric_ip_and_keeps_origin_tls(monkeypatch, scheme):
    connections = []
    stream = WireStream([b"HTTP/1.1 200 Connection established\r\n\r\n", _wire_image()])

    async def connect(_self, host, port, **_kwargs):
        connections.append((host, port))
        return stream

    monkeypatch.setattr(urls.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    result = await urls.fetch_public_image(
        "https://images.example.org/image.png", proxy=f"{scheme}://user:pass@127.0.0.1:7890"
    )
    assert result.content == b"image"
    assert connections == [("127.0.0.1", 7890)]
    wire = b"".join(stream.writes)
    assert b"CONNECT 8.8.8.8:443 HTTP/1.1\r\n" in wire
    assert b"Proxy-Authorization: Basic dXNlcjpwYXNz\r\n" in wire
    assert b"Host: images.example.org\r\n" in wire
    assert [name for name, _context in stream.tls] == (
        ["127.0.0.1", "images.example.org"] if scheme == "https" else ["images.example.org"]
    )
    assert all(ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED for _, ctx in stream.tls)


@pytest.mark.asyncio
async def test_proxy_rejects_private_target_before_proxy_connection(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        pytest.fail("must not connect to proxy for a private target")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", forbidden)
    with pytest.raises(ValueError, match="内网"):
        await urls.fetch_public_image("https://127.0.0.1/image.png", proxy="http://127.0.0.1:7890")


@pytest.mark.asyncio
async def test_wechat_download_uses_same_bounded_secure_fetch(monkeypatch, tmp_path):
    from app.publishers import wechat_browser

    calls = []

    async def fetch(value, **kwargs):
        calls.append((value, kwargs))
        return urls.FetchedImage(value, b"image", "image/png", "test.png")

    monkeypatch.setattr(wechat_browser, "fetch_public_image", fetch)
    image = await wechat_browser._download_image("https://images.example.org/test.png", tmp_path, 1)
    assert image.read_bytes() == b"image"
    assert calls[0][1]["require_https"] is True
    assert calls[0][1]["max_bytes"] == 10 * 1024 * 1024
