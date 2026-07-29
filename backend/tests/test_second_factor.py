"""Face unlock as a second factor (ADR-005).

Signature verification itself is not tested here and cannot be: it needs a
real secure enclave, and asserting against a fabricated signature would test
the stub rather than the security property. It is delegated to `py_webauthn`
and exercised on a real device.

What *is* tested is everything the server owns and could get wrong: challenge
single-use and expiry, the account binding coming from storage rather than
from the client, clone detection, step-up lifetime, revocation, and the
enforcement point.
"""

from datetime import timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.accounts import AccountRepository
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.secondfactor import (
    AUTHENTICATION,
    CHALLENGE_TTL_SECONDS,
    REGISTRATION,
    STEP_UP_TTL_SECONDS,
    SecondFactorError,
    SecondFactorRepository,
    _stamp,
    _now,
)
from emefa.infrastructure.webauthn_verifier import VerifiedAssertion, VerifiedRegistration
from emefa.main import create_app

PASSWORD = "correct-horse-battery"


class StubVerifier:
    """Stands in for the enclave. Everything it returns is what a real
    authenticator would have returned after the OS verified the user."""

    def __init__(self, credential_id="cred-1", sign_count=0):
        self.credential_id = credential_id
        self.sign_count = sign_count
        self.fail = False

    def registration_options(self, account_id, email, display_name, challenge):
        return {"challenge": challenge, "rp": {"id": "localhost"}}

    def verify_registration(self, response, challenge):
        if self.fail:
            raise ValueError("bad attestation")
        return VerifiedRegistration(self.credential_id, "public-key-bytes", self.sign_count)

    def authentication_options(self, challenge, credential_ids):
        return {"challenge": challenge, "allowCredentials": credential_ids}

    def verify_assertion(self, response, challenge, public_key, sign_count):
        if self.fail:
            raise ValueError("bad signature")
        return VerifiedAssertion(self.credential_id, self.sign_count)


# ── the server's own invariants ───────────────────────────────────────────


def test_a_challenge_is_single_use(tmp_path):
    """A captured assertion must not be replayable."""
    factors = SecondFactorRepository(tmp_path / "challenge.db")
    challenge = factors.issue_challenge(AUTHENTICATION, "acc-1")

    assert factors.consume_challenge(challenge, AUTHENTICATION) == "acc-1"
    with pytest.raises(SecondFactorError):
        factors.consume_challenge(challenge, AUTHENTICATION)


def test_a_challenge_expires(tmp_path):
    database = tmp_path / "expiry.db"
    factors = SecondFactorRepository(database)
    challenge = factors.issue_challenge(AUTHENTICATION, "acc-1")

    from emefa.domain import storage

    with storage.connect(database) as connection:
        connection.execute(
            "UPDATE webauthn_challenges SET created_at = ? WHERE challenge = ?",
            (_stamp(_now() - timedelta(seconds=CHALLENGE_TTL_SECONDS + 5)), challenge),
        )
    with pytest.raises(SecondFactorError):
        factors.consume_challenge(challenge, AUTHENTICATION)


def test_a_challenge_cannot_be_used_for_the_other_ceremony(tmp_path):
    factors = SecondFactorRepository(tmp_path / "purpose.db")
    challenge = factors.issue_challenge(REGISTRATION, "acc-1")
    with pytest.raises(SecondFactorError):
        factors.consume_challenge(challenge, AUTHENTICATION)


def test_a_counter_that_goes_backwards_is_a_clone(tmp_path):
    factors = SecondFactorRepository(tmp_path / "counter.db")
    credential = factors.register("cred-1", "acc-1", "key", "MacBook", sign_count=7)

    factors.check_counter(credential, 8)  # forward is fine
    with pytest.raises(SecondFactorError):
        factors.check_counter(credential, 7)
    with pytest.raises(SecondFactorError):
        factors.check_counter(credential, 3)


