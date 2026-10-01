"""Streamable HTTP transport for the always-on host.

Three layers of protection, outermost first:

1. Bind check. The server listens on 127.0.0.1 unless told otherwise, and refuses
   all-interfaces addresses (0.0.0.0, ::) unless KNOWLEDGE_MCP_ALLOW_ALL_INTERFACES=1.
   It also refuses any address other than loopback unless a token is set.
2. Host-header check (DNS rebinding protection), always on. Requests must name a
   host this server expects: localhost, the bind address, or KNOWLEDGE_MCP_ALLOWED_HOSTS.
3. Bearer token (KNOWLEDGE_MCP_TOKEN or KNOWLEDGE_MCP_TOKEN_FILE): optional on
   loopback, required on any other address. When set, every request except
   GET /healthz must send `Authorization: Bearer <token>`.

The MCP endpoint is /mcp. GET /healthz returns {"status": "ok"} and nothing else,
so monitoring can check the server without a token.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from knowledge_mcp.config import ConfigError, Settings

log = logging.getLogger(__name__)

MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"
ALL_INTERFACES = {"0.0.0.0", "::", "", "*"}  # noqa: S104 - listed in order to refuse them
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")


def check_bind(settings: Settings) -> None:
    """Refuse unsafe listen addresses before the server starts.

    - All interfaces (0.0.0.0, ::) only with KNOWLEDGE_MCP_ALLOW_ALL_INTERFACES=1.
    - Any address other than loopback only with a bearer token.
    """
    if settings.host in ALL_INTERFACES and not settings.allow_all_interfaces:
        raise ConfigError(
            f"Refusing to listen on all interfaces ({settings.host!r}). Bind to 127.0.0.1 "
            "or a Tailscale address instead. To override, set "
            "KNOWLEDGE_MCP_ALLOW_ALL_INTERFACES=1 and use a token."
        )
    if not is_loopback(settings.host) and not settings.token:
        raise ConfigError(
            f"Refusing to listen on {settings.host!r} without a bearer token. Anyone who "
            "can reach that address could read and write your ideas. Set "
            "KNOWLEDGE_MCP_TOKEN_FILE (the launchd installer creates one for you)."
        )


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """Host and Origin allow-lists for DNS rebinding protection, always enabled."""
    names = list(LOOPBACK_NAMES)
    host = settings.host
    if host not in ALL_INTERFACES and host not in names:
        names.append(f"[{host}]" if ":" in host else host)
    names += list(settings.allowed_hosts)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{n}:*" for n in names] + names,
        allowed_origins=[f"http://{n}:*" for n in names] + [f"https://{n}:*" for n in names],
    )


class BearerTokenMiddleware:
    """Reject requests without the right bearer token. Constant-time comparison."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") == HEALTH_PATH:
            await self.app(scope, receive, send)
            return
        supplied = dict(scope.get("headers") or []).get(b"authorization", b"")
        if hmac.compare_digest(supplied, self.expected):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            {"error": "unauthorized", "message": "Missing or invalid bearer token."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)


def build_http_app(app: MCPServer, settings: Settings) -> Any:
    """Return the ASGI app: MCP at /mcp, health at /healthz, token check if configured."""
    check_bind(settings)

    @app.custom_route(HEALTH_PATH, methods=["GET"])
    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    asgi: Any = app.streamable_http_app(
        streamable_http_path=MCP_PATH,
        transport_security=transport_security(settings),
        host=settings.host,
    )
    if settings.token:
        asgi = BearerTokenMiddleware(asgi, settings.token)
    return asgi


def run_http(app: MCPServer, settings: Settings) -> None:
    import uvicorn

    asgi = build_http_app(app, settings)
    log.info(
        "Serving MCP at http://%s:%d%s (token %s)",
        settings.host,
        settings.port,
        MCP_PATH,
        "required" if settings.token else "not required",
    )
    uvicorn.run(asgi, host=settings.host, port=settings.port, log_level="info")
