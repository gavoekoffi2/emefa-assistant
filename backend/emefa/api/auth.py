"""The SaaS account path: sign up, verify, sign in, recover, invite.

This replaces the shared instance code as the way a real customer gets in.
The enrollment-code endpoints stay for the existing private deployment, but
nothing here consults them: a company is created by whoever signs up for it.

Two invariants hold across every route below.

* The tenant is never read from the request. It comes from the account that
  authenticated, or — when accepting an invitation — from the invitation the
  inviter created. A client cannot name the company it wants to join.
* Tokens go to the mailbox, not into the response body. An endpoint that
  handed back a verification token would make verification meaningless.
"""

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from emefa.api.devices import SESSION_COOKIE, current_device, enrollment_guard
from emefa.domain.accounts import (
    Account,
    AccountError,
    EmailAlreadyRegisteredError,
    InvalidTokenError,
)
from emefa.domain.devices import Device
from emefa.domain.roles import INVITABLE_ROLES, Role, describe
from emefa.observability import audit

router = APIRouter(prefix="/v1/auth", tags=["auth"])

#: Long enough to resist guessing, short enough to type on a phone.
Password = Field(min_length=10, max_length=256)
#: Shape only. The address is normalised and validated by the accounts
#: domain, which is also what the unique index is built on — one rule,
#: not a second opinion here that could disagree with it.
Email = Field(min_length=3, max_length=254)
DisplayName = Field(min_length=1, max_length=120)


class SignUpRequest(BaseModel):
    email: str = Email
    password: str = Password
    display_name: str = DisplayName
    company_name: str = Field(min_length=1, max_length=160)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)


class SignInRequest(BaseModel):
    email: str = Email
    password: str = Field(min_length=1, max_length=256)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)


class TokenRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)


class EmailRequest(BaseModel):
    email: str = Email


class ResetRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    password: str = Password


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Password


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    password: str = Password
    display_name: str = DisplayName
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)


class InviteRequest(BaseModel):
    email: str = Email
    role: str = Field(default=Role.MEMBER.value, max_length=32)


class RoleRequest(BaseModel):
    role: str = Field(max_length=32)


class StatusRequest(BaseModel):
    status: str = Field(max_length=16)


class AccountResponse(BaseModel):
    account_id: str
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: str
    role_label: str
    status: str
    email_verified: bool
    company_name: str
    permissions: list[str]


def _account_response(account: Account, company_name: str) -> AccountResponse:
    described = describe(account.role)
    return AccountResponse(
        account_id=account.account_id,
        user_id=account.user_id,
        tenant_id=account.tenant_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role.value,
        role_label=str(described["label"]),
        status=account.status,
        email_verified=account.email_verified,
        company_name=company_name,
        permissions=list(described["permissions"]),  # type: ignore[arg-type]
    )


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def current_account(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Account:
    """The authenticated person, resolved from the device that carried the token.

    Anything needing a role must depend on this rather than on the device, so
    a suspended colleague stops being able to act the moment they are
    suspended — not when their browser session happens to expire.
    """
    account = request.app.state.accounts.get(device.user_id)
    if account is None:
        # A device whose owner no longer exists is not a valid session.
        raise HTTPException(status_code=401, detail="Compte introuvable")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Compte suspendu")
    return account


CurrentAccount = Annotated[Account, Depends(current_account)]


class CompatibilityRegistrationRequest(BaseModel):
    email: str = Email
    password: str = Password
    display_name: str = Field(default="", max_length=120)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)
    enrollment_code: str = Field(min_length=1, max_length=256)


class CompatibilityLoginRequest(BaseModel):
    email: str = Email
    password: str = Field(min_length=1, max_length=256)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)


class CompatibilityAccountResponse(BaseModel):
    account_id: str
    email: str
    display_name: str
    role: str


class CompatibilityStatusResponse(BaseModel):
    registered: bool
    authenticated: bool
    account: CompatibilityAccountResponse | None = None


def _compatibility_response(account: Account) -> CompatibilityAccountResponse:
    return CompatibilityAccountResponse(
        account_id=account.account_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role.value,
    )


