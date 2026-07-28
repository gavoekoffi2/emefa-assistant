"""Entities: the things a business is actually about.

Until now EMEFA remembered *the user*. Facts about a project, a client or an
invoice went into the same flat personal memory, which means "où en est le
projet Graphiste GPT ?" could only ever be answered by full-text luck.

An entity is a named thing with its own memory, its own history, and typed
links to other entities. That last part is what makes the difference between
storing facts and being able to reason:

    Client → Projet → Devis → Facture → Réunion → Relance

Three separations are deliberate and load-bearing:

* **Personal memory and business memory are different scopes.** What the user
  prefers for their own calendar is not a fact about their company, and an
  assistant that mixes them leaks one into the other. `EntityScope` keeps them
  apart at the storage layer, not by convention.
* **An entity is not its facts.** The entity is the node — name, kind, status.
  What is known about it lives in the memory kernel, scoped to it, and gets
  all the machinery already built there: reinforcement, supersession, decay.
* **A relation is typed and directed.** "Horizon SARL est client de nous" and
  "le devis 42 porte sur le projet Graphiste GPT" are different edges, and
  answering with context means walking them, not full-text searching.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class EntityKind(StrEnum):
    PROJECT = "project"
    COMPANY = "company"
    PERSON = "person"
    QUOTE = "quote"
    INVOICE = "invoice"
    CONTRACT = "contract"
    MEETING = "meeting"


class EntityScope(StrEnum):
    """Which memory an entity belongs to.

    `personal` is the user's own life; `business` is the company's. Kept
    separate because they have different audiences: a future colleague with
    access to the company assistant must not inherit the owner's private
    memory.
    """

    BUSINESS = "business"
    PERSONAL = "personal"


class EntityStatus(StrEnum):
    ACTIVE = "active"
    #: Work is paused but the entity is not finished.
    ON_HOLD = "on_hold"
    DONE = "done"
    #: Lost, cancelled, withdrawn. Kept, never deleted — the history matters.
    CLOSED = "closed"


class RelationKind(StrEnum):
    #: A company we sell to / buy from / work with.
    CLIENT_OF = "client_of"
    SUPPLIER_OF = "supplier_of"
    PARTNER_OF = "partner_of"
    #: A person inside a company.
    WORKS_FOR = "works_for"
    #: A project belongs to a client; a quote belongs to a project.
    BELONGS_TO = "belongs_to"
    #: A quote covers a project; an invoice settles a quote.
    COVERS = "covers"
    SETTLES = "settles"
    #: A meeting is about something, and someone attended it.
    ABOUT = "about"
    ATTENDED_BY = "attended_by"
    #: Anything else worth linking.
    RELATED_TO = "related_to"


#: The arc a commercial relationship actually travels. Ordering matters: the
#: timeline uses it to tell where a client has got to.
class Milestone(StrEnum):
    FIRST_CONTACT = "first_contact"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    SIGNATURE = "signature"
    DELIVERY = "delivery"
    INVOICE = "invoice"
    PAYMENT = "payment"
    FOLLOW_UP = "follow_up"
    DECISION = "decision"
    ISSUE = "issue"
    NOTE = "note"


MILESTONE_ORDER: tuple[Milestone, ...] = (
    Milestone.FIRST_CONTACT,
    Milestone.MEETING,
    Milestone.PROPOSAL,
    Milestone.NEGOTIATION,
    Milestone.SIGNATURE,
    Milestone.DELIVERY,
    Milestone.INVOICE,
    Milestone.PAYMENT,
)

MILESTONE_LABELS: dict[Milestone, str] = {
    Milestone.FIRST_CONTACT: "Premier contact",
    Milestone.MEETING: "Réunion",
    Milestone.PROPOSAL: "Proposition",
    Milestone.NEGOTIATION: "Négociation",
    Milestone.SIGNATURE: "Signature",
    Milestone.DELIVERY: "Livraison",
    Milestone.INVOICE: "Facturation",
    Milestone.PAYMENT: "Paiement",
    Milestone.FOLLOW_UP: "Relance",
    Milestone.DECISION: "Décision",
    Milestone.ISSUE: "Problème",
    Milestone.NOTE: "Note",
}

KIND_LABELS: dict[EntityKind, str] = {
    EntityKind.PROJECT: "Projet",
    EntityKind.COMPANY: "Entreprise",
    EntityKind.PERSON: "Personne",
    EntityKind.QUOTE: "Devis",
    EntityKind.INVOICE: "Facture",
    EntityKind.CONTRACT: "Contrat",
    EntityKind.MEETING: "Réunion",
}

#: Memory categories that carry a project's actual substance. Used to answer
#: "quelles décisions ?" and "quels problèmes restent ouverts ?" without a
#: full-text search over everything.
DECISION_CATEGORY = "decision"
ISSUE_CATEGORY = "issue"


def slugify(name: str) -> str:
    """Lookup key for a name.

    "Clinique du Lac", "clinique du lac" and "CLINIQUE DU LAC " are the same
    client. Without this, every mention creates a new entity and the graph is
    worthless within a week.
    """
    folded = "".join(
        unicodedata.normalize("NFD", character)[0].lower() for character in name
    )
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:120]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: str
    kind: EntityKind
    name: str
    slug: str
    scope: EntityScope = EntityScope.BUSINESS
    status: EntityStatus = EntityStatus.ACTIVE
    #: One line the user wrote, or EMEFA derived. Not a generated paragraph.
    summary: str = ""
    #: Kind-specific fields: amount and currency on a quote, a date on a
    #: meeting, a role on a person. Deliberately schemaless — pinning every
    #: kind down now would be guessing at a business we have not met.
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "kind": self.kind.value,
            "kind_label": KIND_LABELS.get(self.kind, self.kind.value),
            "name": self.name,
            "scope": self.scope.value,
            "status": self.status.value,
            "summary": self.summary,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class Relation:
    relation_id: str
    from_entity_id: str
    to_entity_id: str
    kind: RelationKind
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    entry_id: str
    entity_id: str
    milestone: Milestone
    #: What happened, in one line, in the user's words.
    headline: str
    occurred_at: str
    #: The memory event this came from, when it came from one.
    event_id: str | None = None
    created_at: str = field(default_factory=_now)

    def summary(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "milestone": self.milestone.value,
            "label": MILESTONE_LABELS.get(self.milestone, self.milestone.value),
            "headline": self.headline,
            "occurred_at": self.occurred_at,
        }


def normalise_kind(value: Any, default: EntityKind = EntityKind.PROJECT) -> EntityKind:
    try:
        return EntityKind(str(value).strip().lower())
    except ValueError:
        return default


def normalise_relation(value: Any) -> RelationKind:
    try:
        return RelationKind(str(value).strip().lower())
    except ValueError:
        return RelationKind.RELATED_TO


def normalise_milestone(value: Any) -> Milestone:
    try:
        return Milestone(str(value).strip().lower())
    except ValueError:
        return Milestone.NOTE


def normalise_status(value: Any) -> EntityStatus:
    try:
        return EntityStatus(str(value).strip().lower())
    except ValueError:
        return EntityStatus.ACTIVE


def normalise_scope(value: Any) -> EntityScope:
    try:
        return EntityScope(str(value).strip().lower())
    except ValueError:
        return EntityScope.BUSINESS
