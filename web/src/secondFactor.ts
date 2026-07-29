/**
 * Face unlock, as a second factor (ADR-005).
 *
 * The biometric never reaches this code. The browser hands the request to the
 * operating system, which verifies the user with hardware — Face ID, Windows
 * Hello — and returns a signature. What travels to the server is a public key
 * and signatures, never an image and never a template.
 *
 * That is why this is a real factor and an in-browser face embedding would not
 * be: the private key lives in the device's secure enclave and is released
 * only after a verification this page cannot fake or bypass.
 */
import { api } from './App'

export type SecondFactorStatus = {
  enrolled: boolean
  verified: boolean
  step_up_seconds: number
  credentials: { credential_id: string; label: string; created_at: string; last_used_at: string | null }[]
}

type Ceremony = { challenge_token: string; options: Record<string, unknown> }

/** Whether this device can do it at all. Said out loud rather than hidden. */
export async function platformAuthenticatorAvailable(): Promise<boolean> {
  if (typeof PublicKeyCredential === 'undefined') return false
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
  } catch {
    return false
  }
}

const fromBase64Url = (value: string): Uint8Array => {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4))
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

const toBase64Url = (buffer: ArrayBuffer): string =>
  btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')

/** The server sends base64url; the WebAuthn API wants ArrayBuffers. */
const decodeCreationOptions = (options: any): PublicKeyCredentialCreationOptions => ({
  ...options,
  challenge: fromBase64Url(options.challenge),
  user: { ...options.user, id: fromBase64Url(options.user.id) },
  excludeCredentials: (options.excludeCredentials ?? []).map((item: any) => ({
    ...item,
    id: fromBase64Url(item.id),
  })),
})

const decodeRequestOptions = (options: any): PublicKeyCredentialRequestOptions => ({
  ...options,
  challenge: fromBase64Url(options.challenge),
  allowCredentials: (options.allowCredentials ?? []).map((item: any) => ({
    ...item,
    id: fromBase64Url(item.id),
  })),
})

const encodeAttestation = (credential: PublicKeyCredential) => {
  const response = credential.response as AuthenticatorAttestationResponse
  return {
    id: credential.id,
    rawId: toBase64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toBase64Url(response.clientDataJSON),
      attestationObject: toBase64Url(response.attestationObject),
    },
  }
}

const encodeAssertion = (credential: PublicKeyCredential) => {
  const response = credential.response as AuthenticatorAssertionResponse
  return {
    id: credential.id,
    rawId: toBase64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toBase64Url(response.clientDataJSON),
      authenticatorData: toBase64Url(response.authenticatorData),
      signature: toBase64Url(response.signature),
      userHandle: response.userHandle ? toBase64Url(response.userHandle) : null,
    },
  }
}

export const getStatus = () => api<SecondFactorStatus>('/v1/auth/second-factor')

export async function enrol(label: string): Promise<void> {
  const ceremony = await api<Ceremony>('/v1/auth/second-factor/register/options', { method: 'POST' })
  const credential = (await navigator.credentials.create({
    publicKey: decodeCreationOptions(ceremony.options),
  })) as PublicKeyCredential | null
  if (credential === null) throw new Error('Aucune empreinte n’a été enregistrée.')

  await api<unknown>('/v1/auth/second-factor/register', {
    method: 'POST',
    body: JSON.stringify({
      label,
      credential: {
        challenge_token: ceremony.challenge_token,
        response_json: encodeAttestation(credential),
        id: credential.id,
      },
    }),
  })
}

export async function stepUp(): Promise<void> {
  const ceremony = await api<Ceremony>('/v1/auth/second-factor/verify/options', { method: 'POST' })
  const credential = (await navigator.credentials.get({
    publicKey: decodeRequestOptions(ceremony.options),
  })) as PublicKeyCredential | null
  if (credential === null) throw new Error('Vérification annulée.')

  await api<unknown>('/v1/auth/second-factor/verify', {
    method: 'POST',
    body: JSON.stringify({
      credential: {
        challenge_token: ceremony.challenge_token,
        response_json: encodeAssertion(credential),
        id: credential.id,
      },
    }),
  })
}

export const revoke = (credentialId: string) =>
  api<void>(`/v1/auth/second-factor/${credentialId}`, { method: 'DELETE' })
