"""The published wording must not overclaim (dokimo-mcp 0.1.0 said "trustless",
"full verification" and "signed-off verdict"; the verdict is Dokimo's unsigned
answer for one record, and the local recompute does not check the anchor)."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SURFACES = ("README.md", "dokimo_mcp.py", "server.json", "glama.json", "smithery.yaml",
            "skills/dokimo-verify/SKILL.md")
BANNED = ("trustless", "no trust in", "without trusting", "signed-off", "signed verdict",
          "full verification", "fully verify")


def _text(name):
    return re.sub(r"\s+", " ", (ROOT / name).read_text(encoding="utf-8")).lower()


def test_no_overclaims_in_published_surfaces():
    for name in SURFACES:
        if not (ROOT / name).exists():
            continue
        text = _text(name)
        for phrase in BANNED:
            assert phrase not in text, f"{name} says {phrase!r}"


def test_verify_tool_names_the_v2_fields_and_says_unsigned():
    src = _text("dokimo_mcp.py")
    assert "'summary'" in src and "'binding'" in src
    assert "not signed" in src and "one record" in src


def test_versions_agree():
    py = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    versions = {server["version"], *(p["version"] for p in server.get("packages", []))}
    assert versions == {py}, (py, versions)


def test_skill_names_real_tools_and_discloses_network_calls():
    """The Agensi SKILL.md must name the server's real tools and disclose every
    network call (marketplace rule: no undisclosed network calls)."""
    skill = (ROOT / "skills/dokimo-verify/SKILL.md").read_text(encoding="utf-8")
    src = (ROOT / "dokimo_mcp.py").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: dokimo-verify\ndescription: ")
    for tool in ("recompute_merkle_root", "verify_evidence_package", "dokimo_agent_card"):
        assert f"def {tool}(" in src and tool in skill, tool
    for url in re.findall(r'"(https://dokimo\.augaster\.com/[^"]+)"', src):
        assert url in skill, f"undisclosed network call: {url}"
    assert "not signed" in skill and "one record" in skill.lower()
