"""Outbound URL validation for user-supplied media addresses.

The application fetches remote images for Weibo/WeChat delivery. Those URLs can
come from an operator, so every hop must be checked after DNS resolution and
redirects must not be able to reach loopback or private networks.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import ssl
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global and not address.is_multicast


def _validate_http_url(value: str, *, require_https: bool = False) -> None:
    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("远程地址必须使用 HTTP 或 HTTPS")
    if require_https and parsed.scheme != "https":
        raise ValueError("远程地址必须使用 HTTPS")
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("远程地址无效")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise ValueError("远程地址端口不受支持")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("不允许读取本机或内网地址")


async def _public_addresses(host: str, port: int) -> list[str]:
    try:
        ipaddress.ip_address(host)
        is_literal = True
    except ValueError:
        is_literal = False
    if is_literal:
        if not _is_public_address(host):
            raise ValueError("不允许读取本机或内网地址")
        return [host]
    addresses = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    resolved = [str(item[4][0]) for item in addresses]
    if not resolved or any(not _is_public_address(address) for address in resolved):
        raise ValueError("不允许读取本机或内网地址")
    return list(dict.fromkeys(resolved))


async def ensure_public_http_url(value: str, *, require_https: bool = False) -> str:
    """Preflight only; actual requests must also use PublicHTTPTransport."""
    _validate_http_url(value, require_https=require_https)
    parsed = urlsplit(value)
    host = parsed.hostname
    if host is None:
        raise ValueError("远程地址无效")
    await _public_addresses(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    return value


class _PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve once at connect time and pass only validated numeric IPs to I/O.

    HTTP core retains the original origin, so Host and TLS certificate/SNI
    checks continue to use the original hostname. An explicitly configured
    proxy is trusted infrastructure, but CONNECT targets are always numeric:
    the proxy never gets a target hostname that it could resolve differently.
    """

    def __init__(self, proxy: str | None = None) -> None:
        self._backend: Any = httpcore.AnyIOBackend()
        self._proxy = httpx.Proxy(proxy) if proxy else None
        if self._proxy and self._proxy.url.scheme not in {"http", "https"}:
            raise ValueError("安全远程请求代理仅支持 HTTP 或 HTTPS")

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await asyncio.wait_for(_public_addresses(host, port), timeout=timeout)
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout("公网地址解析超时") from exc
        last_error = None
        for address in addresses:
            try:
                if self._proxy:
                    return await self._connect_proxy(address, port, timeout, socket_options)
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error or httpcore.ConnectError("远程服务器没有可连接的公网地址")

    async def _connect_proxy(
        self,
        address: str,
        port: int,
        timeout: float | None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None,
    ):
        proxy = self._proxy
        assert proxy is not None
        proxy_url = proxy.url
        proxy_host = proxy_url.host
        if not proxy_host:
            raise httpcore.ConnectError("代理地址缺少主机名")
        proxy_port = proxy_url.port or (443 if proxy_url.scheme == "https" else 80)
        stream = await self._backend.connect_tcp(
            proxy_host, proxy_port, timeout=timeout, socket_options=socket_options
        )
        try:
            if proxy_url.scheme == "https":
                stream = await stream.start_tls(
                    ssl_context=proxy.ssl_context or ssl.create_default_context(),
                    server_hostname=proxy_host,
                    timeout=timeout,
                )
            origin = httpcore.Origin(proxy_url.raw_scheme, proxy_url.raw_host, proxy_port)
            connection = httpcore.AsyncHTTP11Connection(origin=origin, stream=stream)
            target_host = f"[{address}]" if ":" in address else address
            target = f"{target_host}:{port}".encode("ascii")
            headers = [(b"Host", target), (b"Accept", b"*/*")]
            if proxy.raw_auth:
                headers.append(
                    (
                        b"Proxy-Authorization",
                        b"Basic " + base64.b64encode(b":".join(proxy.raw_auth)),
                    )
                )
            response = await connection.handle_async_request(
                httpcore.Request(
                    "CONNECT",
                    httpcore.URL(
                        scheme=proxy_url.raw_scheme,
                        host=proxy_url.raw_host,
                        port=proxy_port,
                        target=target,
                    ),
                    headers=headers,
                    extensions={"timeout": {"connect": timeout, "read": timeout, "write": timeout}},
                )
            )
            if not 200 <= response.status < 300:
                raise httpcore.ProxyError(f"代理隧道建立失败：HTTP {response.status}")
            return response.extensions["network_stream"]
        except BaseException:
            await stream.aclose()
            raise

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def _httpx_error(exc: Exception, request: httpx.Request) -> httpx.HTTPError:
    for name in (
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ProxyError",
        "ConnectError",
        "ReadError",
        "WriteError",
        "RemoteProtocolError",
        "LocalProtocolError",
    ):
        if isinstance(exc, getattr(httpcore, name)):
            return getattr(httpx, name)(str(exc), request=request)
    return httpx.TransportError(str(exc), request=request)


class _PublicResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream, request: httpx.Request) -> None:
        self._stream, self._request = stream, request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._stream:
                yield chunk
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError) as exc:
            raise _httpx_error(exc, self._request) from exc

    async def aclose(self) -> None:
        await self._stream.aclose()


class PublicHTTPTransport(httpx.AsyncBaseTransport):
    """HTTPX transport that cannot bypass public-IP checks through DNS/proxies."""

    def __init__(self, *, proxy: str | None = None, require_https: bool = False) -> None:
        self._require_https = require_https
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_PublicNetworkBackend(proxy),
            retries=0,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _validate_http_url(str(request.url), require_https=self._require_https)
        # Reject caller-supplied Host/SNI overrides before any credentials leave.
        if request.headers.get("host", "").lower() != request.url.netloc.decode("ascii").lower():
            raise ValueError("远程请求 Host 与目标地址不一致")
        extensions = dict(request.extensions)
        extensions.pop("sni_hostname", None)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        try:
            response = await self._pool.handle_async_request(core_request)
        except (
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
            httpcore.ProxyError,
        ) as exc:
            raise _httpx_error(exc, request) from exc
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=_PublicResponseStream(response.stream, request),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


@dataclass
class FetchedImage:
    url: str
    content: bytes
    content_type: str
    filename: str


async def fetch_public_image(
    value: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    require_https: bool = False,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
    proxy: str | None = None,
) -> FetchedImage:
    """Fetch an image while validating DNS, each redirect hop and the size."""
    current = str(value).strip()
    request_headers = {"Accept-Encoding": "identity", **(headers or {})}
    transport = PublicHTTPTransport(proxy=proxy, require_https=require_https)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, transport=transport, trust_env=False
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current, headers=request_headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ValueError("远程地址重定向地址为空")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type and not content_type.startswith("image/"):
                    raise ValueError("远程地址返回的不是图片")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("远程图片不支持压缩传输编码")
                declared_length = response.headers.get("content-length", "")
                if declared_length.isdigit() and int(declared_length) > max_bytes:
                    raise ValueError(f"图片不能超过 {max_bytes // 1024 // 1024}MB")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError(f"图片不能超过 {max_bytes // 1024 // 1024}MB")
                if not content:
                    raise ValueError("图片文件为空")
                filename = urlsplit(current).path.rsplit("/", 1)[-1] or "image"
                return FetchedImage(
                    url=current,
                    content=bytes(content),
                    content_type=content_type or "application/octet-stream",
                    filename=filename,
                )
    raise ValueError("远程地址重定向次数过多")
