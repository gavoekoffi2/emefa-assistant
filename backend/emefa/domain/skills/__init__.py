"""Installable skills, following the jarvis-skills manifest standard.

See `docs/CREDITS.md`. The manifest format is reused under MIT; the loader
deliberately diverges from upstream by never executing a contribution — the
reasoning is in `loader`'s module docstring.
"""

from emefa.domain.skills.loader import catalogue_errors, extract_prompt, load_catalogue, load_skill
from emefa.domain.skills.manifest import (
    InvalidManifestError,
    SkillManifest,
    parse_manifest,
)
from emefa.domain.skills.registry import SkillRegistry, SkillStatus

__all__ = [
    "InvalidManifestError",
    "SkillManifest",
    "SkillRegistry",
    "SkillStatus",
    "catalogue_errors",
    "extract_prompt",
    "load_catalogue",
    "load_skill",
    "parse_manifest",
]