def test_authenticators_that_do_not_count_are_not_treated_as_clones(tmp_path):
    """Many platform authenticators never implement a counter. Refusing zero
    would lock out every Apple device."""
    factors = SecondFactorRepository(tmp_path / "zero.db")
    credential = factors.register("cred-1", "acc-1", "key", sign_count=0)
    factors.check_counter(credential, 0)


def test_the_counter_only_moves_forward(tmp_path):
    factors = SecondFactorRepository(tmp_path / "advance.db")
    factors.register("cred-1", "acc-1", "key", sign_count=5)
    factors.record_use("cred-1", 9)
    assert factors.get("cred-1").sign_count == 9
    factors.record_use("cred-1", 2)
    assert factors.get("cred-1").sign_count == 9


def test_revocation_is_scoped_to_the_owning_account(tmp_path):
    factors = SecondFactorRepository(tmp_path / "revoke.db")
    factors.register("cred-1", "acc-1", "key")

    assert factors.revoke("cred-1", "acc-2") is False, "a credential id is not a capability"
    assert factors.revoke("cred-1", "acc-1") is True
    assert factors.enrolled("acc-1") is False


def test_a_step_up_expires(tmp_path):
    database = tmp_path / "stepup.db"
    factors = SecondFactorRepository(database)
    from emefa.domain.devices import DeviceRepository

    device, _token = DeviceRepository(database).enroll("Navigateur", "acc-1")

    assert factors.verified_recently(device.device_id) is False
    factors.mark_verified(device.device_id)
    assert factors.verified_recently(device.device_id) is True

    from emefa.domain import storage

    with storage.connect(database) as connection:
        connection.execute(
            "UPDATE devices SET second_factor_at = ? WHERE device_id = ?",
            (_stamp(_now() - timedelta(seconds=STEP_UP_TTL_SECONDS + 5)), device.device_id),
        )
    assert factors.verified_recently(device.device_id) is False


def test_no_biometric_data_is_stored(tmp_path):
    """The property the whole design exists for: what is kept is a public key,
    not a face."""
    database = tmp_path / "storage.db"
    SecondFactorRepository(database).register("cred-1", "acc-1", "public-key", "iPhone")

    from emefa.domain import storage

    with storage.connect(database) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(webauthn_credentials)")
        }
    assert "public_key" in columns
    assert not {"image", "template", "embedding", "descriptor"} & columns


# ── through the API ───────────────────────────────────────────────────────


async def signed_in(web, app, verifier=None):
    if verifier is not None:
        app.state.webauthn = verifier
    await web.post(
        "/v1/auth/register",
        json={
            "email": "koffi@example.com",
            "password": PASSWORD,
            "enrollment_code": "CODE-SECRET",
        },
    )


def build_app(tmp_path, brain=None, name="factor.db"):
    class Default:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / name,
            cookie_secure=False,
        ),
        brain=brain or Default(),
    )


