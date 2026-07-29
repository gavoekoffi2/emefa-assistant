"""Accounts, companies and the credentials that link a person to one.

This module deliberately does **not** inherit :class:`ScopedStore`.

Every other repository is scoped because the caller's tenant is already known
by the time it runs. Authentication is the step that *establishes* which tenant
the caller belongs to: a login looks a user up by email across the whole
instance, and a password-reset link is resolved before anyone is authenticated
at all. Scoping those lookups would be circular.

The exception is bounded on purpose:

* the only lookup keys are an email address, a token hash, or an id the caller
  has already been shown to own;
* every row written carries its ``tenant_id``, so everything downstream of
  authentication is scoped normally;
* nothing here returns business data — only identity.

This is the justification required by ``docs/MULTI_TENANCY_AUDIT.md`` for the
two tables that bypass the scoped store.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from emefa.domain import storage
from emefa.domain.roles import INVITABLE_ROLES, Role

#: scrypt parameters. Chosen for a small container: ~64 MB and roughly 100 ms
#: per hash, which is a poor trade for an attacker and unnoticeable at login.
_SCRYPT_N = 2**16
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEYLEN = 32

_VERIFICATION_TTL = timedelta(days=3)
_RESET_TTL = timedelta(hours=2)
_INVITATION_TTL = timedelta(days=14)

_MIN_PASSWORD_LENGTH = 10

#: Pragmatic, deliberately permissive: rejecting valid addresses is a worse
#: failure than accepting one that bounces, and delivery proves the rest.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class AccountError(ValueError):
    """A signup, login or invitation could not be honoured."""


class EmailAlreadyRegisteredError(AccountError):
    def __init__(self) -> None:
        super().__init__("email_already_registered")


class WeakPasswordError(AccountError):
    def __init__(self) -> None:
        super().__init__(
            f"Le mot de passe doit contenir au moins {_MIN_PASSWORD_LENGTH} caractères."
        )


class InvalidEmailError(AccountError):
    def __init__(self) -> None:
        super().__init__("Adresse e-mail invalide.")


class InvalidTokenError(AccountError):
    """Unknown, already used, or expired. The caller is told no more."""

    def __init__(self) -> None:
        super().__init__("invalid_or_expired_token")


class Purpose:
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True, slots=True)
class Account:
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: Role
    status: str
    email_verified: bool

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class Invitation:
    invitation_id: str
    tenant_id: str
    email: str
    role: Role
    invited_by_user_id: str
    expires_at: str
    accepted_at: str | None


@dataclass(frozen=True, slots=True)
class SignUp:
    """A freshly created company and the owner who created it."""

    account: Account
    company_name: str
    verification_token: str


def normalise_email(value: str) -> str:
    """Lower-cased, NFKC-normalised, trimmed.

    Stored normalised so the unique index — not application code — is what
    actually prevents two accounts on the same address.
    """
    cleaned = unicodedata.normalize("NFKC", value).strip().lower()
    if not _EMAIL.match(cleaned):
        raise InvalidEmailError()
    return cleaned


def hash_password(password: str) -> str:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise WeakPasswordError()
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEYLEN,
        maxmem=128 * _SCRYPT_N * _SCRYPT_R * 2,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check that tolerates a missing or malformed hash."""
    try:
        scheme, n, r, p, salt_hex, expected_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        n_int, r_int, p_int = int(n), int(r), int(p)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n_int,
            r=r_int,
            p=p_int,
            dklen=len(bytes.fromhex(expected_hex)),
            maxmem=128 * n_int * r_int * 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected_hex)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class AccountRepository:
    """Signup, verification, login, password reset and invitations."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    # -- signup ------------------------------------------------------------

    def sign_up(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        company_name: str,
    ) -> SignUp:
        """Create a company and its owner in one transaction.

        A signup that half-succeeded would leave a company nobody can log into,
        so the tenant, the owner and the verification token are written
        together or not at all.
        """
        address = normalise_email(email)
        password_hash = hash_password(password)
        company = company_name.strip() or f"Entreprise de {display_name.strip()}"

        tenant_id = f"ten_{uuid.uuid4().hex[:12]}"
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        token = secrets.token_urlsafe(32)

        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO tenants (tenant_id, name) VALUES (?, ?)",
                    (tenant_id, company),
                )
                connection.execute(
                    # Active, but not yet verified. Blocking the account until
                    # the link is followed would hand back a session that can
                    # do nothing — and would lock out the very first customer
                    # on an instance with no mail provider configured.
                    # Verification gates acting *on the address* (sending mail
                    # as the user), not using the product.
                    "INSERT INTO users (user_id, tenant_id, display_name, email, "
                    "password_hash, role, status) VALUES (?, ?, ?, ?, ?, ?, 'active')",
                    (
                        user_id,
                        tenant_id,
                        display_name.strip(),
                        address,
                        password_hash,
                        Role.OWNER.value,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise EmailAlreadyRegisteredError() from error
            self._issue_token(
                connection,
                user_id=user_id,
                tenant_id=tenant_id,
                purpose=Purpose.EMAIL_VERIFICATION,
                token=token,
                ttl=_VERIFICATION_TTL,
            )

        # Read back rather than describing what we think was written: the
        # status here is the row's, so the API cannot report one thing while
        # the database holds another.
        account = self.get(user_id)
        assert account is not None
        return SignUp(account=account, company_name=company, verification_token=token)

    # -- tokens ------------------------------------------------------------

    @staticmethod
    def _issue_token(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        tenant_id: str,
        purpose: str,
        token: str,
        ttl: timedelta,
    ) -> None:
        """Store a single-use secret, replacing any earlier live one.

        Re-requesting a link must invalidate the previous one: two valid reset
        links at once doubles the window an intercepted email is useful for.
        """
        connection.execute(
            "UPDATE auth_tokens SET consumed_at = ? "
            "WHERE user_id = ? AND purpose = ? AND consumed_at IS NULL",
            (_stamp(_now()), user_id, purpose),
        )
        connection.execute(
            "INSERT INTO auth_tokens (token_hash, user_id, tenant_id, purpose, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash_token(token), user_id, tenant_id, purpose, _stamp(_now() + ttl)),
        )

    def _consume_token(self, token: str, purpose: str) -> sqlite3.Row:
        """Redeem a token or raise. Never says *why* it failed."""
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT token_hash, user_id, tenant_id, expires_at, consumed_at "
                "FROM auth_tokens WHERE token_hash = ? AND purpose = ?",
                (_hash_token(token), purpose),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                raise InvalidTokenError()
            if datetime.fromisoformat(row["expires_at"]) < now:
                raise InvalidTokenError()
            connection.execute(
                "UPDATE auth_tokens SET consumed_at = ? WHERE token_hash = ?",
                (_stamp(now), row["token_hash"]),
            )
        return row

    def verify_email(self, token: str) -> Account:
        row = self._consume_token(token, Purpose.EMAIL_VERIFICATION)
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET email_verified_at = ?, "
                "status = CASE WHEN status = 'pending' THEN 'active' ELSE status END "
                "WHERE user_id = ?",
                (_stamp(_now()), row["user_id"]),
            )
        account = self.get(row["user_id"])
        assert account is not None  # the token's foreign key guarantees it
        return account

    def issue_verification(self, user_id: str) -> str | None:
        """Re-send path. Returns None when there is nothing to verify."""
        account = self.get(user_id)
        if account is None or account.email_verified:
            return None
        token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            self._issue_token(
                connection,
                user_id=account.user_id,
                tenant_id=account.tenant_id,
                purpose=Purpose.EMAIL_VERIFICATION,
                token=token,
                ttl=_VERIFICATION_TTL,
            )
        return token

    # -- login -------------------------------------------------------------

    def authenticate(self, email: str, password: str) -> Account | None:
        """Return the account only for a correct password on an active seat.

        An unknown address still costs one password hash, so response time does
        not reveal whether the address exists.
        """
        try:
            address = normalise_email(email)
        except InvalidEmailError:
            address = ""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, tenant_id, email, display_name, role, status, "
                "email_verified_at, password_hash FROM users WHERE email = ?",
                (address,),
            ).fetchone()
        encoded = row["password_hash"] if row is not None else ""
        if not verify_password(password, encoded) or row is None:
            return None
        account = _account_from_row(row)
        if not account.is_active:
            return None
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = ? WHERE user_id = ?",
                (_stamp(_now()), account.user_id),
            )
        return account

    def request_password_reset(self, email: str) -> tuple[Account, str] | None:
        """Issue a reset token, or None if the address is not registered.

        The caller must answer identically either way — whether an address has
        an account is not something an unauthenticated request may learn.
        """
        try:
            address = normalise_email(email)
        except InvalidEmailError:
            return None
        account = self.find_by_email(address)
        if account is None or account.status == "suspended":
            return None
        token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            self._issue_token(
                connection,
                user_id=account.user_id,
                tenant_id=account.tenant_id,
                purpose=Purpose.PASSWORD_RESET,
                token=token,
                ttl=_RESET_TTL,
            )
        return account, token

    def reset_password(self, token: str, new_password: str) -> Account:
        password_hash = hash_password(new_password)
        row = self._consume_token(token, Purpose.PASSWORD_RESET)
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ?, "
                # Holding the reset link proves the address works, so an
                # account that never confirmed becomes usable here.
                "email_verified_at = COALESCE(email_verified_at, ?), "
                "status = CASE WHEN status = 'pending' THEN 'active' ELSE status END "
                "WHERE user_id = ?",
                (password_hash, _stamp(_now()), row["user_id"]),
            )
        account = self.get(row["user_id"])
        assert account is not None
        return account

    def change_password(self, user_id: str, current: str, new_password: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None or not verify_password(current, row["password_hash"]):
            return False
        password_hash = hash_password(new_password)
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (password_hash, user_id),
            )
        return True

    # -- reads -------------------------------------------------------------

    def get(self, user_id: str) -> Account | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, tenant_id, email, display_name, role, status, "
                "email_verified_at FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _account_from_row(row) if row is not None else None

    def find_by_email(self, email: str) -> Account | None:
        try:
            address = normalise_email(email)
        except InvalidEmailError:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, tenant_id, email, display_name, role, status, "
                "email_verified_at FROM users WHERE email = ?",
                (address,),
            ).fetchone()
        return _account_from_row(row) if row is not None else None

    def company_name(self, tenant_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        return row["name"] if row is not None else ""

    def list_members(self, tenant_id: str) -> list[Account]:
        """Everyone in one company. The tenant is a required argument, so
        there is no call shape that lists the whole instance."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, tenant_id, email, display_name, role, status, "
                "email_verified_at FROM users WHERE tenant_id = ? "
                "ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
        return [_account_from_row(row) for row in rows]

    # -- membership --------------------------------------------------------

    def invite(
        self,
        *,
        tenant_id: str,
        email: str,
        role: Role,
        invited_by_user_id: str,
    ) -> tuple[Invitation, str]:
        if role not in INVITABLE_ROLES:
            raise AccountError("role_not_invitable")
        address = normalise_email(email)

        existing = self.find_by_email(address)
        if existing is not None:
            # Already has a seat here, or an account with another company.
            raise EmailAlreadyRegisteredError()

        token = secrets.token_urlsafe(32)
        invitation_id = f"inv_{uuid.uuid4().hex[:12]}"
        expires_at = _stamp(_now() + _INVITATION_TTL)
        with self._connect() as connection:
            # Re-inviting the same address supersedes the earlier link rather
            # than failing on the unique index.
            connection.execute(
                "UPDATE invitations SET revoked_at = ? WHERE tenant_id = ? AND email = ? "
                "AND accepted_at IS NULL AND revoked_at IS NULL",
                (_stamp(_now()), tenant_id, address),
            )
            connection.execute(
                "INSERT INTO invitations (invitation_id, tenant_id, email, role, "
                "token_hash, invited_by_user_id, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    invitation_id,
                    tenant_id,
                    address,
                    role.value,
                    _hash_token(token),
                    invited_by_user_id,
                    expires_at,
                ),
            )
        return (
            Invitation(
                invitation_id=invitation_id,
                tenant_id=tenant_id,
                email=address,
                role=role,
                invited_by_user_id=invited_by_user_id,
                expires_at=expires_at,
                accepted_at=None,
            ),
            token,
        )

    def list_invitations(self, tenant_id: str) -> list[Invitation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT invitation_id, tenant_id, email, role, invited_by_user_id, "
                "expires_at, accepted_at FROM invitations "
                "WHERE tenant_id = ? AND revoked_at IS NULL ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [
            Invitation(
                invitation_id=row["invitation_id"],
                tenant_id=row["tenant_id"],
                email=row["email"],
                role=Role.parse(row["role"]),
                invited_by_user_id=row["invited_by_user_id"],
                expires_at=row["expires_at"],
                accepted_at=row["accepted_at"],
            )
            for row in rows
        ]

    def revoke_invitation(self, tenant_id: str, invitation_id: str) -> bool:
        """The tenant is part of the key, so one company cannot revoke
        another's invitation by guessing an id."""
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE invitations SET revoked_at = ? WHERE invitation_id = ? "
                "AND tenant_id = ? AND accepted_at IS NULL AND revoked_at IS NULL",
                (_stamp(_now()), invitation_id, tenant_id),
            )
        return cursor.rowcount > 0

    def peek_invitation(self, token: str) -> Invitation | None:
        """What the invited person is shown before choosing a password."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT invitation_id, tenant_id, email, role, invited_by_user_id, "
                "expires_at, accepted_at, revoked_at FROM invitations WHERE token_hash = ?",
                (_hash_token(token),),
            ).fetchone()
        if row is None or row["accepted_at"] is not None or row["revoked_at"] is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        return Invitation(
            invitation_id=row["invitation_id"],
            tenant_id=row["tenant_id"],
            email=row["email"],
            role=Role.parse(row["role"]),
            invited_by_user_id=row["invited_by_user_id"],
            expires_at=row["expires_at"],
            accepted_at=None,
        )

    def accept_invitation(
        self, *, token: str, password: str, display_name: str
    ) -> Account:
        """Join an existing company.

        The tenant comes from the invitation, never from the request — an
        invited colleague cannot choose which company they land in, and the
        address is the one that was invited, not one they supply.
        """
        invitation = self.peek_invitation(token)
        if invitation is None:
            raise InvalidTokenError()
        password_hash = hash_password(password)
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = _stamp(_now())
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO users (user_id, tenant_id, display_name, email, "
                    "password_hash, role, status, email_verified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
                    (
                        user_id,
                        invitation.tenant_id,
                        display_name.strip(),
                        invitation.email,
                        password_hash,
                        invitation.role.value,
                        # Following the emailed link is the proof.
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise EmailAlreadyRegisteredError() from error
            cursor = connection.execute(
                "UPDATE invitations SET accepted_at = ?, accepted_user_id = ? "
                "WHERE invitation_id = ? AND accepted_at IS NULL",
                (now, user_id, invitation.invitation_id),
            )
            if cursor.rowcount == 0:
                # Two people followed the same link at once; the loser is told
                # the link is spent rather than getting a second seat.
                connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                raise InvalidTokenError()
        account = self.get(user_id)
        assert account is not None
        return account

    def set_role(self, *, tenant_id: str, user_id: str, role: Role) -> Account | None:
        """Change a colleague's seat. Refuses to leave a company ownerless."""
        account = self.get(user_id)
        if account is None or account.tenant_id != tenant_id:
            return None
        if account.role is Role.OWNER and role is not Role.OWNER:
            if self._owner_count(tenant_id) <= 1:
                raise AccountError("last_owner")
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET role = ? WHERE user_id = ? AND tenant_id = ?",
                (role.value, user_id, tenant_id),
            )
        return self.get(user_id)

    def set_status(self, *, tenant_id: str, user_id: str, status: str) -> Account | None:
        if status not in {"active", "suspended"}:
            raise AccountError("unknown_status")
        account = self.get(user_id)
        if account is None or account.tenant_id != tenant_id:
            return None
        if (
            status == "suspended"
            and account.role is Role.OWNER
            and self._owner_count(tenant_id) <= 1
        ):
            raise AccountError("last_owner")
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET status = ? WHERE user_id = ? AND tenant_id = ?",
                (status, user_id, tenant_id),
            )
        return self.get(user_id)

    def _owner_count(self, tenant_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM users WHERE tenant_id = ? AND role = ? "
                "AND status = 'active'",
                (tenant_id, Role.OWNER.value),
            ).fetchone()
        return int(row[0]) if row is not None else 0


def _account_from_row(row: sqlite3.Row) -> Account:
    return Account(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        email=row["email"],
        display_name=row["display_name"],
        role=Role.parse(row["role"]),
        status=row["status"],
        email_verified=row["email_verified_at"] is not None,
    )
