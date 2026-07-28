"""Per-tenant connected accounts: encrypted, scoped, and provably isolated.

The scenario under test is the one specified:

    Tenant A · Jean  · jean@gmail.com  · encrypted token
    Tenant B · Amina · amina@gmail.com · encrypted token

Jean must never reach Amina's mailbox, and neither token may exist in clear
anywhere on disk.
"""

import base64
import sqlite3

import httpx
import pytest

from emefa.config import Settings
from emefa.domain import storage
from emefa.domain.agent import AgentStep
from emefa.domain.credentials import (
    AccountScope,
    CredentialDecryptionError,
    CredentialError,
    CredentialVault,
    VaultNotConfiguredError,
    derive_key,
)
from emefa.domain.devices import DeviceRepository
from emefa.infrastructure.mailbox import MailboxResolver
from emefa.main import create_app

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
JEAN = AccountScope(tenant_id="ten_a", user_id="usr_jean")
AMINA = AccountScope(tenant_id="ten_b", user_id="usr_amina")


@pytest.fixture
def vault(tmp_path):
    store = CredentialVault(tmp_path / "vault.db", KEY)
    store.connect(JEAN, "gmail", "jean@gmail.com", "jeton-de-jean")
    store.connect(AMINA, "gmail", "amina@gmail.com", "jeton-d-amina")
    return store, tmp_path / "vault.db"


def test_each_tenant_reads_only_its_own_credential(vault):
    store, _ = vault
    assert store.secret(JEAN, "gmail") == "jeton-de-jean"
    assert store.secret(AMINA, "gmail") == "jeton-d-amina"

    # Jean's scope sees exactly one account: his own.
    assert [item.account_label for item in store.list(JEAN)] == ["jean@gmail.com"]
    assert [item.account_label for item in store.list(AMINA)] == ["amina@gmail.com"]

    # A scope with nothing stored gets nothing — never someone else's.
    stranger = AccountScope(tenant_id="ten_c", user_id="usr_x")
    assert store.secret(stranger, "gmail") is None
    assert store.list(stranger) == []


def test_a_ciphertext_moved_between_tenants_refuses_to_decrypt(vault):
    """Isolation is cryptographic, not merely a WHERE clause.

    Simulates the damage a SQL mistake, a bad restore or a tampered database
    could do: Amina's ciphertext is written straight into Jean's row.
    """
    store, database = vault
    with storage.connect(database) as connection:
        stolen = connection.execute(
            "SELECT secret_ciphertext, secret_nonce FROM connected_accounts "
            "WHERE user_id = 'usr_amina'"
        ).fetchone()
        connection.execute(
            "UPDATE connected_accounts SET secret_ciphertext = ?, secret_nonce = ? "
            "WHERE user_id = 'usr_jean'",
            (stolen["secret_ciphertext"], stolen["secret_nonce"]),
        )

    with pytest.raises(CredentialDecryptionError):
        store.secret(JEAN, "gmail")
    # Amina's own row is untouched and still works.
    assert store.secret(AMINA, "gmail") == "jeton-d-amina"


def test_the_token_never_touches_disk_in_clear(vault):
    store, database = vault
    raw = database.read_bytes()
    assert b"jeton-de-jean" not in raw
    assert b"jeton-d-amina" not in raw
    # The label is an identifier, not a secret: it is expected to be readable.
    assert b"jean@gmail.com" in raw

    with storage.connect(database) as connection:
        row = connection.execute(
            "SELECT secret_ciphertext FROM connected_accounts WHERE user_id = 'usr_jean'"
        ).fetchone()
    assert "jeton" not in row["secret_ciphertext"]
    assert store.secret(JEAN, "gmail") == "jeton-de-jean"


def test_a_different_key_cannot_read_the_vault(vault, tmp_path):
    _, database = vault
    other = CredentialVault(database, base64.urlsafe_b64encode(b"z" * 32).decode())
    with pytest.raises(CredentialDecryptionError):
        other.secret(JEAN, "gmail")


def test_the_vault_fails_closed_without_a_key(tmp_path):
    store = CredentialVault(tmp_path / "nokey.db", None)
    assert store.configured is False
    with pytest.raises(VaultNotConfiguredError):
        store.connect(JEAN, "gmail", "jean@gmail.com", "jeton")
    # Nothing was written — refusing beats storing in clear.
    with storage.connect(tmp_path / "nokey.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM connected_accounts").fetchone()[0] == 0


def test_reconnecting_replaces_rather_than_duplicates(vault):
    store, _ = vault
    store.connect(JEAN, "gmail", "jean.pro@gmail.com", "nouveau-jeton")
    accounts = store.list(JEAN)
    assert len(accounts) == 1
    assert accounts[0].account_label == "jean.pro@gmail.com"
    assert store.secret(JEAN, "gmail") == "nouveau-jeton"


