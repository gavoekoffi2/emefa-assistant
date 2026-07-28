"""When a name is ambiguous, EMEFA must ask — never quietly pick one.

Silently choosing the wrong "Horizon" is the worst class of failure this
product can produce: it attaches a proposal, a meeting or a follow-up to the
wrong relationship, confidently and invisibly. Every path that resolves a name
is covered here.
"""

import pytest

from emefa.config import Settings
from emefa.domain.agenda import AgendaRepository
from emefa.domain.agent import AgentStep
from emefa.domain.crm import AmbiguousMatchError, CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.meetings import MeetingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.tasks import TaskRepository
from emefa.domain.workflows import WorkflowEngine
from emefa.main import create_app


@pytest.fixture
def crowded(tmp_path):
    """Two clients whose names collide, plus one that does not."""
    crm = CrmRepository(tmp_path / "ambiguous.db")
    crm.save_contact(name="Horizon Group", kind="client", email="a@horizon.tg")
    crm.save_contact(name="Horizon Logistics", kind="client", email="b@horizon.tg")
    crm.save_contact(name="Ama Mensah", kind="client", email="ama@mensah.tg")
    return tmp_path / "ambiguous.db", crm


def test_resolution_refuses_to_choose_between_equal_matches(crowded):
    _, crm = crowded
    with pytest.raises(AmbiguousMatchError) as raised:
        crm.resolve_contact("Horizon")
    error = raised.value
    assert error.kind == "contact"
    assert {item["name"] for item in error.candidates} == {"Horizon Group", "Horizon Logistics"}
    assert str(error) == "ambiguous_contact"

    # An unambiguous name still resolves without friction.
    assert crm.resolve_contact("Ama") is not None
    assert crm.resolve_contact("Horizon Group") is not None


def test_an_exact_match_is_never_made_ambiguous_by_a_longer_name(tmp_path):
    crm = CrmRepository(tmp_path / "tiers.db")
    exact = crm.save_contact(name="Horizon", kind="client")
    crm.save_contact(name="Horizon Group", kind="client")
    # "Horizon" is exactly one record; the longer name is a weaker tier.
    assert crm.resolve_contact("Horizon") == exact.contact_id


def test_projects_are_disambiguated_too(tmp_path):
    crm = CrmRepository(tmp_path / "projects.db")
    crm.save_project(name="Refonte du site")
    crm.save_project(name="Refonte de l'ERP")
    with pytest.raises(AmbiguousMatchError) as raised:
        crm.resolve_project("Refonte")
    assert raised.value.kind == "project"
    assert len(raised.value.candidates) == 2
    assert crm.resolve_project("Refonte du site") is not None


def test_lookup_returns_the_candidates_instead_of_answering_about_one(crowded):
    _, crm = crowded
    view = crm.lookup("Horizon")
    assert view["found"] is False
    assert view["ambiguous"] is True
    assert {item["name"] for item in view["candidates"]} == {
        "Horizon Group", "Horizon Logistics"
    }
    # A precise query still answers normally.
    assert crm.lookup("Ama Mensah")["found"] is True


def test_a_proposal_never_creates_a_duplicate_client(crowded, tmp_path):
    database, crm = crowded
    workflows = WorkflowEngine(
        ProfileRepository(database), crm, DocumentStore(database), TaskRepository(database)
    )
    before = len(crm.list_contacts())
    with pytest.raises(AmbiguousMatchError):
        workflows.commercial_proposal(client="Horizon", subject="Audit", amount=100_000)
    # Nothing was created, written or promised.
    assert len(crm.list_contacts()) == before
    assert crm.list_deals() == []
    assert DocumentStore(database).list() == []


def test_a_follow_up_reports_the_ambiguity_as_a_status(crowded, tmp_path):
    database, crm = crowded
    workflows = WorkflowEngine(
        ProfileRepository(database), crm, DocumentStore(database), TaskRepository(database)
    )
    result = workflows.follow_up(client="Horizon")
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert "proposed_action" not in result


def test_meeting_capture_reports_ambiguous_links_without_losing_the_meeting(crowded, tmp_path):
    database, crm = crowded
    meetings = MeetingRepository(
        database, crm, TaskRepository(database), DocumentStore(database)
    )
    result = meetings.capture(title="Point commercial", contact="Horizon")
    # The meeting is still recorded — only the link is left open.
    assert meetings.get(result["meeting_id"]) is not None
    assert result["contact_id"] is None
    assert result["ambiguous_links"][0]["reference"] == "Horizon"
    assert len(result["ambiguous_links"][0]["candidates"]) == 2


def test_agenda_refuses_an_ambiguous_link(crowded, tmp_path):
    database, crm = crowded
    agenda = AgendaRepository(database, crm, TaskRepository(database))
    with pytest.raises(AmbiguousMatchError):
        agenda.save_event(title="Réunion", starts_at="2026-08-01T10:00", contact_id="Horizon")


class ProposalBrain:
    """Asks for a proposal on an ambiguous client, then reads the tool result."""

    def __init__(self):
        self.calls = 0
        self.tool_result = None

    async def think(self, history, tools):
        from emefa.domain.agent import RequestedAction

        self.calls += 1
        if self.calls == 1:
            return AgentStep(action=RequestedAction(
                name="workflow_commercial_proposal",
                arguments={"client": "Horizon", "subject": "Audit", "amount": 100000},
            ))
        self.tool_result = next(
            item for item in reversed(history) if item.get("role") == "tool"
        )["content"]
        return AgentStep(answer="De quel Horizon s'agit-il ?")


@pytest.mark.asyncio
async def test_the_skill_hands_the_question_back_to_the_assistant(tmp_path):
    """End to end: the model receives candidates and an instruction to ask."""
    import httpx

    brain = ProposalBrain()
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=brain)
    app.state.crm.save_contact(name="Horizon Group", kind="client")
    app.state.crm.save_contact(name="Horizon Logistics", kind="client")
    token = app.state.devices.enroll("Claude")[1]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        run = await client.post(
            "/v1/agent/runs",
            json={"message": "Prépare une proposition pour Horizon"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert run.json()["status"] == "completed"
    # The tool returned a question, not a guess — and nothing was created.
    assert brain.tool_result["error"] == "ambiguous_contact"
    assert len(brain.tool_result["candidates"]) == 2
    assert "Demande" in brain.tool_result["instruction"]
    assert app.state.crm.list_deals() == []
    assert len(app.state.crm.list_contacts()) == 2


@pytest.mark.asyncio
async def test_the_api_answers_409_with_the_candidates(tmp_path):
    """A well-formed request whose *target* is undecided is a conflict, not a
    validation error — and the client is given what it needs to ask."""
    import httpx

    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="ok")

    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=Brain())
    app.state.crm.save_contact(name="Horizon Group", kind="client")
    app.state.crm.save_contact(name="Horizon Logistics", kind="client")
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        project = await client.post(
            "/v1/crm/projects", headers=headers,
            json={"name": "Refonte", "contact_id": "Horizon"},
        )
        event = await client.post(
            "/v1/agenda", headers=headers,
            json={"title": "Réunion", "starts_at": "2026-08-01T10:00", "contact_id": "Horizon"},
        )
        lookup = await client.get("/v1/crm/lookup", headers=headers, params={"query": "Horizon"})

    assert project.status_code == 409
    assert project.json()["detail"]["error"] == "ambiguous_contact"
    assert len(project.json()["detail"]["candidates"]) == 2
    assert event.status_code == 409
    # The read model reports ambiguity in its payload rather than as an error.
    assert lookup.status_code == 200
    assert lookup.json()["ambiguous"] is True
