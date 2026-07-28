"""Connected accounts API.

The scope always comes from the authenticated device's owner. A client cannot
name a tenant or a user — sending one is not "ignored", the field does not
exist, so there is nothing to spoof (CLAUDE.md §40).

No response on this router ever contains a secret.
"""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.credentials import (
    PROVIDERS,
    CredentialError,
    VaultNotConfiguredError,
)
from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/connections", tags=["connections"])

_PROVIDER_PATTERN = "^(" + "|".join(PROVIDERS) + ")$"


class ConnectRequest(BaseModel):
    provider: str = Field(pattern=_PROVIDER_PATTERN)
    account_label: str = Field(min_length=1, max_length=200)
    #: The token itself. Write-only: it is never echoed back by any endpoint.
    secret: str = Field(min_length=1, max_length=8_000)
    scopes: str = Field(default="", max_length=500)
    expires_at: str | None = Field(default=None, max_length=40)


class ConnectionResponse(BaseModel):
    provider: str
    account_label: str
    status: str
    expires_at: str | None
    last_used_at: str | None
    usable: bool


def _public(account: Any, usable: bool) -> ConnectionResponse:
    data = asdict(account)
    return ConnectionResponse(
        provider=data["provider"],
        account_label=data["account_label"],
        status=data["status"],
        expires_at=data["expires_at"],
        last_used_at=data["last_used_at"],
        usable=usable,
    )


@router.get("", response_model=list[ConnectionResponse])
def list_connections(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[ConnectionResponse]:
    scope = device.scope()
    vault = request.app.state.vault
    return [_public(account, account.is_usable()) for account in vault.list(scope)]


@router.post("", response_model=ConnectionResponse, status_code=201)
def connect(
    payload: ConnectRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> ConnectionResponse:
    try:
        account = request.app.state.vault.connect(
            device.scope(),
            provider=payload.provider,
            account_label=payload.account_label,
            secret=payload.secret,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
    except VaultNotConfiguredError as error:
        # Fail closed and say why, rather than storing the token in clear.
        raise HTTPException(
            status_code=503,
            detail="encryption_key_not_configured: définissez EMEFA_SECRET_KEY",
        ) from error
    except CredentialError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _public(account, account.is_usable())


@router.delete("/{provider}", status_code=204)
def revoke(
    provider: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown_provider")
    if not request.app.state.vault.revoke(device.scope(), provider):
        raise HTTPException(status_code=404, detail="not_connected")
    return Response(status_code=204)


@router.get("/mailbox")
def mailbox_status(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    """Whether *this* owner has a usable mailbox, and where it comes from."""
    return request.app.state.mailboxes.describe(device.scope())