def test_revoking_destroys_the_secret(vault):
    store, database = vault
    assert store.revoke(JEAN, "gmail") is True
    assert store.secret(JEAN, "gmail") is None
    assert store.describe(JEAN, "gmail").status == "revoked"
    with storage.connect(database) as connection:
        row = connection.execute(
            "SELECT secret_ciphertext FROM connected_accounts WHERE user_id = 'usr_jean'"
        ).fetchone()
    assert row["secret_ciphertext"] == ""
    # Amina is unaffected by Jean revoking his own access.
    assert store.secret(AMINA, "gmail") == "jeton-d-amina"


def test_expired_and_unknown_inputs_are_refused(vault):
    store, _ = vault
    with pytest.raises(CredentialError):
        store.connect(JEAN, "telepathy", "x", "secret")
    with pytest.raises(CredentialError):
        store.connect(JEAN, "gmail", "jean@gmail.com", "   ")
    store.connect(AMINA, "gmail", "amina@gmail.com", "jeton", expires_at="2000-01-01T00:00:00+00:00")
    assert store.describe(AMINA, "gmail").is_usable() is False
    assert store.secret(AMINA, "gmail") is None


def test_key_derivation_accepts_a_base64_key_or_a_passphrase():
    assert derive_key(KEY) == b"k" * 32
    stretched = derive_key("une phrase secrète")
    assert len(stretched) == 32
    assert stretched == derive_key("une phrase secrète")
    assert stretched != derive_key("une autre phrase")
    with pytest.raises(VaultNotConfiguredError):
        derive_key("")


# -- mailbox resolution ----------------------------------------------------


class FakeMailbox:
    def __init__(self, label="instance"):
        self.label = label

    def search(self, query, limit):
        return [{"id": "1", "from": self.label, "subject": "x", "date": "", "flags": []}]

    def read(self, message_id):
        return {}

    def create_draft(self, to, subject, body):
        return {"status": "draft_created"}

    def send(self, to, subject, body):
        return {"status": "sent"}


def test_each_owner_resolves_to_their_own_mailbox(vault):
    store, _ = vault
    built: list[tuple[str, str]] = []

    def build(label, secret):
        built.append((label, secret))
        return FakeMailbox(label)

    resolver = MailboxResolver(store, instance_provider=None, build_provider=build)
    jean_box = resolver.for_scope(JEAN)
    amina_box = resolver.for_scope(AMINA)

    assert jean_box.label == "jean@gmail.com"
    assert amina_box.label == "amina@gmail.com"
    assert built == [("jean@gmail.com", "jeton-de-jean"), ("amina@gmail.com", "jeton-d-amina")]
    # A tenant with no connected account gets nothing at all.
    assert resolver.for_scope(AccountScope("ten_c", "usr_x")) is None


def test_another_tenant_never_inherits_the_instance_mailbox(vault):
    """The legacy single-mailbox deployment belongs to the default owner only."""
    store, _ = vault
    resolver = MailboxResolver(store, instance_provider=FakeMailbox("instance"))

    default = AccountScope(storage.DEFAULT_TENANT_ID, storage.DEFAULT_USER_ID)
    assert resolver.for_scope(default).label == "instance"
    # Jean has a connected account but no adapter to build it with, so he gets
    # nothing — crucially, not the instance mailbox.
    assert resolver.for_scope(JEAN) is None
    assert resolver.for_scope(AccountScope("ten_c", "usr_x")) is None


def test_an_unreadable_credential_never_falls_through(vault):
    """A credential that will not decrypt must refuse, not degrade."""
    store, database = vault
    with storage.connect(database) as connection:
        connection.execute(
            "UPDATE connected_accounts SET secret_ciphertext = 'bWFudmFpcw==' "
            "WHERE user_id = 'usr_jean'"
        )
    resolver = MailboxResolver(
        store,
        instance_provider=FakeMailbox("instance"),
        build_provider=lambda label, secret: FakeMailbox(label),
    )
    assert resolver.for_scope(JEAN) is None


# -- API -------------------------------------------------------------------


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="ok")


def _two_tenants(database):
    """Give the instance a second tenant, user and device."""
    with storage.connect(database) as connection:
        connection.execute("INSERT INTO tenants (tenant_id, name) VALUES ('ten_b', 'Amina SARL')")
        connection.execute(
            "INSERT INTO users (user_id, tenant_id, display_name) "
            "VALUES ('usr_amina', 'ten_b', 'Amina')"
        )


