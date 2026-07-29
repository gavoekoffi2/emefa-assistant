"""Face unlock as a second factor (ADR-005).

Enrolment and step-up both require an already-authenticated session. That is
the point: this is a *second* factor. It never replaces the password, and it
can never be the only thing between an attacker and the account.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.auth import current_account
from emefa.api.devices import current_device
from emefa.domain.accounts import Account
from emefa.domain.devices import Device
from emefa.domain.secondfactor import (
    AUTHENTICATION,
    REGISTRATION,
    STEP_UP_TTL_SECONDS,
    SecondFactorError,
)
from emefa.observability import audit

router = APIRouter(prefix="/v1/auth/second-factor", tags=["second-factor"])


def require_recent_step_up(request: Request, device: Device) -> None:
    """Fail closed when an enrolled account has not recently proved presence."""
    factors = request.app.state.second_factor
    if (
        device.account_id
        and factors.enrolled(device.account_id)
        and not factors.verified_recently(device.device_id)
    ):
        raise HTTPException(status_code=403, detail="second_factor_required")


class CeremonyResponse(BaseModel):
    credential: dict[str, Any]
    label: str = Field(default="", max_length=80)


class StatusResponse(BaseModel):
    #: Whether this account has a face factor at all.
    enrolled: bool
    #: Whether this browser has presented it recently enough to act.
    verified: bool
    step_up_seconds: int
    credentials: list[dict[str, Any]]


def _verifier(request: Request):
    verifier = getattr(request.app.state, "webauthn", None)
    if verifier is None:
        raise HTTPException(status_code=503, detail="second_factor_unavailable")
    return verifier


@router.get("", response_model=StatusResponse)
def status(
    request: Request,
    account: Annotated[Account, Depends(current_account)],
    device: Annotated[Device, Depends(current_device)],
) -> StatusResponse:
    factors = request.app.state.second_factor
    return StatusResponse(
        enrolled=factors.enrolled(account.account_id),
        verified=factors.verified_recently(device.device_id),
        step_up_seconds=STEP_UP_TTL_SECONDS,
        credentials=[item.summary() for item in factors.for_account(account.account_id)],
    )


@router.post("/register/options")
def registration_options(
    request: Request,
    account: Annotated[Account, Depends(current_account)],
) -> dict[str, Any]:
    factors = request.app.state.second_factor
    challenge = factors.issue_challenge(REGISTRATION, account.account_id)
    return {
        "challenge_token": challenge,
        "options": _verifier(request).registration_options(
            account.account_id, account.email, account.display_name, challenge
        ),
    }


@router.post("/register", status_code=201)
def register(
    payload: CeremonyResponse,
    request: Request,
    account: Annotated[Account, Depends(current_account)],
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    factors = request.app.state.second_factor
    challenge = str(payload.credential.get("challenge_token", ""))
    try:
        issued_for = factors.consume_challenge(challenge, REGISTRATION)
        if issued_for != account.account_id:
            raise SecondFactorError("account")
        verified = _verifier(request).verify_registration(
            payload.credential.get("response_json") or payload.credential, challenge
        )
    except SecondFactorError:
        audit("second_factor_registration_rejected", account_id=account.account_id)
        raise HTTPException(status_code=400, detail="registration_failed") from None
    except Exception:
        # The library raises its own hierarchy. One message for every failure:
        # distinguishing them helps an attacker and nobody else.
        audit("second_factor_registration_rejected", account_id=account.account_id)
        raise HTTPException(status_code=400, detail="registration_failed") from None

    credential = factors.register(
        verified.credential_id,
        account.account_id,
        verified.public_key,
        payload.label,
        verified.sign_count,
    )
    # Enrolling proves the user is present now, so it counts as a step-up.
    factors.mark_verified(device.device_id)
    audit(
        "second_factor_registered",
        account_id=account.account_id,
        credential_id=credential.credential_id,
    )
    return credential.summary()


@router.post("/verify/options")
def assertion_options(
    request: Request,
    account: Annotated[Account, Depends(current_account)],
) -> dict[str, Any]:
    factors = request.app.state.second_factor
    credentials = factors.for_account(account.account_id)
    if not credentials:
        raise HTTPException(status_code=409, detail="not_enrolled")
    challenge = factors.issue_challenge(AUTHENTICATION, account.account_id)
    return {
        "challenge_token": challenge,
        "options": _verifier(request).authentication_options(
            challenge, [item.credential_id for item in credentials]
        ),
    }


@router.post("/verify")
def verify(
    payload: CeremonyResponse,
    request: Request,
    account: Annotated[Account, Depends(current_account)],
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    factors = request.app.state.second_factor
    challenge = str(payload.credential.get("challenge_token", ""))
    body = payload.credential.get("response_json") or payload.credential
    try:
        issued_for = factors.consume_challenge(challenge, AUTHENTICATION)
        if issued_for != account.account_id:
            raise SecondFactorError("account")

        credential = factors.get(str(body.get("id", "")))
        # The account binding comes from our storage, never from what the
        # client sent alongside the credential.
        if credential is None or credential.account_id != account.account_id:
            raise SecondFactorError("credential")

        assertion = _verifier(request).verify_assertion(
            body, challenge, credential.public_key, credential.sign_count
        )
        factors.check_counter(credential, assertion.sign_count)
    except SecondFactorError:
        audit("second_factor_rejected", account_id=account.account_id)
        raise HTTPException(status_code=403, detail="verification_failed") from None
    except Exception:
        audit("second_factor_rejected", account_id=account.account_id)
        raise HTTPException(status_code=403, detail="verification_failed") from None

    factors.record_use(credential.credential_id, assertion.sign_count)
    factors.mark_verified(device.device_id)
    audit(
        "second_factor_verified",
        account_id=account.account_id,
        credential_id=credential.credential_id,
    )
    return {"verified": True, "valid_for_seconds": STEP_UP_TTL_SECONDS}


@router.delete("/{credential_id}", status_code=204)
def revoke(
    credential_id: str,
    request: Request,
    account: Annotated[Account, Depends(current_account)],
    device: Annotated[Device, Depends(current_device)],
) -> None:
    factors = request.app.state.second_factor
    require_recent_step_up(request, device)
    if not factors.revoke(credential_id, account.account_id):
        raise HTTPException(status_code=404, detail="credential_not_found")
    # Removing the factor also drops the step-up it granted, so a stolen
    # session cannot keep acting on a credential the owner just deleted.
    factors.clear_verification(device.device_id)
    audit(
        "second_factor_revoked",
        account_id=account.account_id,
        credential_id=credential_id,
    )
