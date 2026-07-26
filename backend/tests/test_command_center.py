from datetime import datetime, timezone

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.command_center import InitiativeRepository, RoutineRepository
from emefa.main import create_app


class RoutineBrain:
    async def think(self, history, tools):
        return AgentStep(answer="Routine analysée sans action externe.")


def test_command_center_repositories_persist_and_detect_due_routines(tmp_path):
    database = tmp_path / "command.db"
    initiatives = InitiativeRepository(database)
    created = initiatives.add(
        "Lancer le nouveau service",
        status="active",
        priority="high",
        next_action="Valider le positionnement",
    )
    assert initiatives.get(created.initiative_id) == created
    assert "Lancer le nouveau service" in initiatives.context_block()

    routines = RoutineRepository(database)
    daily = routines.add(
        "Revue du matin",
        "Prépare une revue factuelle de mes priorités.",
        schedule_kind="daily",
        schedule_hour=9,
    )
    assert routines.due(datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)) == [daily]
    run = routines.start_run(daily.routine_id)
    routines.finish_run(run.run_id, "completed", "Revue prête")
    assert routines.due(datetime(2026, 7, 26, 9, 30, tzinfo=timezone.utc)) == []


@pytest.mark.asyncio
async def test_command_center_api_full_visible_path(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CENTRE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=RoutineBrain(),
    )
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/v1/command-center/snapshot")
        assert unauthorized.status_code == 401

        created = await client.post(
            "/v1/command-center/initiatives",
            headers=headers,
            json={
                "title": "Développer EMEFA",
                "objective": "Livrer une assistante réellement utile",
                "status": "active",
                "priority": "critical",
                "risk": "medium",
                "autonomy_level": 1,
                "next_action": "Vérifier le centre de pilotage",
            },
        )
        assert created.status_code == 201
        initiative_id = created.json()["initiative_id"]
        updated = await client.patch(
            f"/v1/command-center/initiatives/{initiative_id}",
            headers=headers,
            json={"next_action": "Tester en production"},
        )
        assert updated.status_code == 200
        assert updated.json()["next_action"] == "Tester en production"

        invalid_routine = await client.post(
            "/v1/command-center/routines",
            headers=headers,
            json={
                "name": "Routine incomplète",
                "prompt": "Analyse mes priorités",
                "schedule_kind": "daily",
            },
        )
        assert invalid_routine.status_code == 422

        routine_response = await client.post(
            "/v1/command-center/routines",
            headers=headers,
            json={
                "name": "Revue hebdomadaire",
                "prompt": "Analyse mes priorités de la semaine.",
                "schedule_kind": "weekly",
                "schedule_hour": 8,
                "schedule_weekday": 0,
            },
        )
        assert routine_response.status_code == 201
        assert routine_response.json()["requires_confirmation"] is True
        routine_id = routine_response.json()["routine_id"]

        executed = await client.post(
            f"/v1/command-center/routines/{routine_id}/run",
            headers=headers,
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "completed"
        assert executed.json()["result"] == "Routine analysée sans action externe."

        snapshot = await client.get("/v1/command-center/snapshot", headers=headers)
        assert snapshot.status_code == 200
        body = snapshot.json()
        assert body["initiative_counts"]["active"] == 1
        assert body["active_routine_count"] == 1
        assert body["skill_count"] >= 5
        assert body["recent_runs"][0]["status"] == "completed"
