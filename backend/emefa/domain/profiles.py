"""Assistant identity and business-profile persistence (single-tenant mode)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from emefa.domain import storage
from emefa.domain.storage import DEFAULT_ASSISTANT_ID

ASSISTANT_FIELDS = ("name", "primary_language", "interaction_style")
BUSINESS_FIELDS = (
    "owner_name",
    "owner_role",
    "company_name",
    "industry",
    "offer",
    "target_customers",
    "goals",
    "constraints_notes",
    "website_url",
    "website_summary",
)


@dataclass(frozen=True, slots=True)
class AssistantProfile:
    assistant_id: str
    name: str
    primary_language: str
    interaction_style: str


@dataclass(frozen=True, slots=True)
class BusinessProfile:
    assistant_id: str
    owner_name: str
    owner_role: str
    company_name: str
    industry: str
    offer: str
    target_customers: str
    goals: str
    constraints_notes: str
    website_url: str
    website_summary: str

    def is_empty(self) -> bool:
        return not any(getattr(self, field) for field in BUSINESS_FIELDS)


class ProfileRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def get_assistant(self) -> AssistantProfile:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT assistant_id, name, primary_language, interaction_style "
                "FROM assistants WHERE assistant_id = ?",
                (DEFAULT_ASSISTANT_ID,),
            ).fetchone()
        if row is None:
            raise RuntimeError("default assistant row missing; migrations not applied")
        return AssistantProfile(**dict(row))

    def update_assistant(self, changes: dict[str, str]) -> AssistantProfile:
        self._update("assistants", "assistant_id", ASSISTANT_FIELDS, changes)
        return self.get_assistant()

    def get_business(self) -> BusinessProfile:
        columns = ", ".join(("assistant_id", *BUSINESS_FIELDS))
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {columns} FROM business_profiles WHERE assistant_id = ?",
                (DEFAULT_ASSISTANT_ID,),
            ).fetchone()
        if row is None:
            raise RuntimeError("default business profile missing; migrations not applied")
        return BusinessProfile(**dict(row))

    def update_business(self, changes: dict[str, str]) -> BusinessProfile:
        self._update("business_profiles", "assistant_id", BUSINESS_FIELDS, changes)
        return self.get_business()

    def _update(
        self,
        table: str,
        key_column: str,
        allowed: tuple[str, ...],
        changes: dict[str, str],
    ) -> None:
        accepted = {field: changes[field] for field in allowed if field in changes}
        if not accepted:
            return
        assignments = ", ".join(f"{field} = ?" for field in accepted)
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"UPDATE {table} SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                f"WHERE {key_column} = ?",
                (*accepted.values(), DEFAULT_ASSISTANT_ID),
            )

    def system_context(self) -> str:
        """Compose the profile block injected into the agent system prompt."""
        assistant = self.get_assistant()
        business = self.get_business()
        lines = [
            f"Tu t'appelles {assistant.name}.",
            f"Langue principale : {assistant.primary_language}.",
        ]
        if assistant.interaction_style:
            lines.append(f"Style d'interaction souhaité : {assistant.interaction_style}.")
        if not business.is_empty():
            lines.append("Contexte professionnel de l'utilisateur :")
            labels = {
                "owner_name": "Nom",
                "owner_role": "Rôle",
                "company_name": "Entreprise",
                "industry": "Secteur",
                "offer": "Offre",
                "target_customers": "Clients cibles",
                "goals": "Objectifs",
                "constraints_notes": "Contraintes et notes",
                "website_url": "Site web officiel",
                "website_summary": "Informations publiques importées du site",
            }
            for field, label in labels.items():
                value = getattr(business, field)
                if value:
                    lines.append(f"- {label} : {value}")
        return "\n".join(lines)
