"""End-to-end proof against the real MCP transport.

The unit tests check the header rewrite in isolation; this drives an actual
`initialize` handshake through the SDK's Streamable HTTP transport to confirm the
406 is genuinely gone — and that an incompatible client still gets one.
"""
from __future__ import annotations

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient          # noqa: E402

import dokimo_mcp                                    # noqa: E402
from dokimo_mcp import WidenAcceptHeader, mcp        # noqa: E402

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "accept-regression", "version": "1.0"},
    },
}


@pytest.fixture
def client():
    # FastMCP caches one StreamableHTTPSessionManager, and the SDK refuses to run a
    # manager twice. Clear it so each test gets a fresh app it can start.
    mcp.settings.transport_security = None
    mcp._session_manager = None
    app = WidenAcceptHeader(mcp.streamable_http_app())
    with TestClient(app) as test_client:
        yield test_client


def _post(client, accept):
    return client.post(
        "/mcp",
        json=INITIALIZE,
        headers={"Content-Type": "application/json", "Accept": accept},
    )


@pytest.mark.parametrize("accept", [
    "*/*",                                              # aiohttp / requests default
    "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",  # a browser
    "application/*, text/*",
])
def test_wildcard_clients_now_complete_the_handshake(client, accept):
    response = _post(client, accept)
    assert response.status_code == 200, response.text
    assert "dokimo" in response.text


def test_compliant_client_still_works(client):
    response = _post(client, "application/json, text/event-stream")
    assert response.status_code == 200, response.text


def test_genuinely_incompatible_client_still_gets_406(client):
    """The fix must not turn the transport into a pushover."""
    response = _post(client, "text/plain")
    assert response.status_code == 406


def test_the_exact_header_that_failed_in_production(client):
    """aiohttp 3.14.3 sent `*/*` and was rejected 8 times on 2026-09-19."""
    assert _post(client, "*/*").status_code == 200


def test_wildcard_client_survives_the_full_production_stack(monkeypatch, capsys):
    """Prod runs WidenAcceptHeader *outside* CORS and UsageLogMiddleware.

    UsageLogMiddleware buffers the request body and replays it, so the two
    middlewares have to compose cleanly — this pins the real wiring from main(),
    not just the Accept middleware in isolation.
    """
    from starlette.middleware.cors import CORSMiddleware

    monkeypatch.setenv("MCP_USAGE_LOG", "1")
    mcp.settings.transport_security = None
    mcp._session_manager = None

    app = mcp.streamable_http_app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["mcp-session-id"])
    app.add_middleware(dokimo_mcp.UsageLogMiddleware)

    with TestClient(WidenAcceptHeader(app)) as c:
        response = _post(c, "*/*")

    assert response.status_code == 200, response.text
    # the usage log still saw the request body the middleware replayed
    assert '"method": "initialize"' in capsys.readouterr().out
