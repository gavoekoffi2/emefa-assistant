"""Account registration, login and session identity (ADR-002).

The enrolment code that used to be the whole authentication story is now what
it always should have been: a bootstrap secret. It authorises creating the
first owner account and nothing else. From the moment an account exists, the
code stops being an authentication path — `/v1/web/session` refuses it and
callers must sign in.

A signed-in session is still a device row carrying an opaque token in an
`httponly` / `secure` / `samesite=strict` cookie. What changed is that the row
now names an account, so every downstream repository has a person to scope to.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from emefa.api.devices import SESSION_COOKIE, current_device, enrollment_guard
from emefa.domain.accounts import Account, WeakPasswordError
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegistrationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(default="", max_length=120)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)
    #: The instance bootstrap secret. Required for the first account only.
    enrollment_code: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    device_name: str = Field(default="Navigateur", min_length=1, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class AccountResponse(BaseModel):
    account_id: str
    email: str
    display_name: str
    role: str


class AuthStatusResponse(BaseModel):
    #: False until the first owner account exists — the front end uses this to
    #: show registration rather than a login form.
    registered: bool
    authenticated: bool
    account: AccountResponse | None = None


def _as_response(account: Account) -> AccountResponse:
    return AccountResponse(
        account_id=account.account_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
    )


def current_account(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Account:
    """The authenticated principal.

    Resolved server-side from the session cookie only. A client-supplied
    account, tenant or role is never trusted (CLAUDE.md §40).
    """
    if device.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account session required",
        )
    account = request.app.state.accounts.get(device.account_id)
    if account is None or account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is not active",
        )
    return account


def _open_session(
    request: Request,
    response: Response,
    account: Account,
    device_name: str,
) -> Device:
    settings = request.app.state.settings
    device, token = request.app.state.devices.enroll(device_name, account.account_id)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return device


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    """Unauthenticated on purpose: the sign-in screen needs to know whether
    this instance has an owner yet. It reveals a boolean, not an address."""
    accounts = request.app.state.accounts
    registered = accounts.count() > 0

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return AuthStatusResponse(registered=registered, authenticated=False)
    device = request.app.state.devices.authenticate(
        token, max_age_seconds=request.app.state.settings.session_max_age_seconds
    )
    if device is None or device.account_id is None:
        return AuthStatusResponse(registered=registered, authenticated=False)
    account = accounts.get(device.account_id)
    if account is None or account.status != "active":
        return AuthStatusResponse(registered=registered, authenticated=False)
    return AuthStatusResponse(
        registered=registered, authenticated=True, account=_as_response(account)
    )


@router.post("/register", response_model=AccountResponse, status_code=201)
def register(
    payload: RegistrationRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> AccountResponse:
    """Create the instance owner. Available exactly once.

    Additional accounts are deliberately not creatable here: multi-user
    membership is a product decision with its own ADR, and leaving an open
    registration endpoint behind a shared code would be worse than the shared
    code alone.
    """
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
        account = accounts.create(payload.email, payload.password, payload.display_name)
    except WeakPasswordError:
        raise HTTPException(status_code=422, detail="password_too_short") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_email") from None

    device = _open_session(request, response, account, payload.device_name)
    audit(
        "owner_account_created",
        account_id=account.account_id,
        device_id=device.device_id,
        source=source,
    )
    return _as_response(account)


@router.post("/login", response_model=AccountResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> AccountResponse:
    account = request.app.state.accounts.authenticate(payload.email, payload.password)
    if account is None:
        request.app.state.activation_limiter.record_failure(source)
        # One message for unknown address, wrong password and suspended
        # account alike, so this endpoint cannot enumerate accounts.
        audit("login_rejected", source=source)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if request.app.state.devices.count() >= request.app.state.settings.max_devices:
        raise HTTPException(status_code=409, detail="Browser limit reached")

    device = _open_session(request, response, account, payload.device_name)
    audit("login_succeeded", account_id=account.account_id, device_id=device.device_id)
    return _as_response(account)


@router.get("/me", response_model=AccountResponse)
def me(account: Annotated[Account, Depends(current_account)]) -> AccountResponse:
    return _as_response(account)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
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
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    account: Annotated[Account, Depends(current_account)],
) -> Response:
    try:
        changed = request.app.state.accounts.change_password(
            account.account_id, payload.current_password, payload.new_password
        )
    except WeakPasswordError:
        raise HTTPException(status_code=422, detail="password_too_short") from None
    if not changed:
        raise HTTPException(status_code=403, detail="current_password_invalid")
    audit("password_changed", account_id=account.account_id)
    return Response(status_code=204)
