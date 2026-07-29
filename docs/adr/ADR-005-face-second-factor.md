# ADR-005 — Face as a real second factor

> **Status:** Accepted · **Date:** 2026-07-28 · **Builds on:** ADR-002

## Context

The owner asked for face-based authentication as a **genuine second factor**, not a
greeting: a biometric profile created at registration, liveness detection resistant to a
photo or a screen, secure comparison, templates stored instead of raw images, revocable,
and complementary to the password and session rather than replacing them.

ADR-002 already rejected jarvis-OS's face scan, but only as an *identification* mechanism
— it gated nothing. This decision is about the harder question: what makes a face factor
actually hold.

## The trap

The obvious implementation is to compute a face embedding in the browser (MediaPipe,
`face-api.js`), send it to the server, and compare it against a stored template. It looks
like it meets every requirement on the list. It does not hold, for three reasons:

1. **The comparison input is attacker-controlled.** The embedding is computed by
   JavaScript on a device the attacker owns. Anyone who can open the developer console can
   `fetch()` the endpoint with a stored embedding and never show a face at all. A factor
   whose input the attacker supplies is not a second factor — it is a second password,
   with the unique defect that the user can never change it.
2. **Liveness in JavaScript is checked by the same attacker-controlled code.** Blink and
   head-turn challenges are defeated by a virtual camera replaying a video, and the page
   cannot attest that the frames came from a real sensor. There is no browser API that
   proves a camera is a camera.
3. **It creates an irreversible liability.** A stored face template is special-category
   personal data under GDPR Article 9 and equivalent regimes. Holding it — for a control
   that does not actually work — trades a real, permanent obligation for a false sense of
   security. A leaked password is rotated; a leaked face is not.

Building it would satisfy the letter of the request and betray its purpose, which is
security.

## Decision

**Use WebAuthn with a platform authenticator and `userVerification: "required"`.**

That is the face unlock the operating system already provides — Face ID on Apple devices,
Windows Hello face on Windows — used as a cryptographic second factor.

Requirement by requirement:

| Asked for | How this delivers it |
|---|---|
| Biometric profile at registration | A credential is created on the device during enrolment, bound to this site |
| Liveness, anti-photo, anti-screen | Enforced by the OS in hardware — depth sensors, infrared, secure enclave. Stronger than anything a web page can do, and not bypassable from JavaScript |
| Secure comparison | The match happens inside the enclave. The server verifies an ECDSA signature over a challenge it issued |
| Templates, never raw images | **Nothing biometric ever leaves the device.** Not an image, not a template. Only a public key and signatures |
| Can be disabled | Deleting the credential removes the factor; the password still works |
| Complements password/session | It is a step-up over an authenticated session, never a replacement for it |

Additionally:

- **Challenges are single-use, server-issued and short-lived.** A replayed assertion fails.
- **The signature counter is stored and must not go backwards.** A counter regression is
  the standard signal of a cloned authenticator, and the assertion is refused.
- **The credential is bound to one account**, and assertion verification checks that
  binding server-side rather than trusting the credential id the client sent.

## What this does *not* do, stated plainly

**WebAuthn cannot demand a specific biometric modality.** The relying party can require
user verification; the operating system chooses how to perform it. On a Mac with Face ID
or a PC with Windows Hello face, it is face. On a device whose only sensor is a
fingerprint reader, the same flow will use the fingerprint, and the server cannot tell the
difference — nor should it, since both are equally strong.

So this is "unlock with your face, where your device does faces". It is not "the server
recognises your face". The second reading is the one that cannot be built securely in a
browser, and shipping something that *looks* like it would be worse than saying so.

If hardware-level face verification specifically is ever required — a kiosk, a shared
terminal — that needs a controlled device with a depth camera and a server-side matcher,
which is a different product decision and a different ADR.

## Alternatives considered

- **In-browser embedding + server comparison.** Rejected: see §The trap.
- **Server-side matcher over an uploaded photo** (dlib, InsightFace). Rejected: the frames
  still come from an untrusted client, so a replayed video defeats it; it adds heavy native
  dependencies; and it obliges us to store special-category biometric data to protect
  against an attack it does not stop.
- **TOTP instead.** A perfectly good second factor, and materially weaker against phishing
  than WebAuthn, which is origin-bound. Not what was asked for either. It remains a
  reasonable addition for devices with no platform authenticator, and is in the backlog.

## Consequences

- The second factor is only offered where a platform authenticator exists. Devices without
  one keep password-only access, and the UI says so rather than hiding the option.
- No biometric data enters EMEFA's database, so there is no biometric breach to have.
- Enforcement point: when a credential is enrolled, approving a consequential action
  requires a fresh step-up. The factor protects what is worth protecting rather than
  adding friction to every page load.
- `py_webauthn` becomes a dependency. Signature verification is delegated to it rather than
  hand-rolled; hand-rolling CBOR and COSE parsing for a security boundary would be the
  wrong kind of ambition.

## Revisit conditions

A shared-device or kiosk deployment, a regulatory requirement naming face specifically, or
demand for a second factor on devices with no platform authenticator (TOTP, security key).
