"""Dokimo MCP server — give an AI agent the ability to verify another agent's
revenue claims.

A self-contained Model Context Protocol server exposing three tools:

  - ``recompute_merkle_root``  — PURE, LOCAL, trustless: recompute a
    ``dokimo-merkle-v1`` root from a leaf + proof path, with no network and no
    trust in anyone. The "check the math yourself" primitive.
  - ``verify_evidence_package`` — full verification via Dokimo's public A2A
    endpoint: recompute + on-chain anchor check, returning a signed-off verdict.
  - ``dokimo_agent_card``       — fetch Dokimo's public A2A agent card.

This is a thin CLIENT: it talks to Dokimo's public endpoints and implements the
public ``dokimo-merkle-v1`` hashing scheme (RFC-6962-style, domain-separated).
It contains no proprietary code.

Verification model: there is NO path to ``verified: true`` without BOTH
(1) the caller's ``(leaf, proof_path)`` recomputing to the claimed root, AND
(2) the compound commitment of ``(root, rule_version_commitment)`` being anchored
on-chain. Tamper one byte → recompute fails. Swap the rule version → the compound
commitment changes → not anchored.

Honest scope: attests that a *reported* figure is reproducible and tamper-evident
against an on-chain anchor — not that any underlying business number is "good."

Run:  ``dokimo-mcp``  (after ``pip install dokimo-mcp``), or ``python -m dokimo_mcp``.
Live demo the tools mirror: https://dokimo.augaster.com/agent-audits-agents.html
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

DOKIMO_A2A = "https://dokimo.augaster.com/a2a"
DOKIMO_AGENT_CARD = "https://dokimo.augaster.com/.well-known/agent-card.json"

# A real User-Agent — the default Python-urllib UA is 403'd by the CDN's bot filter.
_UA = "dokimo-mcp/0.1 (+https://dokimo.augaster.com)"

# --- the public dokimo-merkle-v1 scheme (documented on the public site/demo) ----
# Domain separation: leaves H(0x00 ‖ leaf), internal nodes H(0x01 ‖ left ‖ right),
# over the hex-string representations. No proprietary logic — the published scheme.
MERKLE_SCHEME = "dokimo-merkle-v1"
_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def _hash_leaf(leaf: str) -> str:
    return hashlib.sha256(_LEAF_PREFIX + leaf.encode()).hexdigest()


def _hash_node(a: str, b: str) -> str:
    return hashlib.sha256(_NODE_PREFIX + a.encode() + b.encode()).hexdigest()


mcp = FastMCP("dokimo")


def _post_json(url: str, payload: dict, timeout: float = 25.0) -> Any:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _get_json(url: str, timeout: float = 25.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


@mcp.tool()
def recompute_merkle_root(leaf: str, proof_path: list) -> dict:
    """Trustlessly recompute a dokimo-merkle-v1 root — LOCAL, no network, no trust.

    Hash ``leaf`` in the leaf domain (H(0x00 ‖ leaf)) and replay ``proof_path`` —
    a list of ``[sibling_hash, side]`` where side is "L" or "R" — hashing internal
    nodes as H(0x01 ‖ left ‖ right). Compare the returned root to the ``root`` in an
    evidence package yourself; if it differs, the package was tampered with.

    Returns ``{recomputed_root, merkle_scheme, steps}``.
    """
    path = [(str(h), str(s)) for h, s in proof_path]
    for _, side in path:
        if side not in ("L", "R"):
            raise ValueError("each proof_path side must be 'L' or 'R'")
    acc = _hash_leaf(leaf)
    for sibling, side in path:
        acc = _hash_node(sibling, acc) if side == "L" else _hash_node(acc, sibling)
    return {"recomputed_root": acc, "merkle_scheme": MERKLE_SCHEME, "steps": len(path)}


@mcp.tool()
def verify_evidence_package(package: dict) -> dict:
    """Fully verify a Dokimo evidence package against the LIVE on-chain anchor.

    Sends the package to Dokimo's public A2A endpoint, which recomputes the Merkle
    proof AND checks the compound commitment (root + rule version) against the
    anchor on Base. ``package`` must contain: ``leaf`` (str), ``root`` (str),
    ``proof_path`` (list of [sibling_hash, "L"|"R"]), and
    ``rule_version_commitment`` (str); ``close_id`` is optional/echoed.

    Returns the verdict: ``{verified, checks:{recompute, onchain_anchor,
    rule_version_bound}, ...}``. ``verified`` is true only if the proof recomputes
    AND the commitment is anchored on-chain.
    """
    payload = {
        "jsonrpc": "2.0", "id": "dokimo-mcp", "method": "SendMessage",
        "params": {"message": {"role": "user", "parts": [{"data": package}]}},
    }
    resp = _post_json(DOKIMO_A2A, payload)
    if isinstance(resp, dict) and resp.get("error"):
        return {"verified": False, "error": resp["error"]}
    result = resp.get("result", {}) if isinstance(resp, dict) else {}
    task = result.get("task", result)          # v1.0.1 wraps in {task:...}; legacy is bare
    for artifact in (task.get("artifacts") or []):
        for part in (artifact.get("parts") or []):
            if isinstance(part.get("data"), dict):
                return part["data"]
    return {"verified": False, "error": "no verdict artifact in A2A response", "raw": resp}


@mcp.tool()
def dokimo_agent_card() -> dict:
    """Fetch Dokimo's public A2A agent card — the discovery document describing what
    it can verify (skills, endpoints, supported A2A versions)."""
    return _get_json(DOKIMO_AGENT_CARD)


def main() -> None:
    """Console-script entry point (``dokimo-mcp``).

    Default transport is **stdio** (local use — Claude Desktop, IDE agents).
    Set ``MCP_TRANSPORT=http`` (as the container image does) to serve **Streamable
    HTTP at /mcp** on ``$PORT`` (default 8081) with CORS — the shape Smithery's
    hosted deployments require.
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http", "shttp"):
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware
        from mcp.server.transport_security import TransportSecuritySettings

        port = int(os.environ.get("PORT", "8081"))
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        # DNS-rebinding protection defaults to localhost-only hosts/origins; that
        # protects *local* servers from malicious sites. This is a public, hosted,
        # read-only verifier (calls only public endpoints), and it sits behind a
        # host (Smithery) that sets its own Host/Origin — so allow any.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
        app = mcp.streamable_http_app()          # serves MCP at /mcp
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["mcp-session-id"],   # Smithery/browser clients need this
        )
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run()   # stdio


if __name__ == "__main__":
    main()
