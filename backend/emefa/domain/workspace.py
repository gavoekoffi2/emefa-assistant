"""One owner's view of the system.

A request is served from a workspace, not from application-wide singletons:
the repositories and the agent inside it are bound to the scope of the device
that authenticated. `main.create_app` memoises one per scope.

Only the repositories that are actually tenant-scoped are rebound. The rest
(profiles, documents, prospects, routines…) are still single-scope by design
and are reached through application state — a gap tracked explicitly in
`tests/test_tenant_isolation.py`, not papered over here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from emefa.domain.scope import Scope


@dataclass(frozen=True, slots=True)
class Workspace:
    scope: Scope
    crm: Any
    tasks: Any
    memories: Any
    agenda: Any
    meetings: Any
    workflows: Any
    inbox: Any
    agent: Any
