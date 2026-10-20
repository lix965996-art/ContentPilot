"""Validate instance origins before sending Mastodon credentials."""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit


def normalize_instance_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value).strip())
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in str(value))
        ):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if not address.is_global:
                raise ValueError
            host = f"[{host}]" if address.version == 6 else host
        elif (
            "." not in host
            or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", "."))
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
            or any(not label or len(label) > 63 for label in host.split("."))
        ):
            raise ValueError
        return f"https://{host}"
    except (ValueError, UnicodeError):
        raise ValueError(
            "Mastodon 服务器必须是公网 HTTPS 网址，且不能包含路径、账号或自定义端口"
        ) from None


async def ensure_public_instance(value: str) -> str:
    origin = normalize_instance_url(value)
    host = urlsplit(origin).hostname
    addresses = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Mastodon 服务器不能指向本机或内网地址")
    return origin
