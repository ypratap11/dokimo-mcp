"""Tests for the Accept-header widening middleware.

Regression cover for the 406 storm measured on the public deploy on 2026-09-19:
10 of 100 /mcp requests were rejected as Not Acceptable, including one aiohttp
client that retried 8 times and never got through.
"""
from __future__ import annotations

import pytest

from dokimo_mcp import _REQUIRED_ACCEPT, WidenAcceptHeader, _accepts_wildcard


# --- header parsing -------------------------------------------------------------

@pytest.mark.parametrize("header", [
    "*/*",                                       # aiohttp / requests default
    "",                                          # absent == no preference
    "   ",
    "*/*; q=0.8",
    "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",   # a browser
    "application/*, text/*",                     # both halves covered by wildcards
    "TEXT/*, APPLICATION/*",                     # case-insensitive
])
def test_wildcard_headers_are_widened(header):
    assert _accepts_wildcard(header) is True


@pytest.mark.parametrize("header", [
    "application/json, text/event-stream",       # already correct — leave alone
    "application/json",                          # explicit, genuinely partial
    "text/plain",                                # genuinely cannot read our types
    "application/xml, text/csv",
    "*/*;q=0",                                   # explicit refusal, not an offer
    "application/*",                             # only half the requirement
    "text/*",
])
def test_explicit_headers_are_left_alone(header):
    assert _accepts_wildcard(header) is False


def test_q_zero_wildcard_does_not_mask_a_real_offer():
    # `*/*;q=0` refuses the catch-all, but application/* and text/* still stand.
    assert _accepts_wildcard("application/*, text/*, */*;q=0") is True


# --- middleware behaviour -------------------------------------------------------

def _scope(accept: str | None, kind: str = "http") -> dict:
    headers = [(b"host", b"dokimo.augaster.com")]
    if accept is not None:
        headers.append((b"accept", accept.encode("latin-1")))
    return {"type": kind, "headers": headers}


async def _capture(scope):
    """Run the middleware over `scope` and return the scope the inner app saw."""
    seen = {}

    async def inner_app(inner_scope, receive, send):
        seen["scope"] = inner_scope

    await WidenAcceptHeader(inner_app)(scope, None, None)
    return seen["scope"]


def _accept_values(scope) -> list[bytes]:
    return [v for k, v in scope["headers"] if k.lower() == b"accept"]


@pytest.mark.anyio
async def test_wildcard_is_rewritten_to_the_required_pair():
    scope = await _capture(_scope("*/*"))
    assert _accept_values(scope) == [_REQUIRED_ACCEPT.encode("latin-1")]


@pytest.mark.anyio
async def test_missing_accept_is_rewritten():
    scope = await _capture(_scope(None))
    assert _accept_values(scope) == [_REQUIRED_ACCEPT.encode("latin-1")]


@pytest.mark.anyio
async def test_valid_header_passes_through_untouched():
    original = "application/json, text/event-stream"
    scope = await _capture(_scope(original))
    assert _accept_values(scope) == [original.encode("latin-1")]


@pytest.mark.anyio
async def test_incompatible_header_passes_through_to_get_its_406():
    scope = await _capture(_scope("text/plain"))
    assert _accept_values(scope) == [b"text/plain"]


@pytest.mark.anyio
async def test_non_http_scope_is_untouched():
    original = _scope("*/*", kind="lifespan")
    scope = await _capture(original)
    assert scope is original


@pytest.mark.anyio
async def test_caller_scope_is_not_mutated():
    """The middleware must copy: uvicorn reuses the scope dict it handed us."""
    original = _scope("*/*")
    before = list(original["headers"])
    await _capture(original)
    assert original["headers"] == before
