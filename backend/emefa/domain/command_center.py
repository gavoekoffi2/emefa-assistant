"""Persistent, single-tenant command-center data.

The module is intentionally small and policy-free: API and agent layers validate
input, while this repository owns durable state and deterministic scheduling
queries. No external project code is used here.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain.storage import (
    DEFAULT_TENANT_ID,
    DEFAULT_USER_ID,
    connect,
    run_migrations,
)

INITIATIVE_STATUSES = ("proposed", "active", "paused", "completed", "cancelled")
PRIORITIES = ("low", "normal", "high", "critical")
RISKS = ("low", "medium", "high")
SCHEDULE_KINDS = ("manual", "daily", "weekly")


@dataclass(frozen=True, slots=True)
class Initiative:
    initiative_id: str
    title: str
    objective: str
    status: str
    priority: str
    risk: str
    autonomy_level: int
    next_action: str
    due_date: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class Routine:
    routine_id: str
    name: str
    prompt: str
    schedule_kind: str
    schedule_hour: int | None
    schedule_weekday: int | None
    enabled: bool
    requires_confirmation: bool
    last_run_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RoutineRun:
    run_id: str
    routine_id: str
    status: str
    result: str
    action_id: str | None
    started_at: str
    finished_at: str | None


def _initiative(row: Any) -> Initiative:
    return Initiative(**{field: row[field] for field in Initiative.__dataclass_fields__})


def _routine(row: Any) -> Routine:
    payload = {field: row[field] for field in Routine.__dataclass_fields__}
    payload["enabled"] = bool(payload["enabled"])
    payload["requires_confirmation"] = bool(payload["requires_confirmation"])
    return Routine(**payload)


def _run(row: Any) -> RoutineRun:
    return RoutineRun(**{field: row[field] for field in RoutineRun.__dataclass_fields__})


class InitiativeRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        run_migrations(database_path)

    def add(
        self,
        title: str,
        *,
        objective: str = "",
        status: str = "proposed",
        priority: str = "normal",
        risk: str = "low",
        autonomy_level: int = 0,
        next_action: str = "",
        due_date: str | None = None,
    ) -> Initiative:
        initiative_id = f"ini_{uuid.uuid4().hex[:12]}"
        with connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO initiatives
                (initiative_id, tenant_id, user_id, title, objective, status,
                 priority, risk, autonomy_level, next_action, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    initiative_id, DEFAULT_TENANT_ID, DEFAULT_USER_ID,
                    title.strip()[:300], objective.strip()[:5_000], status,
                    priority, risk, autonomy_level, next_action.strip()[:2_000], due_date,
                ),
            )
        item = self.get(initiative_id)
        assert item is not None
        return item

    def get(self, initiative_id: str) -> Initiative | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM initiatives WHERE initiative_id = ? AND user_id = ?",
                (initiative_id, DEFAULT_USER_ID),
            ).fetchone()
        return _initiative(row) if row else None

    def list(self, include_closed: bool = True, limit: int = 100) -> list[Initiative]:
        where = "user_id = ?"
        params: list[Any] = [DEFAULT_USER_ID]
        if not include_closed:
            where += " AND status NOT IN ('completed', 'cancelled')"
        params.append(max(1, min(limit, 250)))
        with connect(self.database_path) as connection:
            rows = connection.execute(
                f"""SELECT * FROM initiatives WHERE {where}
                ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                WHEN 'normal' THEN 2 ELSE 3 END, COALESCE(due_date, '9999-12-31'), updated_at DESC
                LIMIT ?""",
                params,
            ).fetchall()
        return [_initiative(row) for row in rows]

    def update(self, initiative_id: str, changes: dict[str, Any]) -> Initiative | None:
        allowed = {
            "title", "objective", "status", "priority", "risk",
            "autonomy_level", "next_action", "due_date",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return self.get(initiative_id)
        assignments = ", ".join(f"{key} = ?" for key in values)
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                f"UPDATE initiatives SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE initiative_id = ? AND user_id = ?",
                (*values.values(), initiative_id, DEFAULT_USER_ID),
            )
        return self.get(initiative_id) if cursor.rowcount else None

    def context_block(self, limit: int = 8) -> str:
        items = self.list(include_closed=False, limit=limit)
        if not items:
            return ""
        lines = ["Initiatives actives suivies par l'utilisateur (données de référence) :"]
        for item in items:
            suffix = f" — prochaine action: {item.next_action}" if item.next_action else ""
            lines.append(f"- [{item.priority}/{item.status}] {item.title}{suffix}")
        return "\n".join(lines)


class RoutineRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        run_migrations(database_path)

    def add(
        self,
        name: str,
        prompt: str,
        *,
        schedule_kind: str = "manual",
        schedule_hour: int | None = None,
        schedule_weekday: int | None = None,
        enabled: bool = True,
    ) -> Routine:
        routine_id = f"rtn_{uuid.uuid4().hex[:12]}"
        with connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO routines
                (routine_id, tenant_id, user_id, name, prompt, schedule_kind,
                 schedule_hour, schedule_weekday, enabled, requires_confirmation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    routine_id, DEFAULT_TENANT_ID, DEFAULT_USER_ID,
                    name.strip()[:200], prompt.strip()[:10_000], schedule_kind,
                    schedule_hour, schedule_weekday, int(enabled),
                ),
            )
        item = self.get(routine_id)
        assert item is not None
        return item

    def get(self, routine_id: str) -> Routine | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM routines WHERE routine_id = ? AND user_id = ?",
                (routine_id, DEFAULT_USER_ID),
            ).fetchone()
        return _routine(row) if row else None

    def list(self, enabled_only: bool = False, limit: int = 100) -> list[Routine]:
        condition = "AND enabled = 1" if enabled_only else ""
        with connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT * FROM routines WHERE user_id = ? {condition} "
                "ORDER BY enabled DESC, updated_at DESC LIMIT ?",
                (DEFAULT_USER_ID, max(1, min(limit, 250))),
            ).fetchall()
        return [_routine(row) for row in rows]

    def update(self, routine_id: str, changes: dict[str, Any]) -> Routine | None:
        allowed = {"name", "prompt", "schedule_kind", "schedule_hour", "schedule_weekday", "enabled"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "enabled" in values:
            values["enabled"] = int(bool(values["enabled"]))
        if not values:
            return self.get(routine_id)
        assignments = ", ".join(f"{key} = ?" for key in values)
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                f"UPDATE routines SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE routine_id = ? AND user_id = ?",
                (*values.values(), routine_id, DEFAULT_USER_ID),
            )
        return self.get(routine_id) if cursor.rowcount else None

    def due(self, now: datetime) -> list[Routine]:
        today = now.date().isoformat()
        result: list[Routine] = []
        for routine in self.list(enabled_only=True):
            if routine.schedule_kind == "manual" or routine.schedule_hour != now.hour:
                continue
            if routine.schedule_kind == "weekly" and routine.schedule_weekday != now.weekday():
                continue
            if routine.last_run_at and routine.last_run_at[:10] == today:
                continue
            result.append(routine)
        return result

    def start_run(self, routine_id: str) -> RoutineRun:
        run_id = f"rrn_{uuid.uuid4().hex[:12]}"
        with connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO routine_runs
                (run_id, routine_id, tenant_id, user_id, status)
                VALUES (?, ?, ?, ?, 'running')""",
                (run_id, routine_id, DEFAULT_TENANT_ID, DEFAULT_USER_ID),
            )
            connection.execute(
                "UPDATE routines SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                "WHERE routine_id = ?",
                (routine_id,),
            )
        run = self.get_run(run_id)
        assert run is not None
        return run

    def finish_run(self, run_id: str, status: str, result: str = "", action_id: str | None = None) -> RoutineRun:
        with connect(self.database_path) as connection:
            connection.execute(
                """UPDATE routine_runs SET status = ?, result = ?, action_id = ?,
                finished_at = CURRENT_TIMESTAMP WHERE run_id = ?""",
                (status, result[:10_000], action_id, run_id),
            )
        run = self.get_run(run_id)
        assert run is not None
        return run

    def get_run(self, run_id: str) -> RoutineRun | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM routine_runs WHERE run_id = ? AND user_id = ?",
                (run_id, DEFAULT_USER_ID),
            ).fetchone()
        return _run(row) if row else None

    def list_runs(self, limit: int = 50) -> list[RoutineRun]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM routine_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (DEFAULT_USER_ID, max(1, min(limit, 200))),
            ).fetchall()
        return [_run(row) for row in rows]

    def export(self) -> dict[str, Any]:
        return {
            "routines": [asdict(item) for item in self.list()],
            "runs": [asdict(item) for item in self.list_runs()],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
