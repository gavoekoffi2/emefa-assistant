"""Projects, companies, relations and timelines.

These pin the things that make a graph worth having over a pile of facts:
one node per real thing, memory scoped so projects do not overwrite each
other, personal and business kept apart, and answers assembled from what was
recorded rather than generated.
"""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.entities import (
    EntityGraph,
    EntityKind,
    EntityRepository,
    EntityScope,
    EntityStatus,
    Milestone,
    RelationKind,
    TimelineBuilder,
    slugify,
)
from emefa.domain.memories import MemoryRepository
from emefa.main import create_app


def build(tmp_path, name="graph.db"):
    database = tmp_path / name
    entities = EntityRepository(database)
    memories = MemoryRepository(database)
    graph = EntityGraph(entities, memories)
    return entities, memories, graph, TimelineBuilder(graph)


# ── identity ──────────────────────────────────────────────────────────────


def test_the_same_name_is_the_same_entity(tmp_path):
    """Without this, every mention creates a node and the graph is worthless
    within a week."""
    entities, _, _, _ = build(tmp_path)
    first = entities.upsert("project", "Graphiste GPT")
    again = entities.upsert("project", "  graphiste   gpt  ")

    assert again.entity_id == first.entity_id
    assert again.name == "graphiste gpt", "the latest spelling wins"
    assert len(entities.list_entities()) == 1


def test_mentioning_an_entity_does_not_wipe_what_is_known_about_it(tmp_path):
    entities, _, _, _ = build(tmp_path)
    entities.upsert("project", "CutForge", summary="Découpe laser sur mesure")
    touched = entities.upsert("project", "CutForge")
    assert touched.summary == "Découpe laser sur mesure"


def test_same_name_different_kind_are_different_entities(tmp_path):
    entities, _, _, _ = build(tmp_path)
    company = entities.upsert("company", "Horizon")
    project = entities.upsert("project", "Horizon")
    assert company.entity_id != project.entity_id


def test_resolution_accepts_a_partial_name_but_refuses_ambiguity(tmp_path):
    entities, _, _, _ = build(tmp_path)
    entities.upsert("project", "Graphiste GPT")
    assert entities.resolve("graphiste").name == "Graphiste GPT"

    entities.upsert("project", "Graphiste Studio")
    # Two candidates: answering about the wrong project is worse than asking.
    assert entities.resolve("graphiste") is None


def test_slugify_folds_case_accents_and_punctuation():
    assert slugify("Clinique du Lac") == "clinique-du-lac"
    assert slugify("  CLINIQUE   DU LAC ") == "clinique-du-lac"
    assert slugify("Café & Thé, S.A.") == "cafe-the-s-a"


# ── scoped memory ─────────────────────────────────────────────────────────


def test_each_project_keeps_its_own_memory(tmp_path):
    """The bug this prevents: one project's objective superseding another's."""
    entities, memories, graph, _ = build(tmp_path)
    first = entities.upsert("project", "CutForge")
    second = entities.upsert("project", "Graphiste GPT")

    graph.note(first.entity_id, "livrer la V1 en septembre", category="goal")
    graph.note(second.entity_id, "trouver dix premiers utilisateurs", category="goal")

    assert [fact.object for fact in graph.facts_for(first.entity_id)] == [
        "livrer la V1 en septembre"
    ]
    assert [fact.object for fact in graph.facts_for(second.entity_id)] == [
        "trouver dix premiers utilisateurs"
    ]


def test_restating_a_project_goal_still_supersedes_within_that_project(tmp_path):
    entities, _, graph, _ = build(tmp_path)
    project = entities.upsert("project", "CutForge")
    graph.note(project.entity_id, "livrer la V1 en septembre", category="goal")
    graph.note(project.entity_id, "livrer la V1 en novembre", category="goal")

    goals = [fact.object for fact in graph.facts_for(project.entity_id, category="goal")]
    assert goals == ["livrer la V1 en novembre"]


def test_business_memory_does_not_leak_into_personal_memory(tmp_path):
    entities, memories, graph, _ = build(tmp_path)
    project = entities.upsert("project", "CutForge")
    graph.note(project.entity_id, "le budget est de 4 millions", category="note")
    memories.remember("Je préfère les réunions le matin", "preference")

    personal = memories.kernel.list_facts(personal_only=True)
    assert [fact.object for fact in personal] == ["Je préfère les réunions le matin"]
    assert all(fact.entity_id is None for fact in personal)


def test_personal_and_business_entities_are_separable(tmp_path):
    entities, _, _, _ = build(tmp_path)
    entities.upsert("project", "Refaire la cuisine", scope="personal")
    entities.upsert("project", "CutForge", scope="business")

    assert [item.name for item in entities.list_entities(scope=EntityScope.PERSONAL)] == [
        "Refaire la cuisine"
    ]
    assert [item.name for item in entities.list_entities(scope=EntityScope.BUSINESS)] == [
        "CutForge"
    ]


# ── relations ─────────────────────────────────────────────────────────────