def _open_compatibility_session(
    request: Request, response: Response, account: Account, device_name: str
) -> Device:
    device, token = request.app.state.devices.enroll(device_name, account.user_id)
    _set_session_cookie(request, response, token)
    return device


@router.get("/status", response_model=CompatibilityStatusResponse)
def compatibility_status(request: Request) -> CompatibilityStatusResponse:
    accounts = request.app.state.accounts
    registered = accounts.count() > 0
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return CompatibilityStatusResponse(registered=registered, authenticated=False)
    device = request.app.state.devices.authenticate(
        token, max_age_seconds=request.app.state.settings.session_max_age_seconds
    )
    if device is None:
        return CompatibilityStatusResponse(registered=registered, authenticated=False)
    account = accounts.get(device.user_id)
    if account is None or not account.is_active:
        return CompatibilityStatusResponse(registered=registered, authenticated=False)
    return CompatibilityStatusResponse(
        registered=registered,
        authenticated=True,
        account=_compatibility_response(account),
    )


@router.post("/register", response_model=CompatibilityAccountResponse, status_code=201)
def compatibility_register(
    payload: CompatibilityRegistrationRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> CompatibilityAccountResponse:
    settings = request.app.state.settings
    accounts = request.app.state.accounts
    if accounts.count() > 0:
        raise HTTPException(status_code=409, detail="An owner account already exists")
    if settings.enrollment_code is None:
        raise HTTPException(status_code=503, detail="Registration is not configured")
    if not secrets.compare_digest(payload.enrollment_code, settings.enrollment_code):
        request.app.state.activation_limiter.record_failure(source)
        audit("registration_rejected", source=source)
        raise HTTPException(status_code=403, detail="Invalid activation code")
    try:
        account = accounts.create_first_owner(
            payload.email, payload.password, payload.display_name
        )
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    device = _open_compatibility_session(request, response, account, payload.device_name)
    audit(
        "owner_account_created",
        account_id=account.account_id,
        device_id=device.device_id,
        source=source,
    )
    return _compatibility_response(account)


@router.post("/login", response_model=CompatibilityAccountResponse)
def compatibility_login(
    payload: CompatibilityLoginRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> CompatibilityAccountResponse:
    account = request.app.state.accounts.authenticate(payload.email, payload.password)
    if account is None:
        request.app.state.activation_limiter.record_failure(source)
        audit("login_rejected", source=source)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if request.app.state.devices.count(account.user_id) >= request.app.state.settings.max_devices:
        raise HTTPException(status_code=409, detail="Browser limit reached")
    device = _open_compatibility_session(request, response, account, payload.device_name)
    audit("login_succeeded", account_id=account.account_id, device_id=device.device_id)
    return _compatibility_response(account)


@router.post("/logout", status_code=204)
def compatibility_logout(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> Response:
    request.app.state.devices.revoke(device.device_id)
    audit("logout", device_id=device.device_id, account_id=device.account_id)
    result = Response(status_code=204)
    result.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return result


@router.post("/password", status_code=204)
def compatibility_change_password(
    payload: ChangePasswordRequest,
    request: Request,
    account: CurrentAccount,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    try:
        changed = request.app.state.accounts.change_password(
            account.user_id, payload.current_password, payload.new_password
        )
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=403, detail="current_password_invalid")
    request.app.state.devices.revoke_for_user(
        account.user_id, keep_device_id=device.device_id
    )
    audit("password_changed", account_id=account.account_id)
    return Response(status_code=204)


# -- signup and sign-in ----------------------------------------------------


@router.post("/signup", response_model=AccountResponse, status_code=201)
def sign_up(
    payload: SignUpRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> AccountResponse:
    """Create a company and its first owner, then sign them straight in.

    The account starts unverified: it can be used, but the verification link
    is what proves the address, and features that email on the user's behalf
    stay closed until it is followed.
    """
    accounts = request.app.state.accounts
    try:
        created = accounts.sign_up(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            company_name=payload.company_name,
        )
    except EmailAlreadyRegisteredError:
        request.app.state.activation_limiter.record_failure(source)
        # Signup is the one place we cannot hide that an address is taken —
        # the alternative is silently doing nothing and leaving the person
        # unable to explain why they never receive a link.
        raise HTTPException(status_code=409, detail="Cette adresse a déjà un compte.")
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    delivery = request.app.state.account_mailer.send_verification(
        to=created.account.email,
        display_name=created.account.display_name,
        token=created.verification_token,
    )
    device, token = request.app.state.devices.enroll(
        payload.device_name, created.account.user_id
    )
    _set_session_cookie(request, response, token)
    audit(
        "account_signed_up",
        user_id=created.account.user_id,
        tenant_id=created.account.tenant_id,
        device_id=device.device_id,
        verification_channel=delivery.channel,
    )
    return _account_response(created.account, created.company_name)


@router.post("/signin", response_model=AccountResponse)
def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> AccountResponse:
    accounts = request.app.state.accounts
    account = accounts.authenticate(payload.email, payload.password)
    if account is None:
        request.app.state.activation_limiter.record_failure(source)
        audit("signin_rejected", source=source)
        # One message for a wrong password, an unknown address and a suspended
        # seat alike: the failure must not be a membership oracle.
        raise HTTPException(status_code=401, detail="Identifiants invalides.")

    settings = request.app.state.settings
    if request.app.state.devices.count(account.user_id) >= settings.max_devices:
        raise HTTPException(
            status_code=409,
            detail="Trop d'appareils connectés. Déconnectez-en un avant d'en ajouter.",
        )
    device, token = request.app.state.devices.enroll(payload.device_name, account.user_id)
    _set_session_cookie(request, response, token)
    audit(
        "account_signed_in",
        user_id=account.user_id,
        tenant_id=account.tenant_id,
        device_id=device.device_id,
    )
    return _account_response(account, accounts.company_name(account.tenant_id))


@router.post("/signout", status_code=204)
def sign_out(request: Request, device: Annotated[Device, Depends(current_device)]) -> Response:
    request.app.state.devices.revoke(device.device_id)
    audit("account_signed_out", user_id=device.user_id, device_id=device.device_id)
    result = Response(status_code=204)
    result.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return result


@router.get("/me", response_model=AccountResponse)
def me(request: Request, account: CurrentAccount) -> AccountResponse:
    return _account_response(account, request.app.state.accounts.company_name(account.tenant_id))


# -- address verification --------------------------------------------------


@router.post("/verify-email", response_model=AccountResponse)
def verify_email(payload: TokenRequest, request: Request) -> AccountResponse:
    accounts = request.app.state.accounts
    try:
        account = accounts.verify_email(payload.token)
    except InvalidTokenError as error:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.") from error
    audit("email_verified", user_id=account.user_id, tenant_id=account.tenant_id)
    return _account_response(account, accounts.company_name(account.tenant_id))


@router.post("/verify-email/resend", status_code=202)
def resend_verification(request: Request, account: CurrentAccount) -> dict[str, Any]:
    token = request.app.state.accounts.issue_verification(account.user_id)
    if token is None:
        return {"status": "already_verified"}
    delivery = request.app.state.account_mailer.send_verification(
        to=account.email, display_name=account.display_name, token=token
    )
    audit("verification_resent", user_id=account.user_id, channel=delivery.channel)
    return {"status": "sent", "channel": delivery.channel}


# -- password recovery -----------------------------------------------------


@router.post("/password/forgot", status_code=202)
def forgot_password(
    payload: EmailRequest,
    request: Request,
    source: Annotated[str, Depends(enrollment_guard)],
) -> dict[str, str]:
    """Always answers the same way.

    Whether an address has an account is not something an unauthenticated
    caller may discover, so the response does not vary — only what happens
    behind it does.
    """
    issued = request.app.state.accounts.request_password_reset(payload.email)
    if issued is not None:
        account, token = issued
        request.app.state.account_mailer.send_password_reset(
            to=account.email, display_name=account.display_name, token=token
        )
        audit("password_reset_requested", user_id=account.user_id)
    else:
        request.app.state.activation_limiter.record_failure(source)
    return {"status": "sent_if_registered"}


@router.post("/password/reset", status_code=204)
def reset_password(payload: ResetRequest, request: Request) -> Response:
    try:
        account = request.app.state.accounts.reset_password(payload.token, payload.password)
    except InvalidTokenError as error:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.") from error
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # Whoever had the old password may be why it is being reset; every
    # existing session is dropped so a stolen one dies with it.
    revoked = request.app.state.devices.revoke_for_user(account.user_id)
    audit("password_reset", user_id=account.user_id, sessions_revoked=revoked)
    return Response(status_code=204)


@router.post("/password/change", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    account: CurrentAccount,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    try:
        changed = request.app.state.accounts.change_password(
            account.user_id, payload.current_password, payload.new_password
        )
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=403, detail="Mot de passe actuel incorrect.")
    revoked = request.app.state.devices.revoke_for_user(
        account.user_id, keep_device_id=device.device_id
    )
    audit("password_changed", user_id=account.user_id, sessions_revoked=revoked)
    return Response(status_code=204)


# -- sessions --------------------------------------------------------------


@router.get("/sessions")
def list_sessions(
    request: Request,
    account: CurrentAccount,
    device: Annotated[Device, Depends(current_device)],
) -> list[dict[str, Any]]:
    """The devices attached to this account — its own only, by construction."""
    return [
        {
            "device_id": item.device_id,
            "name": item.name,
            "current": item.device_id == device.device_id,
        }
        for item in request.app.state.devices.list_for_user(account.user_id)
    ]


@router.delete("/sessions/{device_id}", status_code=204)
def revoke_session(
    device_id: str,
    request: Request,
    account: CurrentAccount,
) -> Response:
    owned = {item.device_id for item in request.app.state.devices.list_for_user(account.user_id)}
    if device_id not in owned:
        # Not "forbidden": an id belonging to someone else must not be
        # distinguishable from one that does not exist.
        raise HTTPException(status_code=404, detail="Session introuvable.")
    request.app.state.devices.revoke(device_id)
    audit("session_revoked", user_id=account.user_id, device_id=device_id)
    return Response(status_code=204)


# -- colleagues ------------------------------------------------------------


@router.get("/members")
def list_members(request: Request, account: CurrentAccount) -> list[dict[str, Any]]:
    """Everyone in the caller's company. Any seat may see who they work with."""
    accounts = request.app.state.accounts
    return [
        {
            "user_id": member.user_id,
            "display_name": member.display_name,
            "email": member.email,
            "role": member.role.value,
            "role_label": member.role.label,
            "status": member.status,
            "email_verified": member.email_verified,
            "is_me": member.user_id == account.user_id,
        }
        for member in accounts.list_members(account.tenant_id)
    ]


@router.get("/roles")
def list_roles(_: CurrentAccount) -> list[dict[str, object]]:
    """The seats that can be handed out, with what each one grants."""
    return [describe(role) for role in INVITABLE_ROLES]


@router.post("/invitations", status_code=201)
def invite_member(
    payload: InviteRequest,
    request: Request,
    account: CurrentAccount,
) -> dict[str, Any]:
    accounts = request.app.state.accounts
    try:
        role = Role.parse(payload.role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Rôle inconnu.") from error
    if role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Un propriétaire ne s'invite pas : transférez la propriété.",
        )
    try:
        invitation, token = accounts.invite(
            tenant_id=account.tenant_id,
            email=payload.email,
            role=role,
            invited_by_user_id=account.user_id,
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="Cette adresse a déjà un compte.")
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    delivery = request.app.state.account_mailer.send_invitation(
        to=invitation.email,
        company_name=accounts.company_name(account.tenant_id),
        inviter_name=account.display_name,
        role_label=role.label,
        token=token,
    )
    audit(
        "member_invited",
        tenant_id=account.tenant_id,
        invited_by=account.user_id,
        role=role.value,
        channel=delivery.channel,
    )
    return {
        "invitation_id": invitation.invitation_id,
        "email": invitation.email,
        "role": role.value,
        "role_label": role.label,
        "expires_at": invitation.expires_at,
        "channel": delivery.channel,
    }


@router.get("/invitations")
def list_invitations(
    request: Request,
    account: CurrentAccount,
) -> list[dict[str, Any]]:
    return [
        {
            "invitation_id": item.invitation_id,
            "email": item.email,
            "role": item.role.value,
            "role_label": item.role.label,
            "expires_at": item.expires_at,
            "accepted": item.accepted_at is not None,
        }
        for item in request.app.state.accounts.list_invitations(account.tenant_id)
    ]


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: str,
    request: Request,
    account: CurrentAccount,
) -> Response:
    if not request.app.state.accounts.revoke_invitation(account.tenant_id, invitation_id):
        raise HTTPException(status_code=404, detail="Invitation introuvable.")
    audit("invitation_revoked", tenant_id=account.tenant_id, invitation_id=invitation_id)
    return Response(status_code=204)


@router.get("/invitations/peek")
def peek_invitation(token: str, request: Request) -> dict[str, Any]:
    """Shown on the join page before the invitee chooses a password.

    Unauthenticated by necessity — the whole point is that they have no
    account yet — so it reveals only what the emailed link already told them.
    """
    invitation = request.app.state.accounts.peek_invitation(token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation invalide ou expirée.")
    return {
        "email": invitation.email,
        "role": invitation.role.value,
        "role_label": invitation.role.label,
        "company_name": request.app.state.accounts.company_name(invitation.tenant_id),
    }


@router.post("/invitations/accept", response_model=AccountResponse, status_code=201)
def accept_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> AccountResponse:
    accounts = request.app.state.accounts
    try:
        account = accounts.accept_invitation(
            token=payload.token,
            password=payload.password,
            display_name=payload.display_name,
        )
    except InvalidTokenError as error:
        request.app.state.activation_limiter.record_failure(source)
        raise HTTPException(status_code=400, detail="Invitation invalide ou expirée.") from error
    except AccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    device, token = request.app.state.devices.enroll(payload.device_name, account.user_id)
    _set_session_cookie(request, response, token)
    audit(
        "invitation_accepted",
        user_id=account.user_id,
        tenant_id=account.tenant_id,
        role=account.role.value,
        device_id=device.device_id,
    )
    return _account_response(account, accounts.company_name(account.tenant_id))


@router.patch("/members/{user_id}/role")
def set_member_role(
    user_id: str,
    payload: RoleRequest,
    request: Request,
    account: CurrentAccount,
) -> dict[str, Any]:
    if user_id == account.user_id:
        raise HTTPException(status_code=422, detail="Vous ne pouvez pas changer votre propre rôle.")
    try:
        role = Role.parse(payload.role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Rôle inconnu.") from error
    if role is Role.OWNER and account.role is not Role.OWNER:
        raise HTTPException(
            status_code=403, detail="Seul un propriétaire peut nommer un propriétaire."
        )
    try:
        updated = request.app.state.accounts.set_role(
            tenant_id=account.tenant_id, user_id=user_id, role=role
        )
    except AccountError as error:
        raise HTTPException(
            status_code=409, detail="L'entreprise doit garder un propriétaire."
        ) from error
    if updated is None:
        raise HTTPException(status_code=404, detail="Collaborateur introuvable.")
    audit(
        "member_role_changed",
        tenant_id=account.tenant_id,
        actor=account.user_id,
        target=user_id,
        role=role.value,
    )
    return {"user_id": updated.user_id, "role": updated.role.value, "role_label": updated.role.label}


@router.patch("/members/{user_id}/status")
def set_member_status(
    user_id: str,
    payload: StatusRequest,
    request: Request,
    account: CurrentAccount,
) -> dict[str, Any]:
    if user_id == account.user_id:
        raise HTTPException(status_code=422, detail="Vous ne pouvez pas vous suspendre.")
    try:
        updated = request.app.state.accounts.set_status(
            tenant_id=account.tenant_id, user_id=user_id, status=payload.status
        )
    except AccountError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if updated is None:
        raise HTTPException(status_code=404, detail="Collaborateur introuvable.")
    if updated.status == "suspended":
        # Suspension has to bite immediately, not at session expiry.
        request.app.state.devices.revoke_for_user(user_id)
    audit(
        "member_status_changed",
        tenant_id=account.tenant_id,
        actor=account.user_id,
        target=user_id,
        status=updated.status,
    )
    return {"user_id": updated.user_id, "status": updated.status}
