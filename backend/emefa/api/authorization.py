"""Server-side authorisation for every route, by default.

The tenant problem and the permission problem have the same shape: if the
rule has to be *remembered* at each call site, it will eventually be
forgotten, and the failure is silent. So this is not a decorator that each
route opts into — it is a global dependency, and the default for an
unclassified route is to refuse it.

Adding a route therefore forces a decision. The conformance test in
``tests/test_permissions.py`` walks the live application and fails if any
route is missing from the table below, which means a forgotten permission
breaks CI rather than shipping as an open endpoint.

The frontend is never a barrier. It may hide a control the user cannot use;
this is what actually stops the request.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from emefa.api.auth import current_account
from emefa.domain.accounts import Account
from emefa.domain.roles import Permission, allows
from emefa.observability import audit


class Access:
    """How a route is protected, beyond the ordinary permission check."""

    #: No session at all: signing up, signing in, redeeming an emailed link,
    #: and the OpenAPI/health surface.
    PUBLIC = "public"
    #: A valid account is required, but no business permission — the route
    #: only concerns the caller's own identity or session.
    ACCOUNT = "account"
    #: Authenticated by a shared machine token rather than a person. These
    #: guard themselves; see the note on each entry.
    MACHINE = "machine"


#: (method, path template) → Access.* or the Permission the route requires.
#:
#: Read as a policy document: this is the whole authorisation model of the
#: HTTP surface, in one place, rather than scattered across 114 handlers.
ROUTE_POLICY: dict[tuple[str, str], object] = {
    # -- the open surface --------------------------------------------------
    ("GET", "/health"): Access.PUBLIC,
    ("GET", "/openapi.json"): Access.PUBLIC,
    ("GET", "/docs"): Access.PUBLIC,
    ("GET", "/docs/oauth2-redirect"): Access.PUBLIC,
    ("GET", "/redoc"): Access.PUBLIC,
    # -- getting in --------------------------------------------------------
    ("POST", "/v1/auth/signup"): Access.PUBLIC,
    ("POST", "/v1/auth/signin"): Access.PUBLIC,
    ("POST", "/v1/auth/verify-email"): Access.PUBLIC,
    ("POST", "/v1/auth/password/forgot"): Access.PUBLIC,
    ("POST", "/v1/auth/password/reset"): Access.PUBLIC,
    # Redeemed by someone who has no account yet — that is the point.
    ("GET", "/v1/auth/invitations/peek"): Access.PUBLIC,
    ("POST", "/v1/auth/invitations/accept"): Access.PUBLIC,
    # The pre-SaaS enrollment path, kept for the existing private deployment.
    # Both are guarded by the instance enrollment code and rate limited.
    ("POST", "/v1/devices/enroll"): Access.PUBLIC,
    ("POST", "/v1/web/session"): Access.PUBLIC,
    # -- one's own identity and sessions -----------------------------------
    ("GET", "/v1/auth/me"): Access.ACCOUNT,
    ("POST", "/v1/auth/signout"): Access.ACCOUNT,
    ("POST", "/v1/auth/verify-email/resend"): Access.ACCOUNT,
    ("POST", "/v1/auth/password/change"): Access.ACCOUNT,
    ("GET", "/v1/auth/sessions"): Access.ACCOUNT,
    ("DELETE", "/v1/auth/sessions/{device_id}"): Access.ACCOUNT,
    ("GET", "/v1/auth/roles"): Access.ACCOUNT,
    # Seeing who you work with is not privileged; changing them is.
    ("GET", "/v1/auth/members"): Access.ACCOUNT,
    ("GET", "/v1/devices/me"): Access.ACCOUNT,
    ("DELETE", "/v1/devices/me"): Access.ACCOUNT,
    ("GET", "/v1/web/session"): Access.ACCOUNT,
    ("DELETE", "/v1/web/session"): Access.ACCOUNT,
    ("GET", "/v1/system/status"): Access.ACCOUNT,
    # Returns the speech provider's own error message, which can quote account
    # details. The provider account belongs to whoever runs the instance, so
    # this is the owner's to see and nobody else's.
    ("GET", "/v1/system/voice-check"): Permission.MANAGE_TENANT,
    ("GET", "/v1/demo/scenarios"): Access.ACCOUNT,
    # -- managing colleagues -----------------------------------------------
    ("GET", "/v1/auth/invitations"): Permission.MANAGE_MEMBERS,
    ("POST", "/v1/auth/invitations"): Permission.MANAGE_MEMBERS,
    ("DELETE", "/v1/auth/invitations/{invitation_id}"): Permission.MANAGE_MEMBERS,
    ("PATCH", "/v1/auth/members/{user_id}/role"): Permission.MANAGE_MEMBERS,
    ("PATCH", "/v1/auth/members/{user_id}/status"): Permission.MANAGE_MEMBERS,
    # -- the company's own description -------------------------------------
    # Reading it is ordinary; editing it changes how EMEFA reasons for
    # everyone in the company, so it is an admin decision.
    ("GET", "/v1/assistant/profile"): Permission.READ_BUSINESS,
    ("GET", "/v1/assistant/business"): Permission.READ_BUSINESS,
    ("GET", "/v1/assistant/business/schema"): Permission.READ_BUSINESS,
    ("PATCH", "/v1/assistant/profile"): Permission.MANAGE_COMPANY_PROFILE,
    ("PATCH", "/v1/assistant/business"): Permission.MANAGE_COMPANY_PROFILE,
    ("POST", "/v1/assistant/business/import"): Permission.MANAGE_COMPANY_PROFILE,
    # The welcome interview writes straight into that same profile.
    ("GET", "/v1/onboarding/status"): Permission.READ_BUSINESS,
    ("POST", "/v1/onboarding/start"): Permission.MANAGE_COMPANY_PROFILE,
    ("POST", "/v1/onboarding/skip"): Permission.MANAGE_COMPANY_PROFILE,
    ("POST", "/v1/onboarding/resume"): Permission.MANAGE_COMPANY_PROFILE,
    ("POST", "/v1/onboarding/complete"): Permission.MANAGE_COMPANY_PROFILE,
    ("POST", "/v1/onboarding/reopen"): Permission.MANAGE_COMPANY_PROFILE,
    # -- the executive CRM --------------------------------------------------
    ("GET", "/v1/crm/contacts"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/projects"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/deals"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/contracts"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/interactions"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/overview"): Permission.READ_BUSINESS,
    ("GET", "/v1/crm/lookup"): Permission.READ_BUSINESS,
    ("POST", "/v1/crm/contacts"): Permission.WRITE_BUSINESS,
    ("POST", "/v1/crm/projects"): Permission.WRITE_BUSINESS,
    ("POST", "/v1/crm/deals"): Permission.WRITE_BUSINESS,
    ("POST", "/v1/crm/contracts"): Permission.WRITE_BUSINESS,
    ("POST", "/v1/crm/interactions"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/crm/contacts/{contact_id}"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/crm/projects/{project_id}"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/crm/deals/{deal_id}"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/crm/contracts/{contract_id}"): Permission.WRITE_BUSINESS,
    ("DELETE", "/v1/crm/contacts/{contact_id}"): Permission.DELETE_BUSINESS,
    ("DELETE", "/v1/crm/projects/{project_id}"): Permission.DELETE_BUSINESS,
    ("DELETE", "/v1/crm/deals/{deal_id}"): Permission.DELETE_BUSINESS,
    ("DELETE", "/v1/crm/contracts/{contract_id}"): Permission.DELETE_BUSINESS,
    # -- agenda, tasks, meetings -------------------------------------------
    ("GET", "/v1/agenda"): Permission.READ_BUSINESS,
    ("GET", "/v1/agenda/day/{when}"): Permission.READ_BUSINESS,
    ("GET", "/v1/agenda/{event_id}/preparation"): Permission.READ_BUSINESS,
    ("POST", "/v1/agenda"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/agenda/{event_id}"): Permission.WRITE_BUSINESS,
    ("DELETE", "/v1/agenda/{event_id}"): Permission.DELETE_BUSINESS,
    ("GET", "/v1/tasks"): Permission.READ_BUSINESS,
    ("POST", "/v1/tasks/{task_id}/complete"): Permission.WRITE_BUSINESS,
    ("GET", "/v1/meetings"): Permission.READ_BUSINESS,
    ("GET", "/v1/meetings/{meeting_id}"): Permission.READ_BUSINESS,
    ("POST", "/v1/meetings"): Permission.WRITE_BUSINESS,
    ("DELETE", "/v1/meetings/{meeting_id}"): Permission.DELETE_BUSINESS,
    # -- reports, documents, files, prospects ------------------------------
    ("GET", "/v1/briefings/morning"): Permission.READ_BUSINESS,
    ("GET", "/v1/briefings/evening"): Permission.READ_BUSINESS,
    ("GET", "/v1/briefings/today"): Permission.READ_BUSINESS,
    ("GET", "/v1/briefings/preferences"): Permission.READ_BUSINESS,
    # Which sections appear in one's own briefing is a personal setting.
    ("PUT", "/v1/briefings/preferences"): Access.ACCOUNT,
    ("GET", "/v1/documents"): Permission.READ_BUSINESS,
    ("GET", "/v1/documents/{document_id}/download"): Permission.READ_BUSINESS,
    ("GET", "/v1/files"): Permission.READ_BUSINESS,
    ("GET", "/v1/files/{file_id}"): Permission.READ_BUSINESS,
    ("GET", "/v1/files/{file_id}/download"): Permission.READ_BUSINESS,
    ("POST", "/v1/files"): Permission.WRITE_BUSINESS,
    ("GET", "/v1/prospects"): Permission.READ_BUSINESS,
    # -- command centre -----------------------------------------------------
    ("GET", "/v1/command-center/snapshot"): Permission.READ_BUSINESS,
    ("GET", "/v1/command-center/initiatives"): Permission.READ_BUSINESS,
    ("POST", "/v1/command-center/initiatives"): Permission.WRITE_BUSINESS,
    ("PATCH", "/v1/command-center/initiatives/{initiative_id}"): Permission.WRITE_BUSINESS,
    ("GET", "/v1/command-center/routines"): Permission.READ_BUSINESS,
    # A routine acts on the company's behalf on a schedule, without anyone
    # watching. Creating one is a larger grant than writing a record.
    ("POST", "/v1/command-center/routines"): Permission.MANAGE_ROUTINES,
    ("PATCH", "/v1/command-center/routines/{routine_id}"): Permission.MANAGE_ROUTINES,
    ("POST", "/v1/command-center/routines/{routine_id}/run"): Permission.MANAGE_ROUTINES,
    # -- the assistant itself -----------------------------------------------
    ("POST", "/v1/agent/runs"): Permission.USE_ASSISTANT,
    ("DELETE", "/v1/agent/conversation"): Permission.USE_ASSISTANT,
    ("GET", "/v1/agent/approvals"): Permission.READ_BUSINESS,
    ("POST", "/v1/agent/approvals/{action_id}/decision"): Permission.APPROVE_ACTIONS,
    # Sending mail leaves the building; it is an approval-class action.
    ("POST", "/v1/agent/actions/email-send"): Permission.APPROVE_ACTIONS,
    ("GET", "/v1/realtime/session"): Permission.USE_ASSISTANT,
    ("POST", "/v1/realtime/speech"): Permission.USE_ASSISTANT,
    ("POST", "/v1/livekit/session"): Permission.USE_ASSISTANT,
    # -- personal data ------------------------------------------------------
    # Memories are the caller's own. Anyone who can talk to EMEFA may read,
    # export and forget what it remembered about them; this is deliberately
    # not DELETE_BUSINESS, which is about the company's records.
    ("GET", "/v1/memories"): Permission.USE_ASSISTANT,
    ("GET", "/v1/memories/export"): Permission.USE_ASSISTANT,
    ("DELETE", "/v1/memories/{memory_id}"): Permission.USE_ASSISTANT,
    ("GET", "/v1/connections"): Permission.MANAGE_OWN_CONNECTIONS,
    ("GET", "/v1/connections/mailbox"): Permission.MANAGE_OWN_CONNECTIONS,
    ("POST", "/v1/connections"): Permission.MANAGE_OWN_CONNECTIONS,
    ("DELETE", "/v1/connections/{provider}"): Permission.MANAGE_OWN_CONNECTIONS,
    # -- machine callers ----------------------------------------------------
    # The voice bridge and the LiveKit worker authenticate with a shared
    # token checked inside the handler, because the caller is a process, not
    # a person, and has no account to resolve a role from.
    ("POST", "/v1/voice-llm/chat/completions"): Access.MACHINE,
    ("POST", "/v1/livekit/tools/execute"): Access.MACHINE,
}


def _route_key(request: Request) -> tuple[str, str] | None:
    """The (method, path template) of the matched route.

    Uses the template rather than the concrete URL so an id in the path
    cannot change which policy applies.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path is None:
        return None
    return request.method.upper(), path


