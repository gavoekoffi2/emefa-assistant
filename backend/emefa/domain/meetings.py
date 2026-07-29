"""Meeting capture: notes in, follow-through out.

A meeting is only useful once it has changed something. Capturing one
therefore performs six verified side effects in a single call (mission §6):

  1. a professional Word compte rendu,
  2. the decisions taken,
  3. the actions, each with an owner and a deadline,
  4. a real task for every action the executive owns,
  5. the linked project's next step / blocker refreshed,
  6. a chronology entry on the client relationship.

Every effect is reported back with its identifier so the caller can state what
actually happened rather than claiming a completion it did not verify (§25).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore
from emefa.domain.crm import AmbiguousMatchError, CrmError, CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.tasks import TaskRepository

#: Owner labels that mean "the executive themselves", so a task is created.
_SELF_OWNERS = {"", "moi", "me", "utilisateur", "dirigeant", "moi-même", "moi meme"}


@dataclass(frozen=True, slots=True)
class MeetingAction:
    meeting_action_id: str
    description: str
    owner: str
    due_date: str | None
    task_id: str | None


@dataclass(frozen=True, slots=True)
class Meeting:
    meeting_id: str
    title: str
    occurred_at: str
    participants: str
    project_id: str | None
    contact_id: str | None
    summary: str
    notes: str
    document_id: str | None
    created_at: str


def _text(value: object, limit: int = 2_000) -> str:
    return str(value or "").strip()[:limit]


def _iso_date(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


class MeetingRepository(ScopedStore):
    """Minutes belong to the company: a colleague may read what was decided."""

    ownership = Ownership.TENANT

    def __init__(
        self,
        database_path: Path,
        crm: CrmRepository,
        tasks: TaskRepository,
        documents: DocumentStore,
        scope: Scope | None = None,
    ) -> None:
        super().__init__(database_path, scope)
        self.crm = crm
        self.tasks = tasks
        self.documents = documents

    def for_scope(self, scope: Scope) -> "MeetingRepository":
        return MeetingRepository(
            self.database_path,
            self.crm.for_scope(scope),
            self.tasks.for_scope(scope),
            self.documents.for_scope(scope),
            scope,
        )

    # -- capture ----------------------------------------------------------

    def capture(
        self,
        title: str,
        notes: str = "",
        occurred_at: str | None = None,
        participants: list[str] | None = None,
        summary: str = "",
        decisions: list[str] | None = None,
        actions: list[dict[str, Any]] | None = None,
        project: str | None = None,
        contact: str | None = None,
        create_document: bool = True,
    ) -> dict[str, Any]:
        clean_title = _text(title, 200)
        if not clean_title:
            raise ValueError("title_required")
        when = _iso_date(occurred_at) or date.today().isoformat()
        people = ", ".join(_text(person, 120) for person in (participants or []) if _text(person))
        clean_decisions = [_text(item) for item in (decisions or []) if _text(item)]
        meeting_id = uuid.uuid4().hex

        project_id: str | None = None
        contact_id: str | None = None
        unresolved: list[str] = []
        ambiguous: list[dict[str, Any]] = []
        if project:
            try:
                project_id = self.crm.resolve_project(project)
            except AmbiguousMatchError as error:
                ambiguous.append({"reference": project, "candidates": error.candidates})
            except CrmError:
                unresolved.append(f"projet:{project}")
        if contact:
            try:
                contact_id = self.crm.resolve_contact(contact)
            except AmbiguousMatchError as error:
                ambiguous.append({"reference": contact, "candidates": error.candidates})
            except CrmError:
                unresolved.append(f"contact:{contact}")
        if contact_id is None and project_id is not None:
            linked = self.crm.get_project(project_id)
            contact_id = linked.contact_id if linked else None

        self.insert("meetings", {
            "meeting_id": meeting_id, "title": clean_title, "occurred_at": when,
            "participants": people, "project_id": project_id, "contact_id": contact_id,
            "summary": _text(summary, 8_000), "notes": _text(notes, 40_000),
        })
        for position, text in enumerate(clean_decisions):
            self.insert("meeting_decisions", {
                "decision_id": uuid.uuid4().hex, "meeting_id": meeting_id,
                "text": text, "position": position,
            })

        recorded_actions = self._record_actions(meeting_id, clean_title, actions or [])

        document: dict[str, Any] | None = None
        if create_document:
            document = self.documents.create(
                f"Compte rendu — {clean_title}",
                self._minutes_content(
                    clean_title, when, people, summary, clean_decisions, recorded_actions
                ),
            )
            self.update_scoped(
                "meetings", "meeting_id", meeting_id,
                {"document_id": document["document_id"]}, touch_updated_at=False,
            )

        project_update = self._refresh_project(project_id, recorded_actions)
        interaction_id = None
        if contact_id or project_id:
            interaction = self.crm.log_interaction(
                summary=f"Réunion : {clean_title}",
                kind="réunion",
                contact_id=contact_id,
                project_id=project_id,
                occurred_at=when,
            )
            interaction_id = interaction.interaction_id

        return {
            "meeting_id": meeting_id,
            "title": clean_title,
            "occurred_at": when,
            "participants": people,
            "decisions": clean_decisions,
            "actions": [asdict(action) for action in recorded_actions],
            "tasks_created": [a.task_id for a in recorded_actions if a.task_id],
            "document": document,
            "project_id": project_id,
            "project_updated": project_update,
            "contact_id": contact_id,
            "interaction_id": interaction_id,
            "unresolved_links": unresolved,
            "ambiguous_links": ambiguous,
        }

    def _record_actions(
        self, meeting_id: str, meeting_title: str, actions: list[dict[str, Any]]
    ) -> list[MeetingAction]:
        recorded: list[MeetingAction] = []
        for position, raw in enumerate(actions):
            description = _text(raw.get("description") or raw.get("action"), 500)
            if not description:
                continue
            owner = _text(raw.get("owner"), 120)
            due = _iso_date(raw.get("due_date"))
            task_id: str | None = None
            if owner.lower() in _SELF_OWNERS:
                task = self.tasks.create(
                    description[:200],
                    f"Action décidée en réunion « {meeting_title} ».",
                    due,
                )
                task_id = task.task_id
            action_id = uuid.uuid4().hex
            self.insert("meeting_actions", {
                "meeting_action_id": action_id, "meeting_id": meeting_id,
                "description": description, "owner": owner, "due_date": due,
                "task_id": task_id, "position": position,
            })
            recorded.append(
                MeetingAction(
                    meeting_action_id=action_id,
                    description=description,
                    owner=owner,
                    due_date=due,
                    task_id=task_id,
                )
            )
        return recorded

    def _refresh_project(
        self, project_id: str | None, actions: list[MeetingAction]
    ) -> dict[str, Any] | None:
        if project_id is None or not actions:
            return None
        soonest = sorted(
            actions, key=lambda action: (action.due_date is None, action.due_date or "")
        )[0]
        updated = self.crm.save_project(project_id, next_step=soonest.description[:500])
        return {"project_id": updated.project_id, "next_step": updated.next_step}

    @staticmethod
    def _minutes_content(
        title: str,
        when: str,
        participants: str,
        summary: str,
        decisions: list[str],
        actions: list[MeetingAction],
    ) -> str:
        lines = ["## Informations", f"- Date : {when}"]
        if participants:
            lines.append(f"- Participants : {participants}")
        lines.append(f"- Sujet : {title}")
        if summary:
            lines += ["", "## Résumé", summary]
        if decisions:
            lines += ["", "## Décisions"]
            lines += [f"- {item}" for item in decisions]
        if actions:
            lines += ["", "## Actions", "| Action | Responsable | Échéance |"]
            lines.append("| --- | --- | --- |")
            for action in actions:
                lines.append(
                    f"| {action.description} | {action.owner or 'À attribuer'} "
                    f"| {action.due_date or 'Non datée'} |"
                )
        if not decisions and not actions:
            lines += ["", "## Suites", "Aucune décision ni action enregistrée."]
        return "\n".join(lines)

    # -- reads ------------------------------------------------------------

    def get(self, meeting_id: str) -> dict[str, Any] | None:
        row = self.fetch_one(
            "meeting_id, title, occurred_at, participants, project_id, contact_id, "
            "summary, notes, document_id, created_at",
            "meetings", "meeting_id = ?", (meeting_id,),
        )
        if row is None:
            return None
        decisions = self.fetch_all(
            "text", "meeting_decisions", "meeting_id = ?", (meeting_id,), "ORDER BY position"
        )
        actions = self.fetch_all(
            "meeting_action_id, description, owner, due_date, task_id",
            "meeting_actions", "meeting_id = ?", (meeting_id,), "ORDER BY position",
        )
        return {
            **asdict(Meeting(**row)),
            "decisions": [item["text"] for item in decisions],
            "actions": actions,
        }

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.fetch_all(
            "meeting_id, title, occurred_at, participants, project_id, document_id, summary, "
            "(SELECT COUNT(*) FROM meeting_decisions d WHERE d.meeting_id = meetings.meeting_id) "
            "AS decision_count, "
            "(SELECT COUNT(*) FROM meeting_actions a WHERE a.meeting_id = meetings.meeting_id) "
            "AS action_count",
            "meetings", "", (limit,), "ORDER BY occurred_at DESC, created_at DESC LIMIT ?",
        )

    def open_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Actions assigned to somebody else — the executive's chase list."""
        return self.fetch_all(
            "meeting_action_id, description, owner, due_date, "
            "(SELECT title FROM meetings m WHERE m.meeting_id = meeting_actions.meeting_id) "
            "AS meeting_title",
            "meeting_actions", "task_id IS NULL AND owner != ''", (limit,),
            "ORDER BY due_date IS NULL, due_date LIMIT ?",
        )

    def delete(self, meeting_id: str) -> bool:
        self.delete_scoped("meeting_decisions", "meeting_id", meeting_id)
        self.delete_scoped("meeting_actions", "meeting_id", meeting_id)
        return self.delete_scoped("meetings", "meeting_id", meeting_id)
