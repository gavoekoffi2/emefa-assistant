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
from emefa.domain.entities import EntityKind, EntityStatus, Milestone, RelationKind
from emefa.domain.email import EmailProvider
from emefa.domain.memories import CATEGORIES, MemoryRepository
from emefa.domain.policy import ActionRisk
from emefa.domain.profiles import ASSISTANT_FIELDS, BUSINESS_FIELDS, ProfileRepository
from emefa.domain.prospects import STAGES, ProspectRepository
from emefa.domain.uploaded_files import UploadedFileNotFoundError, UploadedFileStore
from emefa.domain.tasks import TaskRepository
from emefa.domain import visuals
from emefa.observability import audit


def compose_daily_brief(
    profiles: ProfileRepository,
    tasks: TaskRepository,
    prospects: ProspectRepository | None = None,
) -> dict[str, Any]:
    """Deterministic daily brief: open tasks by bucket, goals, due follow-ups."""
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
    brief: dict[str, Any] = {
        "date": date.today().isoformat(),
        "open_task_count": sum(len(items) for items in buckets.values()),
        "tasks": buckets,
        "goals": business.goals,
        "company_name": business.company_name,
    }
    if prospects is not None:
        brief["due_follow_ups"] = [
            {
                "prospect_id": p.prospect_id,
                "name": p.name,
                "company": p.company,
                "stage": p.stage,
                "next_action": p.next_action,
                "next_action_date": p.next_action_date,
            }
            for p in prospects.due_follow_ups()
        ]
    return brief


_BUCKET_TITLES = (
    ("en_retard", "En retard"),
    ("aujourdhui", "Aujourd'hui"),
    ("a_venir", "À venir"),
    ("sans_echeance", "Sans échéance"),
)


def format_brief_text(brief: Mapping[str, Any]) -> str:
    """French plain-text rendering of a brief, for e-mail and display."""
    lines = [f"Brief EMEFA du {brief.get('date', '')}"]
    if brief.get("company_name"):
        lines[0] += f" — {brief['company_name']}"
    task_buckets = brief.get("tasks", {})
    if brief.get("open_task_count"):
        lines.append("")
        lines.append(f"Tâches ouvertes : {brief['open_task_count']}")
        for key, title in _BUCKET_TITLES:
            for task in task_buckets.get(key, []):
                due = f" (échéance {task['due_date']})" if task.get("due_date") else ""
                lines.append(f"- [{title}] {task['title']}{due}")
    else:
        lines.append("")
        lines.append("Aucune tâche ouverte.")
    follow_ups = brief.get("due_follow_ups", [])
    if follow_ups:
        lines.append("")
        lines.append("Relances commerciales dues :")
        for p in follow_ups:
            company = f" ({p['company']})" if p.get("company") else ""
            action = f" — {p['next_action']}" if p.get("next_action") else ""
            lines.append(f"- {p['name']}{company}{action}")
    if brief.get("goals"):
        lines.append("")
        lines.append(f"Objectifs : {brief['goals']}")
    return "\n".join(lines)

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
    prospects: ProspectRepository | None = None,
    uploaded_files: UploadedFileStore | None = None,
    include_mailbox_read: bool = True,
) -> ToolShelf:
    """Assemble the governed tool shelf.

    ``include_mailbox_read=False`` omits the live-mailbox read tools
    (email_search/email_read). The voice channel uses this because its
    bearer secret is shared with the third-party ElevenLabs bridge; those
    tools would otherwise return inbox contents in-band on a channel whose
    credential is not the owner's per-device token (least privilege).
    """
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
        _add_task_skills(shelf, tasks, profiles, prospects)
    if memories is not None:
        _add_memory_skills(shelf, memories)
    if email_provider is not None:
        _add_email_skills(shelf, email_provider, include_mailbox_read)
    if documents is not None:
        _add_document_skills(shelf, documents)
    if uploaded_files is not None:
        _add_uploaded_file_skills(shelf, uploaded_files)
    if prospects is not None:
        _add_prospect_skills(shelf, prospects)
    return shelf


