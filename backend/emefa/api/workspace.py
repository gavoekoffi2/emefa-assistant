"""FastAPI dependency resolving the caller's workspace.

The scope comes from the authenticated device's owner — never from the
request body, query string or a header, so there is nothing to spoof.
"""

from typing import Annotated

from fastapi import Depends, Request

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.domain.scope import Scope
from emefa.domain.workspace import Workspace


def current_workspace(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Workspace:
    scope = Scope(tenant_id=device.tenant_id, user_id=device.user_id)
    return request.app.state.workspace_for(scope)


CurrentWorkspace = Annotated[Workspace, Depends(current_workspace)]
