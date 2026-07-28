"""Mission persistence. Every state change hits the database immediately."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.missions.schemas import (
    MAX_STEPS,
    Mission,
    MissionStatus,
    Step,
    StepStatus,
)

_MISSION_COLUMNS = (
    "mission_id, goal, status, conversation_id, error, max_tokens, "
    "created_at, updated_at"
)
_STEP_COLUMNS = (
    "step_id, mission_id, position, description, tool_name, arguments, status, "
    "attempts, result, verification, error, created_at, updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_mission_id() -> str:
    return f"msn_{uuid.uuid4().hex[:12]}"


class MissionRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    def create(
        self,
        goal: str,
        steps: Sequence[tuple[str, str, dict[str, Any]]],
        conversation_id: str = "",
        max_tokens: int | None = None,
    ) -> Mission:
        """Persist a plan. `steps` is (description, tool_name, arguments).

        A plan longer than `MAX_STEPS` is truncated rather than refused: the
        useful part of an over-long plan is its beginning, and losing the whole
        mission to a verbose planner helps nobody.
        """
        mission_id = new_mission_id()
        now = _now()
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO missions ({_MISSION_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mission_id,
                    goal.strip()[:2_000],
                    MissionStatus.PLANNED.value,
                    conversation_id,
                    "",
                    max_tokens,
                    now,
                    now,
                ),
            )
            for position, (description, tool_name, arguments) in enumerate(
                steps[:MAX_STEPS]
            ):
                connection.execute(
                    f"INSERT INTO mission_steps ({_STEP_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"stp_{uuid.uuid4().hex[:12]}",
                        mission_id,
                        position,
                        description.strip()[:500],
                        tool_name,
                        json.dumps(arguments, ensure_ascii=False),
                        StepStatus.PENDING.value,
                        0,
                        None,
                        "",
                        "",
                        now,
                        now,
                    ),
                )
        found = self.get(mission_id)
        assert found is not None
        return found

    def get(self, mission_id: str) -> Mission | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_MISSION_COLUMNS} FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if row is None:
                return None
            steps = connection.execute(
                f"SELECT {_STEP_COLUMNS} FROM mission_steps WHERE mission_id = ? "
                "ORDER BY position",
                (mission_id,),
            ).fetchall()
        return _mission_from(row, steps)

    def list_recent(self, limit: int = 20) -> list[Mission]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_MISSION_COLUMNS} FROM missions "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [mission for row in rows if (mission := self.get(row["mission_id"]))]

    def resumable(self, limit: int = 20) -> list[Mission]:
        """Missions interrupted mid-flight.

        `executing` is the interesting case: a mission in that state when the
        process starts is one that was cut off, since nothing holds it across a
        restart.
        """
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_MISSION_COLUMNS} FROM missions WHERE status IN (?, ?) "
                "ORDER BY created_at LIMIT ?",
                (MissionStatus.PLANNED.value, MissionStatus.EXECUTING.value, limit),
            ).fetchall()
        return [mission for row in rows if (mission := self.get(row["mission_id"]))]

    def set_mission_status(
        self, mission_id: str, status: MissionStatus, error: str = ""
    ) -> Mission | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE missions SET status = ?, error = ?, updated_at = ? "
                "WHERE mission_id = ?",
                (status.value, error[:1_000], _now(), mission_id),
            )
        return self.get(mission_id)

    def update_step(
        self,
        step_id: str,
        status: StepStatus,
        result: dict[str, Any] | None = None,
        verification: str = "",
        error: str = "",
        increment_attempt: bool = False,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE mission_steps SET status = ?, result = ?, verification = ?, "
                "error = ?, attempts = attempts + ?, updated_at = ? WHERE step_id = ?",
                (
                    status.value,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    verification[:500],
                    error[:500],
                    1 if increment_attempt else 0,
                    _now(),
                    step_id,
                ),
            )


def _mission_from(row: sqlite3.Row, step_rows: Sequence[sqlite3.Row]) -> Mission:
    return Mission(
        mission_id=row["mission_id"],
        goal=row["goal"],
        status=MissionStatus(row["status"]),
        conversation_id=row["conversation_id"],
        error=row["error"],
        max_tokens=row["max_tokens"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        steps=tuple(_step_from(step) for step in step_rows),
    )


def _step_from(row: sqlite3.Row) -> Step:
    return Step(
        step_id=row["step_id"],
        mission_id=row["mission_id"],
        position=int(row["position"]),
        description=row["description"],
        tool_name=row["tool_name"],
        arguments=json.loads(row["arguments"] or "{}"),
        status=StepStatus(row["status"]),
        attempts=int(row["attempts"]),
        result=json.loads(row["result"]) if row["result"] else None,
        verification=row["verification"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
