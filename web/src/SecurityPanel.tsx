import { useCallback, useEffect, useState } from 'react'
import {
  enrol,
  getStatus,
  platformAuthenticatorAvailable,
  revoke,
  stepUp,
  type SecondFactorStatus,
} from './secondFactor'

export function SecurityPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<SecondFactorStatus | null>(null)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    getStatus()
      .then((data) => { setStatus(data); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => {
    if (!open) return
    setStatus(null); setNotice(''); reload()
    void platformAuthenticatorAvailable().then(setAvailable)
  }, [open, reload])

  if (!open) return null

  const run = async (label: string, action: () => Promise<unknown>, done: string) => {
    setBusy(label); setError(''); setNotice('')
    try {
      await action()
      setNotice(done)
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Opération impossible.')
    } finally { setBusy('') }
  }

  const removeCredential = async (credentialId: string) => {
    setBusy(credentialId); setError(''); setNotice('')
    try {
      await stepUp()
      await revoke(credentialId)
      setNotice('Identité vérifiée. Empreinte supprimée.')
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Vérification ou suppression impossible.')
    } finally { setBusy('') }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="security-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="security-title">Sécurité</h2>
            <p>Déverrouillage par le visage, en second facteur. Il s’ajoute à votre mot de passe, il ne le remplace pas.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer la sécurité">✕</button>
        </header>

        {error && <div className="form-error" role="alert">{error}</div>}
        {notice && <p className="profile-status" role="status">{notice}</p>}

        {available === false && (
          <p className="profile-status">
            Cet appareil ne propose pas de déverrouillage biométrique au navigateur.
            Le mot de passe reste votre seul facteur ici — vous pouvez activer le
            visage depuis un appareil qui gère Face ID ou Windows Hello.
          </p>
        )}

        {status === null && !error && <p className="profile-status">Chargement…</p>}

        {status !== null && (
          <div className="task-group">
            <span className="profile-section">Empreinte enregistrée</span>
            {status.credentials.length === 0 && (
              <p className="profile-status">Aucune. Votre compte est protégé par le mot de passe seul.</p>
            )}
            {status.credentials.map((credential) => (
              <div key={credential.credential_id} className="task-row">
                <div>
                  <strong>{credential.label}</strong>
                  <small>Ajoutée le {credential.created_at.slice(0, 10)}</small>
                  <small>
                    {credential.last_used_at
                      ? `Dernière vérification le ${credential.last_used_at.slice(0, 10)}`
                      : 'Jamais utilisée depuis'}
                  </small>
                </div>
                <button
                  onClick={() => void removeCredential(credential.credential_id)}
                  disabled={busy === credential.credential_id}
                >
                  {busy === credential.credential_id ? 'Vérification…' : 'Vérifier et retirer'}
                </button>
              </div>
            ))}
            <div className="profile-actions">
              {available !== false && (
                <button
                  type="button"
                  className="profile-later"
                  onClick={() => void run('enrol', () => enrol('Cet appareil'), 'Visage enregistré sur cet appareil.')}
                  disabled={busy === 'enrol'}
                >
                  {busy === 'enrol' ? 'Enregistrement…' : 'Enregistrer mon visage sur cet appareil'}
                </button>
              )}
              {status.enrolled && (
                <button
                  type="button"
                  className="profile-later"
                  onClick={() => void run('verify', stepUp, 'Vérifié. Vous pouvez approuver vos actions.')}
                  disabled={busy === 'verify'}
                >
                  {busy === 'verify' ? 'Vérification…' : 'Se vérifier maintenant'}
                </button>
              )}
            </div>
            {status.enrolled && (
              <p className="profile-status">
                {status.verified
                  ? `Vérifié. Valable ${Math.round(status.step_up_seconds / 60)} minutes pour approuver une action sensible.`
                  : 'Non vérifié sur ce navigateur. Une vérification sera demandée avant d’approuver une action sensible.'}
              </p>
            )}
          </div>
        )}

        <div className="task-group">
          <span className="profile-section">Ce qui est stocké</span>
          <p className="profile-status">
            Rien de biométrique. Votre visage ne quitte jamais votre appareil : la
            reconnaissance est faite par le système, dans son composant sécurisé, et
            EMEFA ne reçoit qu’une clé publique et des signatures. Il n’y a donc aucune
            image ni gabarit de visage à voler chez nous.
          </p>
          <p className="profile-status">
            Selon l’appareil, le système peut demander l’empreinte digitale plutôt que
            le visage : c’est lui qui choisit, et les deux protègent aussi bien.
          </p>
        </div>

        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
        </footer>
      </section>
    </div>
  )
}
