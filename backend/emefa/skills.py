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
from emefa.domain.command_center import InitiativeRepository, RoutineRepository
from emefa.domain.documents import DocumentNotFoundError, DocumentStore
from emefa.domain.email import EmailProvider
from emefa.domain.memories import CATEGORIES, MemoryRepository
from emefa.domain.policy import ActionRisk
from emefa.domain.profiles import ASSISTANT_FIELDS, BUSINESS_FIELDS, ProfileRepository
from emefa.domain.prospects import STAGES, ProspectRepository
from emefa.domain.tasks import TaskRepository
from emefa.domain.uploaded_files import UploadedFileNotFoundError, UploadedFileStore
from emefa.domain.vision import VisionAnalyzer
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
    initiatives: InitiativeRepository | None = None,
    routines: RoutineRepository | None = None,
    uploaded_files: UploadedFileStore | None = None,
    vision_analyzer: VisionAnalyzer | None = None,
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
        _add_uploaded_file_skills(shelf, uploaded_files, vision_analyzer)
    if prospects is not None:
        _add_prospect_skills(shelf, prospects)
    if initiatives is not None:
        _add_initiative_skills(shelf, initiatives)
    if routines is not None:
        _add_routine_skills(shelf, routines)
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


def _add_uploaded_file_skills(
    shelf: ToolShelf,
    uploaded_files: UploadedFileStore,
    vision_analyzer: VisionAnalyzer | None = None,
) -> None:
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
    if vision_analyzer is not None:
        async def analyze_image(arguments: Mapping[str, Any]) -> dict[str, Any]:
            file_id = str(arguments.get("file_id", "")).strip()
            question = str(arguments.get("question", "")).strip()[:2_000]
            if not question:
                question = "Décris précisément cette image en français."
            try:
                record = uploaded_files.describe(file_id)
                if not record.content_type.startswith("image/"):
                    return {"error": "file_is_not_an_image"}
                analysis = await vision_analyzer.analyze(
                    uploaded_files.get_path(file_id), record.content_type, question
                )
            except UploadedFileNotFoundError:
                return {"error": "file_not_found"}
            audit("skill_image_analyzed", file_id=file_id)
            return {
                "file_id": file_id,
                "filename": record.filename,
                "analysis": analysis,
            }

        shelf.add(AgentTool(
            name="image_analyze",
            description=(
                "Analyse visuellement une image envoyée à EMEFA. Utilise file_list pour "
                "retrouver son file_id, puis cet outil pour décrire la scène, lire le texte "
                "visible, examiner un document photographié ou répondre à une question sur "
                "l'image. L'image est transmise au fournisseur visuel configuré."
            ),
            risk=ActionRisk.PERSONAL_READ,
            parameters={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Identifiant UUID de l'image envoyée",
                    },
                    "question": {
                        "type": "string",
                        "description": "Question précise à propos de l'image",
                    },
                },
                "required": ["file_id"],
                "additionalProperties": False,
            },
            handler=analyze_image,
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


