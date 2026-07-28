"""WebAuthn ceremony options and signature verification.

Delegated to `py_webauthn` rather than hand-rolled. Verifying an attestation
means parsing CBOR, decoding a COSE key and checking an ECDSA signature over a
concatenation with exact byte semantics — a security boundary where a subtle
mistake is silent, and the wrong place to demonstrate ambition.

The verifier is injected wherever it is used, so the API can be exercised
without a physical authenticator. What a test cannot cover is the signature
check itself: that needs a real secure enclave, and pretending otherwise with
a fake signature would test the stub instead of the security property. It is
covered by the library's own suite, and by trying it on a real device.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True, slots=True)
class VerifiedRegistration:
    credential_id: str
    public_key: str
    sign_count: int


@dataclass(frozen=True, slots=True)
class VerifiedAssertion:
    credential_id: str
    sign_count: int


class WebAuthnVerifier(Protocol):
    def registration_options(
        self, account_id: str, email: str, display_name: str, challenge: str
    ) -> dict[str, Any]: ...

    def verify_registration(self, response: dict[str, Any], challenge: str) -> VerifiedRegistration: ...

    def authentication_options(
        self, challenge: str, credential_ids: list[str]
    ) -> dict[str, Any]: ...

    def verify_assertion(
        self, response: dict[str, Any], challenge: str, public_key: str, sign_count: int
    ) -> VerifiedAssertion: ...


class LibraryVerifier:
    def __init__(self, rp_id: str, rp_name: str, origin: str) -> None:
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin

    def registration_options(
        self, account_id: str, email: str, display_name: str, challenge: str
    ) -> dict[str, Any]:
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=account_id.encode("utf-8"),
            user_name=email,
            user_display_name=display_name or email,
            challenge=_unb64(challenge),
            authenticator_selection=AuthenticatorSelectionCriteria(
                # Platform, not roaming: the point is the face unlock the
                # device already has, backed by its secure enclave.
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                # Required, not preferred. "Preferred" silently degrades to a
                # credential that proves possession of the device and nothing
                # about who is holding it — which is not a second factor.
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        import json

        return json.loads(options_to_json(options))

    def verify_registration(
        self, response: dict[str, Any], challenge: str
    ) -> VerifiedRegistration:
        verified = verify_registration_response(
            credential=response,
            expected_challenge=_unb64(challenge),
            expected_origin=self.origin,
            expected_rp_id=self.rp_id,
            require_user_verification=True,
        )
        return VerifiedRegistration(
            credential_id=_b64(verified.credential_id),
            public_key=_b64(verified.credential_public_key),
            sign_count=int(verified.sign_count),
        )

    def authentication_options(
        self, challenge: str, credential_ids: list[str]
    ) -> dict[str, Any]:
        options = generate_authentication_options(
            rp_id=self.rp_id,
            challenge=_unb64(challenge),
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=_unb64(identifier))
                for identifier in credential_ids
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        import json

        return json.loads(options_to_json(options))

    def verify_assertion(
        self, response: dict[str, Any], challenge: str, public_key: str, sign_count: int
    ) -> VerifiedAssertion:
        verified = verify_authentication_response(
            credential=response,
            expected_challenge=_unb64(challenge),
            expected_origin=self.origin,
            expected_rp_id=self.rp_id,
            credential_public_key=_unb64(public_key),
            credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
        return VerifiedAssertion(
            credential_id=_b64(verified.credential_id),
            sign_count=int(verified.new_sign_count),
        )
