"""The welcome interview must be conversational, and never ask twice."""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.onboarding import OnboardingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.main import create_app


def repositories(tmp_path):
    database = tmp_path / "onboarding.db"
    profiles = ProfileRepository(database)
    return profiles, OnboardingRepository(database, profiles)


def test_progress_is_derived_from_what_the_profile_already_knows(tmp_path):
    profiles, onboarding = repositories(tmp_path)
    first = onboarding.status()
    assert first["progress"] == 0.0
    assert first["next_topic"]["topic_id"] == "personnel"
    assert onboarding.next_question() == first["next_topic"]["opening_question"]

    # Learning happens in conversation; the interview simply notices.
    profiles.update_business({"owner_name": "Koffi Gava", "owner_role": "Directeur général"})
    after = onboarding.status()
    personnel = next(t for t in after["topics"] if t["topic_id"] == "personnel")
    assert personnel["status"] == "suffisant"
    assert after["next_topic"]["topic_id"] == "entreprise"
    assert after["progress"] > 0


def test_a_known_field_is_never_asked_for_again(tmp_path):
    profiles, onboarding = repositories(tmp_path)
    profiles.update_business({"company_name": "Horizon SARL"})
    entreprise = next(t for t in onboarding.status()["topics"] if t["topic_id"] == "entreprise")
    known = [item["field"] for item in entreprise["known_fields"]]
    missing = [item["field"] for item in entreprise["missing_fields"]]
    assert "company_name" in known
    assert "company_name" not in missing

    # Once the interview reaches that topic, the brain is told what it must
    # not ask again — the guard against a second "et vous faites quoi ?".
    profiles.update_business({"owner_name": "Koffi Gava", "owner_role": "Directeur"})
    briefing = onboarding.briefing_for_agent()
    assert "Sujet en cours : Entreprise" in briefing
    assert "Déjà connu : Entreprise" in briefing
    assert "Secteur d'activité" in briefing  # still to learn


def test_skipping_and_completing_are_reversible(tmp_path):
    _, onboarding = repositories(tmp_path)
    onboarding.start()
    assert onboarding.status()["started"] is True

    skipped = onboarding.skip("personnel")
    assert next(t for t in skipped["topics"] if t["topic_id"] == "personnel")["status"] == "ignoré"
    assert skipped["next_topic"]["topic_id"] == "entreprise"

    assert onboarding.complete()["completed"] is True
    assert onboarding.is_needed() is False
    assert onboarding.briefing_for_agent() == ""

    reopened = onboarding.reopen()
    assert reopened["completed"] is False
    assert reopened["next_topic"]["topic_id"] == "personnel"

    with pytest.raises(ValueError):
        onboarding.skip("sujet-inexistant")


def test_preferred_name_drives_how_emefa_addresses_the_executive(tmp_path):
    profiles, onboarding = repositories(tmp_path)
    profiles.update_business({"owner_name": "Koffi Gava", "preferred_name": "M. Gava"})
    assert onboarding.status()["address_as"] == "M. Gava"
    assert "Tu t'adresses à M. Gava." in profiles.system_context()


class RecordingBrain:
    """Captures the system context handed to the brain."""

    def __init__(self):
        self.contexts: list[str] = []

    async def think(self, history, tools):
        self.contexts.append(str(history))
        return AgentStep(answer="Enchantée.")


@pytest.mark.asyncio
async def test_onboarding_api_reflects_the_same_state_as_the_conversation(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=RecordingBrain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/onboarding/status")).status_code == 401

        started = await client.post("/v1/onboarding/start", headers=headers)
        assert started.status_code == 200
        assert started.json()["started"] is True

        status = (await client.get("/v1/onboarding/status", headers=headers)).json()
        assert status["next_question"]
        assert len(status["topics"]) == 5

        # Answering through the ordinary profile API advances the interview.
        await client.patch(
            "/v1/assistant/business",
            headers=headers,
            json={"owner_name": "Koffi Gava", "owner_role": "Directeur"},
        )
        advanced = (await client.get("/v1/onboarding/status", headers=headers)).json()
        assert advanced["next_topic"]["topic_id"] == "entreprise"

        skipped = await client.post(
            "/v1/onboarding/skip", headers=headers, json={"topic_id": "preferences"}
        )
        assert skipped.status_code == 200
        assert (
            await client.post("/v1/onboarding/skip", headers=headers, json={"topic_id": "nope"})
        ).status_code == 404

        completed = await client.post("/v1/onboarding/complete", headers=headers)
        assert completed.json()["completed"] is True
        assert (await client.post("/v1/onboarding/reopen", headers=headers)).json()["completed"] is False


@pytest.mark.asyncio
async def test_configuration_centre_exposes_every_field_it_can_edit(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "schema.db"), brain=RecordingBrain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        schema = (await client.get("/v1/assistant/business/schema", headers=headers)).json()
        profile = (await client.get("/v1/assistant/business", headers=headers)).json()

    groups = {group["group"] for group in schema}
    assert groups == {"personnel", "entreprise", "activite", "objectifs", "preferences"}
    # Nothing EMEFA stores may be hidden from its owner.
    exposed = {field["field"] for group in schema for field in group["fields"]}
    assert exposed <= set(profile)
    assert exposed >= {
        "preferred_name", "timezone", "working_hours", "products", "collaborators",
        "clients", "suppliers", "partners", "annual_goals", "quarterly_goals",
        "current_priorities", "challenges", "autonomy_level", "communication_style",
        "report_frequency",
    }
