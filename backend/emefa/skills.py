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
from emefa.domain.documents import DocumentNotFoundError, DocumentStore
from emefa.domain.email import EmailProvider
from emefa.domain.memories import CATEGORIES, MemoryRepository
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
    "website_url": "Adresse du site web officiel",
    "website_summary": "Informations publiques extraites du site web officiel",
}


def build_tool_shelf(
    profiles: ProfileRepository,
    tasks: TaskRepository | None = None,
    memories: MemoryRepository | None = None,
    email_provider: EmailProvider | None = None,
    documents: DocumentStore | None = None,
) -> ToolShelf:
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
    if memories is not None:
        _add_memory_skills(shelf, memories)
    if email_provider is not None:
        _add_email_skills(shelf, email_provider)
    if documents is not None:
        _add_document_skills(shelf, documents)
    return shelf


def _add_document_skills(shelf: ToolShelf, documents: DocumentStore) -> None:
    common_properties = {
        "title": {"type": "string", "description": "Titre professionnel du document"},
        "content": {
            "type": "string",
            "description": "Contenu complet du document, avec une ligne par paragraphe",
        },
    }

    def create(arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = documents.create(arguments.get("title", ""), arguments.get("content", ""))
        audit("skill_document_created", document_id=result["document_id"])
        return result

    def edit(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = documents.edit(
                str(arguments.get("document_id", "")),
                arguments.get("title"),
                arguments.get("content", ""),
            )
        except DocumentNotFoundError:
            return {"error": "document_not_found"}
        audit("skill_document_edited", document_id=result["document_id"])
        return result

    shelf.add(AgentTool(
        name="document_create",
        description=(
            "Crée réellement un nouveau document Word DOCX persistant et renvoie son lien de "
            "téléchargement. Utilise cet outil dès que l'utilisateur demande de rédiger, créer "
            "ou produire un document Word, un rapport, une lettre ou un compte rendu."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": common_properties,
            "required": ["title", "content"],
            "additionalProperties": False,
        },
        handler=create,
    ))
    shelf.add(AgentTool(
        name="document_edit",
        description=(
            "Remplace le titre et le contenu d'un document Word EMEFA existant. Cette action "
            "modifie un artefact et exige donc l'approbation explicite de l'utilisateur."
        ),
        risk=ActionRisk.DESTRUCTIVE,
        parameters={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Identifiant UUID du document"},
                **common_properties,
            },
            "required": ["document_id", "content"],
            "additionalProperties": False,
        },
        handler=edit,
    ))


def _add_email_skills(shelf: ToolShelf, provider: EmailProvider) -> None:
    def search(arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()[:300]
        limit = max(1, min(int(arguments.get("limit", 10)), 20))
        messages = [dict(item) for item in provider.search(query, limit)]
        return {"count": len(messages), "messages": messages}

    def read(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return dict(provider.read(str(arguments.get("message_id", "")).strip()))

    def draft(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return dict(provider.create_draft(
            str(arguments.get("to", "")),
            str(arguments.get("subject", "")),
            str(arguments.get("body", "")),
        ))

    def send(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return dict(provider.send(
            str(arguments.get("to", "")),
            str(arguments.get("subject", "")),
            str(arguments.get("body", "")),
        ))

    message_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Adresse e-mail exacte du destinataire"},
            "subject": {"type": "string", "description": "Objet exact"},
            "body": {"type": "string", "description": "Corps exact du message"},
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False,
    }
    shelf.add(AgentTool(
        name="email_search",
        description="Recherche des e-mails dans la boîte connectée sans les modifier.",
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Mots à rechercher dans l'objet ou le corps"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        handler=search,
    ))
    shelf.add(AgentTool(
        name="email_read",
        description="Lit un e-mail précis sans le marquer comme lu.",
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"message_id": {"type": "string"}},
            "required": ["message_id"],
            "additionalProperties": False,
        },
        handler=read,
    ))
    shelf.add(AgentTool(
        name="email_create_draft",
        description="Crée un brouillon d'e-mail sans l'envoyer.",
        risk=ActionRisk.LOCAL_WRITE,
        parameters=message_schema,
        handler=draft,
    ))
    shelf.add(AgentTool(
        name="email_send",
        description="Envoie un e-mail. Toujours demander une confirmation explicite avant l'envoi.",
        risk=ActionRisk.COMMUNICATE,
        parameters=message_schema,
        handler=send,
    ))


def _add_memory_skills(shelf: ToolShelf, memories: MemoryRepository) -> None:
    def remember(arguments: Mapping[str, Any]) -> dict[str, Any]:
        content = str(arguments.get("content", "")).strip()
        if len(content) < 3:
            return {"error": "content_too_short"}
        memory = memories.remember(
            content, category=str(arguments.get("category", "fact"))
        )
        audit("skill_memory_saved", memory_id=memory.memory_id, category=memory.category)
        return {"memory": asdict(memory)}

    def list_memories(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        entries = memories.list_all()
        return {"count": len(entries), "memories": [asdict(entry) for entry in entries]}

    def forget_memory(arguments: Mapping[str, Any]) -> dict[str, Any]:
        memory_id = str(arguments.get("memory_id", "")).strip()
        if not memory_id or not memories.forget(memory_id):
            return {"error": "memory_not_found"}
        audit("skill_memory_forgotten", memory_id=memory_id)
        return {"forgotten": memory_id}

    shelf.add(
        AgentTool(
            name="remember",
            description=(
                "Mémorise durablement un fait, une préférence, une relation ou une "
                "procédure que l'utilisateur souhaite voir retenue. Une phrase "
                "courte et autonome par souvenir. Ne pas mémoriser d'informations "
                "sensibles non sollicitées."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Le souvenir, en une phrase autonome",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(CATEGORIES),
                        "description": "Catégorie du souvenir",
                    },
                },
                "required": ["content"],
                "additionalProperties": False,
            },
            handler=remember,
        )
    )
    shelf.add(
        AgentTool(
            name="list_memories",
            description="Liste les souvenirs durables enregistrés, avec leur identifiant.",
            risk=ActionRisk.PERSONAL_READ,
            handler=list_memories,
        )
    )
    shelf.add(
        AgentTool(
            name="forget_memory",
            description=(
                "Efface définitivement un souvenir à partir de son memory_id "
                "(obtenu via list_memories). Irréversible."
            ),
            risk=ActionRisk.DESTRUCTIVE,
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Identifiant du souvenir"}
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            },
            handler=forget_memory,
        )
    )


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
