"""Resolving *whose* mailbox a request may touch.

Before this module the mailbox was a single instance-wide object built from
settings: every device shared one inbox. That is correct for a private
single-user instance and wrong the moment two tenants exist, which is what the
connected-account model requires:

    Tenant A · Jean  · jean@gmail.com   -> Jean's provider
    Tenant B · Amina · amina@gmail.com  -> Amina's provider

The resolver takes an :class:`AccountScope` — derived server-side from the
authenticated device, never from anything a client sends — and returns the
provider bound to that scope, or ``None``. There is no method that returns "the"
mailbox, because at platform scale there is no such thing.

Resolution order, so the existing single-tenant deployment keeps working
unchanged (brownfield rule):

1. a connected account stored for this exact tenant+user;
2. the instance-wide mailbox from settings, **only** for the default owner;
3. nothing.
"""

from __future__ import annotations

from typing import Callable

from emefa.domain.credentials import (
    AccountScope,
    CredentialDecryptionError,
    CredentialVault,
)
from emefa.domain.email import EmailProvider
from emefa.domain.storage import DEFAULT_TENANT_ID, DEFAULT_USER_ID
from emefa.observability import audit

#: Provider key under which a mail account is stored.
MAIL_PROVIDER = "gmail"


class MailboxResolver:
    """Maps an account scope to the e-mail provider it is allowed to use."""

    def __init__(
        self,
        vault: CredentialVault,
        instance_provider: EmailProvider | None = None,
        build_provider: Callable[[str, str], EmailProvider] | None = None,
    ) -> None:
        self.vault = vault
        #: The legacy instance-wide mailbox, if one is configured.
        self.instance_provider = instance_provider
        #: Builds a provider from (account_label, secret). Absent until a real
        #: OAuth adapter ships; connected accounts are then stored but unusable,
        #: which the resolver reports honestly rather than silently ignoring.
        self.build_provider = build_provider

    def for_scope(self, scope: AccountScope) -> EmailProvider | None:
        account = self.vault.describe(scope, MAIL_PROVIDER)
        if account is not None and account.is_usable():
            if self.build_provider is None:
                audit(
                    "mailbox_adapter_missing",
                    tenant_id=scope.tenant_id, provider=MAIL_PROVIDER,
                )
                return None
            try:
                secret = self.vault.secret(scope, MAIL_PROVIDER)
            except CredentialDecryptionError:
                # A credential that will not decrypt under its own scope is a
                # security event: refuse, never fall through to another mailbox.
                audit(
                    "mailbox_credential_unreadable",
                    tenant_id=scope.tenant_id, user_id=scope.user_id,
                )
                return None
            if secret:
                self.vault.touch(scope, MAIL_PROVIDER)
                return self.build_provider(account.account_label, secret)
            return None

        # The pre-existing single-mailbox deployment belongs to the default
        # owner only. Another tenant must never inherit it.
        if self.is_default_owner(scope):
            return self.instance_provider
        return None

    @staticmethod
    def is_default_owner(scope: AccountScope) -> bool:
        return scope.tenant_id == DEFAULT_TENANT_ID and scope.user_id == DEFAULT_USER_ID

    def describe(self, scope: AccountScope) -> dict[str, object]:
        """What the interface may show about this scope's mailbox."""
        account = self.vault.describe(scope, MAIL_PROVIDER)
        if account is not None:
            return {
                "connected": account.is_usable(),
                "account_label": account.account_label,
                "status": account.status,
                "source": "connected_account",
                "usable": self.for_scope(scope) is not None,
            }
        if self.is_default_owner(scope) and self.instance_provider is not None:
            return {
                "connected": True,
                "account_label": "",
                "status": "active",
                "source": "instance_settings",
                "usable": True,
            }
        return {"connected": False, "account_label": "", "status": "", "source": "", "usable": False}
