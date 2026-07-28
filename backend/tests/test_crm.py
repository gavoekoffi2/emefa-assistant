"""The executive CRM must answer the questions asked out loud."""

from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.crm import CrmError, CrmRepository
from emefa.main import create_app

TODAY = date(2026, 7, 28)


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def ahead(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def test_follow_ups_surface_only_silent_active_clients(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    quiet = crm.save_contact(name="Ama Mensah", kind="client", company="Mensah Logistics")
    crm.log_interaction("Point trimestriel", contact_id=quiet.contact_id, occurred_at=ago(45))
    recent = crm.save_contact(name="Kodjo Alaza", kind="client")
    crm.log_interaction("Appel", contact_id=recent.contact_id, occurred_at=ago(2))
    supplier = crm.save_contact(name="Fournisseur X", kind="fournisseur")
    crm.log_interaction("Commande", contact_id=supplier.contact_id, occurred_at=ago(90))

    names = [item["name"] for item in crm.follow_ups(TODAY)]
    assert names == ["Ama Mensah"]
    assert crm.follow_ups(TODAY)[0]["silent_days"] == 45


def test_awaiting_deals_respects_deadline_then_falls_back_to_age(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    client = crm.save_contact(name="Horizon SARL", kind="client")
    overdue = crm.save_deal(
        title="Refonte du site", contact_id=client.contact_id, amount=1_500_000,
        stage="envoyé", sent_at=ago(20), response_due_date=ago(3),
    )
    crm.save_deal(
        title="Maintenance", contact_id=client.contact_id, stage="envoyé",
        sent_at=ago(2), response_due_date=ahead(10),
    )
    stale = crm.save_deal(title="Audit", contact_id=client.contact_id, stage="relancé", sent_at=ago(9))
    crm.save_deal(title="Brouillon interne", contact_id=client.contact_id, stage="brouillon")

    awaiting = crm.awaiting_deals(TODAY)
    assert {item["deal_id"] for item in awaiting} == {overdue.deal_id, stale.deal_id}
    assert awaiting[0]["waiting_days"] == 20
    assert awaiting[0]["contact_name"] == "Horizon SARL"


def test_expiring_contracts_honour_status_and_notice(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    soon = crm.save_contract(title="Infogérance", end_date=ahead(20), status="actif")
    crm.save_contract(title="Bail longue durée", end_date=ahead(400), status="actif")
    crm.save_contract(title="Contrat résilié", end_date=ahead(5), status="résilié")
    long_notice = crm.save_contract(
        title="Prestation annuelle", end_date=ahead(80), status="actif", notice_days=90
    )

    expiring = crm.expiring_contracts(within_days=60, today=TODAY)
    assert {item["contract_id"] for item in expiring} == {soon.contract_id, long_notice.contract_id}
    assert expiring[0]["days_to_expiry"] == 20


def test_blocked_projects_include_late_and_unhealthy(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    blocked = crm.save_project(name="Plateforme", status="bloqué", blocker="Attente juridique")
    late = crm.save_project(name="Migration", status="en_cours", due_date=ago(5))
    crm.save_project(name="Sain", status="en_cours", due_date=ahead(30))
    critical = crm.save_project(name="Refonte", status="en_cours", health="critique")

    found = {item["project_id"] for item in crm.blocked_projects(TODAY)}
    assert found == {blocked.project_id, late.project_id, critical.project_id}


def test_lookup_walks_the_relationship_graph(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    client = crm.save_contact(name="Horizon SARL", kind="client", email="contact@horizon.tg")
    project = crm.save_project(
        name="Refonte digitale", contact_id="Horizon SARL", status="bloqué",
        blocker="Validation des maquettes", next_step="Relancer le comité",
    )
    crm.save_deal(title="Phase 1", contact_id=client.contact_id, amount=900_000, stage="envoyé", sent_at=ago(15))
    crm.save_contract(title="Cadre 2026", contact_id=client.contact_id, end_date=ahead(30), status="actif")
    crm.log_interaction("Comité de pilotage", kind="réunion", project_id=project.project_id, occurred_at=ago(4))

    view = crm.lookup("refonte digitale", TODAY)
    assert view["found"] is True
    assert view["project"]["name"] == "Refonte digitale"
    assert view["contact"]["name"] == "Horizon SARL"
    assert [deal["title"] for deal in view["deals"]] == ["Phase 1"]
    assert [contract["title"] for contract in view["contracts"]] == ["Cadre 2026"]
    assert view["history"][0]["summary"] == "Comité de pilotage"
    assert view["signals"]["project_blocked"] is True
    assert view["signals"]["awaiting_deals"] == 1

    assert crm.lookup("client inconnu", TODAY)["found"] is False


def test_names_resolve_to_ids_so_the_agent_never_guesses(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    client = crm.save_contact(name="Horizon SARL", kind="client")
    project = crm.save_project(name="Refonte", contact_id="horizon")
    assert project.contact_id == client.contact_id
    deal = crm.save_deal(title="Lot 1", project_id="Refonte")
    assert deal.project_id == project.project_id
    with pytest.raises(CrmError):
        crm.save_project(name="Autre", contact_id="société fantôme")


def test_interaction_updates_last_contact_and_rejects_bad_input(tmp_path):
    crm = CrmRepository(tmp_path / "crm.db")
    client = crm.save_contact(name="Ama", kind="client")
    crm.log_interaction("Appel de suivi", kind="appel", contact_id=client.contact_id, occurred_at=ago(1))
    assert crm.get_contact(client.contact_id).last_interaction_at == ago(1)
    with pytest.raises(CrmError):
        crm.log_interaction("Test", kind="télépathie", contact_id=client.contact_id)
    with pytest.raises(CrmError):
        crm.save_deal(title="Mauvais devis", stage="inventé")
    with pytest.raises(CrmError):
        crm.save_contract(title="Mauvaise date", end_date="pas-une-date")


class SilentBrain:
    async def think(self, history, tools):
        return AgentStep(answer="Compris.")


@pytest.mark.asyncio
async def test_crm_api_is_authenticated_and_fully_editable(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=SilentBrain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/crm/overview")).status_code == 401

        created = await client.post(
            "/v1/crm/contacts",
            headers=headers,
            json={"name": "Horizon SARL", "kind": "client", "email": "contact@horizon.tg"},
        )
        assert created.status_code == 201
        contact_id = created.json()["contact_id"]

        rejected = await client.post(
            "/v1/crm/contacts", headers=headers, json={"name": "X", "kind": "clientX"}
        )
        assert rejected.status_code == 422

        project = await client.post(
            "/v1/crm/projects",
            headers=headers,
            json={"name": "Refonte", "contact_id": contact_id, "status": "bloqué",
                  "blocker": "Validation en attente"},
        )
        assert project.status_code == 201
        assert project.json()["status"] == "bloqué"

        await client.post(
            "/v1/crm/deals",
            headers=headers,
            json={"title": "Phase 1", "contact_id": contact_id, "amount": 750000,
                  "stage": "envoyé", "sent_at": "2026-01-01"},
        )
        await client.post(
            "/v1/crm/contracts",
            headers=headers,
            json={"title": "Cadre", "contact_id": contact_id, "end_date": "2026-08-01",
                  "status": "actif"},
        )
        await client.post(
            "/v1/crm/interactions",
            headers=headers,
            json={"summary": "Réunion de lancement", "kind": "réunion", "contact_id": contact_id},
        )

        overview = (await client.get("/v1/crm/overview", headers=headers)).json()
        assert overview["counts"]["awaiting_deals"] == 1
        assert overview["counts"]["blocked_projects"] == 1

        lookup = (await client.get("/v1/crm/lookup", headers=headers, params={"query": "Horizon"})).json()
        assert lookup["found"] is True
        assert lookup["contact"]["name"] == "Horizon SARL"

        patched = await client.patch(
            f"/v1/crm/contacts/{contact_id}", headers=headers, json={"notes": "Client historique"}
        )
        assert patched.json()["notes"] == "Client historique"

        deleted = await client.delete(f"/v1/crm/contacts/{contact_id}", headers=headers)
        assert deleted.status_code == 204
        assert (await client.delete(f"/v1/crm/contacts/{contact_id}", headers=headers)).status_code == 404
