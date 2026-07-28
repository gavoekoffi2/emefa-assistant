"""Guards on the governed tool shelf itself.

The shelf is the assistant's whole vocabulary. It has grown to ~44 skills, and
every one of them is sent to the model on **every turn** — so its quality and
its size are both product concerns (CLAUDE.md §15 cost, §18 skills, §37
evaluation).

These checks are deterministic and need no provider. Selection *accuracy*
cannot be measured without a model; that lives in ``evals/tool_selection.py``,
whose cases are validated here so they cannot silently reference a tool that no
longer exists.
"""

import json

import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.policy import ActionRisk, Decision, decide
from emefa.main import create_app
from evals.tool_selection import CASES

#: Ceiling on the tool payload sent with every request, in characters.
#: Measured at 28.6k (~8.2k tokens) for 44 skills on 2026-07-28. This is a
#: budget, not a target: crossing it should force a conversation about skill
#: routing rather than being absorbed silently into every request's cost.
MAX_SCHEMA_CHARS = 34_000


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="ok")


@pytest.fixture
def shelf(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "shelf.db"), brain=Brain())
    return app.state.agent.tools


def test_every_skill_is_distinctly_and_usefully_described(shelf):
    tools = shelf.describe()
    assert len(tools) > 30, "the full shelf should be assembled in the default app"

    names = [tool["name"] for tool in tools]
    assert len(names) == len(set(names)), "duplicate tool names confuse selection"

    descriptions = []
    for tool in tools:
        description = tool["description"].strip()
        # A one-line description is what the model routes on; too short is a
        # selection bug waiting to happen.
        assert len(description) >= 60, f"{tool['name']} is under-described"
        assert description[0].isupper(), f"{tool['name']} description should read as prose"
        descriptions.append(description)
    assert len(descriptions) == len(set(descriptions)), "two skills claim the same purpose"


def test_parameter_schemas_are_well_formed(shelf):
    for tool in shelf.describe():
        parameters = tool["parameters"]
        if parameters is None:
            continue  # a no-argument read
        assert parameters["type"] == "object", tool["name"]
        assert isinstance(parameters["properties"], dict), tool["name"]
        # An open schema lets a model invent arguments the handler ignores.
        assert parameters.get("additionalProperties") is False, tool["name"]
        for field, spec in parameters["properties"].items():
            assert "type" in spec, f"{tool['name']}.{field} has no type"
        for required in parameters.get("required", []):
            assert required in parameters["properties"], f"{tool['name']} requires {required}"


def test_consequential_skills_are_gated_by_the_risk_policy(shelf):
    """Anything that leaves the machine or destroys data must ask first."""
    decisions = {
        tool["name"]: decide(ActionRisk(tool["risk"])) for tool in shelf.describe()
    }
    for name in ("email_send",):
        if name in decisions:
            assert decisions[name] is Decision.ASK, f"{name} must require approval"
    for name in ("reset_business_profile", "forget_memory", "document_edit",
                 "agenda_cancel_event"):
        assert decisions[name] is Decision.ASK, f"{name} destroys data without asking"
    # Reads never stop the conversation for approval.
    for name in ("crm_overview", "crm_lookup", "agenda_view", "get_daily_brief",
                 "get_evening_report", "onboarding_plan"):
        assert decisions[name] is Decision.RUN, f"{name} should not need approval"


def test_the_shelf_stays_within_its_per_request_budget(shelf):
    payload = json.dumps(shelf.describe(), ensure_ascii=False)
    assert len(payload) <= MAX_SCHEMA_CHARS, (
        f"the tool schema now costs {len(payload):,} characters on every request "
        f"(budget {MAX_SCHEMA_CHARS:,}). Before raising this ceiling, consider skill "
        "routing — see docs/adr/ADR-002-executive-domain-model.md."
    )


def test_evaluation_cases_reference_skills_that_exist(shelf):
    """An eval suite that drifts from the shelf measures nothing."""
    available = {tool["name"] for tool in shelf.describe()}
    for case in CASES:
        for expected in case.accepted:
            assert expected in available, (
                f"eval case « {case.utterance} » expects the missing skill {expected}"
            )
    # Every executive question in the mission brief has at least one case.
    utterances = " ".join(case.utterance.lower() for case in CASES)
    for topic in ("relancer", "devis", "contrats", "bloqués", "où en est"):
        assert topic in utterances, f"no evaluation case covers « {topic} »"


@pytest.mark.asyncio
async def test_the_evaluation_harness_scores_correctly(tmp_path):
    """The harness must itself be trustworthy before it can judge a model."""
    from emefa.domain.agent import RequestedAction
    from evals.tool_selection import run

    class AlwaysOverview:
        """Answers every utterance with crm_overview — right sometimes, wrong often."""

        async def think(self, history, tools):
            return AgentStep(action=RequestedAction(name="crm_overview"))

    report = await run(tmp_path / "eval.db", brain=AlwaysOverview())

    assert report["cases"] == len(CASES)
    expected_hits = sum(1 for case in CASES if "crm_overview" in case.accepted)
    assert report["passed"] == expected_hits
    assert report["accuracy"] == round(expected_hits / len(CASES), 3)
    # The four executive questions are exactly the ones this stub gets right.
    correct = {item["utterance"] for item in report["results"] if item["ok"]}
    assert "Quels clients dois-je relancer ?" in correct
    assert "Prépare une proposition commerciale pour Ama." not in correct

    # A case expecting *no* tool passes only when the brain answers in prose.
    class Answers:
        async def think(self, history, tools):
            return AgentStep(answer="Je ne dispose pas d'outil de découverte de prospects.")

    honest = await run(tmp_path / "eval2.db", brain=Answers())
    no_tool_case = next(item for item in honest["results"] if not item["accepted"])
    assert no_tool_case["ok"] is True