def _add_initiative_skills(shelf: ToolShelf, initiatives: InitiativeRepository) -> None:
    def create(arguments: Mapping[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title", "")).strip()
        if not title:
            return {"error": "title_required"}
        try:
            autonomy = max(0, min(int(arguments.get("autonomy_level", 0)), 3))
        except (TypeError, ValueError):
            autonomy = 0
        item = initiatives.add(
            title,
            objective=str(arguments.get("objective", "")),
            status=str(arguments.get("status", "proposed")),
            priority=str(arguments.get("priority", "normal")),
            risk=str(arguments.get("risk", "low")),
            autonomy_level=autonomy,
            next_action=str(arguments.get("next_action", "")),
            due_date=str(arguments["due_date"]) if arguments.get("due_date") else None,
        )
        audit("skill_initiative_created", initiative_id=item.initiative_id)
        return {"initiative": asdict(item)}

    def list_items(arguments: Mapping[str, Any]) -> dict[str, Any]:
        include_closed = bool(arguments.get("include_closed", False))
        items = initiatives.list(include_closed=include_closed)
        return {"count": len(items), "initiatives": [asdict(item) for item in items]}

    def update(arguments: Mapping[str, Any]) -> dict[str, Any]:
        initiative_id = str(arguments.get("initiative_id", "")).strip()
        allowed = {
            "title", "objective", "status", "priority", "risk",
            "autonomy_level", "next_action", "due_date",
        }
        item = initiatives.update(
            initiative_id,
            {key: value for key, value in arguments.items() if key in allowed},
        )
        if item is None:
            return {"error": "initiative_not_found"}
        audit("skill_initiative_updated", initiative_id=initiative_id)
        return {"initiative": asdict(item)}

    common = {
        "title": {"type": "string"},
        "objective": {"type": "string"},
        "status": {"type": "string", "enum": ["proposed", "active", "paused", "completed", "cancelled"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "autonomy_level": {"type": "integer", "minimum": 0, "maximum": 3},
        "next_action": {"type": "string"},
        "due_date": {"type": "string", "description": "Date AAAA-MM-JJ"},
    }
    shelf.add(AgentTool(
        name="create_initiative",
        description="Crée une initiative ou un projet suivi avec objectif, priorité, risque et prochaine action.",
        risk=ActionRisk.LOCAL_WRITE,
        parameters={"type": "object", "properties": common, "required": ["title"], "additionalProperties": False},
        handler=create,
    ))
    shelf.add(AgentTool(
        name="list_initiatives",
        description="Liste les initiatives suivies, leur priorité, état, risque et prochaine action.",
        risk=ActionRisk.PERSONAL_READ,
        parameters={"type": "object", "properties": {"include_closed": {"type": "boolean"}}, "additionalProperties": False},
        handler=list_items,
    ))
    shelf.add(AgentTool(
        name="update_initiative",
        description="Met à jour l'état, la priorité, le risque ou la prochaine action d'une initiative existante.",
        risk=ActionRisk.LOCAL_WRITE,
        parameters={"type": "object", "properties": {"initiative_id": {"type": "string"}, **common}, "required": ["initiative_id"], "additionalProperties": False},
        handler=update,
    ))


def _add_routine_skills(shelf: ToolShelf, routines: RoutineRepository) -> None:
    def create(arguments: Mapping[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("name", "")).strip()
        prompt = str(arguments.get("prompt", "")).strip()
        kind = str(arguments.get("schedule_kind", "manual"))
        if not name or not prompt:
            return {"error": "name_and_prompt_required"}
        hour = arguments.get("schedule_hour")
        weekday = arguments.get("schedule_weekday")
        if kind in {"daily", "weekly"} and hour is None:
            return {"error": "schedule_hour_required"}
        if kind == "weekly" and weekday is None:
            return {"error": "schedule_weekday_required"}
        item = routines.add(
            name,
            prompt,
            schedule_kind=kind,
            schedule_hour=int(hour) if hour is not None else None,
            schedule_weekday=int(weekday) if weekday is not None else None,
            enabled=bool(arguments.get("enabled", True)),
        )
        audit("skill_routine_created", routine_id=item.routine_id)
        return {
            "routine": asdict(item),
            "governance": "Les actions sensibles resteront soumises à approbation.",
        }

    def list_items(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        items = routines.list()
        return {"count": len(items), "routines": [asdict(item) for item in items]}

    properties = {
        "name": {"type": "string"},
        "prompt": {"type": "string", "description": "Instruction à exécuter"},
        "schedule_kind": {"type": "string", "enum": ["manual", "daily", "weekly"]},
        "schedule_hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "schedule_weekday": {"type": "integer", "minimum": 0, "maximum": 6},
        "enabled": {"type": "boolean"},
    }
    shelf.add(AgentTool(
        name="create_routine",
        description=(
            "Crée une routine manuelle, quotidienne ou hebdomadaire. Les actions externes "
            "ou sensibles préparées par une routine attendront toujours l'approbation de l'utilisateur."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={"type": "object", "properties": properties, "required": ["name", "prompt"], "additionalProperties": False},
        handler=create,
    ))
    shelf.add(AgentTool(
        name="list_routines",
        description="Liste les routines configurées, leurs horaires, état et dernière exécution.",
        risk=ActionRisk.PERSONAL_READ,
        handler=list_items,
    ))
