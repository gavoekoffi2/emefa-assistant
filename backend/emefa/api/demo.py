"""Integrated demo experience: an honest catalog of the guided scenarios.

Each scenario's availability is derived from the *real* system state
(registered skills, configured integrations) — never asserted. Statuses:
- "live":     backed end-to-end by a real, executable capability;
- "assisted": EMEFA composes from real stored data (no dedicated tool);
- "preview":  the capability does not exist yet; must not be simulated.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/demo", tags=["demo"])


class Scenario(BaseModel):
    id: str
    title: str
    prompt: str
    status: Literal["live", "assisted", "preview"]
    note: str


@router.get("/scenarios", response_model=list[Scenario])
def scenarios(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[Scenario]:
    skills = {tool["name"] for tool in request.app.state.agent.tools.describe()}
    has_email = "email_send" in skills
    has_documents = "document_create" in skills
    has_crm = "crm_overview" in skills
    has_meetings = "meeting_capture" in skills
    has_proposal = "workflow_commercial_proposal" in skills
    has_office = "spreadsheet_create" in skills

    email_note = (
        "Réel : EMEFA peut préparer un e-mail ; l'envoi passe par votre approbation."
        if has_email
        else "Connectez la boîte mail pour activer l'envoi d'e-mail réel."
    )
    return [
        Scenario(
            id="executive_brief",
            title="Briefing exécutif",
            prompt="Bonjour EMEFA, qu'est-ce qui mérite mon attention aujourd'hui ?",
            status="live",
            note=(
                "Réel : priorités, tâches, relances, devis en attente, contrats à "
                "échéance, projets bloqués et recommandations, lus dans vos données."
            ),
        ),
        Scenario(
            id="evening_report",
            title="Rapport du soir",
            prompt="Fais le point sur ma journée et dis-moi par quoi commencer demain.",
            status="live",
            note=(
                "Réel : tâches terminées, tâches restantes, blocages et priorités du "
                "lendemain, calculés — jamais inventés."
            ),
        ),
        Scenario(
            id="crm_review",
            title="Point commercial",
            prompt="Quels clients dois-je relancer, et quels devis attendent une réponse ?",
            status="live" if has_crm else "preview",
            note=(
                "Réel : EMEFA lit sa mémoire relationnelle (clients, projets, devis, "
                "contrats, historique des échanges)."
                if has_crm
                else "Aperçu : la mémoire relationnelle n'est pas disponible."
            ),
        ),
        Scenario(
            id="project_status",
            title="État d'un projet",
            prompt="Où en est le projet Refonte ?",
            status="live" if has_crm else "preview",
            note=(
                "Réel : EMEFA remonte le client, les devis liés, les contrats liés, "
                "l'historique et les signaux d'alerte du projet."
                if has_crm
                else "Aperçu : nécessite la mémoire relationnelle."
            ),
        ),
        Scenario(
            id="meeting_followup",
            title="Compte rendu de réunion",
            prompt=(
                "Voici mes notes de réunion : rédige le compte rendu, liste les "
                "décisions et crée les tâches."
            ),
            status="live" if has_meetings else "preview",
            note=(
                "Réel : compte rendu Word, décisions, actions avec responsable et "
                "échéance, tâches créées et projet mis à jour."
                if has_meetings
                else "Aperçu : la capture de réunion n'est pas disponible."
            ),
        ),
        Scenario(
            id="commercial_proposal",
            title="Proposition commerciale",
            prompt="Prépare une proposition commerciale pour Horizon.",
            status="live" if has_proposal else "preview",
            note=(
                "Réel : client retrouvé, historique et anciens devis récupérés, "
                "document généré, devis enregistré, tâche de relance créée et e-mail "
                "préparé. Rien n'est envoyé sans votre approbation."
                if has_proposal
                else "Aperçu : le scénario complet n'est pas disponible."
            ),
        ),
        Scenario(
            id="document",
            title="Bureautique professionnelle",
            prompt="Prépare un tableau de budget pour ce projet.",
            status="live" if has_documents else "preview",
            note=(
                "Réel : Word, Excel (formules vivantes) et PowerPoint, tous "
                "modifiables et téléchargeables."
                if has_office
                else "Réel : EMEFA génère un document Word (DOCX) persistant."
                if has_documents
                else "Aperçu : la génération de document n'est pas encore disponible."
            ),
        ),
        Scenario(
            id="business_development",
            title="Développement commercial",
            prompt="Trouve-moi 10 prospects sérieux correspondant à notre cible.",
            status="preview",
            note=(
                "Aperçu : la découverte automatique de prospects n'est pas disponible "
                "(nécessite des fournisseurs vérifiés, pas de prospection non contrôlée). "
                "EMEFA suit en revanche les prospects et clients que vous lui confiez."
            ),
        ),
        Scenario(
            id="recurring_autonomy",
            title="Autonomie encadrée",
            prompt=(
                "Fais cette prospection chaque semaine, mais demande-moi avant "
                "d'envoyer les messages."
            ),
            status="assisted",
            note=(
                "Partiel : briefing du matin et rapport du soir sont planifiés, et "
                "tout envoi reste soumis à votre approbation. " + email_note
            ),
        ),
    ]
