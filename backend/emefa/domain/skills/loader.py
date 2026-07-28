"""Reading a skill from disk **without importing it**.

This is the single most important decision in the skills subsystem, so it gets
its own module and this docstring.

Upstream, a skill is a Python file that gets imported into the host process:
`skills_data/installed/<name>/skill.py`, subclassing `SkillBase`. On a
single-user desktop app, where the user installed the skill deliberately and
owns the machine, that is a defensible trade.

EMEFA is a hosted product holding other people's mail, documents and business
data. Importing a marketplace contribution there means running a stranger's
code with EMEFA's credentials, filesystem and network — which is exactly the
shortcut `CLAUDE.md` §48 forbids ("allow arbitrary MCP installation without
trust controls", "give unrestricted shell/network/file access to an LLM").

So a skill contributes three things and no behaviour:

1. a **manifest** — what it is, what it needs;
2. a **system prompt** — read out of the file with `ast`, never executed;
3. **declarative bindings** to tools EMEFA already ships and already governs.

`ast.parse` builds a syntax tree without evaluating anything: a `skill.py`
containing `os.system("rm -rf /")` at module level yields a tree node and no
subprocess. Only string literals assigned to `SYSTEM_PROMPT` are read, and
only if they are literals — an f-string or a concatenation of calls is
ignored, because evaluating it would mean running the contribution.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from emefa.domain.skills.manifest import (
    InvalidManifestError,
    SkillManifest,
    parse_manifest,
)

PROMPT_CONSTANT = "SYSTEM_PROMPT"
MANIFEST_FILENAME = "skill.yaml"
MODULE_FILENAME = "skill.py"
PROMPT_FILENAME = "PROMPT.md"

#: A contribution larger than this is not a prompt; refuse to read it into
#: memory rather than discovering the problem later.
MAX_FILE_BYTES = 256 * 1024


def extract_prompt(source: str) -> str:
    """Pull `SYSTEM_PROMPT` out of Python source without executing it.

    Handles the two shapes the upstream standard produces — a module-level
    constant and a class attribute — and returns "" for anything that would
    need evaluation.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [
            target.id for target in node.targets if isinstance(target, ast.Name)
        ]
        if PROMPT_CONSTANT not in names:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
        # Anything else (f-string, call, concatenation) would require running
        # the contribution to know its value. Not worth a prompt.
        return ""
    return ""


def load_skill(directory: Path, source: str = "catalogue") -> SkillManifest:
    """Load one skill directory. Raises `InvalidManifestError` on anything
    unusable, so a bad contribution fails loudly at load time rather than
    silently at conversation time."""
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise InvalidManifestError(f"missing {MANIFEST_FILENAME} in {directory.name}")
    if manifest_path.stat().st_size > MAX_FILE_BYTES:
        raise InvalidManifestError(f"{MANIFEST_FILENAME} is implausibly large")

    try:
        # safe_load, not load: full YAML can construct arbitrary Python
        # objects, which would reintroduce exactly what this module exists to
        # prevent.
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise InvalidManifestError(f"unreadable manifest: {error}") from error

    prompt = ""
    prompt_path = directory / PROMPT_FILENAME
    module_path = directory / MODULE_FILENAME
    if prompt_path.is_file() and prompt_path.stat().st_size <= MAX_FILE_BYTES:
        prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
    elif module_path.is_file() and module_path.stat().st_size <= MAX_FILE_BYTES:
        prompt = extract_prompt(module_path.read_text(encoding="utf-8", errors="replace"))

    manifest = parse_manifest(document, prompt, source=source)
    if manifest.name != directory.name:
        raise InvalidManifestError(
            f"manifest name {manifest.name!r} does not match directory {directory.name!r}"
        )
    return manifest


def load_catalogue(root: Path, source: str = "catalogue") -> list[SkillManifest]:
    """Load every skill under `root`, skipping the ones that do not load.

    One broken contribution must not take the catalogue down with it, so
    failures are dropped here; `catalogue_errors` reports them for the admin
    view.
    """
    return [manifest for manifest, _ in _load_all(root, source) if manifest is not None]


def catalogue_errors(root: Path, source: str = "catalogue") -> dict[str, str]:
    return {
        name: error
        for manifest, (name, error) in _load_all(root, source)
        if manifest is None
    }


def _load_all(
    root: Path, source: str
) -> list[tuple[SkillManifest | None, tuple[str, str]]]:
    if not root.is_dir():
        return []
    results: list[tuple[SkillManifest | None, tuple[str, str]]] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        # A directory with no manifest is not a broken skill, it is not a
        # skill — a cache, a stray upload folder, an editor's scratch dir.
        # Reporting those as errors would bury the ones that matter.
        if not (directory / MANIFEST_FILENAME).is_file():
            continue
        try:
            results.append((load_skill(directory, source), (directory.name, "")))
        except InvalidManifestError as error:
            results.append((None, (directory.name, str(error))))
        except OSError as error:
            results.append((None, (directory.name, f"unreadable: {error}")))
    return results
