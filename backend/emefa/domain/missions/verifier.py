"""Did the step actually do what it claimed?

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

CLAUDE.md §25 forbids reporting success because a tool returned *something*.
Verification is what makes the difference between "the call did not raise" and
"the work exists", and it comes in three kinds, in increasing cost and
decreasing certainty:

1. **Structural** — the result has the shape a success has, and does not
   carry an error. Cheap, always run, catches the common case of a tool
   returning `{"error": ...}` with a 200.
2. **Deterministic** — read the world back and check. Did the document exist
   afterwards? Is the task actually closed? This is the only kind that proves
   anything, and it is why verifiers are registered per tool rather than
   inferred.
3. **Semantic** — ask a model whether the output satisfies the intent. Useful
   for prose, expensive, and itself unreliable, so it is an *injected*
   dependency here, not a default: a mission with no semantic verifier
   configured runs on the first two and says so, rather than pretending.

A step nobody can verify is `unverified`, never `verified`. That distinction
is the whole reason this module exists.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

#: A deterministic check: given the step's arguments and its result, is the
#: effect really there? Returns (ok, explanation).
DeterministicCheck = Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reason: str
    #: Which kind of check reached this conclusion, so a report can say
    #: "confirmed by reading it back" rather than an unqualified "done".
    method: str = "structural"


def structural(result: Mapping[str, Any] | None) -> Verdict:
    if result is None:
        return Verdict(False, "l'outil n'a rien renvoyé", "structural")
    error = result.get("error")
    if error:
        return Verdict(False, f"l'outil a renvoyé une erreur : {error}", "structural")
    if not result:
        return Verdict(False, "réponse vide", "structural")
    return Verdict(True, "réponse structurellement valide", "structural")


class StepVerifier:
    """Runs the checks a step is entitled to, cheapest first."""

    def __init__(
        self,
        deterministic: Mapping[str, DeterministicCheck] | None = None,
        semantic: Callable[[str, Mapping[str, Any]], tuple[bool, str]] | None = None,
    ) -> None:
        self.deterministic = dict(deterministic or {})
        self.semantic = semantic

    def verify(
        self,
        tool_name: str,
        description: str,
        arguments: Mapping[str, Any],
        result: Mapping[str, Any] | None,
    ) -> Verdict:
        structure = structural(result)
        if not structure.ok:
            return structure

        check = self.deterministic.get(tool_name)
        if check is not None:
            try:
                ok, reason = check(arguments, result or {})
            except Exception as error:
                # A verifier that crashes must not be read as a pass. The
                # honest outcome is "could not confirm".
                return Verdict(False, f"vérification impossible : {type(error).__name__}", "deterministic")
            return Verdict(ok, reason, "deterministic")

        if self.semantic is not None:
            try:
                ok, reason = self.semantic(description, result or {})
            except Exception as error:
                return Verdict(False, f"vérification impossible : {type(error).__name__}", "semantic")
            return Verdict(ok, reason, "semantic")

        # Nothing beyond structure was available. Passing here is a judgement
        # call: the alternative is marking every step of every mission
        # unverified, which would make the distinction meaningless. The method
        # is recorded so the report never overstates what was checked.
        return structure


def default_checks(documents=None, tasks=None) -> dict[str, DeterministicCheck]:
    """Deterministic checks for the tools whose effects EMEFA can read back."""
    checks: dict[str, DeterministicCheck] = {}

    if documents is not None:
        def document_exists(_arguments, result):
            document_id = (result.get("document") or {}).get("document_id")
            if not document_id:
                return False, "aucun identifiant de document renvoyé"
            found = documents.get(document_id)
            return (
                (True, "document relu depuis le stockage")
                if found is not None
                else (False, "le document annoncé est introuvable")
            )

        checks["document_create"] = document_exists

    if tasks is not None:
        def task_created(_arguments, result):
            task_id = (result.get("task") or {}).get("task_id")
            if not task_id:
                return False, "aucun identifiant de tâche renvoyé"
            return (
                (True, "tâche relue depuis le stockage")
                if tasks.get(task_id) is not None
                else (False, "la tâche annoncée est introuvable")
            )

        def task_completed(arguments, _result):
            task = tasks.get(str(arguments.get("task_id", "")))
            if task is None:
                return False, "tâche introuvable"
            return (
                (task.status == "done", f"statut relu : {task.status}")
                if hasattr(task, "status")
                else (True, "tâche relue")
            )

        checks["create_task"] = task_created
        checks["complete_task"] = task_completed

    return checks
