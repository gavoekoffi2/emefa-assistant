"""Deterministic plans for the work that recurs.

Preparing a meeting, organising a trip, sending a proposal and following it
up — an assistant does these constantly, and they have the same shape every
time. A template produces the same correct plan every time, costs nothing, and
cannot invent a tool that does not exist.

That is why templates are tried before the model, not as a fallback after it.

Each recipe is a small data structure: how to recognise the intent, the steps,
and what success means for each. Adding one is adding a `Recipe` to the list.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from emefa.domain.agent import ToolShelf
from emefa.domain.missions.planning import Plan, PlanRequest, PlanStep, fill

#: Words that name a subject without identifying it. "ce client" is a question,
#: not an answer, and filling a plan with it would be inventing.
_ANAPHORIC = {
    "ce", "cet", "cette", "ces", "le", "la", "les", "mon", "ma", "mes",
    "notre", "nos", "un", "une", "des", "lui", "elle", "eux",
}

#: Nouns that name a role rather than a party. "avec ce client" identifies
#: nobody, and a plan built on it would be addressed to "client".
_GENERIC_SUBJECTS = {
    "client", "clients", "prospect", "prospects", "fournisseur", "fournisseurs",
    "partenaire", "partenaires", "equipe", "collaborateur", "collaborateurs",
    "collegue", "collegues", "personne", "societe", "entreprise", "boite",
    "dossier", "projet", "reunion", "rendez-vous",
}

_WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}


def _fold(text: str) -> str:
    """Lowercase and strip accents, so "réunion" and "reunion" both match.

    Folded character by character so the result has the same length as the
    input: `extract_subject` matches on the folded text and slices the
    original, which only works if the indices line up.
    """
    return "".join(
        unicodedata.normalize("NFD", character)[0].lower() for character in text
    )


#: A date expression tacked onto a name — "la Clinique du Lac mardi" — is not
#: part of the name. Cut at the first temporal word.
_TEMPORAL_TAIL = re.compile(
    r"\s+(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain|"
    r"apres-demain|aujourd'?hui|(?:la\s+)?semaine\s+prochaine|"
    r"dans\s+\d{1,2}\s+jours?|le\s+\d{1,2}(?:er)?\b|\d{4}-\d{2}-\d{2})\b"
)

#: An amount tacked onto a name — "pour Horizon SARL de 1 200 000 FCFA" — is
#: not part of the name either.
_AMOUNT_TAIL = re.compile(r"\s+(?:de|a|au)\s+\d")


def extract_subject(goal: str) -> str:
    """Pull the named party out of a request, or return "" when there is none.

    "une proposition pour la Clinique du Lac" gives the clinic. "une réunion
    avec ce client" gives nothing, deliberately: the plan must then carry the
    question rather than a placeholder the user never answered.
    """
    folded = _fold(goal)
    match = re.search(
        r"\b(?:a destination de|au profit de|pour|avec|chez|a|au|aux)\s+(.{2,60})",
        folded,
    )
    if match is None:
        return ""
    # Slice the original text at the folded match position: accents belong in
    # the client's name, they just must not block the match.
    start = match.start(1)
    candidate = goal[start : start + len(match.group(1))]

    candidate = re.split(r"[,.;]| et | puis | avant | afin ", candidate)[0]
    for pattern in (_TEMPORAL_TAIL, _AMOUNT_TAIL):
        tail = pattern.search(_fold(candidate))
        if tail is not None:
            candidate = candidate[: tail.start()]

    words = candidate.split()
    while words and _fold(words[0]) in _ANAPHORIC:
        words.pop(0)
    subject = " ".join(words).strip(" '\"")

    # What is left must name someone. A role noun ("client"), an article, or
    # two characters is a question, not an answer — and the plan must carry
    # the question rather than address a document to "client".
    folded_subject = _fold(subject)
    if len(subject) <= 2 or folded_subject in _ANAPHORIC or folded_subject in _GENERIC_SUBJECTS:
        return ""
    return subject


def resolve_date(goal: str, today: date | None = None) -> str:
    """Read a French date expression out of a request.

    Deterministic on purpose: "vendredi" is not a judgement call, and paying a
    model to resolve it would be absurd. Returns "" when nothing is said, so
    the caller decides the default rather than inheriting a guess.
    """
    reference = today or date.today()
    folded = _fold(goal)

    explicit = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", goal)
    if explicit:
        return explicit.group(1)

    in_days = re.search(r"\bdans\s+(\d{1,2})\s+jours?\b", folded)
    if in_days:
        return (reference + timedelta(days=int(in_days.group(1)))).isoformat()

    if re.search(r"\baujourd'?hui\b", folded):
        return reference.isoformat()
    if re.search(r"\bdemain\b", folded):
        return (reference + timedelta(days=1)).isoformat()
    if re.search(r"\bapres-demain\b", folded):
        return (reference + timedelta(days=2)).isoformat()

    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", folded):
            ahead = (index - reference.weekday()) % 7
            # "vendredi" said on a Friday means the next one, not today.
            return (reference + timedelta(days=ahead or 7)).isoformat()

    if re.search(r"\b(la\s+)?semaine\s+prochaine\b", folded):
        return (reference + timedelta(days=7)).isoformat()
    return ""


@dataclass(frozen=True, slots=True)
class Recipe:
    name: str
    #: Folded keywords; any one of them present is a match.
    triggers: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    #: What this recipe deliberately does not do. Shown to the user.
    notes: tuple[str, ...] = ()
    #: Keywords that must also be present. Used to separate "proposal" from
    #: "proposal and follow-up".
    requires_all: tuple[str, ...] = ()
    extras: dict[str, str] = field(default_factory=dict)

    def matches(self, folded_goal: str) -> bool:
        if not any(trigger in folded_goal for trigger in self.triggers):
            return False
        return all(word in folded_goal for word in self.requires_all)


MEETING = Recipe(
    name="preparation-reunion",
    triggers=("reunion", "rendez-vous", "rdv", "meeting", "entretien"),
    steps=(
        PlanStep(
            description="Rassembler ce que je sais déjà de {sujet}",
            tool="recall",
            arguments={"query": "{sujet}"},
            success_criteria="Les souvenirs liés à {sujet} sont retrouvés, ou leur absence est constatée explicitement.",
        ),
        PlanStep(
            description="Relire l'état commercial en cours",
            tool="list_pipeline",
            arguments={},
            success_criteria="Le pipeline est relu et les opportunités liées identifiées.",
        ),
        PlanStep(
            description="Rédiger l'ordre du jour de la réunion avec {sujet}",
            tool="document_create",
            arguments={
                "title": "Ordre du jour — {sujet}",
                "content": (
                    "Réunion avec {sujet}\n\n"
                    "1. Objectif de la rencontre\n"
                    "2. Points à aborder\n"
                    "3. Décisions attendues\n"
                    "4. Prochaines étapes et responsables\n"
                ),
            },
            success_criteria="Un document d'ordre du jour existe et peut être relu depuis le stockage.",
        ),
        PlanStep(
            description="Poser la préparation comme tâche datée",
            tool="create_task",
            arguments={
                "title": "Préparer la réunion avec {sujet}",
                "due_date": "{date}",
            },
            success_criteria="Une tâche datée existe et apparaît dans les tâches ouvertes.",
        ),
    ),
    notes=(
        "Je ne peux pas encore poser l'invitation dans un agenda : aucun agenda "
        "n'est connecté à cette installation.",
    ),
)

TRAVEL = Recipe(
    name="organisation-voyage",
    triggers=("voyage", "deplacement", "mission a ", "billet", "sejour"),
    steps=(
        PlanStep(
            description="Établir la feuille de route pour {sujet}",
            tool="document_create",
            arguments={
                "title": "Feuille de route — {sujet}",
                "content": (
                    "Déplacement : {sujet}\n"
                    "Date cible : {date}\n\n"
                    "Transport :\nHébergement :\nFormalités :\n"
                    "Rendez-vous sur place :\nBudget :\n"
                ),
            },
            success_criteria="Une feuille de route existe et peut être relue depuis le stockage.",
        ),
        PlanStep(
            description="Réserver le transport",
            tool="create_task",
            arguments={"title": "Réserver le transport pour {sujet}", "due_date": "{date}"},
            success_criteria="La tâche de réservation existe et est datée.",
        ),
        PlanStep(
            description="Réserver l'hébergement",
            tool="create_task",
            arguments={"title": "Réserver l'hébergement à {sujet}", "due_date": "{date}"},
            success_criteria="La tâche d'hébergement existe et est datée.",
        ),
        PlanStep(
            description="Vérifier les formalités d'entrée",
            tool="create_task",
            arguments={
                "title": "Vérifier visa, passeport et vaccins pour {sujet}",
                "due_date": "{date}",
            },
            success_criteria="La tâche de formalités existe et est datée.",
        ),
    ),
    notes=(
        "Je prépare et je suis le déplacement ; je ne réserve rien moi-même — "
        "aucun outil de réservation n'est connecté.",
    ),
)

PROPOSAL = Recipe(
    name="proposition-et-relance",
    triggers=("proposition", "devis", "offre commerciale", "propal"),
    steps=(
        PlanStep(
            description="Relire ce que je sais de {sujet} et de notre offre",
            tool="recall",
            arguments={"query": "{sujet}"},
            success_criteria="Le contexte connu sur {sujet} est retrouvé, ou son absence est constatée.",
        ),
        PlanStep(
            description="Relire l'offre et la cible de l'entreprise",
            tool="get_profiles",
            arguments={},
            success_criteria="Le profil professionnel est relu et sert de base à la proposition.",
        ),
        PlanStep(
            description="Rédiger la proposition commerciale pour {sujet}",
            tool="document_create",
            arguments={
                "title": "Proposition commerciale — {sujet}",
                "content": (
                    "Proposition commerciale\n"
                    "Destinataire : {sujet}\n\n"
                    "1. Contexte et besoin\n"
                    "2. Approche proposée\n"
                    "3. Livrables\n"
                    "4. Calendrier\n"
                    "5. Conditions financières\n"
                    "6. Validité de l'offre\n"
                ),
            },
            success_criteria="La proposition existe comme document et peut être relue depuis le stockage.",
        ),
        PlanStep(
            description="Programmer la relance",
            tool="create_task",
            arguments={"title": "Relancer {sujet} sur la proposition", "due_date": "{date}"},
            success_criteria="Une tâche de relance datée existe et apparaît dans les tâches ouvertes.",
        ),
    ),
    notes=(
        "Les montants et délais sont laissés en blanc : je n'invente pas de "
        "chiffres. Dites-les-moi et je complète le document.",
        "Pour rattacher la relance au pipeline commercial, précisez le prospect "
        "concerné.",
    ),
)

FOLLOW_UP = Recipe(
    name="relance-simple",
    triggers=("relance", "relancer", "recontacter"),
    steps=(
        PlanStep(
            description="Retrouver l'historique avec {sujet}",
            tool="recall",
            arguments={"query": "{sujet}"},
            success_criteria="L'historique connu est retrouvé, ou son absence est constatée.",
        ),
        PlanStep(
            description="Programmer la relance",
            tool="create_task",
            arguments={"title": "Relancer {sujet}", "due_date": "{date}"},
            success_criteria="Une tâche de relance datée existe et apparaît dans les tâches ouvertes.",
        ),
    ),
)

#: Order matters: the more specific recipe wins. A request mentioning both a
#: proposal and a follow-up is a proposal mission, not two.
RECIPES: tuple[Recipe, ...] = (PROPOSAL, MEETING, TRAVEL, FOLLOW_UP)

#: How far ahead an undated action is placed. Near enough to stay real, far
#: enough not to be due the moment it is created.
DEFAULT_HORIZON_DAYS = 3


class TemplatePlanner:
    """First strategy in the chain. Deterministic, free, unable to hallucinate."""

    name = "template"

    def __init__(self, recipes: Sequence[Recipe] = RECIPES, today: date | None = None) -> None:
        self.recipes = list(recipes)
        self.today = today

    async def plan(self, request: PlanRequest, tools: ToolShelf) -> Plan | None:
        folded = _fold(request.goal)
        recipe = next((item for item in self.recipes if item.matches(folded)), None)
        if recipe is None:
            return None

        reference = self.today or date.today()
        context = dict(request.context)
        context.setdefault("sujet", extract_subject(request.goal))
        context.setdefault(
            "date",
            resolve_date(request.goal, reference)
            or (reference + timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat(),
        )
        # An empty subject must stay a placeholder so validation turns it into
        # a question. Filling it with "" would silently produce "Réunion avec ".
        context = {key: value for key, value in context.items() if value}

        steps = tuple(
            PlanStep(
                description=fill(step.description, context),
                tool=step.tool,
                arguments={
                    key: fill(value, context) if isinstance(value, str) else value
                    for key, value in step.arguments.items()
                },
                success_criteria=fill(step.success_criteria, context),
            )
            for step in recipe.steps
        )
        return Plan(
            goal=request.goal,
            steps=steps,
            strategy=f"{self.name}:{recipe.name}",
            notes=recipe.notes,
        )
