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
    has_pipeline = "list_pipeline" in skills
    has_documents = "document_create" in skills

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
            note="Réel : compose le brief du jour (tâches, relances, objectifs) à partir de vos données.",
        ),
        Scenario(
            id="meeting_prep",
            title="Préparation de réunion",
            prompt="Prépare ma réunion avec Horizon.",
            status="assisted" if has_pipeline else "preview",
            note=(
                "Assisté : EMEFA rassemble ce qu'elle sait déjà (profil, pipeline, "
                "tâches, e-mails si connectés). Pas d'accès agenda dédié pour l'instant."
            ),
        ),
        Scenario(
            id="document",
            title="Création de document",
            prompt="Prépare la proposition.",
            status="live" if has_documents else "preview",
            note=(
                "Réel : EMEFA génère un document Word (DOCX) persistant et renvoie "
                "son lien de téléchargement."
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
                "EMEFA suit dans le pipeline les prospects que vous lui donnez."
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
                "Partiel : le brief récurrent existe (planifié) et tout envoi reste "
                "soumis à votre approbation. " + email_note
            ),
        ),
    ]
