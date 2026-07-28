"""Closed vocabulary for the memory kernel (ADR-003 §3).

Extraction is done by a language model, and a language model left free will
invent a new predicate for every sentence: *aime*, *apprécie*, *a une
préférence pour*. Three predicates, one meaning, no possible match — so a
restated fact becomes a duplicate instead of a reinforcement, and the whole
point of the kernel is lost.

Everything the model may write is therefore enumerated here. Anything outside
the enumeration is coerced to a neutral member rather than rejected: a fact
recorded imprecisely is worth more than a fact dropped.

Categories carry two things the retrieval score needs and that cannot be
inferred from the text: how fast the claim goes stale (`DecayPolicy`) and how
much it matters when it is still fresh (`importance`). A stated business goal
is worth remembering for a year; what the user had for lunch is not.
"""

from __future__ import annotations

from emefa.domain.memory.schemas import DecayPolicy

# Categories inherited from the flat store that preceded the kernel. They stay
# valid inputs forever: existing rows carry them and the public API accepts
# them (`remember(content, category="preference")`).
LEGACY_CATEGORIES: tuple[str, ...] = (
    "fact",
    "preference",
    "relationship",
    "procedure",
    "other",
)

# Categories the extraction pass may assign.
CATEGORIES: dict[str, tuple[DecayPolicy, float]] = {
    # who the user is — does not decay
    "identity": (DecayPolicy.NONE, 0.95),
    "organisation": (DecayPolicy.NONE, 0.90),
    # what the business does — changes, but slowly
    "offer": (DecayPolicy.VERY_SLOW, 0.85),
    "market": (DecayPolicy.SLOW, 0.80),
    "relationship": (DecayPolicy.VERY_SLOW, 0.75),
    # how the user wants to be served
    "preference": (DecayPolicy.SLOW, 0.70),
    "procedure": (DecayPolicy.SLOW, 0.75),
    # what the user is trying to achieve — revisited often
    "goal": (DecayPolicy.MEDIUM, 0.85),
    "constraint": (DecayPolicy.MEDIUM, 0.70),
    "project": (DecayPolicy.MEDIUM, 0.70),
    # dated, perishable
    "commitment": (DecayPolicy.FAST, 0.80),
    "event": (DecayPolicy.FAST, 0.50),
    # what a project is actually made of: what was decided, and what is still
    # wrong. Decisions barely decay — a decision taken a year ago still binds.
    "decision": (DecayPolicy.VERY_SLOW, 0.88),
    "issue": (DecayPolicy.MEDIUM, 0.82),
    "note": (DecayPolicy.MEDIUM, 0.55),
    # unstructured leftovers
    "fact": (DecayPolicy.SLOW, 0.60),
    "other": (DecayPolicy.MEDIUM, 0.50),
}

DEFAULT_CATEGORY = "other"

#: Categories where a new claim *adds* to what is known instead of replacing
#: it. A project has one current objective but many decisions and many open
#: problems; superseding a decision because a later one exists would erase the
#: record of how the project got here, which is the main thing a decision log
#: is for.
ACCUMULATING_CATEGORIES: frozenset[str] = frozenset(
    {"decision", "issue", "event", "note"}
)

# Closed predicate set. French, third person, one meaning each.
PREDICATES: tuple[str, ...] = (
    "s_appelle",
    "occupe_le_role",
    "travaille_pour",
    "est_situe_a",
    "propose",
    "cible",
    "prefere",
    "evite",
    "souhaite",
    "doit",
    "connait",
    "utilise",
    "parle_langue",
    "a_pour_echeance",
    "a_realise",
    "note",
)

#: Predicate used when a claim carries no usable structure — the object then
#: holds the whole sentence. Rendering strips it back out, so a note reads as
#: the plain text the user wrote.
NEUTRAL_PREDICATE = "note"

#: Subject used when a claim is about the user themselves, which is the
#: overwhelming majority.
DEFAULT_SUBJECT = "utilisateur"

# Predicate suggested for each category when extraction gives a category but no
# predicate. Never authoritative — only a better default than "note".
_CATEGORY_PREDICATE: dict[str, str] = {
    "identity": "s_appelle",
    "organisation": "travaille_pour",
    "offer": "propose",
    "market": "cible",
    "relationship": "connait",
    "preference": "prefere",
    "goal": "souhaite",
    "constraint": "doit",
    "commitment": "a_pour_echeance",
    "procedure": "utilise",
    "decision": "a_realise",
    "issue": "doit",
}


def normalise_category(category: str | None) -> str:
    """Coerce any input to a known category. Unknown input becomes `other`."""
    if category is None:
        return DEFAULT_CATEGORY
    cleaned = category.strip().lower()
    return cleaned if cleaned in CATEGORIES else DEFAULT_CATEGORY


def normalise_predicate(predicate: str | None, category: str) -> str:
    """Coerce any input to a known predicate, falling back via the category."""
    if predicate is not None:
        cleaned = predicate.strip().lower().replace(" ", "_").replace("'", "_")
        if cleaned in PREDICATES:
            return cleaned
    return _CATEGORY_PREDICATE.get(category, NEUTRAL_PREDICATE)


def decay_for(category: str) -> DecayPolicy:
    return CATEGORIES[normalise_category(category)][0]


def importance_for(category: str) -> float:
    return CATEGORIES[normalise_category(category)][1]


def normalise_term(term: str) -> str:
    """Matching key for subject/predicate/object: collapsed, trimmed, lowered."""
    return " ".join(term.split()).strip().lower()
