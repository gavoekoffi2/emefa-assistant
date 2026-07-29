"""Skill manifests, compatible with the jarvis-skills standard (schema 1.0).

Manifest format follows `github.com/Grominet95/jarvis-skills` (MIT) so skills
written for that catalogue load here unchanged. EMEFA adds three fields the
standard does not carry, because a hosted multi-tenant product needs them and
a single-user desktop app does not:

* `risk` — which action class the skill's tools fall under, so the existing
  RUN / ASK / BLOCK policy applies to a contributed skill exactly as it does
  to a built-in one;
* `prompt` — the system prompt, read out of the contribution rather than
  imported from it (see `loader`);
* `source` — where the manifest came from, for audit.

Validation is strict on the fields EMEFA acts on (name, type, tools, risk) and
forgiving on the rest: a catalogue entry with a malformed `requires_apps`
should degrade to "no app requirements", not make the whole catalogue
unloadable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from emefa.domain.policy import ActionRisk

SCHEMA_VERSION = "1.0"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SUPPORTED_TYPES = ("conversational",)

MAX_PROMPT_CHARS = 6_000
MAX_CAPABILITIES = 6


class InvalidManifestError(ValueError):
    """The manifest cannot be trusted enough to load."""


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    version: str
    author: str
    description: str
    prompt: str
    tags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    requires_env: tuple[str, ...] = ()
    requires_tools: tuple[str, ...] = ()
    requires_oauth: tuple[str, ...] = ()
    requires_apps: tuple[str, ...] = ()
    #: Highest action class the skill's declared tools may reach. Defaults to
    #: read-only: a contributed skill earns nothing by existing.
    risk: ActionRisk = ActionRisk.PERSONAL_READ
    type: str = "conversational"
    source: str = "catalogue"
    permissions: tuple[str, ...] = field(default=())

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "requires_env": list(self.requires_env),
            "requires_tools": list(self.requires_tools),
            "requires_oauth": list(self.requires_oauth),
            "requires_apps": list(self.requires_apps),
            "risk": self.risk.value,
            "source": self.source,
        }


def _strings(value: Any, limit: int = 32) -> tuple[str, ...]:
    """Coerce a manifest list field into clean strings.

    `requires_env` accepts both the short form (a bare name) and the enriched
    form (an object with a description), so entries are unwrapped rather than
    dropped.
    """
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value[:limit]:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                result.append(name.strip())
    return tuple(result)


def parse_manifest(
    document: Any, prompt: str, source: str = "catalogue"
) -> SkillManifest:
    if not isinstance(document, dict):
        raise InvalidManifestError("manifest must be a mapping")

    name = str(document.get("name", "")).strip()
    if not NAME_PATTERN.match(name):
        raise InvalidManifestError(f"invalid skill name: {name!r}")

    skill_type = str(document.get("type", "conversational")).strip()
    if skill_type not in SUPPORTED_TYPES:
        # Presets and views are real parts of the upstream standard; EMEFA
        # simply has nowhere to run them yet. Refusing by name is clearer
        # than loading them into a shape they do not fit.
        raise InvalidManifestError(f"unsupported skill type: {skill_type!r}")

    cleaned_prompt = prompt.strip()
    if len(cleaned_prompt) < 20:
        raise InvalidManifestError("skill prompt is missing or too short")

    return SkillManifest(
        name=name,
        version=str(document.get("version", "0.0.0")).strip() or "0.0.0",
        author=str(document.get("author", "")).strip()[:120],
        description=str(document.get("description", "")).strip()[:400],
        prompt=cleaned_prompt[:MAX_PROMPT_CHARS],
        tags=_strings(document.get("tags")),
        capabilities=_strings(document.get("capabilities"))[:MAX_CAPABILITIES],
        requires_env=_strings(document.get("requires_env")),
        requires_tools=_strings(document.get("requires_tools")),
        requires_oauth=_strings(document.get("requires_oauth")),
        requires_apps=_strings(document.get("requires_apps")),
        risk=_risk(document.get("risk")),
        type=skill_type,
        source=source,
        permissions=_strings(document.get("permissions")),
    )


def _risk(value: Any) -> ActionRisk:
    """Unknown or absent risk means read-only, never something looser.

    A contributed manifest asking for a risk class EMEFA does not recognise is
    asking for something it has not defined; granting the default would be a
    privilege it did not earn.
    """
    if isinstance(value, str):
        try:
            return ActionRisk(value.strip().lower())
        except ValueError:
            return ActionRisk.PERSONAL_READ
    return ActionRisk.PERSONAL_READ
