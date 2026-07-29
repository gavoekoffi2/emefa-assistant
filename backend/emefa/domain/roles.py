"""Roles and the permissions they grant.

One table, consulted server-side. The frontend may hide a button, but hiding
is a courtesy — every route resolves the caller's role from the authenticated
session and checks it here before doing anything.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """The five seats a company can give someone."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]

    @classmethod
    def parse(cls, value: str) -> "Role":
        try:
            return cls(value.strip().lower())
        except ValueError as error:
            raise UnknownRoleError(value) from error


class UnknownRoleError(ValueError):
    def __init__(self, value: str) -> None:
        super().__init__(f"unknown role: {value!r}")
        self.value = value


ROLE_LABELS: dict[Role, str] = {
    Role.OWNER: "Propriétaire",
    Role.ADMIN: "Administrateur",
    Role.MANAGER: "Manager",
    Role.MEMBER: "Collaborateur",
    Role.VIEWER: "Lecture seule",
}


class Permission(str, Enum):
    """What a seat is allowed to do.

    Deliberately coarse. Permissions describe *kinds* of action, so adding a
    CRM endpoint does not mean inventing a new permission — it means deciding
    whether it reads or writes business data.
    """

    #: See the company's business data: CRM, tasks, agenda, meetings, reports.
    READ_BUSINESS = "read_business"
    #: Create and change that data.
    WRITE_BUSINESS = "write_business"
    #: Delete it. Separated from writing because it is not reversible.
    DELETE_BUSINESS = "delete_business"
    #: Read and edit the company profile the assistant reasons from.
    MANAGE_COMPANY_PROFILE = "manage_company_profile"
    #: Invite, re-role, suspend and remove colleagues.
    MANAGE_MEMBERS = "manage_members"
    #: Connect Gmail, calendars and other providers for oneself.
    MANAGE_OWN_CONNECTIONS = "manage_own_connections"
    #: Approve a consequential action EMEFA has prepared.
    APPROVE_ACTIONS = "approve_actions"
    #: Run the assistant at all — send it messages, ask it to work.
    USE_ASSISTANT = "use_assistant"
    #: Create, edit and run recurring routines on the company's behalf.
    MANAGE_ROUTINES = "manage_routines"
    #: Irreversible company-level operations: close the account, transfer it.
    MANAGE_TENANT = "manage_tenant"


_VIEWER: frozenset[Permission] = frozenset({Permission.READ_BUSINESS})

_MEMBER: frozenset[Permission] = _VIEWER | {
    Permission.WRITE_BUSINESS,
    Permission.USE_ASSISTANT,
    Permission.MANAGE_OWN_CONNECTIONS,
    Permission.APPROVE_ACTIONS,
}

_MANAGER: frozenset[Permission] = _MEMBER | {
    Permission.DELETE_BUSINESS,
    Permission.MANAGE_ROUTINES,
}

_ADMIN: frozenset[Permission] = _MANAGER | {
    Permission.MANAGE_COMPANY_PROFILE,
    Permission.MANAGE_MEMBERS,
}

_OWNER: frozenset[Permission] = _ADMIN | {Permission.MANAGE_TENANT}

#: The whole authorisation model, in one readable place.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _OWNER,
    Role.ADMIN: _ADMIN,
    Role.MANAGER: _MANAGER,
    Role.MEMBER: _MEMBER,
    Role.VIEWER: _VIEWER,
}

#: Seats that may be handed out by an invitation. A second owner is created by
#: transferring ownership, never by inviting one, so a compromised admin
#: account cannot mint a peer of the founder.
INVITABLE_ROLES: tuple[Role, ...] = (Role.ADMIN, Role.MANAGER, Role.MEMBER, Role.VIEWER)


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def allows(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def describe(role: Role) -> dict[str, object]:
    """Role, label and granted permissions — what the frontend renders."""
    return {
        "role": role.value,
        "label": role.label,
        "permissions": sorted(item.value for item in ROLE_PERMISSIONS[role]),
    }
