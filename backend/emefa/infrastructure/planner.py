"""Model-backed planning, for the requests no template covers.

Last strategy in the chain, and the only one that can be wrong in interesting
ways. Three constraints shape it:

* **The model may only name tools that exist.** The shelf is listed in the
  prompt, and every returned step is validated against the real shelf
  afterwards anyway — a prompt is a request, not a guarantee.
* **The model must be allowed to say it does not know.** A planner that
  always produces a plan produces a wrong one whenever the request is
  ambiguous, and "prépare une réunion avec ce client" is ambiguous. The
  response schema carries `missing_information` for exactly that.
* **It plans; it does not act.** No tool is executed here. The output is a
  proposal that the mission engine will run later, step by step, under the
  risk policy.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from emefa.domain.agent import ToolShelf
from emefa.domain.missions.planning import Plan, PlanRequest, PlanStep
from emefa.domain.missions.schemas import MAX_STEPS

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_TOKENS = 1_200

PLANNER_PROMPT = """\
Tu es le planificateur d'EMEFA, une assistante personnelle professionnelle.

On te donne un objectif exprimé par l'utilisateur. Tu le découpes en étapes \
concrètes, exécutables avec les outils listés ci-dessous, et rien d'autre.

Réponds en JSON strict :
{"steps": [{"description", "tool", "arguments", "success_criteria"}], \
"missing_information": [], "notes": []}

Règles :
- `tool` doit être exactement l'un des noms d'outils fournis. N'invente jamais \
un outil.
- `arguments` doit respecter le schéma de l'outil choisi.
- `success_criteria` décrit en une phrase ce qui prouve que l'étape a réussi, \
de façon vérifiable (« le document existe et peut être relu »), pas « l'étape \
est faite ».
- Maximum %(max_steps)d étapes. Moins vaut mieux que plus.
- Si l'objectif ne précise pas une information indispensable (quel client, \
quelle date, quel montant), NE DEVINE PAS : mets la question dans \
`missing_information` et n'invente pas de valeur.
- Si une partie de la demande dépasse ce que les outils permettent, dis-le \
dans `notes` au lieu de faire semblant.
- N'inclus jamais d'étape qui enverrait un message, publierait ou paierait \
sans que l'utilisateur l'ait explicitement demandé.

Outils disponibles :
%(tools)s
"""


class LLMPlanner:
    name = "model"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        on_usage: Any = None,
    ) -> None:
        self.model = model
        self.on_usage = on_usage
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
            transport=transport,
        )

    async def plan(self, request: PlanRequest, tools: ToolShelf) -> Plan | None:
        catalogue = "\n".join(
            f"- {tool['name']} ({tool['risk']}) : {tool['description']}"
            + (
                f"\n  arguments : {json.dumps(tool['parameters'], ensure_ascii=False)}"
                if tool.get("parameters")
                else ""
            )
            for tool in tools.describe()
        )
        system = PLANNER_PROMPT % {"max_steps": MAX_STEPS, "tools": catalogue}

        context = ""
        if request.context:
            known = ", ".join(f"{key} = {value}" for key, value in request.context.items())
            context = f"\nÉléments déjà connus : {known}."

        response = await self.client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"Objectif de l'utilisateur :\n{request.goal}{context}",
                    },
                ],
                "temperature": 0.1,
                "max_tokens": _MAX_TOKENS,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage")
        if self.on_usage is not None and isinstance(usage, dict):
            self.on_usage(
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
            )
        content = payload["choices"][0]["message"].get("content") or ""
        return parse_plan(request.goal, content, strategy=self.name)

    async def close(self) -> None:
        await self.client.aclose()


def parse_plan(goal: str, payload: str | dict[str, Any], strategy: str = "model") -> Plan | None:
    """Read a model's planning response.

    Returns None — not an empty plan — when the response is unusable, so the
    composite falls through to the next strategy instead of storing a plan
    that says nothing.
    """
    document = payload
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            text = text.strip("`")
            _, _, text = text.partition("\n")
        try:
            document = json.loads(text)
        except (ValueError, TypeError):
            return None
    if not isinstance(document, dict):
        return None

    raw_steps = document.get("steps")
    steps: list[PlanStep] = []
    if isinstance(raw_steps, list):
        for item in raw_steps[:MAX_STEPS]:
            if not isinstance(item, dict):
                continue
            tool = str(item.get("tool", "")).strip()
            description = " ".join(str(item.get("description", "")).split()).strip()
            if not tool or len(description) < 3:
                continue
            arguments = item.get("arguments")
            steps.append(
                PlanStep(
                    description=description[:500],
                    tool=tool,
                    arguments=arguments if isinstance(arguments, dict) else {},
                    success_criteria=" ".join(
                        str(item.get("success_criteria", "")).split()
                    )[:300],
                )
            )

    missing = _strings(document.get("missing_information"))
    notes = _strings(document.get("notes"))
    if not steps and not missing:
        return None
    return Plan(
        goal=goal,
        steps=tuple(steps),
        strategy=strategy,
        missing_information=missing,
        notes=notes,
    )


def _strings(value: Any, limit: int = 6) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        " ".join(str(item).split())[:300]
        for item in value[:limit]
        if isinstance(item, str) and item.strip()
    )
