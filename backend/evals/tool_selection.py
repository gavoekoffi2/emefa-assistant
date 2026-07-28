"""Tool-selection evaluation cases.

CLAUDE.md §37 forbids declaring a prompt or routing change "better" on
impression. Selection quality needs a model to measure, so this module holds
the *cases* and a runner; the harness in ``tests/test_tool_shelf.py`` runs the
model-free structural checks on every CI run, and this runner is executed on
demand against a configured provider:

    EMEFA_DEEPSEEK_API_KEY=... python -m evals.tool_selection

Each case is a French utterance an executive would actually produce, with the
tools that would be a correct first move. Several answers are often acceptable
— "what do I have today?" is legitimately either the agenda or the daily brief
— so a case lists every tool that counts as correct rather than pretending
there is one right answer.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.main import create_app


@dataclass(frozen=True, slots=True)
class Case:
    utterance: str
    accepted: tuple[str, ...]
    #: Why this case exists — printed on failure so a regression is readable.
    intent: str


CASES: tuple[Case, ...] = (
    # -- reading the day ---------------------------------------------------
    Case("Qu'est-ce qui mérite mon attention aujourd'hui ?", ("get_daily_brief",),
         "the morning brief is the executive's default question"),
    Case("Fais le point sur ma journée.", ("get_evening_report", "get_daily_brief"),
         "end-of-day review"),
    Case("Qu'est-ce que j'ai comme rendez-vous aujourd'hui ?", ("agenda_view", "get_daily_brief"),
         "the schedule; the brief also opens on it"),
    Case("Prépare ma réunion avec Horizon.", ("agenda_prepare_meeting", "crm_lookup"),
         "meeting preparation walks the relationship"),

    # -- the four executive questions --------------------------------------
    Case("Quels clients dois-je relancer ?", ("crm_overview",),
         "must read the CRM, not improvise"),
    Case("Quels devis attendent une réponse ?", ("crm_overview",), "unanswered quotations"),
    Case("Quels contrats expirent bientôt ?", ("crm_overview",), "expiring contracts"),
    Case("Quels projets sont bloqués ?", ("crm_overview",), "blocked projects"),
    Case("Où en est le projet Refonte digitale ?", ("crm_lookup",),
         "single-entity relational lookup, not the whole overview"),

    # -- capture -----------------------------------------------------------
    Case("J'ai eu Ama au téléphone ce matin, elle veut avancer.",
         ("crm_log_interaction",), "a call must land in the chronology"),
    Case("Note que j'ai rendez-vous jeudi à 10 h avec Ama.", ("agenda_save_event",),
         "an appointment goes to the agenda"),
    Case("Rappelle-moi d'envoyer la facture vendredi.", ("create_task",), "a commitment"),
    Case("Mensah Logistics devient un client, son contact est Ama Mensah.",
         ("crm_save_contact",), "a new relationship"),
    Case("Le projet Refonte est bloqué par la validation des maquettes.",
         ("crm_save_project",), "project state change"),

    # -- production --------------------------------------------------------
    Case("Prépare une proposition commerciale pour Ama.",
         ("workflow_commercial_proposal",),
         "the whole chain, not document_create alone"),
    Case("Relance le client Horizon.", ("workflow_follow_up", "crm_lookup"),
         "the follow-up scenario"),
    Case("Voici mes notes de réunion, fais-en le compte rendu.", ("meeting_capture",),
         "meeting capture, not a bare document"),
    Case("Fais-moi un tableau de budget pour ce projet.", ("spreadsheet_create",),
         "a spreadsheet, not a Word document"),
    Case("Prépare une présentation pour le comité.", ("presentation_create",), "a deck"),
    Case("Rédige une lettre de relance pour ce fournisseur.", ("document_create",),
         "a Word document"),

    # -- memory and identity ----------------------------------------------
    Case("Retiens que je préfère être appelé M. Gava.",
         ("update_business_profile", "remember"), "a durable preference"),
    Case("Mon entreprise s'appelle Horizon SARL.", ("update_business_profile",),
         "business profile, not a loose memory"),
    Case("Qu'est-ce que tu sais de moi ?", ("get_profiles", "list_memories"),
         "the executive inspecting their own data"),

    # -- honesty guard -----------------------------------------------------
    Case("Trouve-moi dix nouveaux prospects correspondant à ma cible.", (),
         "no prospect-discovery tool exists: EMEFA must answer without inventing one"),
)


async def _select(app: Any, utterance: str) -> str | None:
    """Ask the configured brain for its first move; return the tool it picked."""
    engine = app.state.agent
    step: AgentStep = await engine.brain.think(
        [{"role": "user", "content": utterance}], engine.tools.describe()
    )
    return step.action.name if step.action is not None else None


async def run(database_path: Path, brain: Any = None) -> dict[str, Any]:
    """Run every case. ``brain`` is injectable so the harness itself is testable."""
    app = create_app(Settings(database_path=database_path), brain=brain)
    if brain is None and not app.state.brain_configured:
        raise RuntimeError(
            "no LLM provider configured; set EMEFA_DEEPSEEK_API_KEY or EMEFA_OPENROUTER_API_KEY"
        )
    results: list[dict[str, Any]] = []
    for case in CASES:
        try:
            chosen = await _select(app, case.utterance)
        except Exception as error:  # a provider failure is a result, not a crash
            results.append({"utterance": case.utterance, "chosen": None,
                            "ok": False, "error": str(error)[:200], "intent": case.intent})
            continue
        ok = (chosen in case.accepted) if case.accepted else (chosen is None)
        results.append({"utterance": case.utterance, "chosen": chosen,
                        "accepted": list(case.accepted), "ok": ok, "intent": case.intent})
    passed = sum(1 for item in results if item["ok"])
    return {
        "cases": len(CASES),
        "passed": passed,
        "accuracy": round(passed / len(CASES), 3),
        "tool_count": len(app.state.agent.tools.describe()),
        "results": results,
    }


def main() -> None:
    import tempfile

    report = asyncio.run(run(Path(tempfile.mkdtemp()) / "eval.db"))
    for item in report["results"]:
        mark = "ok  " if item["ok"] else "FAIL"
        expected = ", ".join(item.get("accepted") or ["(aucun outil)"])
        print(f"{mark} {item['utterance']}\n     chose: {item['chosen']} | accepted: {expected}")
        if not item["ok"]:
            print(f"     why it matters: {item['intent']}")
    print(json.dumps(
        {k: v for k, v in report.items() if k != "results"}, indent=2, ensure_ascii=False
    ))


if __name__ == "__main__":
    main()
