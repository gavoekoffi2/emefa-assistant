"""The SaaS account path, end to end through the API.

These cover the journey the mission specifies — création de compte,
vérification e-mail, création automatique du tenant, création du propriétaire,
connexion, récupération de mot de passe, gestion des sessions, rattachement des
appareils, invitation de collaborateurs — and the ways each one can be abused.
"""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain import storage
from emefa.domain.accounts import (
    AccountRepository,
    EmailAlreadyRegisteredError,
    InvalidEmailError,
    InvalidTokenError,
    WeakPasswordError,
    hash_password,
    normalise_email,
    verify_password,
)
from emefa.domain.agent import AgentStep
from emefa.domain.roles import Permission, Role, allows
from emefa.main import create_app


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="ok")


class CapturingMailer:
    """Stands in for delivery so tests can read the link a user would click.

    Deliberately the *only* way a test gets a token: no endpoint returns one,
    so a test that could not read the mailbox is a test of something real.
    """

    def __init__(self):
        self.sent: list[dict] = []

    def _record(self, kind, **fields):
        self.sent.append({"kind": kind, **fields})
        from emefa.domain.account_mail import Delivery

        return Delivery(channel="email", delivered=True)

    def send_verification(self, *, to, display_name, token):
        return self._record("verification", to=to, token=token)

    def send_password_reset(self, *, to, display_name, token):
        return self._record("reset", to=to, token=token)

    def send_invitation(self, *, to, company_name, inviter_name, role_label, token):
        return self._record("invitation", to=to, token=token, role_label=role_label)

    def last(self, kind: str) -> dict:
        return [item for item in self.sent if item["kind"] == kind][-1]


@pytest.fixture
def app(tmp_path):
    application = create_app(
        Settings(database_path=tmp_path / "accounts.db", cookie_secure=False),
        brain=Brain(),
    )
    application.state.account_mailer = CapturingMailer()
    return application


@pytest.fixture
def client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def _signup(client, email="jean@alpha.tg", company="Entreprise Alpha", name="Jean"):
    return await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "motdepasse-solide",
            "display_name": name,
            "company_name": company,
        },
    )


# -- password hashing ------------------------------------------------------


def test_passwords_are_salted_and_never_recoverable():
    first = hash_password("motdepasse-solide")
    second = hash_password("motdepasse-solide")
    assert first != second, "the same password must not produce the same hash"
    assert "motdepasse-solide" not in first
    assert verify_password("motdepasse-solide", first)
    assert verify_password("motdepasse-solide", second)
    assert not verify_password("motdepasse-solid", first)


def test_a_missing_or_corrupt_hash_is_a_failed_check_not_a_crash():
    # The seeded single-tenant user has no password. Trying to log in as it
    # must fail cleanly rather than raise.
    assert verify_password("nimporte quoi", "") is False
    assert verify_password("nimporte quoi", "scrypt$broken") is False
    assert verify_password("nimporte quoi", "bcrypt$1$2$3$aa$bb") is False


def test_short_passwords_are_refused():
    with pytest.raises(WeakPasswordError):
        hash_password("court")


def test_addresses_are_normalised_before_they_are_compared():
    assert normalise_email("  Jean.Dupont@Alpha.TG ") == "jean.dupont@alpha.tg"
    with pytest.raises(InvalidEmailError):
        normalise_email("pas-une-adresse")
    with pytest.raises(InvalidEmailError):
        normalise_email("jean@alpha")


# -- signup ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_creates_a_company_an_owner_and_a_session(app, client):
    async with client:
        response = await _signup(client)
        assert response.status_code == 201, response.text
        body = response.json()

        assert body["role"] == "owner"
        assert body["company_name"] == "Entreprise Alpha"
        assert body["email_verified"] is False
        assert body["tenant_id"] != storage.DEFAULT_TENANT_ID, (
            "a signup must get its own company, not the seeded instance one"
        )
        # Signed in already: the session cookie was set.
        assert "emefa_session" in response.cookies
        assert (await client.get("/v1/auth/me")).json()["user_id"] == body["user_id"]


