"""Executive workflows: complete scenarios, not isolated features.

Mission §8. When the executive says « Prépare une proposition commerciale »,
one instruction must produce the whole chain — find the client, recall the
history, look up past quotations, write the document, register the deal,
create the follow-up task, draft the e-mail — and then *stop* at the point
where a human decision is required.

That stopping point is the important part. A workflow never sends anything.
It prepares, records what it prepared, and returns an explicit
``proposed_action`` describing the one consequential step left. Sending still
goes through the normal approval gate in the agent engine, so no workflow can
turn itself into an automatic mailer (CLAUDE.md §24, §29).

Each step is reported with a real status so the assistant can say what it did
and what it could not do, instead of claiming a clean success (§25).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from emefa.domain.crm import AmbiguousMatchError, CrmError, CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.profiles import ProfileRepository
from emefa.domain.tasks import TaskRepository

#: Default number of days a proposal stays open before the follow-up task fires.
PROPOSAL_FOLLOW_UP_DAYS = 7


@dataclass
class StepResult:
    name: str
    status: str  # done | skipped | failed
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """Composes existing governed capabilities into executive scenarios."""

    def __init__(
        self,
        profiles: ProfileRepository,
        crm: CrmRepository,
        documents: DocumentStore,
        tasks: TaskRepository,
    ) -> None:
        self.profiles = profiles
        self.crm = crm
        self.documents = documents
        self.tasks = tasks

    # -- proposition commerciale -----------------------------------------

    def commercial_proposal(
        self,
        client: str,
        subject: str,
        items: list[dict[str, Any]] | None = None,
        context: str = "",
        amount: float | None = None,
        currency: str = "XOF",
        validity_days: int = 30,
        project: str | None = None,
        today: date | None = None,
    ) -> dict[str, Any]:
        reference = today or date.today()
        steps: list[StepResult] = []
        business = self.profiles.get_business()

        # 1 — find the client and recall everything already known about them.
        contact = None
        history: dict[str, Any] = {}
        try:
            contact_id = self.crm.resolve_contact(client)
            contact = self.crm.get_contact(contact_id) if contact_id else None
        except AmbiguousMatchError:
            # Creating a second "Horizon" here would quietly split the
            # relationship in two. The caller has to disambiguate first.
            raise
        except CrmError:
            contact = None
        if contact is None:
            contact = self.crm.save_contact(name=client, kind="prospect")
            steps.append(
                StepResult("client", "done", f"Nouveau contact créé : {contact.name}",
                           {"contact_id": contact.contact_id, "created": True})
            )
        else:
            history = self.crm.lookup(contact.name, reference)
            steps.append(
                StepResult("client", "done", f"Client retrouvé : {contact.name}",
                           {"contact_id": contact.contact_id, "created": False})
            )

        previous_deals = [
            deal for deal in self.crm.list_deals() if deal.contact_id == contact.contact_id
        ]
        steps.append(
            StepResult(
                "historique", "done",
                f"{len(previous_deals)} devis antérieur(s), "
                f"{len(history.get('history', []))} échange(s) retrouvé(s)",
                {
                    "previous_deals": [asdict(deal) for deal in previous_deals[:5]],
                    "last_interactions": history.get("history", [])[:5],
                },
            )
        )

        # 2 — price the proposal from the line items when they are given.
        lines = self._normalise_items(items or [])
        computed_total = round(sum(line["total"] for line in lines), 2)
        total = round(float(amount), 2) if amount is not None else computed_total

        # 3 — write the document.
        document = self.documents.create(
            f"Proposition commerciale — {subject}",
            self._proposal_content(
                business_name=business.company_name or "Notre organisation",
                client_name=contact.name,
                client_company=contact.company,
                subject=subject,
                context=context,
                lines=lines,
                total=total,
                currency=currency,
                previous=previous_deals,
                valid_until=(reference + timedelta(days=validity_days)).isoformat(),
                signatory=business.address_as() or business.owner_name,
            ),
        )
        steps.append(
            StepResult("document", "done", f"Document Word généré : {document['title']}",
                       {"document": document})
        )

        # 4 — register the quotation so it can be chased later.
        deal_fields: dict[str, Any] = {
            "title": subject,
            "contact_id": contact.contact_id,
            "amount": total,
            "currency": currency,
            "stage": "brouillon",
            "document_id": document["document_id"],
            "response_due_date": (reference + timedelta(days=validity_days)).isoformat(),
            "notes": context[:2_000],
        }
        if project:
            try:
                deal_fields["project_id"] = self.crm.resolve_project(project)
            except CrmError:
                steps.append(StepResult("projet", "skipped", f"Projet « {project} » introuvable"))
        deal = self.crm.save_deal(**deal_fields)
        steps.append(
            StepResult("devis", "done", f"Devis enregistré ({total:.0f} {currency})",
                       {"deal_id": deal.deal_id})
        )

        # 5 — the follow-up the executive would otherwise forget.
        follow_up = self.tasks.create(
            f"Relancer {contact.name} — {subject}",
            f"Proposition commerciale envoyée le {reference.isoformat()}. "
            f"Montant : {total:.0f} {currency}. Devis {deal.deal_id}.",
            (reference + timedelta(days=PROPOSAL_FOLLOW_UP_DAYS)).isoformat(),
        )
        steps.append(
            StepResult("relance", "done", f"Tâche de relance créée pour le {follow_up.due_date}",
                       {"task_id": follow_up.task_id})
        )

        # 6 — the e-mail, prepared but never sent from here.
        email = {
            "to": contact.email,
            "subject": f"Proposition commerciale — {subject}",
            "body": self._proposal_email(
                contact_name=contact.name,
                subject=subject,
                total=total,
                currency=currency,
                valid_until=(reference + timedelta(days=validity_days)).isoformat(),
                signatory=business.address_as() or business.owner_name,
                company=business.company_name,
            ),
        }
        if contact.email:
            steps.append(StepResult("email", "done", "Brouillon d'e-mail préparé", {"email": email}))
            proposed_action = {
                "tool": "email_send",
                "arguments": email,
                "requires_approval": True,
                "label": f"Envoyer la proposition à {contact.name} ({contact.email})",
            }
        else:
            steps.append(
                StepResult("email", "skipped", f"Aucune adresse e-mail connue pour {contact.name}")
            )
            proposed_action = {
                "tool": "crm_save_contact",
                "arguments": {"contact_id": contact.contact_id, "email": ""},
                "requires_approval": False,
                "label": f"Renseigner l'adresse e-mail de {contact.name} pour permettre l'envoi",
            }

        self.crm.log_interaction(
            summary=f"Proposition commerciale préparée : {subject}",
            kind="note",
            contact_id=contact.contact_id,
            occurred_at=reference.isoformat(),
        )
        return {
            "workflow": "proposition_commerciale",
            "status": "prepared",
            "client": asdict(contact),
            "total": total,
            "currency": currency,
            "document": document,
            "deal_id": deal.deal_id,
            "follow_up_task_id": follow_up.task_id,
            "steps": [asdict(step) for step in steps],
            "proposed_action": proposed_action,
            "note": (
                "Rien n'a été envoyé. L'envoi reste une action soumise à ton approbation."
            ),
        }

    # -- relance client ---------------------------------------------------

    def follow_up(
        self, client: str, tone: str = "courtois", today: date | None = None
    ) -> dict[str, Any]:
        """Prepare a context-aware chase for one client."""
        reference = today or date.today()
        try:
            contact_id = self.crm.resolve_contact(client)
        except AmbiguousMatchError as error:
            return {
                "workflow": "relance", "status": "ambiguous",
                "error": str(error), "candidates": error.candidates,
            }
        except CrmError:
            return {"workflow": "relance", "status": "failed", "error": "client_introuvable"}
        contact = self.crm.get_contact(contact_id) if contact_id else None
        if contact is None:
            return {"workflow": "relance", "status": "failed", "error": "client_introuvable"}

        context = self.crm.lookup(contact.name, reference)
        pending = [
            deal for deal in self.crm.list_deals()
            if deal.contact_id == contact.contact_id and deal.stage in ("envoyé", "relancé")
        ]
        business = self.profiles.get_business()
        subject_line = (
            f"Suivi de notre proposition — {pending[0].title}" if pending
            else f"Prise de nouvelles — {business.company_name or 'EMEFA'}"
        )
        email = {
            "to": contact.email,
            "subject": subject_line,
            "body": self._follow_up_email(contact, pending, business, tone),
        }
        task = self.tasks.create(
            f"Relance {contact.name}",
            f"Relance préparée le {reference.isoformat()}.",
            (reference + timedelta(days=3)).isoformat(),
        )
        return {
            "workflow": "relance",
            "status": "prepared",
            "client": asdict(contact),
            "silent_days": contact.silent_days(reference),
            "pending_deals": [asdict(deal) for deal in pending],
            "history": context.get("history", [])[:5],
            "task_id": task.task_id,
            "proposed_action": {
                "tool": "email_send",
                "arguments": email,
                "requires_approval": True,
                "label": f"Envoyer la relance à {contact.name}"
                         + (f" ({contact.email})" if contact.email else " — adresse manquante"),
            } if contact.email else None,
            "note": "Aucun message n'a été envoyé.",
        }

    # -- rendering --------------------------------------------------------

    @staticmethod
    def _normalise_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for item in items:
            label = str(item.get("label") or item.get("description") or "").strip()[:200]
            if not label:
                continue
            try:
                quantity = float(item.get("quantity", 1) or 1)
                unit_price = float(item.get("unit_price", item.get("price", 0)) or 0)
            except (TypeError, ValueError):
                quantity, unit_price = 1.0, 0.0
            lines.append(
                {
                    "label": label,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total": round(quantity * unit_price, 2),
                }
            )
        return lines

    @staticmethod
    def _proposal_content(
        business_name: str,
        client_name: str,
        client_company: str,
        subject: str,
        context: str,
        lines: list[dict[str, Any]],
        total: float,
        currency: str,
        previous: list[Any],
        valid_until: str,
        signatory: str,
    ) -> str:
        client_label = f"{client_name}" + (f" — {client_company}" if client_company else "")
        content = [
            "## Destinataire",
            f"- Client : {client_label}",
            f"- Émetteur : {business_name}",
            f"- Validité de l'offre : jusqu'au {valid_until}",
            "",
            "## Contexte",
            context or f"Proposition relative à : {subject}.",
        ]
        if previous:
            content += [
                "",
                "## Historique",
                f"Nous avons déjà échangé sur {len(previous)} proposition(s) : "
                + ", ".join(deal.title for deal in previous[:3])
                + ".",
            ]
        content += ["", "## Proposition"]
        if lines:
            content += ["| Prestation | Quantité | Prix unitaire | Total |", "| --- | --- | --- | --- |"]
            for line in lines:
                content.append(
                    f"| {line['label']} | {line['quantity']:g} | "
                    f"{line['unit_price']:,.0f} {currency} | {line['total']:,.0f} {currency} |".replace(",", " ")
                )
            content.append(f"| **Total** |  |  | **{total:,.0f} {currency}** |".replace(",", " "))
        else:
            content.append(f"Montant proposé : {total:,.0f} {currency}.".replace(",", " "))
        content += [
            "",
            "## Prochaines étapes",
            "- Validation de la présente proposition",
            "- Planification de la mise en œuvre",
            "- Point de suivi hebdomadaire",
            "",
            "## Signature",
            signatory or business_name,
        ]
        return "\n".join(content)

    @staticmethod
    def _proposal_email(
        contact_name: str,
        subject: str,
        total: float,
        currency: str,
        valid_until: str,
        signatory: str,
        company: str,
    ) -> str:
        return (
            f"Bonjour {contact_name},\n\n"
            f"Suite à nos échanges, vous trouverez ci-joint notre proposition concernant "
            f"{subject}.\n\n"
            f"Montant proposé : {total:,.0f} {currency}. Offre valable jusqu'au {valid_until}.\n\n".replace(",", " ")
            + "Je reste disponible pour en discuter et ajuster ce qui doit l'être.\n\n"
            f"Cordialement,\n{signatory}"
            + (f"\n{company}" if company else "")
        )

    @staticmethod
    def _follow_up_email(contact: Any, pending: list[Any], business: Any, tone: str) -> str:
        opening = "J'espère que vous allez bien."
        if tone == "direct":
            opening = "Je me permets un point rapide."
        if pending:
            middle = (
                f"Je reviens vers vous au sujet de notre proposition « {pending[0].title} », "
                f"transmise le {pending[0].sent_at or 'récemment'}. "
                "Avez-vous eu l'occasion de l'examiner ?"
            )
        else:
            middle = (
                "Cela fait un moment que nous n'avons pas échangé. "
                "Y a-t-il un sujet sur lequel nous pourrions vous être utiles ?"
            )
        return (
            f"Bonjour {contact.name},\n\n{opening}\n\n{middle}\n\n"
            f"Cordialement,\n{business.address_as() or business.owner_name}"
            + (f"\n{business.company_name}" if business.company_name else "")
        )
