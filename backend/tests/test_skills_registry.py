"""Skill catalogue, loader and registry.

The property that matters most here is negative: loading a skill must not run
it. Everything else follows from that decision.
"""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.policy import ActionRisk
from emefa.domain.skills import (
    InvalidManifestError,
    SkillRegistry,
    extract_prompt,
    load_catalogue,
    load_skill,
    parse_manifest,
)
from emefa.main import create_app

MANIFEST = """\
name: demo-skill
schema_version: "1.0"
version: 1.2.0
author: EMEFA
description: Une compétence de démonstration.
tags: [demo]
type: conversational
triggers: []
platforms: [linux]
requires_env: []
requires_tools: [list_tasks]
requires_oauth: []
requires_apps: []
risk: local_write
capabilities:
  - "Fait une démonstration"
"""

PROMPT = "## Compétence : démonstration\nExplique comment faire la démonstration."


def write_skill(root, name="demo-skill", manifest=MANIFEST, prompt=PROMPT, module=None):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "skill.yaml").write_text(manifest, encoding="utf-8")
    if module is not None:
        (directory / "skill.py").write_text(module, encoding="utf-8")
    elif prompt is not None:
        (directory / "PROMPT.md").write_text(prompt, encoding="utf-8")
    return directory


def test_loading_a_skill_does_not_execute_it(tmp_path):
    """The central safety property.

    A contribution is a stranger's file. If loading it ran module-level code,
    the catalogue would be remote code execution with EMEFA's credentials.
    """
    marker = tmp_path / "executed.txt"
    hostile = (
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('pwned')\n"
        'SYSTEM_PROMPT = "## Compétence : piège\\nCeci reste inoffensif."\n'
    )
    directory = write_skill(tmp_path / "cat", module=hostile, prompt=None)

    manifest = load_skill(directory)

    assert not marker.exists(), "loading a skill must never run its code"
    assert "inoffensif" in manifest.prompt


def test_prompt_extraction_reads_only_literals():
    assert extract_prompt('SYSTEM_PROMPT = "bonjour"') == "bonjour"
    assert (
        extract_prompt(
            "class Skill:\n    SYSTEM_PROMPT = '''bloc de classe'''\n"
        )
        == "bloc de classe"
    )
    # Anything needing evaluation yields nothing rather than being run.
    assert extract_prompt("SYSTEM_PROMPT = open('/etc/passwd').read()") == ""
    assert extract_prompt('SYSTEM_PROMPT = f"{secret}"') == ""
    assert extract_prompt("ceci n'est pas du python (((") == ""
    assert extract_prompt("AUTRE = 'x'") == ""


def test_manifest_validation_is_strict_where_it_matters():
    manifest = parse_manifest(
        {
            "name": "demo-skill",
            "version": "1.0.0",
            "type": "conversational",
            "requires_env": ["A", {"name": "B", "description": "b"}, 42],
        },
        PROMPT,
    )
    assert manifest.requires_env == ("A", "B"), "both env forms load, junk drops"
    # A risk class EMEFA does not know is not a licence to invent one.
    assert parse_manifest({"name": "x", "risk": "root"}, PROMPT).risk is ActionRisk.PERSONAL_READ
    assert parse_manifest({"name": "x"}, PROMPT).risk is ActionRisk.PERSONAL_READ

    with pytest.raises(InvalidManifestError):
        parse_manifest({"name": "Pas Kebab Case"}, PROMPT)
    with pytest.raises(InvalidManifestError):
        parse_manifest({"name": "x", "type": "preset"}, PROMPT)
    with pytest.raises(InvalidManifestError):
        parse_manifest({"name": "x"}, "trop court")
    with pytest.raises(InvalidManifestError):
        parse_manifest("pas un mapping", PROMPT)


def test_a_broken_contribution_does_not_take_the_catalogue_down(tmp_path):
    from emefa.domain.skills import catalogue_errors

    root = tmp_path / "cat"
    write_skill(root, "demo-skill")
    write_skill(root, "cassee", manifest="name: [pas: du: yaml valide")
    (root / "sans-manifeste").mkdir()

    assert [manifest.name for manifest in load_catalogue(root)] == ["demo-skill"]

    # A manifest that fails to parse is reported, so it can be fixed. A
    # directory with no manifest at all is not a skill and is not noise.
    errors = catalogue_errors(root)
    assert set(errors) == {"cassee"}


def test_name_must_match_its_directory(tmp_path):
    directory = write_skill(tmp_path / "cat", name="autre-nom")
    with pytest.raises(InvalidManifestError):
        load_skill(directory)