@pytest.mark.asyncio
async def test_the_api_scopes_connections_to_the_calling_device(tmp_path):
    database = tmp_path / "api.db"
    app = create_app(Settings(database_path=database, secret_key=KEY), brain=Brain())
    _two_tenants(database)

    devices = DeviceRepository(database)
    _, jean_token = devices.enroll("Poste de Jean")           # default tenant
    _, amina_token = devices.enroll("Poste d'Amina")
    with storage.connect(database) as connection:
        connection.execute(
            "UPDATE devices SET user_id = 'usr_amina' WHERE name = ?", ("Poste d'Amina",)
        )
    jean = {"Authorization": f"Bearer {jean_token}"}
    amina = {"Authorization": f"Bearer {amina_token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/connections")).status_code == 401

        created = await client.post(
            "/v1/connections", headers=jean,
            json={"provider": "gmail", "account_label": "jean@gmail.com",
                  "secret": "jeton-de-jean"},
        )
        assert created.status_code == 201
        # The secret is write-only: no endpoint echoes it back.
        assert "jeton" not in created.text
        assert created.json()["account_label"] == "jean@gmail.com"

        await client.post(
            "/v1/connections", headers=amina,
            json={"provider": "gmail", "account_label": "amina@gmail.com",
                  "secret": "jeton-d-amina"},
        )

        jean_view = (await client.get("/v1/connections", headers=jean)).json()
        amina_view = (await client.get("/v1/connections", headers=amina)).json()
        assert [item["account_label"] for item in jean_view] == ["jean@gmail.com"]
        assert [item["account_label"] for item in amina_view] == ["amina@gmail.com"]
        assert "jeton" not in str(jean_view) + str(amina_view)

        # Jean revoking his own connection leaves Amina's intact.
        assert (await client.delete("/v1/connections/gmail", headers=jean)).status_code == 204
        assert (await client.get("/v1/connections", headers=jean)).json()[0]["status"] == "revoked"
        assert (await client.get("/v1/connections", headers=amina)).json()[0]["status"] == "active"

    store = CredentialVault(database, KEY)
    assert store.secret(AccountScope("ten_b", "usr_amina"), "gmail") == "jeton-d-amina"


@pytest.mark.asyncio
async def test_the_api_refuses_to_store_a_token_without_an_encryption_key(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "nokey.db"), brain=Brain())
    token = app.state.devices.enroll("Poste")[1]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
            json={"provider": "gmail", "account_label": "jean@gmail.com", "secret": "jeton"},
        )
    assert response.status_code == 503
    assert "EMEFA_SECRET_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_client_cannot_name_the_tenant_it_wants(tmp_path):
    """There is no tenant field to spoof: the scope comes from the device."""
    database = tmp_path / "spoof.db"
    app = create_app(Settings(database_path=database, secret_key=KEY), brain=Brain())
    _two_tenants(database)
    token = app.state.devices.enroll("Poste de Jean")[1]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/connections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider": "gmail", "account_label": "jean@gmail.com", "secret": "jeton",
                "tenant_id": "ten_b", "user_id": "usr_amina",  # ignored by the schema
            },
        )
    assert response.status_code == 201
    store = CredentialVault(database, KEY)
    # The credential landed under Jean's real owner, not the one he named.
    assert store.secret(AccountScope("ten_b", "usr_amina"), "gmail") is None
    assert store.secret(
        AccountScope(storage.DEFAULT_TENANT_ID, storage.DEFAULT_USER_ID), "gmail"
    ) == "jeton"


def test_the_devices_table_carries_the_owning_tenant(tmp_path):
    database = tmp_path / "devices.db"
    DeviceRepository(database)
    _two_tenants(database)
    devices = DeviceRepository(database)
    _, token = devices.enroll("Poste d'Amina")
    with storage.connect(database) as connection:
        connection.execute("UPDATE devices SET user_id = 'usr_amina'")

    device = devices.authenticate(token)
    assert device.user_id == "usr_amina"
    assert device.tenant_id == "ten_b"
    assert device.scope() == AccountScope("ten_b", "usr_amina")


def test_secrets_never_reach_the_audit_log(vault, caplog):
    import logging

    store, _ = vault
    with caplog.at_level(logging.INFO, logger="emefa.audit"):
        store.connect(JEAN, "gmail", "jean@gmail.com", "jeton-tres-secret")
        store.revoke(JEAN, "gmail")
    logged = caplog.text
    assert "jeton-tres-secret" not in logged
    assert "account_connected" in logged
    assert "account_revoked" in logged


def test_the_database_file_survives_a_key_that_is_a_passphrase(tmp_path):
    store = CredentialVault(tmp_path / "phrase.db", "ma phrase de chiffrement")
    store.connect(JEAN, "gmail", "jean@gmail.com", "jeton")
    reopened = CredentialVault(tmp_path / "phrase.db", "ma phrase de chiffrement")
    assert reopened.secret(JEAN, "gmail") == "jeton"


def test_sqlite_enforces_one_account_per_provider_per_user(vault):
    _, database = vault
    with pytest.raises(sqlite3.IntegrityError):
        with storage.connect(database) as connection:
            connection.execute(
                "INSERT INTO connected_accounts (account_id, tenant_id, user_id, provider, "
                "account_label, secret_ciphertext, secret_nonce) "
                "VALUES ('dup', 'ten_a', 'usr_jean', 'gmail', 'autre@gmail.com', 'x', 'y')"
            )
