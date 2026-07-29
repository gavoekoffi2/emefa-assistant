/* oxlint-disable react/only-export-components */
import { useEffect, useState } from 'react'
import { api, BrandMark } from './App'

/** The signed-in person, as the server describes them. */
export type Account = {
  user_id: string
  tenant_id: string
  email: string
  display_name: string
  role: string
  role_label: string
  status: string
  email_verified: boolean
  company_name: string
  permissions: string[]
}

type Invitation = { email: string; role: string; role_label: string; company_name: string }

/** Which screen the visitor is on. Driven by the URL for the emailed links,
 *  so a verification or invitation link opens straight onto the right form. */
type View = 'signin' | 'signup' | 'forgot' | 'reset' | 'verify' | 'join' | 'code'

const VIEW_BY_PATH: Record<string, View> = {
  '/verifier-email': 'verify',
  '/nouveau-mot-de-passe': 'reset',
  '/rejoindre': 'join',
}

/** Read the view and token the emailed link is pointing at. */
function routeFromLocation(): { view: View; token: string } {
  if (typeof window === 'undefined') return { view: 'signin', token: '' }
  const view = VIEW_BY_PATH[window.location.pathname]
  const token = new URLSearchParams(window.location.search).get('token') ?? ''
  return view && token ? { view, token } : { view: 'signin', token: '' }
}

/** Clear the token out of the address bar once it has been redeemed, so it is
 *  not left in history, bookmarks or a screenshot. */
function forgetToken() {
  if (typeof window !== 'undefined' && window.location.search) {
    window.history.replaceState({}, '', '/')
  }
}

export function useDeviceName(): string {
  if (typeof navigator === 'undefined') return 'Navigateur'
  const agent = navigator.userAgent
  if (/iPhone|Android.*Mobile/.test(agent)) return 'Téléphone'
  if (/iPad|Android/.test(agent)) return 'Tablette'
  return 'Ordinateur'
}

type FieldProps = {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  autoComplete?: string
  placeholder?: string
  hint?: string
  disabled?: boolean
}

function Field({ id, label, value, onChange, type = 'text', autoComplete, placeholder, hint, disabled }: FieldProps) {
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        autoComplete={autoComplete}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        required
      />
      {hint && <small className="field-hint">{hint}</small>}
    </>
  )
}

