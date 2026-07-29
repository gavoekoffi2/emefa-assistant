"""Account identity and password verification (ADR-002).

Before this, EMEFA authenticated *devices* enrolled with one shared code.
That is a transport credential with no person behind it: nothing downstream —
memory, initiatives, audit — could name who did something, and two humans
sharing an instance were indistinguishable.

Devices remain the transport. What they now carry is an account.

Passwords are hashed with scrypt from the standard library. The parameters are
stored inside each hash rather than read from configuration, so raising the
cost later strengthens new and rotated passwords without invalidating existing
ones — a stored hash always knows how to verify itself.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from emefa.domain import storage

#: scrypt cost parameters. n=2**15 with r=8 needs ~32 MB and a few tens of
#: milliseconds per verification — enough to make offline cracking expensive
#: without making a login noticeably slow.
_SCRYPT_N = 1 << 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
#: OpenSSL refuses scrypt above a 32 MB default, which n=2**15 with r=8 sits
#: exactly on. Raised explicitly rather than weakening the cost parameters.
_MAXMEM = 96 << 20

ROLES = ("owner", "member")
MIN_PASSWORD_CHARS = 10

_COLUMNS = (
    "account_id, tenant_id, user_id, email, display_name, role, status, "
    "created_at, last_login_at"
)


class WeakPasswordError(ValueError):
    """Raised rather than silently accepting a password that cannot protect
    anything."""


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    tenant_id: str
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str
    last_login_at: str | None


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$key`, all hex. Self-describing so the parameters can
    be raised later without a migration."""
    if len(password) < MIN_PASSWORD_CHARS:
        raise WeakPasswordError(
            f"password must be at least {MIN_PASSWORD_CHARS} characters"
        )
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
        maxmem=_MAXMEM,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification against a self-describing hash."""
    try:
        scheme, n, r, p, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(key_hex) // 2,
            maxmem=_MAXMEM,
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(key_hex))


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AccountRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])

    def create(
        self,
        email: str,
        password: str,
        display_name: str = "",
        role: str = "owner",
    ) -> Account:
        address = normalise_email(email)
        if "@" not in address or len(address) < 5:
            raise ValueError("invalid email address")
        if role not in ROLES:
            raise ValueError("unknown role")
        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO accounts "
                    "(account_id, email, password_hash, display_name, role) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        account_id,
                        address,
                        hash_password(password),
                        display_name.strip()[:120],
                        role,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("email already registered") from error
        found = self.get(account_id)
        assert found is not None
        return found

    def create_first_owner(self, email: str, password: str, display_name: str = "") -> Account:
        """Atomically claim the single owner slot.

        The v20 partial unique index is the final authority.  This method keeps
        validation/hash work outside no security boundary and maps every race
        loser to one stable error for the API.
        """
        return self.create(email, password, display_name, role="owner")

    def get(self, account_id: str) -> Account | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
        return _from_row(row)

    def by_email(self, email: str) -> Account | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM accounts WHERE email = ?",
                (normalise_email(email),),
            ).fetchone()
        return _from_row(row)

    def authenticate(self, email: str, password: str) -> Account | None:
        """Verify credentials. Returns None for unknown address, wrong
        password and suspended account alike — the caller must not be able to
        tell which, or the endpoint becomes an account enumerator."""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS}, password_hash FROM accounts WHERE email = ?",
                (normalise_email(email),),
            ).fetchone()
        if row is None:
            # Spend comparable time on an unknown address so response latency
            # does not reveal whether the account exists.
            verify_password(password, _decoy_hash())
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        if row["status"] != "active":
            return None
        self._touch_login(row["account_id"])
        return _from_row(row)

    def change_password(self, account_id: str, current: str, replacement: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if row is None or not verify_password(current, row["password_hash"]):
                return False
            connection.execute(
                "UPDATE accounts SET password_hash = ? WHERE account_id = ?",
                (hash_password(replacement), account_id),
            )
        return True

    def _touch_login(self, account_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE accounts SET last_login_at = ? WHERE account_id = ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), account_id),
            )


def _from_row(row: sqlite3.Row | None) -> Account | None:
    if row is None:
        return None
    return Account(
        account_id=row["account_id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        status=row["status"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


@functools.lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """A real hash of a value nobody knows, used only to keep the timing of a
    failed lookup comparable to a failed password. Built on first use rather
    than at import, so importing the module stays free."""
    return hash_password(secrets.token_urlsafe(32))
