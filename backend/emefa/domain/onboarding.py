"""Conversational welcome interview.

Design rule (mission §1): onboarding is an *interview*, never a form. So the
progress model is **derived from the executive profile itself** rather than
stored separately — whatever EMEFA learns during a normal conversation counts
as progress, whether it was learned by asking or in passing. Only the two
facts a conversation cannot infer are persisted: which topics the executive
asked to skip, and when the interview was declared finished.

Consequence: the interview cannot desynchronise from the memory it feeds, and
the user can never be asked twice for something already known (mission §27 of
the constitution).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.profiles import (
    ACTIVITY_FIELDS,
    COMPANY_FIELDS,
    FIELD_LABELS,
    OBJECTIVE_FIELDS,
    PERSONAL_FIELDS,
    PREFERENCE_FIELDS,
    ProfileRepository,
)
from emefa.domain.scope import Ownership, Scope, ScopedStore


@dataclass(frozen=True, slots=True)
class Topic:
    topic_id: str
    title: str
    fields: tuple[str, ...]
    #: Fields without which the topic cannot be considered covered at all.
    essential: tuple[str, ...]
    opening_question: str
    intent: str


TOPICS: tuple[Topic, ...] = (
    Topic(
        topic_id="personnel",
        title="Profil personnel",
        fields=PERSONAL_FIELDS,
        essential=("owner_name", "owner_role"),
        opening_question=(
            "Pour commencer, comment souhaitez-vous que je vous appelle, et quelle "
            "fonction occupez-vous ?"
        ),
        intent=(
            "Apprendre le nom d'usage, la fonction, le pays, la ville, le fuseau "
            "horaire et les horaires de travail habituels."
        ),
    ),
    Topic(
        topic_id="entreprise",
        title="Entreprise",
        fields=COMPANY_FIELDS,
        essential=("company_name", "industry"),
        opening_question="Parlez-moi de votre entreprise : que fait-elle exactement ?",
        intent=(
            "Apprendre le nom de l'entreprise, le secteur, les produits, les "
            "services, l'organisation interne et les collaborateurs."
        ),
    ),
    Topic(
        topic_id="activite",
        title="Activité",
        fields=ACTIVITY_FIELDS,
        essential=("target_customers",),
        opening_question="Qui sont vos clients, et avec quels partenaires travaillez-vous ?",
        intent=(
            "Apprendre les clients cibles, les clients principaux, les "
            "fournisseurs, les partenaires et les projets en cours. Les projets "
            "concrets doivent être enregistrés avec crm_save_project."
        ),
    ),
    Topic(
        topic_id="objectifs",
        title="Objectifs",
        fields=OBJECTIVE_FIELDS,
        essential=("current_priorities",),
        opening_question=(
            "Quels sont vos objectifs pour cette année, et qu'est-ce qui vous "
            "occupe le plus en ce moment ?"
        ),
        intent=(
            "Apprendre les objectifs annuels, les objectifs trimestriels, les "
            "priorités actuelles et les difficultés rencontrées."
        ),
    ),
    Topic(
        topic_id="preferences",
        title="Préférences de travail",
        fields=PREFERENCE_FIELDS,
        essential=("autonomy_level", "communication_style"),
        opening_question=(
            "Dernier point : jusqu'où souhaitez-vous que j'agisse seule, et "
            "préférez-vous des réponses brèves ou détaillées ?"
        ),
        intent=(
            "Apprendre le niveau d'autonomie souhaité, le style de communication, "
            "la fréquence des rapports et les préférences d'organisation."
        ),
    ),
)

TOPIC_BY_ID = {topic.topic_id: topic for topic in TOPICS}


class OnboardingRepository(ScopedStore):
    """How well EMEFA knows *this* person; the profile it fills is the company's."""

    ownership = Ownership.USER

    def __init__(
        self,
        database_path: Path,
        profiles: ProfileRepository,
        scope: Scope | None = None,
    ) -> None:
        super().__init__(database_path, scope)
        self.profiles = profiles

    def for_scope(self, scope: Scope) -> "OnboardingRepository":
        return OnboardingRepository(self.database_path, self.profiles.for_scope(scope), scope)

    # -- persisted state --------------------------------------------------

    def _state(self) -> dict[str, Any]:
        row = self.fetch_one(
            "started_at, completed_at, skipped_topics", "onboarding_state"
        )
        if row is None:
            self.insert("onboarding_state", {})
            return {"started_at": None, "completed_at": None, "skipped_topics": ""}
        return row

    def _write(self, values: dict[str, Any]) -> None:
        self._state()  # ensure the row exists for this owner
        self.update_scoped("onboarding_state", "user_id", self.scope.user_id, values)

    def _skipped(self) -> set[str]:
        raw = self._state().get("skipped_topics") or ""
        return {item for item in raw.split(",") if item}

    def start(self) -> dict[str, Any]:
        state = self._state()
        if not state.get("started_at"):
            self._write({"started_at": datetime.now(timezone.utc).isoformat()})
        return self.status()

    def skip(self, topic_id: str) -> dict[str, Any]:
        if topic_id not in TOPIC_BY_ID:
            raise ValueError("unknown_topic")
        skipped = self._skipped() | {topic_id}
        self._write({"skipped_topics": ",".join(sorted(skipped))})
        return self.status()

    def resume(self, topic_id: str) -> dict[str, Any]:
        """Undo a skip and clear completion, so the interview can go on."""
        skipped = self._skipped() - {topic_id}
        self._write({"skipped_topics": ",".join(sorted(skipped)), "completed_at": None})
        return self.status()

    def complete(self) -> dict[str, Any]:
        self._write({"completed_at": datetime.now(timezone.utc).isoformat()})
        return self.status()

    def reopen(self) -> dict[str, Any]:
        self._write({"completed_at": None, "skipped_topics": ""})
        return self.status()

    # -- derived view -----------------------------------------------------

    def status(self) -> dict[str, Any]:
        business = self.profiles.get_business()
        state = self._state()
        skipped = self._skipped()
        filled = set(business.filled_fields())

        topics: list[dict[str, Any]] = []
        for topic in TOPICS:
            known = [field for field in topic.fields if field in filled]
            missing = [field for field in topic.fields if field not in filled]
            essential_missing = [field for field in topic.essential if field not in filled]
            if topic.topic_id in skipped:
                topic_status = "ignoré"
            elif not essential_missing and len(known) >= len(topic.essential):
                topic_status = "complet" if not missing else "suffisant"
            elif known:
                topic_status = "en_cours"
            else:
                topic_status = "à_faire"
            topics.append(
                {
                    "topic_id": topic.topic_id,
                    "title": topic.title,
                    "status": topic_status,
                    "opening_question": topic.opening_question,
                    "intent": topic.intent,
                    "known_fields": [
                        {"field": field, "label": FIELD_LABELS.get(field, field),
                         "value": getattr(business, field)}
                        for field in known
                    ],
                    "missing_fields": [
                        {"field": field, "label": FIELD_LABELS.get(field, field),
                         "essential": field in topic.essential}
                        for field in missing
                    ],
                    "completion": round(len(known) / len(topic.fields), 2) if topic.fields else 1.0,
                }
            )

        pending = [item for item in topics if item["status"] in ("à_faire", "en_cours")]
        next_topic = pending[0] if pending else None
        answered = sum(1 for item in topics if item["status"] in ("complet", "suffisant"))
        return {
            "started": bool(state.get("started_at")),
            "completed": bool(state.get("completed_at")),
            "started_at": state.get("started_at"),
            "completed_at": state.get("completed_at"),
            "address_as": business.address_as(),
            "topics": topics,
            "next_topic": next_topic,
            "progress": round((answered + len(skipped)) / len(TOPICS), 2),
            "known_field_count": len(filled),
            "total_field_count": sum(len(topic.fields) for topic in TOPICS),
        }

    def is_needed(self) -> bool:
        status = self.status()
        return not status["completed"] and status["next_topic"] is not None

    def next_question(self) -> str | None:
        status = self.status()
        topic = status["next_topic"]
        if topic is None:
            return None
        if topic["status"] == "à_faire":
            return topic["opening_question"]
        labels = ", ".join(item["label"] for item in topic["missing_fields"][:3])
        return f"Pour compléter « {topic['title']} », il me manque encore : {labels}."

    def briefing_for_agent(self) -> str:
        """Instruction block handed to the brain while onboarding is unfinished."""
        status = self.status()
        if status["completed"] or status["next_topic"] is None:
            return ""
        topic = status["next_topic"]
        known = ", ".join(item["label"] for item in topic["known_fields"]) or "rien encore"
        missing = ", ".join(item["label"] for item in topic["missing_fields"]) or "rien"
        return (
            "ENTRETIEN D'ACCUEIL EN COURS. Tu apprends à connaître ton dirigeant par "
            "la conversation, jamais par un formulaire : une ou deux questions à la "
            "fois, en rebondissant sur ses réponses.\n"
            f"- Sujet en cours : {topic['title']} ({topic['intent']})\n"
            f"- Déjà connu : {known}\n"
            f"- Reste à apprendre : {missing}\n"
            f"- Progression globale : {int(status['progress'] * 100)} %\n"
            "Dès qu'une information est donnée, enregistre-la immédiatement avec "
            "update_business_profile, puis enchaîne naturellement. Ne redemande "
            "jamais une information déjà connue. Si le dirigeant préfère passer à "
            "autre chose, arrête l'entretien sans insister — il reprendra plus tard."
        )
