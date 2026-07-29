"""The executive's agenda, and the preparation an assistant does before a meeting.

Mission §3 requires the morning briefing to open on the day's schedule, and §28
lists meeting preparation as a priority workflow. Neither is possible without a
place to hold appointments.

Two deliberate design choices:

**Local first, provider-ready.** Events live in our own table and are created by
conversation ("j'ai rendez-vous jeudi à 10 h avec Ama"). A `CalendarProvider`
protocol and the `source`/`external_id` columns exist so a Google or Microsoft
calendar can be *synced in* later as one more source, without the agenda
becoming a thin wrapper around somebody else's API (CLAUDE.md §16). Nothing
here pretends a sync exists today.

**Preparation is a read, not a generation.** `prepare()` assembles what is
already known about the person and the project — history, quotations,
contracts, open tasks, blockers — so the assistant walks in briefed rather than
improvising (§25).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from emefa.domain.crm import AmbiguousMatchError, CrmError, CrmRepository
from emefa.domain.scope import Scope, ScopedStore
from emefa.domain.tasks import TaskRepository

EVENT_KINDS = ("rendez_vous", "réunion", "déplacement", "échéance", "personnel")

_COLUMNS = (
    "event_id, title, kind, starts_at, ends_at, location, participants, "
    "contact_id, project_id, notes, source, external_id, meeting_id, "
    "created_at, updated_at"
)

#: Default length assumed when the executive gives a start time and no end.
DEFAULT_DURATION_MINUTES = 60


class AgendaError(ValueError):
    """Invalid agenda input (bad time, unknown kind, unknown link)."""


def parse_moment(value: object, field: str = "starts_at") -> str:
    """Accept the shapes a conversation produces, store one canonical form.

    ``2026-07-30T10:00`` · ``2026-07-30 10:00`` · ``2026-07-30`` (whole day,
    stored at 00:00). Anything else is rejected rather than guessed.
    """
    text = str(value or "").strip().replace(" ", "T")
    if not text:
        raise AgendaError(f"missing_{field}")
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue
    raise AgendaError(f"invalid_{field}")


def _text(value: object, limit: int = 2_000) -> str:
    return str(value or "").strip()[:limit]


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    title: str
    kind: str
    starts_at: str
    ends_at: str | None
    location: str
    participants: str
    contact_id: str | None
    project_id: str | None
    notes: str
    source: str
    external_id: str | None
    meeting_id: str | None
    created_at: str
    updated_at: str

    @property
    def start(self) -> datetime:
        return datetime.strptime(self.starts_at, "%Y-%m-%dT%H:%M")

    @property
    def end(self) -> datetime:
        if self.ends_at:
            try:
                return datetime.strptime(self.ends_at, "%Y-%m-%dT%H:%M")
            except ValueError:
                pass
        return self.start + timedelta(minutes=DEFAULT_DURATION_MINUTES)

    def on(self, day: date) -> bool:
        return self.start.date() == day

    def overlaps(self, other: Event) -> bool:
        return self.start < other.end and other.start < self.end

    def label(self) -> str:
        when = self.start.strftime("%H:%M")
        where = f" — {self.location}" if self.location else ""
        return f"{when} {self.title}{where}"


class CalendarProvider(Protocol):
    """A source of events. The local table is one; a synced calendar is another."""

    source_name: str

    def fetch(self, since: date, until: date) -> list[dict[str, Any]]: ...


class AgendaRepository(ScopedStore):
    def __init__(
        self,
        database_path: Path,
        crm: CrmRepository | None = None,
        tasks: TaskRepository | None = None,
        scope: Scope | None = None,
    ) -> None:
        super().__init__(database_path, scope)
        self.crm = crm
        self.tasks = tasks

    def for_scope(self, scope: Scope) -> "AgendaRepository":
        return AgendaRepository(
            self.database_path,
            self.crm.for_scope(scope) if self.crm is not None else None,
            self.tasks.for_scope(scope) if self.tasks is not None else None,
            scope,
        )

    # -- writes -----------------------------------------------------------

    def save_event(self, event_id: str | None = None, **fields: Any) -> Event:
        values: dict[str, Any] = {}
        if "title" in fields:
            values["title"] = _text(fields["title"], 200)
        if "kind" in fields:
            kind = _text(fields["kind"], 40)
            if kind not in EVENT_KINDS:
                raise AgendaError("invalid_kind")
            values["kind"] = kind
        if "starts_at" in fields:
            values["starts_at"] = parse_moment(fields["starts_at"], "starts_at")
        if "ends_at" in fields:
            values["ends_at"] = (
                parse_moment(fields["ends_at"], "ends_at") if fields["ends_at"] else None
            )
        for field in ("location", "notes"):
            if field in fields:
                values[field] = _text(fields[field])
        if "participants" in fields:
            people = fields["participants"]
            if isinstance(people, (list, tuple)):
                people = ", ".join(_text(person, 120) for person in people if _text(person))
            values["participants"] = _text(people)
        if "contact_id" in fields and self.crm is not None:
            values["contact_id"] = self._link(self.crm.resolve_contact, fields["contact_id"])
        if "project_id" in fields and self.crm is not None:
            values["project_id"] = self._link(self.crm.resolve_project, fields["project_id"])
        if "meeting_id" in fields:
            values["meeting_id"] = _text(fields["meeting_id"], 64) or None

        if values.get("ends_at") and values.get("starts_at"):
            if values["ends_at"] < values["starts_at"]:
                raise AgendaError("ends_before_starts")

        if event_id:
            if self.get(event_id) is None:
                raise AgendaError("event_not_found")
            self._update(event_id, values)
            found = self.get(event_id)
        else:
            if not values.get("title"):
                raise AgendaError("title_required")
            if not values.get("starts_at"):
                raise AgendaError("missing_starts_at")
            new_id = uuid.uuid4().hex
            values["event_id"] = new_id
            self._insert(values)
            found = self.get(new_id)
        assert found is not None
        return found

    @staticmethod
    def _link(resolver: Any, reference: object) -> str | None:
        try:
            return resolver(reference)
        except AmbiguousMatchError:
            raise  # the caller must ask which record was meant
        except CrmError as error:
            raise AgendaError(str(error)) from error

    def delete(self, event_id: str) -> bool:
        return self.delete_scoped("events", "event_id", event_id)

    def sync(self, provider: CalendarProvider, since: date, until: date) -> dict[str, int]:
        """Pull an external calendar in. Idempotent on ``(source, external_id)``.

        No provider ships today; this is the seam a Google/Microsoft adapter
        plugs into, and it is exercised by tests with a fake provider so the
        contract cannot rot before the real one arrives.
        """
        imported = updated = skipped = 0
        for raw in provider.fetch(since, until):
            external_id = _text(raw.get("external_id"), 200)
            if not external_id:
                skipped += 1
                continue
            try:
                values = {
                    "title": _text(raw.get("title"), 200) or "Sans titre",
                    "kind": raw.get("kind") if raw.get("kind") in EVENT_KINDS else "rendez_vous",
                    "starts_at": parse_moment(raw.get("starts_at")),
                    "ends_at": parse_moment(raw["ends_at"], "ends_at") if raw.get("ends_at") else None,
                    "location": _text(raw.get("location")),
                    "participants": _text(raw.get("participants")),
                    "notes": _text(raw.get("notes")),
                    "source": provider.source_name,
                    "external_id": external_id,
                }
            except AgendaError:
                skipped += 1
                continue
            existing = self.fetch_one(
                _COLUMNS, "events", "source = ? AND external_id = ?",
                (provider.source_name, external_id),
            )
            if existing is None:
                values["event_id"] = uuid.uuid4().hex
                self._insert(values)
                imported += 1
            else:
                self._update(existing["event_id"], values)
                updated += 1
        return {"imported": imported, "updated": updated, "skipped": skipped}

    # -- reads ------------------------------------------------------------

    def get(self, event_id: str) -> Event | None:
        row = self.fetch_one(_COLUMNS, "events", "event_id = ?", (event_id,))
        return Event(**row) if row else None

    def between(self, since: date, until: date) -> list[Event]:
        rows = self.fetch_all(
            _COLUMNS, "events", "starts_at >= ? AND starts_at < ?",
            (since.isoformat(), (until + timedelta(days=1)).isoformat()),
            "ORDER BY starts_at",
        )
        return [Event(**row) for row in rows]

    def day(self, when: date | None = None) -> list[Event]:
        reference = when or date.today()
        return self.between(reference, reference)

    def upcoming(self, days: int = 7, today: date | None = None) -> list[Event]:
        reference = today or date.today()
        return self.between(reference, reference + timedelta(days=max(0, days)))

    def conflicts(self, when: date | None = None) -> list[dict[str, Any]]:
        """Overlapping appointments — the thing an assistant catches for you."""
        events = self.day(when)
        clashes: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            for other in events[index + 1:]:
                if event.overlaps(other):
                    clashes.append(
                        {
                            "first": {"event_id": event.event_id, "title": event.title,
                                      "starts_at": event.starts_at},
                            "second": {"event_id": other.event_id, "title": other.title,
                                       "starts_at": other.starts_at},
                        }
                    )
        return clashes

    def digest(self, when: date | None = None) -> dict[str, Any]:
        """The agenda block used by the morning briefing."""
        reference = when or date.today()
        today_events = self.day(reference)
        tomorrow = self.day(reference + timedelta(days=1))
        return {
            "date": reference.isoformat(),
            "events": [
                {**asdict(event), "label": event.label(),
                 "ends_at_effective": event.end.strftime("%Y-%m-%dT%H:%M")}
                for event in today_events
            ],
            "event_count": len(today_events),
            "first_event": today_events[0].label() if today_events else "",
            "conflicts": self.conflicts(reference),
            "tomorrow_count": len(tomorrow),
            "tomorrow_first": tomorrow[0].label() if tomorrow else "",
        }

    # -- meeting preparation ---------------------------------------------

    def prepare(self, event_id: str) -> dict[str, Any]:
        """Everything an assistant would put in front of you before you walk in."""
        event = self.get(event_id)
        if event is None:
            raise AgendaError("event_not_found")

        preparation: dict[str, Any] = {
            "event": {**asdict(event), "label": event.label()},
            "context_available": False,
            "talking_points": [],
        }
        if self.crm is None:
            return preparation

        # ``lookup`` searches by name, so a linked id is resolved to its name
        # first; the event title is only a fallback when nothing is linked.
        anchors: list[str] = []
        if event.project_id:
            project = self.crm.get_project(event.project_id)
            if project is not None:
                anchors.append(project.name)
        if event.contact_id:
            contact = self.crm.get_contact(event.contact_id)
            if contact is not None:
                anchors.append(contact.name)
        if event.title:
            anchors.append(event.title)

        relation: dict[str, Any] = {"found": False}
        for anchor in anchors:
            relation = self.crm.lookup(anchor)
            if relation.get("found"):
                break
        if not relation.get("found"):
            preparation["talking_points"].append(
                "Aucun dossier lié : rattachez ce rendez-vous à un client ou à un projet "
                "pour qu'EMEFA prépare le contexte la prochaine fois."
            )
            return preparation

        preparation["context_available"] = True
        preparation["contact"] = relation.get("contact")
        preparation["project"] = relation.get("project")
        preparation["deals"] = relation.get("deals", [])
        preparation["contracts"] = relation.get("contracts", [])
        preparation["history"] = relation.get("history", [])[:5]

        points: list[str] = []
        contact = relation.get("contact")
        if contact and contact.get("last_interaction_at"):
            points.append(f"Dernier échange le {contact['last_interaction_at']}.")
        project = relation.get("project")
        if project:
            if project.get("blocker"):
                points.append(f"Blocage à traiter : {project['blocker']}.")
            if project.get("next_step"):
                points.append(f"Prochaine étape convenue : {project['next_step']}.")
            if project.get("due_date"):
                points.append(f"Échéance du projet : {project['due_date']}.")
        for deal in relation.get("deals", []):
            if deal.get("stage") in ("envoyé", "relancé"):
                points.append(
                    f"Devis « {deal['title']} » toujours sans réponse "
                    f"({deal.get('amount', 0):,.0f} {deal.get('currency', '')}).".replace(",", " ")
                )
        for contract in relation.get("contracts", []):
            if contract.get("end_date"):
                points.append(f"Contrat « {contract['title']} » court jusqu'au {contract['end_date']}.")
        if self.tasks is not None and contact:
            needle = contact["name"].lower()
            related = [
                task.title for task in self.tasks.list_open()
                if needle in task.title.lower() or needle in task.details.lower()
            ]
            if related:
                preparation["open_tasks"] = related
                points.append(f"Tâches ouvertes liées : {', '.join(related[:3])}.")
        preparation["talking_points"] = points
        return preparation

    # -- SQL --------------------------------------------------------------

    def _insert(self, values: dict[str, Any]) -> None:
        self.insert("events", values)

    def _update(self, event_id: str, values: dict[str, Any]) -> None:
        self.update_scoped("events", "event_id", event_id, values)
