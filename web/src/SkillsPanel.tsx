import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

export type Skill = {
  name: string
  version: string
  author: string
  description: string
  tags: string[]
  capabilities: string[]
  requires_env: string[]
  requires_tools: string[]
  risk: string
  enabled: boolean
  usable: boolean
  missing_env: string[]
  missing_tools: string[]
  blocked_reason: string | null
}

type Catalogue = { skills: Skill[]; errors: Record<string, string> }

const riskLabels: Record<string, string> = {
  observe: 'Lecture seule',
  personal_read: 'Lecture de vos données',
  local_write: 'Écriture locale',
  communicate: 'Communication externe',
  destructive: 'Action destructive',
  money: 'Financier',
  system_change: 'Système',
}

export function SkillsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    api<Catalogue>('/v1/skills')
      .then((data) => { setCatalogue(data); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) { setCatalogue(null); reload() } }, [open, reload])

  if (!open) return null

  const toggle = async (skill: Skill) => {
    setBusy(skill.name)
    try {
      await api<unknown>(`/v1/skills/${skill.name}/${skill.enabled ? 'disable' : 'enable'}`, { method: 'POST' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Modification impossible.')
    } finally { setBusy('') }
  }

  /** Why a skill cannot be switched on, in the user's terms rather than the manifest's. */
  const blocker = (skill: Skill) => {
    if (skill.blocked_reason) return skill.blocked_reason
    if (skill.missing_tools.length) return `Outil indisponible dans cette installation : ${skill.missing_tools.join(', ')}`
    if (skill.missing_env.length) return `Configuration manquante : ${skill.missing_env.join(', ')}`
    return ''
  }

  const failures = Object.entries(catalogue?.errors ?? {})

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="skills-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="skills-title">Compétences</h2>
            <p>Ce qu’EMEFA sait faire. Une compétence lui explique une méthode — elle ne lui accorde aucune permission supplémentaire.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer les compétences">✕</button>
        </header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {catalogue === null && !error && <p className="profile-status">Chargement…</p>}
        {catalogue?.skills.map((skill) => {
          const reason = blocker(skill)
          return (
            <div key={skill.name} className={`task-row skill-row${skill.enabled ? ' skill-on' : ''}`}>
              <div>
                <span className="memory-category">{riskLabels[skill.risk] || skill.risk}</span>
                <strong>{skill.name}</strong>
                <small>{skill.description}</small>
                {skill.capabilities.length > 0 && (
                  <ul className="skill-capabilities">
                    {skill.capabilities.map((capability) => <li key={capability}>{capability}</li>)}
                  </ul>
                )}
                {reason && <small className="skill-blocked">{reason}</small>}
              </div>
              <button onClick={() => void toggle(skill)} disabled={busy === skill.name || (!skill.usable && !skill.enabled)}>
                {busy === skill.name ? '…' : skill.enabled ? 'Désactiver' : 'Activer'}
              </button>
            </div>
          )
        })}
        {failures.length > 0 && (
          <div className="task-group">
            <span className="profile-section">Compétences illisibles</span>
            {failures.map(([name, message]) => <p key={name} className="profile-status">{name} — {message}</p>)}
          </div>
        )}
        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
        </footer>
      </section>
    </div>
  )
}
