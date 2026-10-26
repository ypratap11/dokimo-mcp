# dokimo-mcp

<!-- mcp-name: io.github.ypratap11/dokimo-mcp -->

**Give an AI agent the ability to verify another agent's revenue claims.**

An [MCP](https://modelcontextprotocol.io) server exposing [Dokimo's](https://dokimo.augaster.com)
evidence checks as tools any MCP client (Claude Desktop, IDE agents, custom
agents) can call. It's the "agent that audits agents" — as tools.

Live, clickable version of what these tools do:
**https://dokimo.augaster.com/agent-audits-agents.html**

> This is a thin, self-contained **client**: it calls Dokimo's public endpoints and
> implements the public `dokimo-merkle-v1` hashing scheme. It contains no proprietary
> code. MIT-licensed.

## Tools

| Tool | What it does | Network? |
|---|---|---|
| `recompute_merkle_root(leaf, proof_path)` | **Local recompute** — hash a leaf under `dokimo-merkle-v1` and replay the proof path to a root, in this process, with **no network call**. Compare it to a package's claimed `root` yourself. It does not check the on-chain anchor. | none |
| `verify_evidence_package(package)` | **Dokimo's check of one record**, via its public A2A endpoint: recompute **and** check the anchored commitment (root + rule version, plus the close summary for v2 closes) against the **on-chain anchor on Base**. Returns `verified: true` only if both hold. The verdict is Dokimo's answer and is **not signed** — to avoid relying on it, recompute locally and read the anchor yourself (e.g. [/verify.html](https://dokimo.augaster.com/verify.html)). | Dokimo A2A |
| `dokimo_agent_card()` | Fetch Dokimo's public A2A agent card — what it can verify. | Dokimo |

**Verification model:** there is no path to `verified: true` without (1) the
caller's `(leaf, proof_path)` recomputing to the claimed `root`, **and** (2) the
commitment of `(root, rule_version_commitment)` — and, for a `dokimo-anchor-v2`
close, its `summary` — being anchored on-chain. Tamper one byte → recompute fails.
Swap the rule version → the commitment changes → not anchored. A package without
`summary` and `binding` is checked as legacy v1, which verifies only closes
anchored before the v2 cutover.

**Honest scope:** for one record, checks that its proof reaches the root and that
the commitment is anchored on-chain. It does not recompute the close's figures
from all its records (that needs the full package, e.g. in /verify.html), and it
says nothing about whether a business number is "good." Non-custodial; reads
public on-chain state only.

## Install & run

```bash
pip install dokimo-mcp
dokimo-mcp                 # runs over stdio
# or, from a clone:
pip install .
python -m dokimo_mcp
```

## Add to an MCP client

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dokimo": {
      "command": "dokimo-mcp"
    }
  }
}
```

If `dokimo-mcp` isn't on `PATH`, use the module form:

```json
{
  "mcpServers": {
    "dokimo": {
      "command": "python",
      "args": ["-m", "dokimo_mcp"]
    }
  }
}
```

Then ask the agent: *"Use Dokimo to verify this evidence package"* (paste one), or
*"recompute this Merkle root and tell me if it matches."*

## Agent skill

[`skills/dokimo-verify/SKILL.md`](skills/dokimo-verify/SKILL.md) tells an agent when
and how to use these tools: check the package shape, recompute locally first, ask
before sending anything to Dokimo, and report the result for one record without
overstating it. Drop the `dokimo-verify` folder into your agent's skills directory
(e.g. `~/.claude/skills/` for Claude Code). It is also listed, free, on
[Agensi](https://www.agensi.io/skills/dokimo-verify).

## Try it

The live demo page embeds a real, anchored evidence package. Fetch it and verify:

```python
import re, json, urllib.request
import dokimo_mcp as d
html = urllib.request.urlopen(urllib.request.Request(
    "https://dokimo.augaster.com/agent-audits-agents.html",
    headers={"User-Agent": d._UA})).read().decode()
pkg = json.loads(re.search(r"const PKG\s*=\s*(\{.*?\})\s*;", html, re.S).group(1))
print(d.verify_evidence_package(pkg)["verified"])   # True
# tamper one unit -> False
pkg["leaf"] = pkg["leaf"].replace("1001190933933115", "1001190933933116")
print(d.verify_evidence_package(pkg)["verified"])   # False
```

## Hosted / HTTP mode

The default transport is **stdio** (local use). Set `MCP_TRANSPORT=http` to serve
**MCP Streamable HTTP at `/mcp`** on `$PORT` (default 8081) with CORS — the shape
hosted platforms like [Smithery](https://smithery.ai) require. The included
`Dockerfile` + `smithery.yaml` (`runtime: container`) are set up for exactly this,
so Smithery can build and host it from this repo.

```bash
MCP_TRANSPORT=http PORT=8081 dokimo-mcp     # or: docker run -p 8081:8081 <image>
```

## What is Dokimo?

Verifiable revenue infrastructure for autonomous commerce — audit-ready, independently
reproducible books for AI-agent machine payments (x402 / AP2 / Stripe), with each figure
tamper-evidently committed and anchored on-chain. https://dokimo.augaster.com

## License

MIT — see [LICENSE](LICENSE).