def _add_prospect_skills(shelf: ToolShelf, prospects: ProspectRepository) -> None:
    _prospect_properties = {
        "name": {"type": "string", "description": "Nom du contact"},
        "company": {"type": "string", "description": "Entreprise du prospect"},
        "email": {"type": "string", "description": "Adresse e-mail"},
        "phone": {"type": "string", "description": "Téléphone"},
        "notes": {"type": "string", "description": "Notes de qualification"},
        "next_action": {"type": "string", "description": "Prochaine action prévue"},
        "next_action_date": {
            "type": "string",
            "description": "Date de la prochaine action, AAAA-MM-JJ",
        },
    }

    def add_prospect(arguments: Mapping[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("name", "")).strip()
        if not name:
            return {"error": "name_required"}
        try:
            prospect = prospects.add(name, **{k: v for k, v in arguments.items() if k != "name"})
        except ValueError:
            return {"error": "invalid_next_action_date", "expected_format": "AAAA-MM-JJ"}
        audit("skill_prospect_added", prospect_id=prospect.prospect_id)
        return {"prospect": asdict(prospect)}

    def list_pipeline(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        entries = prospects.list_open()
        return {
            "count": len(entries),
            "prospects": [
                {**asdict(p), "follow_up_due": p.follow_up_due()} for p in entries
            ],
        }

    def update_prospect(arguments: Mapping[str, Any]) -> dict[str, Any]:
        prospect_id = str(arguments.get("prospect_id", "")).strip()
        stage = arguments.get("stage")
        if stage is not None and stage not in STAGES:
            return {"error": "invalid_stage", "allowed_stages": list(STAGES)}
        try:
            updated = prospects.update(
                prospect_id, **{k: v for k, v in arguments.items() if k != "prospect_id"}
            )
        except ValueError:
            return {"error": "invalid_next_action_date", "expected_format": "AAAA-MM-JJ"}
        if updated is None:
            return {"error": "prospect_not_found"}
        audit("skill_prospect_updated", prospect_id=prospect_id)
        return {"prospect": asdict(updated)}

    shelf.add(
        AgentTool(
            name="add_prospect",
            description=(
                "Ajoute un prospect au pipeline commercial quand l'utilisateur "
                "mentionne un client potentiel à suivre."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": _prospect_properties,
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=add_prospect,
        )
    )
    shelf.add(
        AgentTool(
            name="list_pipeline",
            description=(
                "Liste le pipeline commercial : prospects ouverts, leur étape "
                "(nouveau, contacté, qualifié, proposition) et les relances dues."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=list_pipeline,
        )
    )
    shelf.add(
        AgentTool(
            name="update_prospect",
            description=(
                "Met à jour un prospect (étape, notes, prochaine action datée) à "
                "partir de son prospect_id. Étapes: "
                "nouveau, contacté, qualifié, proposition, gagné, perdu."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "prospect_id": {"type": "string", "description": "Identifiant du prospect"},
                    "stage": {"type": "string", "enum": list(STAGES)},
                    **_prospect_properties,
                },
                "required": ["prospect_id"],
                "additionalProperties": False,
            },
            handler=update_prospect,
        )
    )


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


def _add_uploaded_file_skills(shelf: ToolShelf, uploaded_files: UploadedFileStore) -> None:
    def list_files(arguments: Mapping[str, Any]) -> dict[str, Any]:
        limit = max(1, min(int(arguments.get("limit", 20)), 50))
        entries = uploaded_files.list(limit=limit)
        return {"count": len(entries), "files": [asdict(entry) for entry in entries]}

    def read_file(arguments: Mapping[str, Any]) -> dict[str, Any]:
        file_id = str(arguments.get("file_id", "")).strip()
        limit = max(1, min(int(arguments.get("limit", 20_000)), 120_000))
        try:
            return dict(uploaded_files.read_text(file_id, limit=limit))
        except UploadedFileNotFoundError:
            return {"error": "file_not_found"}

    shelf.add(AgentTool(
        name="file_list",
        description=(
            "Liste les fichiers que l'utilisateur a envoyés à EMEFA : PDF, Word, images, "
            "textes ou autres pièces jointes. Utilise cet outil quand l'utilisateur parle "
            "du fichier envoyé, de la pièce jointe, du PDF, de l'image ou du document sans "
            "donner d'identifiant précis."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "additionalProperties": False,
        },
        handler=list_files,
    ))
    shelf.add(AgentTool(
        name="file_read",
        description=(
            "Lit le texte extrait d'un fichier envoyé à EMEFA à partir de son file_id. "
            "Fonctionne pour PDF textuels, DOCX, TXT, CSV, JSON et Markdown. Pour les images "
            "ou fichiers sans texte extrait, renvoie le statut afin de répondre honnêtement."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Identifiant UUID du fichier envoyé"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 120000},
            },
            "required": ["file_id"],
            "additionalProperties": False,
        },
        handler=read_file,
    ))


def _add_email_skills(
    shelf: ToolShelf, provider: EmailProvider, include_mailbox_read: bool = True
) -> None:
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
    if include_mailbox_read:
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

    def recall(arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if len(query) < 3:
            return {"error": "query_too_short"}
        found = memories.search(query, limit=8)
        return {"count": len(found), "memories": [asdict(entry) for entry in found]}

    def correct_memory(arguments: Mapping[str, Any]) -> dict[str, Any]:
        memory_id = str(arguments.get("memory_id", "")).strip()
        content = str(arguments.get("content", "")).strip()
        if len(content) < 3:
            return {"error": "content_too_short"}
        corrected = memories.correct(memory_id, content)
        if corrected is None:
            return {"error": "memory_not_found"}
        audit("skill_memory_corrected", memory_id=memory_id)
        return {"memory": asdict(corrected)}

    def memory_history(arguments: Mapping[str, Any]) -> dict[str, Any]:
        history = memories.history(str(arguments.get("memory_id", "")).strip())
        if history is None:
            return {"error": "memory_not_found"}
        return history

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
    shelf.add(
        AgentTool(
            name="recall",
            description=(
                "Cherche dans la mémoire durable les souvenirs pertinents pour une "
                "question, classés par importance et fraîcheur. À utiliser avant de "
                "répondre qu'on ne sait pas quelque chose."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Ce qu'on cherche à retrouver",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=recall,
        )
    )
    shelf.add(
        AgentTool(
            name="correct_memory",
            description=(
                "Corrige un souvenir mal enregistré (erreur de transcription, faute "
                "de nom). À utiliser quand l'utilisateur dit qu'un souvenir est faux. "
                "Si l'utilisateur a simplement changé d'avis, utiliser remember : la "
                "mémoire garde alors la trace de l'ancienne version."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Identifiant du souvenir"},
                    "content": {"type": "string", "description": "Le texte corrigé"},
                },
                "required": ["memory_id", "content"],
                "additionalProperties": False,
            },
            handler=correct_memory,
        )
    )
    shelf.add(
        AgentTool(
            name="memory_history",
            description=(
                "Explique pourquoi un souvenir est retenu : combien de fois il a été "
                "confirmé, et ce qu'il a remplacé."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Identifiant du souvenir"}
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            },
            handler=memory_history,
        )
    )


def _add_task_skills(
    shelf: ToolShelf,
    tasks: TaskRepository,
    profiles: ProfileRepository,
    prospects: ProspectRepository | None = None,
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
        return compose_daily_brief(profiles, tasks, prospects)

    shelf.add(
        AgentTool(
            name="get_daily_brief",
            description=(
                "Compose le brief du jour : tâches ouvertes classées (en retard, "
                "aujourd'hui, à venir, sans échéance), relances commerciales dues "
                "et objectifs professionnels. À utiliser quand l'utilisateur "
                "demande ce qui mérite son attention."
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


def add_mission_skills(shelf: ToolShelf, planner, missions, orchestrator) -> None:
    """Let EMEFA plan and run a mission from the conversation.

    Registered after the planner is built, and named in
    `missions.planning.RESERVED_TOOLS`, so they never appear in the catalogue a
    plan is drawn from — a plan whose first step is "make a plan" is a loop.
    """

    async def plan_mission(arguments: Mapping[str, Any]) -> dict[str, Any]:
        goal = str(arguments.get("goal", "")).strip()
        if len(goal) < 5:
            return {"error": "goal_too_short"}
        context = arguments.get("context")
        plan = await planner.plan(goal, context if isinstance(context, dict) else None)
        if not plan.steps:
            return {
                "planned": False,
                "missing_information": list(plan.missing_information),
                "notes": list(plan.notes),
            }
        mission = missions.create(
            plan.goal,
            list(plan.steps),
            strategy=plan.strategy,
            missing_information=plan.missing_information,
        )
        audit("skill_mission_planned", mission_id=mission.mission_id, strategy=plan.strategy)
        return {
            "planned": True,
            "mission_id": mission.mission_id,
            "executable": plan.executable,
            "missing_information": list(plan.missing_information),
            "notes": list(plan.notes),
            "steps": [step.summary() for step in plan.steps],
        }

    async def advance_mission(arguments: Mapping[str, Any]) -> dict[str, Any]:
        mission_id = str(arguments.get("mission_id", "")).strip()
        mission = await orchestrator.run_to_completion(mission_id)
        if mission is None:
            return {"error": "mission_not_found"}
        audit("skill_mission_advanced", mission_id=mission_id, status=mission.status.value)
        return mission.summary()

    def mission_status(arguments: Mapping[str, Any]) -> dict[str, Any]:
        mission = missions.get(str(arguments.get("mission_id", "")).strip())
        return mission.summary() if mission is not None else {"error": "mission_not_found"}

    shelf.add(
        AgentTool(
            name="plan_mission",
            description=(
                "Transforme une demande en plan d'exécution vérifiable (« prépare "
                "une réunion avec X », « organise mon voyage à Y », « prépare une "
                "proposition et relance vendredi »). Le plan est enregistré mais "
                "PAS exécuté. Si le plan revient avec missing_information, pose la "
                "question à l'utilisateur au lieu de deviner."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "La demande, telle que l'utilisateur l'a formulée",
                    },
                    "context": {
                        "type": "object",
                        "description": (
                            "Éléments déjà connus de la conversation, par exemple "
                            "{\"sujet\": \"Clinique du Lac\", \"date\": \"2026-08-04\"}"
                        ),
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["goal"],
                "additionalProperties": False,
            },
            handler=plan_mission,
        )
    )
    shelf.add(
        AgentTool(
            name="advance_mission",
            description=(
                "Exécute un plan déjà enregistré, étape par étape, avec vérification. "
                "Chaque étape reste soumise à la politique de risque : une action "
                "sensible s'arrête et demande l'accord de l'utilisateur."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {"mission_id": {"type": "string"}},
                "required": ["mission_id"],
                "additionalProperties": False,
            },
            handler=advance_mission,
        )
    )
    shelf.add(
        AgentTool(
            name="mission_status",
            description="Donne l'état d'une mission : étapes, vérifications, ce qui reste.",
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {"mission_id": {"type": "string"}},
                "required": ["mission_id"],
                "additionalProperties": False,
            },
            handler=mission_status,
        )
    )


def add_entity_skills(shelf: ToolShelf, graph, timeline) -> None:
    """Projects, companies, people — and the questions the user actually asks.

    Everything here reads or writes the graph; nothing generates. A brief that
    invents a project status is worse than no brief, because the user cannot
    tell which is which.
    """
    entities = graph.entities

    def _resolve(arguments: Mapping[str, Any]):
        identifier = str(arguments.get("entity_id", "")).strip()
        if identifier:
            return entities.get(identifier)
        return entities.resolve(
            str(arguments.get("name", "")).strip(), arguments.get("kind")
        )

    def entity_upsert(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            entity = entities.upsert(
                arguments.get("kind", "project"),
                str(arguments.get("name", "")),
                scope=arguments.get("scope", "business"),
                status=arguments.get("status"),
                summary=arguments.get("summary"),
                attributes=arguments.get("attributes")
                if isinstance(arguments.get("attributes"), dict)
                else None,
            )
        except ValueError:
            return {"error": "name_required"}
        audit("skill_entity_upserted", entity_id=entity.entity_id, kind=entity.kind.value)
        return {"entity": entity.summary_dict()}

    def entity_link(arguments: Mapping[str, Any]) -> dict[str, Any]:
        source = entities.resolve(str(arguments.get("from_name", "")), arguments.get("from_kind"))
        target = entities.resolve(str(arguments.get("to_name", "")), arguments.get("to_kind"))
        if source is None or target is None:
            return {"error": "entity_not_found", "hint": "Créez d'abord les deux entités."}
        relation = entities.link(
            source.entity_id, target.entity_id, arguments.get("relation", "related_to")
        )
        audit("skill_entity_linked", relation=arguments.get("relation"))
        return {
            "linked": relation is not None,
            "already_known": relation is None,
            "from": source.name,
            "to": target.name,
        }

    def entity_note(arguments: Mapping[str, Any]) -> dict[str, Any]:
        entity = _resolve(arguments)
        if entity is None:
            return {"error": "entity_not_found"}
        content = str(arguments.get("content", "")).strip()
        if len(content) < 3:
            return {"error": "content_too_short"}
        fact_id = graph.note(
            entity.entity_id, content, category=str(arguments.get("category", "note"))
        )
        audit("skill_entity_noted", entity_id=entity.entity_id)
        return {"entity": entity.name, "memory_id": fact_id}

    def entity_milestone(arguments: Mapping[str, Any]) -> dict[str, Any]:
        entity = _resolve(arguments)
        if entity is None:
            return {"error": "entity_not_found"}
        headline = str(arguments.get("headline", "")).strip()
        if len(headline) < 3:
            return {"error": "headline_too_short"}
        entry = entities.record_milestone(
            entity.entity_id,
            arguments.get("milestone", "note"),
            headline,
            occurred_at=arguments.get("occurred_at") or None,
        )
        audit("skill_milestone_recorded", entity_id=entity.entity_id)
        return {"entity": entity.name, "entry": entry.summary()}

    def entity_brief(arguments: Mapping[str, Any]) -> dict[str, Any]:
        entity = _resolve(arguments)
        if entity is None:
            return {
                "error": "entity_not_found",
                "known": [item.name for item in entities.list_entities(limit=12)],
            }
        brief = graph.brief(entity.entity_id)
        return {**brief.summary(), "text": brief.as_text()}

    def entity_story(arguments: Mapping[str, Any]) -> dict[str, Any]:
        entity = _resolve(arguments)
        if entity is None:
            return {"error": "entity_not_found"}
        story = timeline.story(entity.entity_id)
        return story.summary()

    def entity_list(arguments: Mapping[str, Any]) -> dict[str, Any]:
        found = entities.list_entities(
            kind=arguments.get("kind"),
            scope=arguments.get("scope"),
            status=arguments.get("status"),
            limit=50,
        )
        return {
            "count": len(found),
            "entities": [item.summary_dict() for item in found],
        }

    _NAME_ARGUMENTS = {
        "name": {"type": "string", "description": "Nom tel que l'utilisateur l'emploie"},
        "kind": {
            "type": "string",
            "enum": [kind.value for kind in EntityKind],
            "description": "Type d'entité",
        },
    }

    shelf.add(
        AgentTool(
            name="entity_upsert",
            description=(
                "Enregistre ou met à jour un projet, une entreprise, une personne, "
                "un devis, une facture, un contrat ou une réunion. Réutilise "
                "l'entité existante si le nom correspond : ne crée jamais de doublon."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    **_NAME_ARGUMENTS,
                    "scope": {
                        "type": "string",
                        "enum": ["business", "personal"],
                        "description": "Mémoire d'entreprise ou mémoire personnelle",
                    },
                    "status": {
                        "type": "string",
                        "enum": [status.value for status in EntityStatus],
                    },
                    "summary": {"type": "string", "description": "Résumé en une phrase"},
                    "attributes": {
                        "type": "object",
                        "description": "Champs libres : montant, échéance, rôle…",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=entity_upsert,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_link",
            description=(
                "Relie deux entités : un client à un projet, un devis à un projet, "
                "une facture à un devis, une personne à une entreprise. C'est ce qui "
                "permet de répondre avec du contexte."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    "from_name": {"type": "string"},
                    "from_kind": {"type": "string", "enum": [k.value for k in EntityKind]},
                    "to_name": {"type": "string"},
                    "to_kind": {"type": "string", "enum": [k.value for k in EntityKind]},
                    "relation": {
                        "type": "string",
                        "enum": [relation.value for relation in RelationKind],
                    },
                },
                "required": ["from_name", "to_name", "relation"],
                "additionalProperties": False,
            },
            handler=entity_link,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_note",
            description=(
                "Attache un fait à une entité : un objectif, une décision prise, un "
                "problème ouvert. Utilise category='decision' pour une décision et "
                "category='issue' pour un problème — c'est ce qui rend « quelles "
                "décisions avons-nous prises ? » et « quels problèmes restent "
                "ouverts ? » répondables."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    **_NAME_ARGUMENTS,
                    "content": {"type": "string", "description": "Le fait, en une phrase"},
                    "category": {
                        "type": "string",
                        "enum": ["decision", "issue", "goal", "note", "constraint", "event"],
                    },
                },
                "required": ["name", "content"],
                "additionalProperties": False,
            },
            handler=entity_note,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_milestone",
            description=(
                "Inscrit un évènement daté dans l'histoire d'une entité : premier "
                "contact, réunion, proposition, négociation, signature, livraison, "
                "facturation, paiement, relance."
            ),
            risk=ActionRisk.LOCAL_WRITE,
            parameters={
                "type": "object",
                "properties": {
                    **_NAME_ARGUMENTS,
                    "milestone": {
                        "type": "string",
                        "enum": [milestone.value for milestone in Milestone],
                    },
                    "headline": {"type": "string", "description": "Ce qui s'est passé, en une phrase"},
                    "occurred_at": {
                        "type": "string",
                        "description": "Date ISO (AAAA-MM-JJ). Par défaut : maintenant.",
                    },
                },
                "required": ["name", "milestone", "headline"],
                "additionalProperties": False,
            },
            handler=entity_milestone,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_brief",
            description=(
                "Répond à « où en est le projet X ? », « quelles décisions pour Y ? », "
                "« quels problèmes restent ouverts sur Z ? ». Donne le statut, les "
                "rattachements, les décisions, les problèmes ouverts et les derniers "
                "évènements."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": _NAME_ARGUMENTS,
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=entity_brief,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_story",
            description=(
                "Raconte toute l'histoire d'un client, d'un projet ou d'une "
                "entreprise, dans l'ordre, avec les étapes jamais franchies et "
                "l'étape suivante attendue."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": _NAME_ARGUMENTS,
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=entity_story,
        )
    )
    shelf.add(
        AgentTool(
            name="entity_list",
            description="Liste les projets, entreprises, personnes ou documents connus.",
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": [k.value for k in EntityKind]},
                    "scope": {"type": "string", "enum": ["business", "personal"]},
                    "status": {"type": "string", "enum": [s.value for s in EntityStatus]},
                },
                "additionalProperties": False,
            },
            handler=entity_list,
        )
    )


def add_visual_skills(shelf: ToolShelf, documents: DocumentStore, uploaded_files) -> None:
    """Let EMEFA show something alongside what she says.

    Every card is built from data this deployment actually holds. There is no
    image search and no map tiles, and the tool descriptions say so, because
    the alternative is an assistant that promises a picture and renders a
    broken frame.
    """

    def show_file(arguments: Mapping[str, Any]) -> dict[str, Any]:
        file_id = str(arguments.get("file_id", "")).strip()
        try:
            item = uploaded_files.describe(file_id)
        except (UploadedFileNotFoundError, ValueError):
            return {"error": "file_not_found"}
        caption = str(arguments.get("caption", ""))
        kind = (item.content_type or "").lower()
        try:
            if kind.startswith("image/"):
                card = visuals.image_card(file_id, item.filename, caption)
            elif kind.startswith("video/"):
                card = visuals.video_card(file_id, item.filename, caption)
            else:
                card = visuals.file_card(file_id, item.filename, item.content_type, caption)
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    def show_document(arguments: Mapping[str, Any]) -> dict[str, Any]:
        document_id = str(arguments.get("document_id", "")).strip()
        try:
            # `describe`, not `get`: the latter returns a filesystem path, and
            # a card needs the title and the download URL.
            document = documents.describe(document_id)
        except (DocumentNotFoundError, ValueError, OSError):
            return {"error": "document_not_found"}
        try:
            card = visuals.document_card(
                document_id,
                document.get("title") or "Document",
                document.get("download_url", ""),
                str(arguments.get("caption", "")),
            )
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    def show_chart(arguments: Mapping[str, Any]) -> dict[str, Any]:
        points = arguments.get("points")
        if not isinstance(points, list):
            return {"error": "points_required"}
        try:
            card = visuals.chart_card(
                str(arguments.get("title", "Graphique")),
                points,
                str(arguments.get("shape", "bar")),
                str(arguments.get("unit", "")),
                str(arguments.get("caption", "")),
            )
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    def show_table(arguments: Mapping[str, Any]) -> dict[str, Any]:
        columns, rows = arguments.get("columns"), arguments.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            return {"error": "columns_and_rows_required"}
        try:
            card = visuals.table_card(
                str(arguments.get("title", "Tableau")),
                columns,
                rows,
                str(arguments.get("caption", "")),
            )
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    def show_metrics(arguments: Mapping[str, Any]) -> dict[str, Any]:
        metrics = arguments.get("metrics")
        if not isinstance(metrics, list):
            return {"error": "metrics_required"}
        try:
            card = visuals.metrics_card(
                str(arguments.get("title", "Résultats")),
                metrics,
                str(arguments.get("caption", "")),
            )
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    def show_location(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            card = visuals.map_card(
                str(arguments.get("title", "Localisation")),
                arguments.get("latitude"),
                arguments.get("longitude"),
                str(arguments.get("label", "")),
                str(arguments.get("caption", "")),
            )
        except visuals.VisualCardError as error:
            return {"error": str(error)}
        return {"shown": visuals.offer(card), "card": card.summary()}

    shelf.add(
        AgentTool(
            name="show_file",
            description=(
                "Affiche un fichier que l'utilisateur a envoyé : image en grand, "
                "vidéo, ou lien de téléchargement selon le type. Utilise file_list "
                "pour retrouver l'identifiant. Tu ne peux PAS aller chercher une "
                "image sur le web : si on te demande une photo que tu n'as pas, "
                "dis-le simplement."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "caption": {"type": "string", "description": "Ce que l'utilisateur regarde"},
                },
                "required": ["file_id"],
                "additionalProperties": False,
            },
            handler=show_file,
        )
    )
    shelf.add(
        AgentTool(
            name="show_document",
            description=(
                "Affiche un document produit par EMEFA (devis, proposition, compte "
                "rendu) avec son lien de téléchargement."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["document_id"],
                "additionalProperties": False,
            },
            handler=show_document,
        )
    )
    shelf.add(
        AgentTool(
            name="show_chart",
            description=(
                "Affiche un graphique à partir de chiffres que tu possèdes réellement "
                "(pipeline, tâches, montants donnés par l'utilisateur). N'invente "
                "jamais de valeurs pour remplir un graphique."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "shape": {"type": "string", "enum": ["bar", "line"]},
                    "unit": {"type": "string", "description": "FCFA, %, jours…"},
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                    "caption": {"type": "string"},
                },
                "required": ["title", "points"],
                "additionalProperties": False,
            },
            handler=show_chart,
        )
    )
    shelf.add(
        AgentTool(
            name="show_table",
            description=(
                "Affiche un tableau lisible plutôt qu'une longue liste dans la "
                "conversation. À utiliser dès qu'il y a plus de quatre lignes à comparer."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "rows": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "caption": {"type": "string"},
                },
                "required": ["title", "columns", "rows"],
                "additionalProperties": False,
            },
            handler=show_table,
        )
    )
    shelf.add(
        AgentTool(
            name="show_metrics",
            description="Affiche quelques chiffres clés côte à côte (résultat d'analyse, bilan).",
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "metrics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                                "hint": {"type": "string"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                    "caption": {"type": "string"},
                },
                "required": ["title", "metrics"],
                "additionalProperties": False,
            },
            handler=show_metrics,
        )
    )
    shelf.add(
        AgentTool(
            name="show_location",
            description=(
                "Situe un lieu par ses coordonnées. Ce n'est pas une carte routière "
                "ni satellite : aucun fournisseur de cartes n'est connecté, et tu "
                "dois le dire à l'utilisateur plutôt que de laisser croire le contraire."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "label": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["title", "latitude", "longitude"],
                "additionalProperties": False,
            },
            handler=show_location,
        )
    )