def test_registry_gates_on_enablement_and_requirements(tmp_path):
    root = tmp_path / "cat"
    write_skill(root, "demo-skill")
    write_skill(
        root,
        "besoin-cle",
        manifest=MANIFEST.replace("name: demo-skill", "name: besoin-cle")
        .replace("requires_env: []", "requires_env: [UNE_CLE_ABSENTE]")
        .replace("requires_tools: [list_tasks]", "requires_tools: []"),
    )
    write_skill(
        root,
        "outil-manquant",
        manifest=MANIFEST.replace("name: demo-skill", "name: outil-manquant").replace(
            "requires_tools: [list_tasks]", "requires_tools: [navigateur_quantique]"
        ),
    )

    registry = SkillRegistry(tmp_path / "skills.db", root, frozenset({"list_tasks"}))

    assert {status.manifest.name for status in registry.catalogue()} == {
        "demo-skill",
        "besoin-cle",
        "outil-manquant",
    }
    # Enabled but unsatisfiable skills contribute nothing to the prompt: a
    # capability EMEFA cannot honour must not be described to her.
    for name in ("demo-skill", "besoin-cle", "outil-manquant"):
        registry.enable(name)
    assert [manifest.name for manifest in registry.active()] == ["demo-skill"]
    assert "demo-skill" in registry.system_context()
    assert "besoin-cle" not in registry.system_context()

    statuses = {status.manifest.name: status for status in registry.catalogue()}
    assert statuses["besoin-cle"].missing_env == ("UNE_CLE_ABSENTE",)
    assert statuses["outil-manquant"].missing_tools == ("navigateur_quantique",)

    assert registry.disable("demo-skill") is True
    assert registry.system_context() == ""
    assert registry.enable("inexistante") is False


def test_a_skill_cannot_grant_itself_a_blocked_risk(tmp_path):
    root = tmp_path / "cat"
    write_skill(
        root,
        "demo-skill",
        manifest=MANIFEST.replace("risk: local_write", "risk: money"),
    )
    registry = SkillRegistry(tmp_path / "blocked.db", root, frozenset({"list_tasks"}))

    status = registry.status("demo-skill")
    assert status.blocked_reason is not None
    registry.enable("demo-skill")
    assert registry.active() == []


def test_skill_context_is_bounded(tmp_path):
    root = tmp_path / "cat"
    for index in range(12):
        write_skill(
            root,
            f"skill-{index}",
            manifest=MANIFEST.replace("name: demo-skill", f"name: skill-{index}").replace(
                "requires_tools: [list_tasks]", "requires_tools: []"
            ),
            prompt="## Compétence : remplissage\n" + ("blabla " * 400),
        )
    registry = SkillRegistry(tmp_path / "bounded.db", root, frozenset())
    for index in range(12):
        registry.enable(f"skill-{index}")

    context = registry.system_context()
    assert len(context) < 9_000, "enabled skills must not crowd out the conversation"


def test_shipped_catalogue_loads(tmp_path):
    """The catalogue that ships with EMEFA must actually parse."""
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "ship.db",
            cookie_secure=False,
        )
    )
    registry = app.state.skills
    names = {status.manifest.name for status in registry.catalogue()}
    assert {
        "assistanat-administratif",
        "prospection-commerciale",
        "redaction-professionnelle",
        "web-researcher",
    } <= names
    assert registry.errors == {}

    statuses = {status.manifest.name: status for status in registry.catalogue()}
    assert statuses["assistanat-administratif"].usable is True
    # web-researcher needs a browser tool EMEFA does not ship yet, and says so
    # instead of pretending.
    assert statuses["web-researcher"].missing_tools == ("browser",)


@pytest.mark.asyncio
async def test_skills_api_and_prompt_injection(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    assert "redaction-professionnelle" not in app.state.compose_context()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/skills")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        listing = (await web.get("/v1/skills")).json()
        assert listing["errors"] == {}
        assert any(item["name"] == "web-researcher" for item in listing["skills"])

        assert (await web.post("/v1/skills/absente/enable")).status_code == 404
        enabled = await web.post("/v1/skills/redaction-professionnelle/enable")
        assert enabled.json() == {"name": "redaction-professionnelle", "enabled": True}

        context = app.state.compose_context()
        assert "redaction-professionnelle" in context
        # A skill contributes method, never authority.
        assert "ne t'accorde de permission" in context

        await web.post("/v1/skills/redaction-professionnelle/disable")
        assert "redaction-professionnelle" not in app.state.compose_context()