def test_relations_are_typed_directed_and_deduplicated(tmp_path):
    entities, _, _, _ = build(tmp_path)
    client = entities.upsert("company", "Horizon SARL")
    project = entities.upsert("project", "CutForge")

    assert entities.link(project.entity_id, client.entity_id, RelationKind.BELONGS_TO)
    # Restating a known relationship is common and must not duplicate it.
    assert entities.link(project.entity_id, client.entity_id, RelationKind.BELONGS_TO) is None
    # An entity cannot be related to itself.
    assert entities.link(project.entity_id, project.entity_id, RelationKind.RELATED_TO) is None

    edges = entities.relations_of(project.entity_id)
    assert [(other.name, direction) for _relation, other, direction in edges] == [
        ("Horizon SARL", "out")
    ]
    # The same edge is visible from the other end, pointing the other way.
    assert entities.relations_of(client.entity_id)[0][2] == "in"


def test_the_commercial_chain_is_walkable(tmp_path):
    """Client -> Projet -> Devis -> Facture, which is the whole point."""
    entities, _, graph, _ = build(tmp_path)
    client = entities.upsert("company", "Horizon SARL")
    project = entities.upsert("project", "CutForge")
    quote = entities.upsert("quote", "Devis 2026-042", attributes={"amount": "4 000 000 FCFA"})
    invoice = entities.upsert("invoice", "Facture 2026-118")

    entities.link(project.entity_id, client.entity_id, RelationKind.BELONGS_TO)
    entities.link(quote.entity_id, project.entity_id, RelationKind.COVERS)
    entities.link(invoice.entity_id, quote.entity_id, RelationKind.SETTLES)

    brief = graph.brief(project.entity_id)
    labels = {label: other.name for label, other in brief.related}
    assert labels == {"Rattaché à": "Horizon SARL", "Couvert par": "Devis 2026-042"}
    assert "Horizon SARL" in brief.as_text()


# ── briefs ────────────────────────────────────────────────────────────────


def test_a_brief_answers_the_questions_actually_asked(tmp_path):
    entities, _, graph, _ = build(tmp_path)
    project = entities.upsert(
        "project", "Graphiste GPT", summary="Assistant de création graphique"
    )
    client = entities.upsert("company", "Horizon SARL")
    entities.link(project.entity_id, client.entity_id, RelationKind.BELONGS_TO)

    graph.note(project.entity_id, "sortir une bêta publique avant décembre", category="goal")
    graph.note(project.entity_id, "on part sur une facturation à l'usage", category="decision")
    graph.note(project.entity_id, "on abandonne l'abonnement mensuel", category="decision")
    graph.note(project.entity_id, "la génération d'images coûte trop cher", category="issue")

    entities.record_milestone(
        project.entity_id, Milestone.MEETING, "Cadrage avec Horizon", "2026-06-02T09:00:00+00:00"
    )

    brief = graph.brief_by_name("Graphiste GPT")

    # An entity's facts render bare: the project is the subject already.
    assert brief.objectives == ("sortir une bêta publique avant décembre",)
    assert len(brief.decisions) == 2
    assert "coûte trop cher" in brief.open_issues[0]
    text = brief.as_text()
    assert "Graphiste GPT" in text
    assert "en cours" in text
    assert "Problèmes ouverts" in text
    # Empty sections are omitted rather than printed as "aucun".
    assert "aucun" not in text.lower()


def test_a_brief_for_an_unknown_entity_is_none_not_an_invention(tmp_path):
    _, _, graph, _ = build(tmp_path)
    assert graph.brief_by_name("Projet Fantôme") is None


def test_a_closed_project_reads_as_closed(tmp_path):
    entities, _, graph, _ = build(tmp_path)
    project = entities.upsert("project", "Ancien projet")
    entities.set_status(project.entity_id, EntityStatus.CLOSED)
    assert "clos" in graph.brief(project.entity_id).as_text()


# ── timeline ──────────────────────────────────────────────────────────────


def test_the_story_reads_in_order_and_names_what_never_happened(tmp_path):
    entities, _, _, timeline = build(tmp_path)
    client = entities.upsert("company", "Clinique du Lac")

    entities.record_milestone(
        client.entity_id, Milestone.FIRST_CONTACT, "Rencontre au salon santé",
        "2026-01-15T10:00:00+00:00",
    )
    entities.record_milestone(
        client.entity_id, Milestone.MEETING, "Présentation de l'offre",
        "2026-02-03T14:00:00+00:00",
    )
    entities.record_milestone(
        client.entity_id, Milestone.PROPOSAL, "Envoi de la proposition",
        "2026-02-20T09:00:00+00:00",
    )
    entities.record_milestone(
        client.entity_id, Milestone.SIGNATURE, "Contrat signé",
        "2026-03-11T16:00:00+00:00",
    )

    story = timeline.story_by_name("Clinique du Lac")
    text = story.as_text()

    assert text.index("15 janvier 2026") < text.index("3 février 2026") < text.index("11 mars 2026")
    assert "Premier contact" in text
    # A gap in the record is information: a signature with no delivery is a
    # client to call.
    assert "Livraison" in story.missing
    assert story.next_expected == "Livraison"
    assert story.duration_days == 55
    assert "après 19 jours" in text