@pytest.mark.asyncio
async def test_enrol_verify_and_revoke(tmp_path):
    app = build_app(tmp_path)
    verifier = StubVerifier()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        # A second factor requires a first one: no session, no enrolment.
        assert (await web.post("/v1/auth/second-factor/register/options")).status_code == 401

        await signed_in(web, app, verifier)

        status = (await web.get("/v1/auth/second-factor")).json()
        assert status == {
            "enrolled": False,
            "verified": False,
            "step_up_seconds": STEP_UP_TTL_SECONDS,
            "credentials": [],
        }

        # Verifying before enrolling has nothing to verify against.
        assert (await web.post("/v1/auth/second-factor/verify/options")).status_code == 409

        options = (await web.post("/v1/auth/second-factor/register/options")).json()
        assert options["challenge_token"]

        registered = await web.post(
            "/v1/auth/second-factor/register",
            json={
                "credential": {"challenge_token": options["challenge_token"], "id": "cred-1"},
                "label": "MacBook de Koffi",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["label"] == "MacBook de Koffi"

        status = (await web.get("/v1/auth/second-factor")).json()
        assert status["enrolled"] is True
        # Enrolling proves presence, so it counts as a step-up.
        assert status["verified"] is True

        # Step up again.
        assertion = (await web.post("/v1/auth/second-factor/verify/options")).json()
        verifier.sign_count = 1
        verified = await web.post(
            "/v1/auth/second-factor/verify",
            json={
                "credential": {
                    "challenge_token": assertion["challenge_token"],
                    "id": "cred-1",
                }
            },
        )
        assert verified.status_code == 200
        assert verified.json()["verified"] is True

        credential_id = status["credentials"][0]["credential_id"]
        assert (
            await web.delete(f"/v1/auth/second-factor/{credential_id}")
        ).status_code == 204
        assert (await web.get("/v1/auth/second-factor")).json() == {
            "enrolled": False,
            # Removing the factor drops the step-up it granted.
            "verified": False,
            "step_up_seconds": STEP_UP_TTL_SECONDS,
            "credentials": [],
        }


@pytest.mark.asyncio
async def test_a_replayed_or_foreign_challenge_is_refused(tmp_path):
    app = build_app(tmp_path, name="replay.db")
    verifier = StubVerifier()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app, verifier)
        options = (await web.post("/v1/auth/second-factor/register/options")).json()
        body = {
            "credential": {"challenge_token": options["challenge_token"], "id": "cred-1"}
        }
        assert (await web.post("/v1/auth/second-factor/register", json=body)).status_code == 201
        # Same challenge again: single use.
        assert (await web.post("/v1/auth/second-factor/register", json=body)).status_code == 400
        # A challenge nobody issued.
        assert (
            await web.post(
                "/v1/auth/second-factor/register",
                json={"credential": {"challenge_token": "inventé", "id": "cred-2"}},
            )
        ).status_code == 400


@pytest.mark.asyncio
async def test_a_credential_belonging_to_someone_else_does_not_verify(tmp_path):
    """The account binding is read from our storage, never from the client."""
    database = tmp_path / "binding.db"
    app = build_app(tmp_path, name="binding.db")
    verifier = StubVerifier(credential_id="cred-other")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app, verifier)
        # A credential registered to a different account entirely.
        app.state.second_factor.register("cred-other", "acc-someone-else", "key")
        # And one for this account, so the ceremony can start.
        options = (await web.post("/v1/auth/second-factor/register/options")).json()
        verifier.credential_id = "cred-mine"
        await web.post(
            "/v1/auth/second-factor/register",
            json={"credential": {"challenge_token": options["challenge_token"]}},
        )

        assertion = (await web.post("/v1/auth/second-factor/verify/options")).json()
        refused = await web.post(
            "/v1/auth/second-factor/verify",
            json={
                "credential": {
                    "challenge_token": assertion["challenge_token"],
                    "id": "cred-other",
                }
            },
        )
    assert refused.status_code == 403
    assert AccountRepository(database).count() == 1


@pytest.mark.asyncio
async def test_a_failed_ceremony_says_nothing_useful(tmp_path):
    app = build_app(tmp_path, name="opaque.db")
    verifier = StubVerifier()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app, verifier)
        options = (await web.post("/v1/auth/second-factor/register/options")).json()
        verifier.fail = True
        failed = await web.post(
            "/v1/auth/second-factor/register",
            json={"credential": {"challenge_token": options["challenge_token"]}},
        )
    assert failed.status_code == 400
    # One message for every cause: telling an attacker which part failed helps
    # only them.
    assert failed.json()["detail"] == "registration_failed"