def enforce_permissions(request: Request) -> None:
    """Global dependency. Runs on every route, including new ones.

    Unclassified routes are refused rather than allowed: forgetting to
    classify a route must fail closed. The conformance test makes that a
    build failure instead of a runtime surprise.
    """
    key = _route_key(request)
    if key is None:  # static files and other non-API routes
        return
    policy = ROUTE_POLICY.get(key)

    if policy is None:
        audit("route_not_classified", method=key[0], path=key[1])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette route n'a pas de politique d'autorisation.",
        )
    if policy in (Access.PUBLIC, Access.MACHINE):
        return

    # Resolving the account also rejects a revoked device and a suspended
    # colleague, so those never reach a handler.
    account: Account = current_account(request, _authenticated_device(request))
    request.state.account = account
    if policy is Access.ACCOUNT:
        return

    assert isinstance(policy, Permission)
    if not allows(account.role, policy):
        audit(
            "permission_denied",
            user_id=account.user_id,
            tenant_id=account.tenant_id,
            role=account.role.value,
            permission=policy.value,
            method=key[0],
            path=key[1],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Votre rôle ({account.role.label}) ne permet pas cette action.",
        )


def _authenticated_device(request: Request):
    """Resolve the device the same way ``current_device`` does.

    Called directly rather than through ``Depends`` because this runs as a
    plain function inside the global dependency.
    """
    from emefa.api.devices import SESSION_COOKIE

    header = request.headers.get("Authorization", "")
    token = (
        header.removeprefix("Bearer ").strip()
        if header.lower().startswith("bearer ")
        else request.cookies.get(SESSION_COOKIE)
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device session required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device = request.app.state.devices.authenticate(
        token, max_age_seconds=request.app.state.settings.session_max_age_seconds
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return device


#: What ``create_app`` installs.
GLOBAL_DEPENDENCIES = [Depends(enforce_permissions)]
