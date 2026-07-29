"""One owner's view of the system.

A request is served from a workspace, not from application-wide singletons:
the repositories and the agent inside it are bound to the scope of the device
that authenticated. `main.create_app` memoises one per scope.

Every business resource is rebound: there is no longer a category of data
reached through application state. `tests/test_tenant_isolation.py` asserts
that no table carrying `tenant_id` is left unscoped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from emefa.domain.scope import Scope


@dataclass(frozen=True, slots=True)
class Workspace:
    scope: Scope
    # company-owned
    crm: Any
    tasks: Any
    meetings: Any
    documents: Any
    profiles: Any
    prospects: Any
    initiatives: Any
    routines: Any
    # personal
    memories: Any
    agenda: Any
    conversations: Any
    approvals: Any
    briefings: Any
    evening_reports: Any
    report_preferences: Any
    onboarding: Any
    uploaded_files: Any
    # composed
    workflows: Any
    inbox: Any
    agent: Any
