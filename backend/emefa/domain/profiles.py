"""Assistant identity and business-profile persistence (single-tenant mode)."""

from __future__ import annotations

import uuid

from dataclasses import dataclass
from pathlib import Path

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore
from emefa.domain.storage import DEFAULT_ASSISTANT_ID

ASSISTANT_FIELDS = ("name", "primary_language", "interaction_style")

#: Field groups mirror the onboarding interview so a captured answer always
#: has one obvious home. Order is the order the executive profile is shown in.
PERSONAL_FIELDS = (
    "owner_name",
    "preferred_name",
    "owner_role",
    "country",
    "city",
    "timezone",
    "working_hours",
)
COMPANY_FIELDS = (
    "company_name",
    "industry",
    "offer",
    "products",
    "services",
    "organization",
    "collaborators",
    "website_url",
    "website_summary",
)
ACTIVITY_FIELDS = (
    "target_customers",
    "clients",
    "suppliers",
    "partners",
)
OBJECTIVE_FIELDS = (
    "goals",
    "annual_goals",
    "quarterly_goals",
    "current_priorities",
    "challenges",
)
PREFERENCE_FIELDS = (
    "autonomy_level",
    "communication_style",
    "report_frequency",
    "organization_preferences",
    "constraints_notes",
)

BUSINESS_FIELDS = (
    *PERSONAL_FIELDS,
    *COMPANY_FIELDS,
    *ACTIVITY_FIELDS,
    *OBJECTIVE_FIELDS,
    *PREFERENCE_FIELDS,
)

#: Human labels, used for the configuration centre, the onboarding interview
#: and the system-context block — one source of truth, three surfaces.
FIELD_LABELS: dict[str, str] = {
    "owner_name": "Nom complet",
    "preferred_name": "Nom d'usage souhaité",
    "owner_role": "Fonction",
    "country": "Pays",
    "city": "Ville",
    "timezone": "Fuseau horaire",
    "working_hours": "Horaires de travail",
    "company_name": "Entreprise",
    "industry": "Secteur d'activité",
    "offer": "Offre principale",
    "products": "Produits",
    "services": "Services",
    "organization": "Organisation interne",
    "collaborators": "Collaborateurs",
    "website_url": "Site web officiel",
    "website_summary": "Informations publiques importées du site",
    "target_customers": "Clients cibles",
    "clients": "Clients principaux",
    "suppliers": "Fournisseurs",
    "partners": "Partenaires",
    "goals": "Objectifs généraux",
    "annual_goals": "Objectifs annuels",
    "quarterly_goals": "Objectifs trimestriels",
    "current_priorities": "Priorités actuelles",
    "challenges": "Difficultés et défis",
    "autonomy_level": "Niveau d'autonomie souhaité",
    "communication_style": "Style de communication",
    "report_frequency": "Fréquence des rapports",
    "organization_preferences": "Préférences d'organisation",
    "constraints_notes": "Contraintes et notes",
}


@dataclass(frozen=True, slots=True)
class AssistantProfile:
    assistant_id: str
    name: str
    primary_language: str
    interaction_style: str


@dataclass(frozen=True, slots=True)
class BusinessProfile:
    assistant_id: str
    # Personal
    owner_name: str = ""
    preferred_name: str = ""
    owner_role: str = ""
    country: str = ""
    city: str = ""
    timezone: str = ""
    working_hours: str = ""
    # Company
    company_name: str = ""
    industry: str = ""
    offer: str = ""
    products: str = ""
    services: str = ""
    organization: str = ""
    collaborators: str = ""
    website_url: str = ""
    website_summary: str = ""
    # Activity
    target_customers: str = ""
    clients: str = ""
    suppliers: str = ""
    partners: str = ""
    # Objectives
    goals: str = ""
    annual_goals: str = ""
    quarterly_goals: str = ""
    current_priorities: str = ""
    challenges: str = ""
    # Preferences
    autonomy_level: str = ""
    communication_style: str = ""
    report_frequency: str = ""
    organization_preferences: str = ""
    constraints_notes: str = ""

    def is_empty(self) -> bool:
        return not any(getattr(self, field) for field in BUSINESS_FIELDS)

    def filled_fields(self) -> tuple[str, ...]:
        return tuple(field for field in BUSINESS_FIELDS if getattr(self, field).strip())

    def address_as(self) -> str:
        """How EMEFA should name the executive out loud."""
        return self.preferred_name.strip() or self.owner_name.strip()


class ProfileRepository(ScopedStore):
    """The company's own description, and the assistant serving it.

    Both are tenant-owned: every colleague works with the same company profile
    and the same assistant identity.
    """

    ownership = Ownership.TENANT

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)
        self.assistant_id = self._resolve_assistant_id()

    def _resolve_assistant_id(self) -> str:
        """One assistant per company, provisioned on first use.

        Migration 2 seeded rows for the default tenant only. Any other company
        gets its own assistant and its own empty business profile the first
        time it is touched, so a new tenant is usable without a separate
        bootstrap step — and can never fall back to another company's profile.
        """
        row = self.fetch_one("assistant_id", "assistants")
        if row is not None:
            return row["assistant_id"]
        assistant_id = (
            DEFAULT_ASSISTANT_ID
            if self.scope.is_default()
            else f"ast_{uuid.uuid4().hex[:12]}"
        )
        self.insert("assistants", {"assistant_id": assistant_id, "name": "EMEFA"})
        self.insert("business_profiles", {"assistant_id": assistant_id})
        return assistant_id

    def get_assistant(self) -> AssistantProfile:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT assistant_id, name, primary_language, interaction_style "
                "FROM assistants WHERE assistant_id = ? AND tenant_id = ?",
                (self.assistant_id, self.scope.tenant_id),
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
                f"SELECT {columns} FROM business_profiles "
                "WHERE assistant_id = ? AND tenant_id = ?",
                (self.assistant_id, self.scope.tenant_id),
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
                f"WHERE {key_column} = ? AND tenant_id = ?",
                (*accepted.values(), self.assistant_id, self.scope.tenant_id),
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
        address = business.address_as()
        if address:
            lines.append(f"Tu t'adresses à {address}.")
        if business.communication_style:
            lines.append(f"Style de communication attendu : {business.communication_style}.")
        if business.autonomy_level:
            lines.append(
                f"Niveau d'autonomie accordé : {business.autonomy_level}. Les actions "
                "sensibles restent soumises à approbation quelle que soit cette préférence."
            )
        if not business.is_empty():
            lines.append("Contexte professionnel de l'utilisateur :")
            for field in BUSINESS_FIELDS:
                value = getattr(business, field)
                if value:
                    lines.append(f"- {FIELD_LABELS.get(field, field)} : {value}")
        return "\n".join(lines)
