"""First governed skills: read and update the user profiles.

Every skill goes through the ToolShelf so the risk policy in
emefa.domain.policy applies before any handler runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from emefa.domain.agenda import EVENT_KINDS, AgendaError, AgendaRepository
from emefa.domain.agent import AgentTool, ToolShelf
from emefa.domain.command_center import InitiativeRepository, RoutineRepository
from emefa.domain.crm import (
    CONTACT_KINDS,
    CONTACT_STATUSES,
    CONTRACT_STATUSES,
    DEAL_STAGES,
    INTERACTION_KINDS,
    PROJECT_HEALTH,
    PROJECT_STATUSES,
    AmbiguousMatchError,
    CrmError,
    CrmRepository,
)
from emefa.domain.documents import DocumentNotFoundError, DocumentStore
from emefa.domain.email import EmailProvider
from emefa.domain.meetings import MeetingRepository
from emefa.domain.memories import CATEGORIES, MemoryRepository
from emefa.domain.onboarding import OnboardingRepository
from emefa.domain.policy import ActionRisk
from emefa.domain.profiles import (
    ASSISTANT_FIELDS,
    BUSINESS_FIELDS,
    FIELD_LABELS,
    ProfileRepository,
)
from emefa.domain.prospects import STAGES, ProspectRepository
from emefa.domain.reports import (
    ReportPreferences,
    ReportPreferencesRepository,
    compose_evening_report,
    compose_morning_brief,
    format_morning_text,
)
from emefa.domain.tasks import TaskRepository
from emefa.domain.uploaded_files import UploadedFileNotFoundError, UploadedFileStore
from emefa.domain.vision import VisionAnalyzer
from emefa.domain.workflows import WorkflowEngine
from emefa.observability import audit


def compose_daily_brief(
    profiles: ProfileRepository,
    tasks: TaskRepository,
    prospects: ProspectRepository | None = None,
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferences | None = None,
    agenda: AgendaRepository | None = None,
) -> dict[str, Any]:
    """Deterministic morning brief. See :mod:`emefa.domain.reports`."""
    return compose_morning_brief(profiles, tasks, prospects, crm, meetings, preferences, agenda=agenda)


#: Rendering lives with the composition logic; re-exported for existing callers.
format_brief_text = format_morning_text


_BUSINESS_FIELD_DESCRIPTIONS = {
    field: FIELD_LABELS.get(field, field) for field in BUSINESS_FIELDS
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
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    workflows: WorkflowEngine | None = None,
    onboarding: OnboardingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
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
        _add_task_skills(shelf, tasks, profiles, prospects, crm, meetings, preferences, agenda)
    if crm is not None:
        _add_crm_skills(shelf, crm)
    if agenda is not None:
        _add_agenda_skills(shelf, agenda)
    if meetings is not None:
        _add_meeting_skills(shelf, meetings)
    if workflows is not None:
        _add_workflow_skills(shelf, workflows)
    if onboarding is not None:
        _add_onboarding_skills(shelf, onboarding)
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

    def read_document(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return documents.read(str(arguments.get("document_id", "")))
        except DocumentNotFoundError:
            return {"error": "document_not_found"}

    shelf.add(AgentTool(
        name="document_read",
        description=(
            "Relit le contenu d'un document Word produit par EMEFA, dans le format "
            "structuré attendu par document_edit. À utiliser avant de réviser un "
            "document existant, pour ne jamais réécrire à l'aveugle."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
        handler=read_document,
    ))

    def create_workbook(arguments: Mapping[str, Any]) -> dict[str, Any]:
        sheets = list(arguments.get("sheets") or [])
        if not sheets:
            return {"error": "sheets_required"}
        result = documents.create_workbook(arguments.get("title", ""), sheets)
        audit("skill_workbook_created", document_id=result["document_id"])
        return result

    shelf.add(AgentTool(
        name="spreadsheet_create",
        description=(
            "Crée un vrai classeur Excel XLSX modifiable et renvoie son lien de "
            "téléchargement : budget, suivi, tableau de bord, facture, plan de "
            "trésorerie. Les formules restent vivantes : écris une cellule "
            "commençant par « = » (ex. « =B2*C2 ») et Excel la recalculera. "
            "total_columns ajoute automatiquement une ligne de totaux SUM sur les "
            "colonnes indiquées (ex. [\"D\"])."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre du classeur"},
                "sheets": {
                    "type": "array",
                    "description": "Feuilles du classeur",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Nom de la feuille"},
                            "columns": {
                                "type": "array", "items": {"type": "string"},
                                "description": "En-têtes de colonnes",
                            },
                            "rows": {
                                "type": "array",
                                "description": "Lignes de données ; « =… » reste une formule vivante",
                                "items": {"type": "array", "items": {}},
                            },
                            "total_columns": {
                                "type": "array", "items": {"type": "string"},
                                "description": "Lettres de colonnes à totaliser, ex. [\"C\", \"D\"]",
                            },
                            "notes": {"type": "string"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "sheets"],
            "additionalProperties": False,
        },
        handler=create_workbook,
    ))

    def create_presentation(arguments: Mapping[str, Any]) -> dict[str, Any]:
        slides = list(arguments.get("slides") or [])
        if not slides:
            return {"error": "slides_required"}
        result = documents.create_presentation(
            arguments.get("title", ""), slides, str(arguments.get("subtitle", ""))
        )
        audit("skill_presentation_created", document_id=result["document_id"])
        return result

    shelf.add(AgentTool(
        name="presentation_create",
        description=(
            "Crée une vraie présentation PowerPoint PPTX modifiable et renvoie son "
            "lien de téléchargement : présentation client, comité, pitch, restitution. "
            "Chaque diapositive a un titre, des puces courtes et des notes pour "
            "l'orateur."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre de la présentation"},
                "subtitle": {"type": "string", "description": "Sous-titre de la diapositive d'ouverture"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                            "notes": {"type": "string", "description": "Notes de l'orateur"},
                        },
                        "required": ["title"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "slides"],
            "additionalProperties": False,
        },
        handler=create_presentation,
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
            description=(
                "Liste les souvenirs durables enregistrés, avec leur identifiant et leur "
                "catégorie. À utiliser quand l'utilisateur demande ce qu'EMEFA a retenu, "
                "ou avant d'en effacer un."
            ),
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
    crm: CrmRepository | None = None,
    meetings: MeetingRepository | None = None,
    preferences: ReportPreferencesRepository | None = None,
    agenda: AgendaRepository | None = None,
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

    def _prefs() -> ReportPreferences | None:
        # Resolved per call: the executive can retune their report sections
        # at any moment without a restart.
        return preferences.get() if preferences is not None else None

    def daily_brief(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        brief = compose_morning_brief(profiles, tasks, prospects, crm, meetings, _prefs(), agenda=agenda)
        return {**brief, "text": format_morning_text(brief)}

    def evening_report(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        return compose_evening_report(profiles, tasks, crm, meetings, _prefs(), agenda=agenda)

    shelf.add(
        AgentTool(
            name="get_daily_brief",
            description=(
                "Compose le briefing exécutif du matin : priorités, tâches classées "
                "(en retard, aujourd'hui, à venir), clients à relancer, devis en "
                "attente de réponse, contrats à échéance, projets à surveiller, "
                "risques, opportunités et recommandations. À utiliser dès que "
                "l'utilisateur demande son brief, son point du jour ou ce qui "
                "mérite son attention."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=daily_brief,
        )
    )
    shelf.add(
        AgentTool(
            name="get_evening_report",
            description=(
                "Compose le rapport du soir : résumé de la journée, tâches "
                "terminées, tâches restantes, blocages, recommandations et "
                "priorités du lendemain. À utiliser en fin de journée ou quand "
                "l'utilisateur demande un bilan."
            ),
            risk=ActionRisk.PERSONAL_READ,
            handler=evening_report,
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
            description=(
                "Marque une tâche comme terminée à partir de son task_id, obtenu via "
                "list_tasks ou le brief du jour. À utiliser dès que l'utilisateur dit "
                "avoir fait quelque chose qu'EMEFA suivait."
            ),
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


def _add_crm_skills(shelf: ToolShelf, crm: CrmRepository) -> None:
    """The relational memory an executive assistant is expected to hold."""

    def guarded(handler: Any) -> Any:
        def wrapped(arguments: Mapping[str, Any]) -> dict[str, Any]:
            try:
                return handler(arguments)
            except AmbiguousMatchError as error:
                # The model must ask which one, not choose for the executive.
                return {
                    "error": str(error),
                    "candidates": error.candidates,
                    "instruction": (
                        "Plusieurs enregistrements correspondent. Demande à "
                        "l'utilisateur lequel il vise avant de continuer, puis "
                        "réutilise l'identifiant exact."
                    ),
                }
            except CrmError as error:
                return {"error": str(error)}
        return wrapped

    def overview(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        return crm.overview()

    def lookup(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return crm.lookup(str(arguments.get("query", "")))

    def save_contact(arguments: Mapping[str, Any]) -> dict[str, Any]:
        fields = {key: value for key, value in arguments.items() if key != "contact_id"}
        contact = crm.save_contact(arguments.get("contact_id") or None, **fields)
        audit("skill_crm_contact_saved", contact_id=contact.contact_id)
        return {"contact": asdict(contact)}

    def save_project(arguments: Mapping[str, Any]) -> dict[str, Any]:
        fields = {key: value for key, value in arguments.items() if key != "project_id"}
        project = crm.save_project(arguments.get("project_id") or None, **fields)
        audit("skill_crm_project_saved", project_id=project.project_id)
        return {"project": asdict(project)}

    def save_deal(arguments: Mapping[str, Any]) -> dict[str, Any]:
        fields = {key: value for key, value in arguments.items() if key != "deal_id"}
        deal = crm.save_deal(arguments.get("deal_id") or None, **fields)
        audit("skill_crm_deal_saved", deal_id=deal.deal_id)
        return {"deal": asdict(deal)}

    def save_contract(arguments: Mapping[str, Any]) -> dict[str, Any]:
        fields = {key: value for key, value in arguments.items() if key != "contract_id"}
        contract = crm.save_contract(arguments.get("contract_id") or None, **fields)
        audit("skill_crm_contract_saved", contract_id=contract.contract_id)
        return {"contract": asdict(contract)}

    def log_interaction(arguments: Mapping[str, Any]) -> dict[str, Any]:
        interaction = crm.log_interaction(
            summary=str(arguments.get("summary", "")),
            kind=str(arguments.get("kind", "note")),
            contact_id=arguments.get("contact") or arguments.get("contact_id"),
            project_id=arguments.get("project") or arguments.get("project_id"),
            occurred_at=arguments.get("occurred_at"),
        )
        audit("skill_crm_interaction_logged", interaction_id=interaction.interaction_id)
        return {"interaction": asdict(interaction)}

    shelf.add(AgentTool(
        name="crm_overview",
        description=(
            "Répond aux questions de pilotage commercial en une fois : quels clients "
            "relancer, quels devis attendent une réponse, quels contrats expirent "
            "bientôt et quels projets sont bloqués. Utilise cet outil pour toute "
            "question du type « qui dois-je relancer ? » ou « où en sommes-nous ? »."
        ),
        risk=ActionRisk.PERSONAL_READ,
        handler=overview,
    ))
    shelf.add(AgentTool(
        name="crm_lookup",
        description=(
            "Retrouve tout ce qu'EMEFA sait sur un client, un projet, un devis ou un "
            "contrat à partir de son nom, avec l'historique des échanges, les devis "
            "liés, les contrats liés et les signaux d'alerte. C'est l'outil à utiliser "
            "pour « où en est le projet X ? » ou « parle-moi du client Y »."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nom du client, projet, devis ou contrat"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=guarded(lookup),
    ))
    shelf.add(AgentTool(
        name="crm_save_contact",
        description=(
            "Crée ou met à jour un client, prospect, fournisseur, partenaire ou "
            "collaborateur. Fournis contact_id pour modifier un contact existant, "
            "sinon un nouveau contact est créé."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": list(CONTACT_KINDS)},
                "company": {"type": "string"},
                "role": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "notes": {"type": "string"},
                "status": {"type": "string", "enum": list(CONTACT_STATUSES)},
                "follow_up_days": {
                    "type": "integer", "minimum": 0, "maximum": 365,
                    "description": "Silence toléré avant relance, en jours",
                },
            },
            "additionalProperties": False,
        },
        handler=guarded(save_contact),
    ))
    shelf.add(AgentTool(
        name="crm_save_project",
        description=(
            "Crée ou met à jour un projet : objectif, état, santé, prochaine étape, "
            "blocage et échéance. Le champ contact_id accepte aussi le nom du client."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "contact_id": {"type": "string", "description": "Identifiant ou nom du client"},
                "objective": {"type": "string"},
                "status": {"type": "string", "enum": list(PROJECT_STATUSES)},
                "health": {"type": "string", "enum": list(PROJECT_HEALTH)},
                "next_step": {"type": "string"},
                "blocker": {"type": "string", "description": "Ce qui bloque, vide si rien"},
                "due_date": {"type": "string", "description": "Échéance AAAA-MM-JJ"},
            },
            "additionalProperties": False,
        },
        handler=guarded(save_project),
    ))
    shelf.add(AgentTool(
        name="crm_save_deal",
        description=(
            "Crée ou met à jour un devis / une proposition commerciale : montant, "
            "étape, date d'envoi et date de réponse attendue. Sert à répondre plus "
            "tard à « quels devis attendent une réponse ? »."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "title": {"type": "string"},
                "contact_id": {"type": "string", "description": "Identifiant ou nom du client"},
                "project_id": {"type": "string", "description": "Identifiant ou nom du projet"},
                "amount": {"type": "number"},
                "currency": {"type": "string"},
                "stage": {"type": "string", "enum": list(DEAL_STAGES)},
                "sent_at": {"type": "string", "description": "Date d'envoi AAAA-MM-JJ"},
                "response_due_date": {"type": "string", "description": "Réponse attendue AAAA-MM-JJ"},
                "notes": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=guarded(save_deal),
    ))
    shelf.add(AgentTool(
        name="crm_save_contract",
        description=(
            "Crée ou met à jour un contrat : dates de début et de fin, valeur, statut "
            "et préavis. Permet d'alerter avant expiration."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "contract_id": {"type": "string"},
                "title": {"type": "string"},
                "contact_id": {"type": "string", "description": "Identifiant ou nom du client"},
                "project_id": {"type": "string", "description": "Identifiant ou nom du projet"},
                "start_date": {"type": "string", "description": "AAAA-MM-JJ"},
                "end_date": {"type": "string", "description": "AAAA-MM-JJ"},
                "value": {"type": "number"},
                "currency": {"type": "string"},
                "status": {"type": "string", "enum": list(CONTRACT_STATUSES)},
                "notice_days": {"type": "integer", "minimum": 0, "maximum": 365},
                "notes": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=guarded(save_contract),
    ))
    shelf.add(AgentTool(
        name="crm_log_interaction",
        description=(
            "Enregistre un échange dans la chronologie d'une relation : appel, "
            "e-mail, réunion, message ou note. Met à jour la date du dernier contact, "
            "ce qui évite de relancer quelqu'un que l'on vient d'appeler."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Ce qui s'est dit, en une phrase"},
                "kind": {"type": "string", "enum": list(INTERACTION_KINDS)},
                "contact": {"type": "string", "description": "Identifiant ou nom du contact"},
                "project": {"type": "string", "description": "Identifiant ou nom du projet"},
                "occurred_at": {"type": "string", "description": "Date AAAA-MM-JJ"},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        handler=guarded(log_interaction),
    ))


def _add_agenda_skills(shelf: ToolShelf, agenda: AgendaRepository) -> None:
    def view(arguments: Mapping[str, Any]) -> dict[str, Any]:
        days = max(0, min(int(arguments.get("days", 0) or 0), 30))
        digest = agenda.digest()
        if days:
            digest["upcoming"] = [
                {**asdict(event), "label": event.label()} for event in agenda.upcoming(days)
            ]
        return digest

    def save_event(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            event = agenda.save_event(
                arguments.get("event_id") or None,
                **{key: value for key, value in arguments.items() if key != "event_id"},
            )
        except AgendaError as error:
            return {"error": str(error)}
        audit("skill_event_saved", event_id=event.event_id)
        return {"event": asdict(event), "label": event.label()}

    def prepare(arguments: Mapping[str, Any]) -> dict[str, Any]:
        reference = str(arguments.get("event_id", "")).strip()
        if not reference:
            # Convenience: prepare the next appointment when none is named.
            upcoming = agenda.upcoming(7)
            if not upcoming:
                return {"error": "no_upcoming_event"}
            reference = upcoming[0].event_id
        try:
            return agenda.prepare(reference)
        except AgendaError as error:
            return {"error": str(error)}

    def cancel(arguments: Mapping[str, Any]) -> dict[str, Any]:
        event_id = str(arguments.get("event_id", "")).strip()
        if not event_id or not agenda.delete(event_id):
            return {"error": "event_not_found"}
        audit("skill_event_deleted", event_id=event_id)
        return {"deleted": event_id}

    event_properties = {
        "title": {"type": "string", "description": "Objet du rendez-vous"},
        "starts_at": {
            "type": "string",
            "description": "Début, AAAA-MM-JJTHH:MM (ou AAAA-MM-JJ pour la journée)",
        },
        "ends_at": {"type": "string", "description": "Fin, AAAA-MM-JJTHH:MM"},
        "kind": {"type": "string", "enum": list(EVENT_KINDS)},
        "location": {"type": "string", "description": "Lieu ou lien de visioconférence"},
        "participants": {"type": "array", "items": {"type": "string"}},
        "contact_id": {"type": "string", "description": "Identifiant ou nom du client concerné"},
        "project_id": {"type": "string", "description": "Identifiant ou nom du projet concerné"},
        "notes": {"type": "string"},
    }

    shelf.add(AgentTool(
        name="agenda_view",
        description=(
            "Consulte l'agenda : rendez-vous du jour, chevauchements détectés et "
            "premier rendez-vous de demain. Avec le paramètre days, ajoute les "
            "rendez-vous à venir. À utiliser pour « qu'est-ce que j'ai aujourd'hui ? » "
            "ou « quand suis-je libre ? »."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 0, "maximum": 30}},
            "additionalProperties": False,
        },
        handler=view,
    ))
    shelf.add(AgentTool(
        name="agenda_save_event",
        description=(
            "Enregistre ou modifie un rendez-vous quand l'utilisateur en mentionne un "
            "(« j'ai rendez-vous jeudi à 10 h avec Ama »). Rattache-le au client ou au "
            "projet concerné dès que possible : c'est ce qui permettra à EMEFA de "
            "préparer la réunion. Fournis event_id pour modifier un rendez-vous existant."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {"event_id": {"type": "string"}, **event_properties},
            "required": ["title", "starts_at"],
            "additionalProperties": False,
        },
        handler=save_event,
    ))
    shelf.add(AgentTool(
        name="agenda_prepare_meeting",
        description=(
            "Prépare un rendez-vous : rassemble le client, le projet, les devis en "
            "attente, les contrats, les derniers échanges et les tâches liées, puis "
            "propose les points à aborder. Sans event_id, prépare le prochain "
            "rendez-vous à venir. À utiliser pour « prépare ma réunion avec X »."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=prepare,
    ))
    shelf.add(AgentTool(
        name="agenda_cancel_event",
        description=(
            "Supprime un rendez-vous de l'agenda à partir de son event_id. "
            "Action irréversible : à n'utiliser que sur demande explicite."
        ),
        risk=ActionRisk.DESTRUCTIVE,
        parameters={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
            "additionalProperties": False,
        },
        handler=cancel,
    ))


def _add_meeting_skills(shelf: ToolShelf, meetings: MeetingRepository) -> None:
    def capture(arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = meetings.capture(
                title=str(arguments.get("title", "")),
                notes=str(arguments.get("notes", "")),
                occurred_at=arguments.get("occurred_at"),
                participants=list(arguments.get("participants") or []),
                summary=str(arguments.get("summary", "")),
                decisions=list(arguments.get("decisions") or []),
                actions=list(arguments.get("actions") or []),
                project=arguments.get("project"),
                contact=arguments.get("contact"),
            )
        except ValueError as error:
            return {"error": str(error)}
        audit("skill_meeting_captured", meeting_id=result["meeting_id"])
        return result

    def list_meetings(arguments: Mapping[str, Any]) -> dict[str, Any]:
        limit = max(1, min(int(arguments.get("limit", 10)), 50))
        entries = meetings.list(limit=limit)
        return {"count": len(entries), "meetings": entries, "open_actions": meetings.open_actions(20)}

    shelf.add(AgentTool(
        name="meeting_capture",
        description=(
            "Transforme des notes de réunion en suivi réel : rédige le compte rendu "
            "Word, enregistre les décisions, enregistre les actions avec responsable "
            "et échéance, crée une tâche pour chaque action qui incombe à "
            "l'utilisateur, met à jour la prochaine étape du projet concerné et "
            "consigne la réunion dans l'historique du client. Utilise cet outil dès "
            "qu'une réunion est racontée ou dictée."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Sujet de la réunion"},
                "occurred_at": {"type": "string", "description": "Date AAAA-MM-JJ"},
                "participants": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string", "description": "Résumé professionnel des échanges"},
                "notes": {"type": "string", "description": "Notes brutes éventuelles"},
                "decisions": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Décisions prises, une par entrée",
                },
                "actions": {
                    "type": "array",
                    "description": "Actions décidées. Responsable « moi » = une tâche est créée.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "owner": {"type": "string"},
                            "due_date": {"type": "string", "description": "AAAA-MM-JJ"},
                        },
                        "required": ["description"],
                        "additionalProperties": False,
                    },
                },
                "project": {"type": "string", "description": "Nom du projet concerné"},
                "contact": {"type": "string", "description": "Nom du client concerné"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=capture,
    ))
    shelf.add(AgentTool(
        name="meeting_list",
        description=(
            "Liste les dernières réunions enregistrées avec leurs comptes rendus, "
            "ainsi que les actions encore attendues d'autres personnes."
        ),
        risk=ActionRisk.PERSONAL_READ,
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "additionalProperties": False,
        },
        handler=list_meetings,
    ))


def _add_workflow_skills(shelf: ToolShelf, workflows: WorkflowEngine) -> None:
    def proposal(arguments: Mapping[str, Any]) -> dict[str, Any]:
        client = str(arguments.get("client", "")).strip()
        subject = str(arguments.get("subject", "")).strip()
        if not client or not subject:
            return {"error": "client_and_subject_required"}
        try:
            result = workflows.commercial_proposal(
                client=client,
                subject=subject,
                items=list(arguments.get("items") or []),
                context=str(arguments.get("context", "")),
                amount=arguments.get("amount"),
                currency=str(arguments.get("currency", "XOF")),
                validity_days=int(arguments.get("validity_days", 30) or 30),
                project=arguments.get("project"),
            )
        except AmbiguousMatchError as error:
            return {
                "error": str(error),
                "candidates": error.candidates,
                "instruction": (
                    "Plusieurs clients portent ce nom. Demande lequel avant de "
                    "préparer quoi que ce soit."
                ),
            }
        except CrmError as error:
            return {"error": str(error)}
        audit("skill_workflow_proposal", deal_id=result["deal_id"])
        return result

    def relance(arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = workflows.follow_up(
            client=str(arguments.get("client", "")),
            tone=str(arguments.get("tone", "courtois")),
        )
        audit("skill_workflow_follow_up", status=result.get("status", ""))
        return result

    shelf.add(AgentTool(
        name="workflow_commercial_proposal",
        description=(
            "Scénario complet « prépare une proposition commerciale » : retrouve le "
            "client et son historique, récupère les devis antérieurs, génère le "
            "document Word, enregistre le devis, crée la tâche de relance et prépare "
            "l'e-mail. Rien n'est envoyé : l'envoi est proposé et attend l'approbation "
            "de l'utilisateur. Utilise cet outil plutôt que d'enchaîner les outils un "
            "par un."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "client": {"type": "string", "description": "Nom du client ou du prospect"},
                "subject": {"type": "string", "description": "Objet de la proposition"},
                "context": {"type": "string", "description": "Contexte et besoin exprimé"},
                "items": {
                    "type": "array",
                    "description": "Lignes chiffrées de la proposition",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                        "required": ["label"],
                        "additionalProperties": False,
                    },
                },
                "amount": {"type": "number", "description": "Montant global si pas de lignes"},
                "currency": {"type": "string"},
                "validity_days": {"type": "integer", "minimum": 1, "maximum": 365},
                "project": {"type": "string"},
            },
            "required": ["client", "subject"],
            "additionalProperties": False,
        },
        handler=proposal,
    ))
    shelf.add(AgentTool(
        name="workflow_follow_up",
        description=(
            "Scénario complet « relance ce client » : rassemble l'historique et les "
            "devis en attente, prépare un message de relance adapté et crée la tâche "
            "de suivi. L'envoi reste soumis à approbation."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "client": {"type": "string"},
                "tone": {"type": "string", "enum": ["courtois", "direct"]},
            },
            "required": ["client"],
            "additionalProperties": False,
        },
        handler=relance,
    ))


def _add_onboarding_skills(shelf: ToolShelf, onboarding: OnboardingRepository) -> None:
    def plan(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        status = onboarding.status()
        return {
            "completed": status["completed"],
            "progress": status["progress"],
            "next_topic": status["next_topic"],
            "next_question": onboarding.next_question(),
            "topics": [
                {
                    "topic_id": topic["topic_id"],
                    "title": topic["title"],
                    "status": topic["status"],
                    "missing": [item["label"] for item in topic["missing_fields"]],
                }
                for topic in status["topics"]
            ],
        }

    def finish(arguments: Mapping[str, Any]) -> dict[str, Any]:
        topic_id = str(arguments.get("skip_topic", "")).strip()
        if topic_id:
            try:
                return {"onboarding": onboarding.skip(topic_id)}
            except ValueError:
                return {"error": "unknown_topic"}
        status = onboarding.complete()
        audit("skill_onboarding_completed", progress=status["progress"])
        return {"onboarding": status}

    shelf.add(AgentTool(
        name="onboarding_plan",
        description=(
            "Indique où en est l'entretien d'accueil : ce qui est déjà connu du "
            "dirigeant et de son entreprise, ce qu'il reste à découvrir, et la "
            "prochaine question naturelle à poser. À consulter au début d'une "
            "première conversation et avant de poser une question personnelle, pour "
            "ne jamais redemander une information déjà connue."
        ),
        risk=ActionRisk.PERSONAL_READ,
        handler=plan,
    ))
    shelf.add(AgentTool(
        name="onboarding_finish",
        description=(
            "Clôt l'entretien d'accueil quand le dirigeant estime en avoir assez dit, "
            "ou met de côté un sujet précis via skip_topic (personnel, entreprise, "
            "activite, objectifs, preferences). L'entretien pourra toujours reprendre."
        ),
        risk=ActionRisk.LOCAL_WRITE,
        parameters={
            "type": "object",
            "properties": {
                "skip_topic": {
                    "type": "string",
                    "enum": ["personnel", "entreprise", "activite", "objectifs", "preferences"],
                }
            },
            "additionalProperties": False,
        },
        handler=finish,
    ))


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
