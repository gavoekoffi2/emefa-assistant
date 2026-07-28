"""Turning a sentence into a plan.

"Prépare une réunion avec ce client" is not a tool call. It is an outcome, and
between the outcome and the tools sits a decision: what has to happen, in what
order, and how each part will be known to have worked.

The planner is a **chain of strategies**, tried in order, first answer wins:

    templates → model → nothing

That order is the design, not an optimisation. Recurring intents — preparing a
meeting, organising a trip, sending a proposal and following up — are the same
shape every time. A template produces the same correct plan every time, costs
nothing, and cannot hallucinate a tool. A model is for everything else, and it
is validated against the real tool shelf before anything is stored.

Adding a strategy means adding an entry to the chain. Nothing else in the
mission engine knows how a plan was produced.

Two rules the whole module exists to enforce:

* **Every step carries a success criterion**, written when the step is
  invented. A step without one can only ever be verified as "the call
  returned something", which is the failure CLAUDE.md §25 is about.
* **A plan may be incomplete, and must say so.** "Prépare une réunion avec ce
  client" does not say which client. The honest output is a plan plus the
  question, not a plan with a guessed answer in it. `missing_information` is
  how EMEFA asks instead of inventing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from emefa.domain.agent import ToolShelf
from emefa.domain.missions.schemas import MAX_STEPS

#: Placeholders a template leaves for the caller to fill: `{client}`.
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True, slots=True)
class PlanStep:
    description: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    #: What "this worked" means for this step, in the user's terms. Stored on
    #: the mission and shown; used by verification.
    success_criteria: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "tool": self.tool,
            "arguments": self.arguments,
            "success_criteria": self.success_criteria,
        }


@dataclass(frozen=True, slots=True)
class Plan:
    goal: str
    steps: tuple[PlanStep, ...] = ()
    #: Which strategy produced this, so a report can say so.
    strategy: str = "none"
    #: What EMEFA needs to ask before this plan is executable.
    missing_information: tuple[str, ...] = ()
    #: Things she deliberately did not include, and why. Honesty about the
    #: edges of what she can actually do.
    notes: tuple[str, ...] = ()

    @property
    def executable(self) -> bool:
        return bool(self.steps) and not self.missing_information

    def summary(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "strategy": self.strategy,
            "executable": self.executable,
            "missing_information": list(self.missing_information),
            "notes": list(self.notes),
            "steps": [step.summary() for step in self.steps],
        }


@dataclass(frozen=True, slots=True)
class PlanRequest:
    """What the planner is given: the sentence, plus anything already known."""

    goal: str
    #: Values that can fill template placeholders — a client name pulled from
    #: the conversation, a date, a project.
    context: dict[str, str] = field(default_factory=dict)


class PlanningStrategy(Protocol):
    name: str

    async def plan(self, request: PlanRequest, tools: ToolShelf) -> Plan | None: ...


# ── validation ────────────────────────────────────────────────────────────


def validate(plan: Plan, tools: ToolShelf) -> Plan:
    """Make a plan safe to store.

    Anything a strategy produced is a proposal, including a template's — a
    template can name a tool that a given deployment does not ship, because
    the shelf depends on what is configured. Steps that cannot run are dropped
    with a note rather than left to fail halfway through execution.
    """
    kept: list[PlanStep] = []
    missing = list(plan.missing_information)
    notes = list(plan.notes)

    for step in plan.steps[:MAX_STEPS]:
        if tools.get(step.tool) is None:
            notes.append(
                f"Étape ignorée — EMEFA ne dispose pas de l'outil « {step.tool} » "
                "dans cette installation."
            )
            continue
        unresolved = _unresolved(step.arguments)
        if unresolved:
            for name in unresolved:
                question = _question_for(name)
                if question not in missing:
                    missing.append(question)
            notes.append(f"Étape « {step.description} » en attente d'une précision.")
            continue
        kept.append(
            PlanStep(
                description=step.description.strip()[:500],
                tool=step.tool,
                arguments=step.arguments,
                success_criteria=(step.success_criteria or _default_criteria(step)).strip()[:300],
            )
        )

    return Plan(
        goal=plan.goal,
        steps=tuple(kept),
        strategy=plan.strategy,
        missing_information=tuple(dict.fromkeys(missing)),
        notes=tuple(dict.fromkeys(notes)),
    )


def _unresolved(arguments: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for value in arguments.values():
        if isinstance(value, str):
            found.extend(PLACEHOLDER.findall(value))
    return found


_QUESTIONS = {
    "client": "De quel client s'agit-il ?",
    "prospect": "De quel prospect s'agit-il ?",
    "projet": "De quel projet s'agit-il ?",
    "destination": "Quelle est la destination ?",
    "date": "Pour quelle date ?",
    "sujet": "Avec qui, ou pour qui exactement ?",
    "montant": "Quel montant faut-il indiquer ?",
}


def _question_for(name: str) -> str:
    return _QUESTIONS.get(name, f"Quelle valeur pour « {name} » ?")


def _default_criteria(step: PlanStep) -> str:
    """A criterion is always better than none, but a generic one is honest
    about being generic."""
    return f"L'outil {step.tool} a bien produit son effet (vérification structurelle)."


def fill(template: str, context: dict[str, str]) -> str:
    """Substitute known context into a template string, leaving unknown
    placeholders in place so validation can turn them into questions."""
    def replace(match: re.Match[str]) -> str:
        return context.get(match.group(1), match.group(0))

    return PLACEHOLDER.sub(replace, template)


# ── the chain ─────────────────────────────────────────────────────────────


#: Tools a plan may never contain. `plan_mission` is the obvious one: a plan
#: whose first step is "make a plan" is a loop, and a model handed the tool
#: will reach for it. Excluding it from the catalogue removes the hazard
#: structurally rather than asking a prompt not to.
RESERVED_TOOLS = frozenset({"plan_mission", "advance_mission", "mission_status"})


class CompositePlanner:
    """Tries each strategy in turn and returns the first usable plan."""

    def __init__(
        self,
        strategies: Sequence[PlanningStrategy],
        tools: ToolShelf,
        reserved: frozenset[str] = RESERVED_TOOLS,
    ) -> None:
        self.strategies = list(strategies)
        self.tools = tools
        self.reserved = reserved

    def _plannable(self) -> ToolShelf:
        """The shelf as strategies see it: everything a plan may legitimately
        use, and nothing that would let a plan plan."""
        visible = ToolShelf()
        for name, tool in self.tools._tools.items():  # noqa: SLF001 — same package concern
            if name not in self.reserved:
                visible.add(tool)
        return visible

    async def plan(self, goal: str, context: dict[str, str] | None = None) -> Plan:
        request = PlanRequest(goal=goal.strip(), context=dict(context or {}))
        plannable = self._plannable()
        for strategy in self.strategies:
            try:
                candidate = await strategy.plan(request, plannable)
            except Exception as error:
                # A failing strategy falls through to the next one. Planning
                # that dies because one backend is down is worse than a
                # simpler plan.
                candidate = None
                _ = error
            if candidate is None:
                continue
            validated = validate(candidate, plannable)
            if validated.steps or validated.missing_information:
                return validated
        return Plan(
            goal=goal.strip(),
            strategy="none",
            notes=(
                "Je n'ai pas su découper cette demande en étapes réalisables avec "
                "mes outils actuels. Dites-moi ce que vous attendez concrètement "
                "et je m'en occupe.",
            ),
        )