export function Auth({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const initial = routeFromLocation()
  const [view, setView] = useState<View>(initial.view)
  const [token] = useState(initial.token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const deviceName = useDeviceName()

  // shared fields
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [code, setCode] = useState('')
  const [invitation, setInvitation] = useState<Invitation | null>(null)

  // An invitation link shows who invited you, and to what, before you commit.
  useEffect(() => {
    if (view !== 'join' || !token) return
    api<Invitation>(`/v1/auth/invitations/peek?token=${encodeURIComponent(token)}`)
      .then(setInvitation)
      .catch(() => setError("Cette invitation n'est plus valable. Demandez-en une nouvelle."))
  }, [view, token])

  // A verification link is redeemed on arrival: there is nothing to fill in.
  useEffect(() => {
    if (view !== 'verify' || !token) return
    api<Account>('/v1/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) })
      .then((account) => {
        forgetToken()
        setNotice(`Adresse confirmée. Bienvenue, ${account.display_name}.`)
        setView('signin')
      })
      .catch(() => {
        forgetToken()
        setError('Ce lien est invalide ou expiré. Connectez-vous pour en recevoir un nouveau.')
        setView('signin')
      })
  }, [view, token])

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Une erreur est survenue.')
    } finally {
      setBusy(false)
    }
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    void run(async () => {
      if (view === 'signup') {
        const account = await api<Account>('/v1/auth/signup', {
          method: 'POST',
          body: JSON.stringify({
            email: email.trim(),
            password,
            display_name: displayName.trim(),
            company_name: companyName.trim(),
            device_name: deviceName,
          }),
        })
        onSignedIn(account)
      } else if (view === 'signin') {
        const account = await api<Account>('/v1/auth/signin', {
          method: 'POST',
          body: JSON.stringify({ email: email.trim(), password, device_name: deviceName }),
        })
        onSignedIn(account)
      } else if (view === 'forgot') {
        await api<{ status: string }>('/v1/auth/password/forgot', {
          method: 'POST',
          body: JSON.stringify({ email: email.trim() }),
        })
        // Deliberately the same message whether or not the address is known.
        setNotice("Si cette adresse a un compte, un lien de réinitialisation vient d'être envoyé.")
        setView('signin')
      } else if (view === 'reset') {
        await api<void>('/v1/auth/password/reset', {
          method: 'POST',
          body: JSON.stringify({ token, password }),
        })
        forgetToken()
        setNotice('Mot de passe modifié. Connectez-vous avec le nouveau.')
        setView('signin')
      } else if (view === 'join') {
        const account = await api<Account>('/v1/auth/invitations/accept', {
          method: 'POST',
          body: JSON.stringify({
            token,
            password,
            display_name: displayName.trim(),
            device_name: deviceName,
          }),
        })
        forgetToken()
        onSignedIn(account)
      } else if (view === 'code') {
        await api<{ device_id: string; name: string }>('/v1/web/session', {
          method: 'POST',
          body: JSON.stringify({ name: deviceName, enrollment_code: code }),
        })
        onSignedIn(await api<Account>('/v1/auth/me'))
      }
    })
  }

  const go = (next: View) => {
    setError('')
    setNotice('')
    setPassword('')
    setView(next)
  }

  const titles: Record<View, string> = {
    signin: 'Connexion',
    signup: 'Créer votre espace',
    forgot: 'Mot de passe oublié',
    reset: 'Nouveau mot de passe',
    verify: 'Confirmation en cours…',
    join: invitation ? `Rejoindre ${invitation.company_name}` : 'Rejoindre une entreprise',
    code: 'Accès par code privé',
  }

  const actions: Record<View, string> = {
    signin: 'Entrer dans EMEFA',
    signup: 'Créer mon espace',
    forgot: 'Recevoir un lien',
    reset: 'Enregistrer',
    verify: '…',
    join: 'Rejoindre',
    code: 'Entrer dans EMEFA',
  }

  return (
    <main className="activation-page">
      <section className="activation-intro">
        <div className="brand-row"><BrandMark /><strong>EMEFA</strong></div>
        <div className="intro-copy">
          <span className="eyebrow">Assistante exécutive</span>
          <h1>Une conversation.<br />Pas un chatbot.</h1>
          <p>
            EMEFA comprend votre entreprise, retient ce qui compte, prépare vos documents
            et vous alerte sur ce qui mérite votre attention aujourd'hui.
          </p>
        </div>
        <div className="privacy-note">
          <span className="privacy-dot" />
          <div>
            <strong>Vos données restent les vôtres</strong>
            <small>Chaque entreprise dispose d'un espace strictement séparé.</small>
          </div>
        </div>
      </section>

      <section className="activation-panel" aria-labelledby="activation-title">
        <div className="activation-card">
          <BrandMark />
          <h2 id="activation-title">{titles[view]}</h2>

          {view === 'signup' && <p>Créez votre entreprise et son assistante en une minute.</p>}
          {view === 'signin' && <p>Content de vous revoir.</p>}
          {view === 'forgot' && <p>Indiquez votre adresse : nous vous enverrons un lien.</p>}
          {view === 'reset' && <p>Choisissez un nouveau mot de passe.</p>}
          {view === 'code' && <p>Réservé aux instances privées déjà déployées.</p>}
          {view === 'join' && invitation && (
            <p>
              Vous êtes invité comme <strong>{invitation.role_label.toLowerCase()}</strong> avec
              l'adresse <strong>{invitation.email}</strong>.
            </p>
          )}

          {notice && <div className="form-notice" role="status">{notice}</div>}

          {view !== 'verify' && (
            <form onSubmit={submit}>
              {(view === 'signup' || view === 'signin' || view === 'forgot') && (
                <Field
                  id="email" label="Adresse e-mail" type="email" value={email}
                  onChange={setEmail} autoComplete="email" placeholder="vous@entreprise.tg"
                />
              )}

              {view === 'signup' && (
                <>
                  <Field
                    id="display-name" label="Votre nom" value={displayName}
                    onChange={setDisplayName} autoComplete="name" placeholder="Koffi Gava"
                  />
                  <Field
                    id="company-name" label="Nom de votre entreprise" value={companyName}
                    onChange={setCompanyName} autoComplete="organization" placeholder="Horizon SARL"
                  />
                </>
              )}

              {view === 'join' && (
                <Field
                  id="display-name" label="Votre nom" value={displayName}
                  onChange={setDisplayName} autoComplete="name" placeholder="Votre nom complet"
                />
              )}

              {(view === 'signup' || view === 'signin' || view === 'reset' || view === 'join') && (
                <Field
                  id="password"
                  label={view === 'reset' ? 'Nouveau mot de passe' : 'Mot de passe'}
                  type="password"
                  value={password}
                  onChange={setPassword}
                  autoComplete={view === 'signin' ? 'current-password' : 'new-password'}
                  hint={view === 'signin' ? undefined : 'Au moins 10 caractères.'}
                />
              )}

              {view === 'code' && (
                <Field
                  id="activation-code" label="Code d'activation" type="password"
                  value={code} onChange={setCode} placeholder="Votre code privé"
                />
              )}

              {error && <div className="form-error" role="alert">{error}</div>}

              <button
                className="primary-button"
                disabled={busy || (view === 'join' && !invitation)}
              >
                {busy ? 'Un instant…' : actions[view]}
              </button>
            </form>
          )}

          <div className="auth-switch">
            {view === 'signin' && (
              <>
                <button type="button" onClick={() => go('signup')}>Créer un espace</button>
                <button type="button" onClick={() => go('forgot')}>Mot de passe oublié ?</button>
                <button type="button" className="quiet" onClick={() => go('code')}>
                  Accès par code privé
                </button>
              </>
            )}
            {(view === 'signup' || view === 'forgot' || view === 'code') && (
              <button type="button" onClick={() => go('signin')}>Retour à la connexion</button>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}
