"""First governed skills: read and update the user profiles.

Every skill goes through the ToolShelf so the risk policy in
emefa.domain.policy applies before any handler runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

from emefa.domain.agent import AgentTool, ToolShelf
from emefa.domain.policy import ActionRisk
from emefa.domain.profiles import ASSISTANT_FIELDS, BUSINESS_FIELDS, ProfileRepository
from emefa.domain.tasks import TaskRepository
from emefa.observability import audit

_BUSINESS_FIELD_DESCRIPTIONS = {
    "owner_name": "Nom de l'utilisateur",
    "owner_role": "Rôle ou fonction de l'utilisateur",
    "company_name": "Nom de l'entreprise",
    "industry": "Secteur d'activité",
    "offer": "Produits ou services proposés",
    "target_customers": "Clients cibles",
    "goals": "Objectifs professionnels",
    "constraints_notes": "Contraintes et notes diverses",
}


def build_tool_shelf(profiles: ProfileRepository, tasks: TaskRepository | None = None) -> ToolShelf:
    shelf = ToolShelf()

    def get_profiles(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "assistant": asdict(profiles.get_assistant()),
            "business": asdict(profiles.get_business()),
        }

    def update_business(arguments: Mapping[str, Any]) -> dict[str, Any]:
        changes = {
            field: str(arguments[field])[:2_000]
            for field in BUSINESS_FIELDS
            if field in arguments and isinstance(arguments[field], (str, int, float))
        }
        updated = profiles.update_business(changes)
        audit("skill_business_profile_updated", fields=sorted(changes))
        return {"updated_fields": sorted(changes), "business": asdict(updated)}

    shelf.add(
        AgentTool(
            name="get_profiles",
            description=(
                "Consulte le profil de l'assistante et le profil professionnel "
                "enregistrés de l'utilisateur."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=get_profiles,
        )
    )
    def update_assistant(arguments: Mapping[str, Any]) -> dict[str, Any]:
        changes = {
            field: str(arguments[field]).strip()[:200]
            for field in ASSISTANT_FIELDS
            if field in arguments
            and isinstance(arguments[field], (str, int, float))
            and str(arguments[field]).strip()
        }
        if not changes:
            return {"error": "no_valid_fields", "allowed_fields": list(ASSISTANT_FIELDS)}
        updated = profiles.update_assistant(changes)
        audit("skill_assistant_profile_updated", fields=sorted(changes))
        return {"updated_fields": sorted(changes), "assistant": asdict(updated)}

    shelf.add(
        AgentTool(
            name="update_assistant_profile",
            description=(
                "Ajuste l'identité de l'assistante quand l'utilisateur demande un "
                "changement durable de nom, de langue principale ou de style "
                "d'interaction (ex. tutoiement, ton plus concis). Ne pas utiliser "
                "pour une demande ponctuelle valable un seul message."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom de l'assistante"},
                    "primary_language": {
                        "type": "string",
                        "description": "Langue principale (ex. français)",
                    },
                    "interaction_style": {
                        "type": "string",
                        "description": "Style d'interaction durable souhaité",
                    },
                },
                "additionalProperties": False,
            },
            handler=update_assistant,
        )
    )

    def reset_business(arguments: Mapping[str, Any]) -> dict[str, Any]:
        requested = arguments.get("fields")
        if isinstance(requested, list):
            targets = [field for field in requested if field in BUSINESS_FIELDS]
            if not targets:
                targets = list(BUSINESS_FIELDS)
        else:
            targets = list(BUSINESS_FIELDS)
        profiles.update_business({field: "" for field in targets})
        audit("skill_business_profile_reset", fields=sorted(targets))
        return {"cleared_fields": sorted(targets)}

    shelf.add(
        AgentTool(
            name="reset_business_profile",
            description=(
                "Efface définitivement tout ou partie du profil professionnel "
                "enregistré. Action irréversible : à n'utiliser que si l'utilisateur "
                "le demande explicitement. Sans le paramètre fields, tout est effacé."
            ),
            risk=ActionRisk.DESTRUCTIVE,
            parameters={
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(BUSINESS_FIELDS)},
                        "description": "Champs à effacer ; omettre pour tout effacer.",
                    }
                },
                "additionalProperties": False,
            },
            handler=reset_business,
        )
    )
    shelf.add(
        AgentTool(
            name="update_business_profile",
            description=(
                "Enregistre ou met à jour le profil professionnel de l'utilisateur "
                "quand il présente son activité ou demande de retenir une information "
                "professionnelle durable. Fournis uniquement les champs à modifier."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    field: {"type": "string", "description": description}
                    for field, description in _BUSINESS_FIELD_DESCRIPTIONS.items()
                },
                "additionalProperties": False,
            },
            handler=update_business,
        )
    )
    if tasks is not None:
        _add_task_skills(shelf, tasks, profiles)
    return shelf


def _add_task_skills(
    shelf: ToolShelf, tasks: TaskRepository, profiles: ProfileRepository
) -> None:
    def create_task(arguments: Mapping[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title", "")).strip()[:200]
        if not title:
            return {"error": "title_required"}
        details = str(arguments.get("details", "")).strip()[:2_000]
        due_date = arguments.get("due_date")
        try:
            task = tasks.create(
                title, details, str(due_date) if due_date else None
            )
        except ValueError:
            return {"error": "invalid_due_date", "expected_format": "AAAA-MM-JJ"}
        audit("skill_task_created", task_id=task.task_id)
        return {"task": asdict(task)}

    def list_tasks(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        open_tasks = tasks.list_open()
        return {
            "count": len(open_tasks),
            "tasks": [{**asdict(task), "bucket": task.bucket()} for task in open_tasks],
        }

    def complete_task(arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(arguments.get("task_id", "")).strip()
        task = tasks.complete(task_id) if task_id else None
        if task is None:
            return {"error": "task_not_found_or_not_open"}
        audit("skill_task_completed", task_id=task.task_id)
        return {"task": asdict(task)}

    def daily_brief(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        buckets: dict[str, list[dict[str, Any]]] = {
            "en_retard": [],
            "aujourdhui": [],
            "a_venir": [],
            "sans_echeance": [],
        }
        for task in tasks.list_open():
            buckets[task.bucket()].append(
                {"task_id": task.task_id, "title": task.title, "due_date": task.due_date}
            )
        business = profiles.get_business()
        return {
            "date": date.today().isoformat(),
            "open_task_count": sum(len(items) for items in buckets.values()),
            "tasks": buckets,
            "goals": business.goals,
            "company_name": business.company_name,
        }

    shelf.add(
        AgentTool(
            name="get_daily_brief",
            description=(
                "Compose le brief du jour : tâches ouvertes classées (en retard, "
                "aujourd'hui, à venir, sans échéance) et objectifs professionnels. "
                "À utiliser quand l'utilisateur demande ce qui mérite son attention."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=daily_brief,
        )
    )

    shelf.add(
        AgentTool(
            name="create_task",
            description=(
                "Crée une tâche ou un engagement à suivre pour l'utilisateur. "
                "due_date est optionnelle, au format AAAA-MM-JJ."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Intitulé court de la tâche"},
                    "details": {"type": "string", "description": "Détails éventuels"},
                    "due_date": {"type": "string", "description": "Échéance AAAA-MM-JJ"},
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            handler=create_task,
        )
    )
    shelf.add(
        AgentTool(
            name="list_tasks",
            description=(
                "Liste les tâches ouvertes de l'utilisateur avec leur échéance et leur "
                "catégorie (en_retard, aujourdhui, a_venir, sans_echeance)."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=list_tasks,
        )
    )
    shelf.add(
        AgentTool(
            name="complete_task",
            description="Marque une tâche comme terminée à partir de son task_id.",
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Identifiant de la tâche"}
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
            handler=complete_task,
        )
    )