@pytest.mark.asyncio
async def test_two_signups_get_two_separate_companies(app, client):
    async with client:
        alpha = (await _signup(client)).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as second:
        beta = (await _signup(second, "amina@beta.tg", "Entreprise Beta", "Amina")).json()

    assert alpha["tenant_id"] != beta["tenant_id"]
    assert alpha["user_id"] != beta["user_id"]
    # Each is the owner of their own, and neither is the seeded default.
    assert alpha["role"] == beta["role"] == "owner"


@pytest.mark.asyncio
async def test_the_same_address_cannot_register_twice(client):
    async with client:
        assert (await _signup(client)).status_code == 201
        again = await _signup(client, "JEAN@ALPHA.TG")
        assert again.status_code == 409, "normalisation must make these the same address"


@pytest.mark.asyncio
async def test_signup_refuses_a_weak_password(client):
    async with client:
        response = await client.post(
            "/v1/auth/signup",
            json={
                "email": "jean@alpha.tg",
                "password": "court",
                "display_name": "Jean",
                "company_name": "Alpha",
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_signup_never_returns_the_verification_token(app, client):
    async with client:
        body = (await _signup(client)).text
    token = app.state.account_mailer.last("verification")["token"]
    assert token not in body, "holding the response must not prove you own the address"


# -- email verification ----------------------------------------------------


@pytest.mark.asyncio
async def test_the_emailed_link_verifies_the_address_once(app, client):
    async with client:
        await _signup(client)
        token = app.state.account_mailer.last("verification")["token"]

        verified = await client.post("/v1/auth/verify-email", json={"token": token})
        assert verified.status_code == 200
        assert verified.json()["email_verified"] is True
        assert verified.json()["status"] == "active"

        # Single use: a replayed link is refused.
        replayed = await client.post("/v1/auth/verify-email", json={"token": token})
        assert replayed.status_code == 400


@pytest.mark.asyncio
async def test_an_unknown_verification_token_is_refused(client):
    async with client:
        await _signup(client)
        response = await client.post(
            "/v1/auth/verify-email", json={"token": "x" * 43}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_resending_verification_invalidates_the_previous_link(app, client):
    async with client:
        await _signup(client)
        first = app.state.account_mailer.last("verification")["token"]
        assert (await client.post("/v1/auth/verify-email/resend")).status_code == 202
        second = app.state.account_mailer.last("verification")["token"]
        assert first != second

        assert (await client.post(
            "/v1/auth/verify-email", json={"token": first}
        )).status_code == 400
        assert (await client.post(
            "/v1/auth/verify-email", json={"token": second}
        )).status_code == 200


# -- sign in ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_in_with_the_right_password(app, client):
    async with client:
        created = (await _signup(client)).json()
        await client.post("/v1/auth/signout")

        response = await client.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "motdepasse-solide"},
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == created["user_id"]
        assert (await client.get("/v1/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_a_wrong_password_and_an_unknown_address_are_indistinguishable(client):
    async with client:
        await _signup(client)
        wrong = await client.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "mauvais-mot-de-passe"},
        )
        unknown = await client.post(
            "/v1/auth/signin",
            json={"email": "personne@nulle-part.tg", "password": "mauvais-mot-de-passe"},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"], (
            "the error must not reveal whether the address has an account"
        )


@pytest.mark.asyncio
async def test_signing_out_kills_that_session_only(app, client):
    async with client:
        laptop = (await _signup(client)).cookies["emefa_session"]
        phone = (await client.post(
            "/v1/auth/signin",
            json={
                "email": "jean@alpha.tg",
                "password": "motdepasse-solide",
                "device_name": "Téléphone",
            },
        )).cookies["emefa_session"]

        # Each session is addressed explicitly: the shared cookie jar would
        # otherwise decide which device these calls act on.
        laptop_auth = {"Authorization": f"Bearer {laptop}"}
        phone_auth = {"Authorization": f"Bearer {phone}"}
        assert (await client.post("/v1/auth/signout", headers=laptop_auth)).status_code == 204

        assert (await client.get("/v1/auth/me", headers=laptop_auth)).status_code == 401
        assert (await client.get("/v1/auth/me", headers=phone_auth)).status_code == 200


# -- password recovery -----------------------------------------------------


@pytest.mark.asyncio
async def test_password_reset_replaces_the_password_and_drops_every_session(app, client):
    async with client:
        await _signup(client)
        stolen = (await client.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "motdepasse-solide"},
        )).cookies["emefa_session"]

        assert (await client.post(
            "/v1/auth/password/forgot", json={"email": "jean@alpha.tg"}
        )).status_code == 202
        token = app.state.account_mailer.last("reset")["token"]

        assert (await client.post(
            "/v1/auth/password/reset",
            json={"token": token, "password": "nouveau-mot-de-passe"},
        )).status_code == 204

        # Whoever held a session before the reset no longer has one.
        assert (await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {stolen}"}
        )).status_code == 401
        # The old password is dead, the new one works.
        assert (await client.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "motdepasse-solide"},
        )).status_code == 401
        assert (await client.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "nouveau-mot-de-passe"},
        )).status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_answers_identically_for_an_unknown_address(client):
    async with client:
        await _signup(client)
        known = await client.post(
            "/v1/auth/password/forgot", json={"email": "jean@alpha.tg"}
        )
        unknown = await client.post(
            "/v1/auth/password/forgot", json={"email": "personne@nulle-part.tg"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()


@pytest.mark.asyncio
async def test_a_reset_link_cannot_be_used_twice(app, client):
    async with client:
        await _signup(client)
        await client.post("/v1/auth/password/forgot", json={"email": "jean@alpha.tg"})
        token = app.state.account_mailer.last("reset")["token"]
        payload = {"token": token, "password": "nouveau-mot-de-passe"}
        assert (await client.post("/v1/auth/password/reset", json=payload)).status_code == 204
        assert (await client.post("/v1/auth/password/reset", json=payload)).status_code == 400


@pytest.mark.asyncio
async def test_changing_a_password_keeps_the_current_session_and_drops_the_others(app, client):
    async with client:
        laptop = (await _signup(client)).cookies["emefa_session"]
        phone = (await client.post(
            "/v1/auth/signin",
            json={
                "email": "jean@alpha.tg",
                "password": "motdepasse-solide",
                "device_name": "Téléphone",
            },
        )).cookies["emefa_session"]
        laptop_auth = {"Authorization": f"Bearer {laptop}"}
        phone_auth = {"Authorization": f"Bearer {phone}"}

        refused = await client.post(
            "/v1/auth/password/change",
            headers=laptop_auth,
            json={"current_password": "faux", "new_password": "nouveau-mot-de-passe"},
        )
        assert refused.status_code == 403

        changed = await client.post(
            "/v1/auth/password/change",
            headers=laptop_auth,
            json={
                "current_password": "motdepasse-solide",
                "new_password": "nouveau-mot-de-passe",
            },
        )
        assert changed.status_code == 204
        # The session that made the change survives; every other one dies.
        assert (await client.get("/v1/auth/me", headers=laptop_auth)).status_code == 200
        assert (await client.get("/v1/auth/me", headers=phone_auth)).status_code == 401


# -- sessions and devices --------------------------------------------------


@pytest.mark.asyncio
async def test_an_account_sees_and_revokes_only_its_own_sessions(app, client):
    async with client:
        await _signup(client)
        await client.post(
            "/v1/auth/signin",
            json={
                "email": "jean@alpha.tg",
                "password": "motdepasse-solide",
                "device_name": "Téléphone",
            },
        )
        sessions = (await client.get("/v1/auth/sessions")).json()
        assert {item["name"] for item in sessions} == {"Navigateur", "Téléphone"}
        assert sum(item["current"] for item in sessions) == 1

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as amina:
        await _signup(amina, "amina@beta.tg", "Entreprise Beta", "Amina")
        # Amina's list contains only her own device.
        hers = (await amina.get("/v1/auth/sessions")).json()
        assert [item["name"] for item in hers] == ["Navigateur"]
        # And she cannot revoke one of Jean's by id.
        stolen = await amina.delete(f"/v1/auth/sessions/{sessions[0]['device_id']}")
        assert stolen.status_code == 404


@pytest.mark.asyncio
async def test_the_device_limit_is_per_account_not_per_instance(app, client):
    """One company filling its seats must not lock another company out."""
    limit = app.state.settings.max_devices
    async with client:
        await _signup(client)
        for index in range(limit - 1):
            assert (await client.post(
                "/v1/auth/signin",
                json={
                    "email": "jean@alpha.tg",
                    "password": "motdepasse-solide",
                    "device_name": f"Appareil {index}",
                },
            )).status_code == 200
        over = await client.post(
            "/v1/auth/signin",
            json={
                "email": "jean@alpha.tg",
                "password": "motdepasse-solide",
                "device_name": "Un de trop",
            },
        )
        assert over.status_code == 409

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as amina:
        assert (await _signup(
            amina, "amina@beta.tg", "Entreprise Beta", "Amina"
        )).status_code == 201


# -- invitations -----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_owner_invites_a_colleague_who_joins_the_same_company(app, client):
    async with client:
        owner = (await _signup(client)).json()
        invited = await client.post(
            "/v1/auth/invitations", json={"email": "pierre@alpha.tg", "role": "manager"}
        )
        assert invited.status_code == 201, invited.text
        token = app.state.account_mailer.last("invitation")["token"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as pierre:
        # The join page shows what he was invited to, before he has an account.
        peek = await pierre.get("/v1/auth/invitations/peek", params={"token": token})
        assert peek.status_code == 200
        assert peek.json()["company_name"] == "Entreprise Alpha"
        assert peek.json()["role"] == "manager"

        joined = await pierre.post(
            "/v1/auth/invitations/accept",
            json={
                "token": token,
                "password": "motdepasse-pierre",
                "display_name": "Pierre",
            },
        )
        assert joined.status_code == 201, joined.text
        body = joined.json()
        assert body["tenant_id"] == owner["tenant_id"], "he must land in Alpha"
        assert body["role"] == "manager"
        assert body["email"] == "pierre@alpha.tg", "the address is the invited one"
        assert body["email_verified"] is True, "following the link proves the address"


@pytest.mark.asyncio
async def test_an_invitation_cannot_be_redeemed_twice(app, client):
    async with client:
        await _signup(client)
        await client.post("/v1/auth/invitations", json={"email": "pierre@alpha.tg"})
        token = app.state.account_mailer.last("invitation")["token"]

    payload = {
        "token": token,
        "password": "motdepasse-pierre",
        "display_name": "Pierre",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as guest:
        assert (await guest.post("/v1/auth/invitations/accept", json=payload)).status_code == 201
        second = await guest.post("/v1/auth/invitations/accept", json=payload)
        assert second.status_code == 400, "a spent link must not create a second seat"


@pytest.mark.asyncio
async def test_a_revoked_invitation_stops_working(app, client):
    async with client:
        await _signup(client)
        created = (await client.post(
            "/v1/auth/invitations", json={"email": "pierre@alpha.tg"}
        )).json()
        token = app.state.account_mailer.last("invitation")["token"]
        assert (await client.delete(
            f"/v1/auth/invitations/{created['invitation_id']}"
        )).status_code == 204

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as guest:
        assert (await guest.get(
            "/v1/auth/invitations/peek", params={"token": token}
        )).status_code == 404
        assert (await guest.post(
            "/v1/auth/invitations/accept",
            json={"token": token, "password": "motdepasse-pierre", "display_name": "P"},
        )).status_code == 400


@pytest.mark.asyncio
async def test_one_company_cannot_revoke_another_s_invitation(app, client):
    async with client:
        await _signup(client)
        alpha_invite = (await client.post(
            "/v1/auth/invitations", json={"email": "pierre@alpha.tg"}
        )).json()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as amina:
        await _signup(amina, "amina@beta.tg", "Entreprise Beta", "Amina")
        assert (await amina.delete(
            f"/v1/auth/invitations/{alpha_invite['invitation_id']}"
        )).status_code == 404
        # And Beta's list does not mention Alpha's invitation at all.
        assert (await amina.get("/v1/auth/invitations")).json() == []


@pytest.mark.asyncio
async def test_nobody_can_be_invited_as_an_owner(client):
    async with client:
        await _signup(client)
        response = await client.post(
            "/v1/auth/invitations", json={"email": "pierre@alpha.tg", "role": "owner"}
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_an_invitation_is_refused_for_an_address_that_already_has_an_account(app, client):
    async with client:
        await _signup(client)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as amina:
        await _signup(amina, "amina@beta.tg", "Entreprise Beta", "Amina")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as jean:
        await jean.post(
            "/v1/auth/signin",
            json={"email": "jean@alpha.tg", "password": "motdepasse-solide"},
        )
        # Amina belongs to Beta; Alpha cannot pull her in with an invitation.
        assert (await jean.post(
            "/v1/auth/invitations", json={"email": "amina@beta.tg"}
        )).status_code == 409


# -- membership ------------------------------------------------------------


@pytest.mark.asyncio
async def test_members_lists_only_the_caller_s_company(app, client):
    async with client:
        await _signup(client)
        await client.post("/v1/auth/invitations", json={"email": "pierre@alpha.tg"})
        token = app.state.account_mailer.last("invitation")["token"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as pierre:
        await pierre.post(
            "/v1/auth/invitations/accept",
            json={"token": token, "password": "motdepasse-pierre", "display_name": "Pierre"},
        )
        alpha_members = (await pierre.get("/v1/auth/members")).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as amina:
        await _signup(amina, "amina@beta.tg", "Entreprise Beta", "Amina")
        beta_members = (await amina.get("/v1/auth/members")).json()

    assert {m["email"] for m in alpha_members} == {"jean@alpha.tg", "pierre@alpha.tg"}
    assert {m["email"] for m in beta_members} == {"amina@beta.tg"}


@pytest.mark.asyncio
async def test_suspending_a_colleague_ends_their_access_immediately(app, client):
    async with client:
        await _signup(client)
        await client.post("/v1/auth/invitations", json={"email": "pierre@alpha.tg"})
        token = app.state.account_mailer.last("invitation")["token"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as pierre:
        joined = await pierre.post(
            "/v1/auth/invitations/accept",
            json={"token": token, "password": "motdepasse-pierre", "display_name": "Pierre"},
        )
        pierre_id = joined.json()["user_id"]
        pierre_session = joined.cookies["emefa_session"]
        assert (await pierre.get("/v1/auth/me")).status_code == 200

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as jean:
            await jean.post(
                "/v1/auth/signin",
                json={"email": "jean@alpha.tg", "password": "motdepasse-solide"},
            )
            suspended = await jean.patch(
                f"/v1/auth/members/{pierre_id}/status", json={"status": "suspended"}
            )
            assert suspended.status_code == 200

        # His live session stops working straight away, not at expiry.
        assert (await pierre.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {pierre_session}"}
        )).status_code == 401
        # And he cannot sign back in.
        assert (await pierre.post(
            "/v1/auth/signin",
            json={"email": "pierre@alpha.tg", "password": "motdepasse-pierre"},
        )).status_code == 401


@pytest.mark.asyncio
async def test_a_company_cannot_be_left_without_an_owner(app, client):
    async with client:
        owner = (await _signup(client)).json()
        # Changing your own role is refused outright.
        assert (await client.patch(
            f"/v1/auth/members/{owner['user_id']}/role", json={"role": "viewer"}
        )).status_code == 422
        assert (await client.patch(
            f"/v1/auth/members/{owner['user_id']}/status", json={"status": "suspended"}
        )).status_code == 422


@pytest.mark.asyncio
async def test_a_manager_cannot_invite_or_re_role_anyone(app, client):
    """MANAGE_MEMBERS is an admin permission, checked on the server."""
    async with client:
        await _signup(client)
        await client.post(
            "/v1/auth/invitations", json={"email": "pierre@alpha.tg", "role": "manager"}
        )
        token = app.state.account_mailer.last("invitation")["token"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as pierre:
        joined = await pierre.post(
            "/v1/auth/invitations/accept",
            json={"token": token, "password": "motdepasse-pierre", "display_name": "Pierre"},
        )
        assert joined.json()["role"] == "manager"
        refused = await pierre.post(
            "/v1/auth/invitations", json={"email": "autre@alpha.tg"}
        )
        assert refused.status_code == 403
        assert (await pierre.get("/v1/auth/invitations")).status_code == 403


def test_the_permission_matrix_says_what_we_think_it_says():
    """A change to who can do what should be a deliberate edit, not a surprise."""
    assert allows(Role.OWNER, Permission.MANAGE_TENANT)
    assert not allows(Role.ADMIN, Permission.MANAGE_TENANT)
    assert allows(Role.ADMIN, Permission.MANAGE_MEMBERS)
    assert not allows(Role.MANAGER, Permission.MANAGE_MEMBERS)
    assert allows(Role.MANAGER, Permission.DELETE_BUSINESS)
    assert not allows(Role.MEMBER, Permission.DELETE_BUSINESS)
    assert allows(Role.MEMBER, Permission.WRITE_BUSINESS)
    assert not allows(Role.VIEWER, Permission.WRITE_BUSINESS)
    assert allows(Role.VIEWER, Permission.READ_BUSINESS)
    # A read-only seat cannot drive the assistant into doing work either.
    assert not allows(Role.VIEWER, Permission.USE_ASSISTANT)
    assert not allows(Role.VIEWER, Permission.APPROVE_ACTIONS)


# -- the repository directly -----------------------------------------------


def test_the_seeded_single_tenant_user_cannot_be_logged_into(tmp_path):
    """The existing deployment has a passwordless user row. It must not be
    an account anyone can authenticate as."""
    accounts = AccountRepository(tmp_path / "seeded.db")
    assert accounts.get(storage.DEFAULT_USER_ID) is not None
    assert accounts.authenticate("", "") is None
    assert accounts.find_by_email("") is None


def test_accepting_an_invitation_with_an_expired_token_is_refused(tmp_path):
    accounts = AccountRepository(tmp_path / "expiry.db")
    created = accounts.sign_up(
        email="jean@alpha.tg", password="motdepasse-solide",
        display_name="Jean", company_name="Alpha",
    )
    _, token = accounts.invite(
        tenant_id=created.account.tenant_id, email="pierre@alpha.tg",
        role=Role.MEMBER, invited_by_user_id=created.account.user_id,
    )
    with storage.connect(tmp_path / "expiry.db") as connection:
        connection.execute("UPDATE invitations SET expires_at = '2020-01-01T00:00:00+00:00'")
    assert accounts.peek_invitation(token) is None
    with pytest.raises(InvalidTokenError):
        accounts.accept_invitation(
            token=token, password="motdepasse-pierre", display_name="Pierre"
        )


def test_an_expired_verification_token_is_refused(tmp_path):
    accounts = AccountRepository(tmp_path / "stale.db")
    created = accounts.sign_up(
        email="jean@alpha.tg", password="motdepasse-solide",
        display_name="Jean", company_name="Alpha",
    )
    with storage.connect(tmp_path / "stale.db") as connection:
        connection.execute("UPDATE auth_tokens SET expires_at = '2020-01-01T00:00:00+00:00'")
    with pytest.raises(InvalidTokenError):
        accounts.verify_email(created.verification_token)


def test_signing_up_twice_on_one_address_leaves_no_orphan_company(tmp_path):
    """A failed signup must not leave a company nobody can log into."""
    database = tmp_path / "atomic.db"
    accounts = AccountRepository(database)
    accounts.sign_up(
        email="jean@alpha.tg", password="motdepasse-solide",
        display_name="Jean", company_name="Alpha",
    )
    with pytest.raises(EmailAlreadyRegisteredError):
        accounts.sign_up(
            email="jean@alpha.tg", password="motdepasse-solide",
            display_name="Jean", company_name="Alpha bis",
        )
    with storage.connect(database) as connection:
        names = [row[0] for row in connection.execute("SELECT name FROM tenants")]
    assert "Alpha bis" not in names