@pytest.mark.asyncio
async def test_an_enrolled_account_must_step_up_to_approve_an_action(tmp_path):
    """The enforcement point: the factor protects what is worth protecting."""

    class Brain:
        def __init__(self):
            self.turn = 0

        async def think(self, history, tools):
            self.turn += 1
            if self.turn == 1:
                return AgentStep(
                    action=RequestedAction(
                        name="forget_memory", arguments={"memory_id": "peu-importe"}
                    )
                )
            return AgentStep(answer="C'est fait.")

    app = build_app(tmp_path, Brain(), name="gate.db")
    verifier = StubVerifier()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app, verifier)
        options = (await web.post("/v1/auth/second-factor/register/options")).json()
        await web.post(
            "/v1/auth/second-factor/register",
            json={"credential": {"challenge_token": options["challenge_token"]}},
        )
        # Enrolment granted a step-up; drop it so the gate is exercised.
        session = await web.get("/v1/web/session")
        app.state.second_factor.clear_verification(session.json()["device_id"])

        run = (await web.post("/v1/agent/runs", json={"message": "Oublie ça"})).json()
        assert run["status"] == "confirmation_required"

        refused = await web.post(
            f"/v1/agent/approvals/{run['action_id']}/decision", json={"approve": True}
        )
        assert refused.status_code == 403
        assert refused.json()["detail"] == "second_factor_required"

        # Refusing must not consume the approval: it is still there afterwards.
        pending = (await web.get("/v1/agent/approvals")).json()
        assert [item["action_id"] for item in pending] == [run["action_id"]]

        # Rejecting an action never needs the factor — declining is always safe.
        assert (
            await web.post(
                f"/v1/agent/approvals/{run['action_id']}/decision", json={"approve": False}
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_approval_is_unaffected_when_no_factor_is_enrolled(tmp_path):
    """Nobody is locked out by a feature they have not switched on."""

    class Brain:
        def __init__(self):
            self.turn = 0

        async def think(self, history, tools):
            self.turn += 1
            if self.turn == 1:
                return AgentStep(
                    action=RequestedAction(
                        name="forget_memory", arguments={"memory_id": "peu-importe"}
                    )
                )
            return AgentStep(answer="C'est fait.")

    app = build_app(tmp_path, Brain(), name="nogate.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = (await web.post("/v1/agent/runs", json={"message": "Oublie ça"})).json()
        decided = await web.post(
            f"/v1/agent/approvals/{run['action_id']}/decision", json={"approve": True}
        )
    assert decided.status_code == 200


@pytest.mark.asyncio
async def test_revoking_a_credential_requires_a_recent_step_up(tmp_path):
    app = build_app(tmp_path, name="revoke-stepup.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app)
        account = app.state.accounts.by_email("koffi@example.com")
        credential = app.state.second_factor.register(
            "cred-delete", account.account_id, "public-key", "Téléphone"
        )
        refused = await web.delete(
            f"/v1/auth/second-factor/{credential.credential_id}"
        )
        assert refused.status_code == 403
        assert refused.json()["detail"] == "second_factor_required"
        assert app.state.second_factor.get(credential.credential_id) is not None

        device_id = (await web.get("/v1/web/session")).json()["device_id"]
        app.state.second_factor.mark_verified(device_id)
        assert (
            await web.delete(f"/v1/auth/second-factor/{credential.credential_id}")
        ).status_code == 204


@pytest.mark.asyncio
async def test_mission_approval_uses_the_same_recent_step_up_guard(tmp_path):
    app = build_app(tmp_path, name="mission-stepup.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await signed_in(web, app)
        account = app.state.accounts.by_email("koffi@example.com")
        app.state.second_factor.register("cred-mission", account.account_id, "key")
        refused = await web.post("/v1/missions/absent/steps/absent/approve")
        assert refused.status_code == 403
        assert refused.json()["detail"] == "second_factor_required"

        device_id = (await web.get("/v1/web/session")).json()["device_id"]
        app.state.second_factor.mark_verified(device_id)
        assert (
            await web.post("/v1/missions/absent/steps/absent/approve")
        ).status_code == 404