def test_a_clients_story_includes_what_happened_on_their_projects(tmp_path):
    """The user thinks of it as one history, not five."""
    entities, _, _, timeline = build(tmp_path)
    client = entities.upsert("company", "Horizon SARL")
    project = entities.upsert("project", "CutForge")
    entities.link(project.entity_id, client.entity_id, RelationKind.BELONGS_TO)

    entities.record_milestone(
        client.entity_id, Milestone.FIRST_CONTACT, "Appel entrant", "2026-01-05T10:00:00+00:00"
    )
    entities.record_milestone(
        project.entity_id, Milestone.DELIVERY, "V1 livrée", "2026-04-02T10:00:00+00:00"
    )

    story = timeline.story(client.entity_id)
    assert [entry.milestone for entry in story.entries] == [
        Milestone.FIRST_CONTACT,
        Milestone.DELIVERY,
    ]


def test_an_empty_history_says_so_rather_than_inventing_one(tmp_path):
    entities, _, _, timeline = build(tmp_path)
    entity = entities.upsert("company", "Nouveau contact")
    story = timeline.story(entity.entity_id)
    assert story.entries == ()
    assert "aucun évènement" in story.as_text()
    assert "Racontez-moi" in story.as_text()


# ── through the agent ─────────────────────────────────────────────────────


def app_with(tmp_path, name):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / name,
            cookie_secure=False,
        ),
        brain=Brain(),
    )


def test_the_agent_can_build_and_query_the_graph(tmp_path):
    app = app_with(tmp_path, "tools.db")
    tools = app.state.agent.tools

    tools.get("entity_upsert").handler(
        {"kind": "company", "name": "Horizon SARL", "summary": "Transport urbain"}
    )
    tools.get("entity_upsert").handler(
        {"kind": "project", "name": "CutForge", "summary": "Découpe laser"}
    )
    linked = tools.get("entity_link").handler(
        {
            "from_name": "CutForge",
            "to_name": "Horizon SARL",
            "relation": "belongs_to",
        }
    )
    assert linked["linked"] is True
    assert tools.get("entity_link").handler(
        {"from_name": "CutForge", "to_name": "Horizon SARL", "relation": "belongs_to"}
    )["already_known"] is True

    tools.get("entity_note").handler(
        {"name": "CutForge", "content": "on facture à l'usage", "category": "decision"}
    )
    tools.get("entity_note").handler(
        {"name": "CutForge", "content": "le délai fournisseur bloque la V1", "category": "issue"}
    )
    tools.get("entity_milestone").handler(
        {
            "name": "CutForge",
            "milestone": "proposal",
            "headline": "Proposition envoyée",
            "occurred_at": "2026-05-04T09:00:00+00:00",
        }
    )

    brief = tools.get("entity_brief").handler({"name": "cutforge"})
    assert brief["name"] == "CutForge"
    assert brief["decisions"] == ["on facture à l'usage"]
    assert brief["open_issues"]
    assert brief["related"][0]["name"] == "Horizon SARL"
    assert "Proposition envoyée" in brief["text"]

    story = tools.get("entity_story").handler({"name": "Horizon SARL"})
    assert "Proposition" in story["text"]

    listing = tools.get("entity_list").handler({"kind": "project"})
    assert listing["count"] == 1

    # An unknown name never invents an answer; it offers what is known.
    missing = tools.get("entity_brief").handler({"name": "Projet Fantôme"})
    assert missing["error"] == "entity_not_found"
    assert "CutForge" in missing["known"]


def test_tracked_entities_reach_the_prompt_without_their_substance(tmp_path):
    """Names and statuses on every turn; the detail only when asked for."""
    app = app_with(tmp_path, "context.db")
    app.state.agent.tools.get("entity_upsert").handler(
        {"kind": "project", "name": "CutForge", "summary": "Découpe laser"}
    )
    app.state.entity_graph.note(
        app.state.entities.resolve("CutForge").entity_id,
        "le budget confidentiel est de 4 millions",
        category="note",
    )

    context = app.state.compose_context()
    assert "CutForge" in context
    assert "budget confidentiel" not in context
    assert "entity_brief" in context


@pytest.mark.asyncio
async def test_entity_api(tmp_path):
    app = app_with(tmp_path, "api.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/entities")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        created = await web.post(
            "/v1/entities",
            json={"kind": "project", "name": "CutForge", "summary": "Découpe laser"},
        )
        assert created.status_code == 201
        entity_id = created.json()["entity_id"]

        listing = (await web.get("/v1/entities", params={"kind": "project"})).json()
        assert [item["name"] for item in listing["entities"]] == ["CutForge"]

        brief = (await web.get(f"/v1/entities/{entity_id}")).json()
        assert brief["name"] == "CutForge"
        assert "text" in brief

        story = (await web.get(f"/v1/entities/{entity_id}/story")).json()
        assert story["entries"] == []

        assert (await web.get("/v1/entities/absente")).status_code == 404
