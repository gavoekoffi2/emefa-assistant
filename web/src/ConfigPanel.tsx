import { useCallback, useEffect, useState } from 'react'
import { api } from './App'
import { describeSpeechFailure } from './voiceErrors.ts'

export type AssistantProfile = {
  assistant_id: string; name: string; primary_language: string; interaction_style: string
}
export type BusinessProfile = Record<string, string> & { assistant_id: string }

type SchemaField = { field: string; label: string; long: boolean }
type SchemaGroup = { group: string; title: string; fields: SchemaField[] }
type Memory = { memory_id: string; category: string; content: string; created_at: string }
type OnboardingTopic = { topic_id: string; title: string; status: string }
type VoiceCheckResult = {
  ok: boolean
  configured: boolean
  voice_id: string
  reason: string
  provider_status: number | null
  provider_message: string
  available_voices: { voice_id: string; name: string; category: string }[]
}
type OnboardingStatus = {
  completed: boolean; progress: number; topics: OnboardingTopic[]; known_field_count: number
  total_field_count: number
}
type ImportResult = { profile: BusinessProfile; pages_imported: number }

/** Ask the provider directly why the cloned voice is refused.
 *
 * Added because diagnosing this from a mid-conversation error meant reading
 * the server log, which the person who owns the provider account generally
 * cannot do. The most common cause is a stale voice id, so a failure also
 * lists the ids the key can actually use.
 */
function VoiceCheckRow() {
  const [result, setResult] = useState<VoiceCheckResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState('')

  const check = async () => {
    setBusy(true)
    setFailed('')
    setResult(null)
    try {
      setResult(await api<VoiceCheckResult>('/v1/system/voice-check'))
    } catch (cause) {
      setFailed(cause instanceof Error ? cause.message : 'Vérification impossible.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="voice-check">
      <button type="button" onClick={() => void check()} disabled={busy}>
        {busy ? 'Vérification…' : 'Tester la voix clonée'}
      </button>
      {failed && <div className="form-error" role="alert">{failed}</div>}
      {result?.ok && (
        <p className="profile-saved" role="status">
          La voix clonée répond correctement ({result.voice_id}).
        </p>
      )}
      {result && !result.ok && (
        <div className="form-error" role="alert">
          <strong>{describeSpeechFailure(new Error(result.reason))}</strong>
          {result.provider_message && (
            <small>Réponse du fournisseur : {result.provider_message}</small>
          )}
          {result.available_voices.length > 0 && (
            <>
              <small>Voix disponibles avec cette clé :</small>
              <ul>
                {result.available_voices.map((voice) => (
                  <li key={voice.voice_id}>
                    {voice.name} — <code>{voice.voice_id}</code>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}

const TOPIC_STATUS: Record<string, string> = {
  complet: 'Complet',
  suffisant: 'Suffisant',
  en_cours: 'En cours',
  'à_faire': 'À faire',
  'ignoré': 'Ignoré',
}

/**
 * The configuration centre: everything EMEFA knows about its executive, in one
 * place, editable and erasable. Field groups come from the backend schema so
 * this panel never drifts from what the welcome interview actually captures.
 */
export function ConfigPanel({ open, onClose, onStartInterview }: {
  open: boolean
  onClose: () => void
  onStartInterview: () => void
}) {
  const [assistant, setAssistant] = useState<AssistantProfile | null>(null)
  const [business, setBusiness] = useState<BusinessProfile | null>(null)
  const [schema, setSchema] = useState<SchemaGroup[]>([])
  const [memories, setMemories] = useState<Memory[]>([])
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null)
  const [website, setWebsite] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'importing' | 'saved' | 'error'>('loading')
  const [error, setError] = useState('')
  const [importedPages, setImportedPages] = useState(0)
  const [busyMemory, setBusyMemory] = useState('')

  const reloadMemories = useCallback(() => {
    api<Memory[]>('/v1/memories').then(setMemories).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!open) return
    setStatus('loading'); setError(''); setImportedPages(0)
    Promise.all([
      api<AssistantProfile>('/v1/assistant/profile'),
      api<BusinessProfile>('/v1/assistant/business'),
      api<SchemaGroup[]>('/v1/assistant/business/schema'),
      api<OnboardingStatus>('/v1/onboarding/status'),
    ]).then(([profileData, businessData, schemaData, onboardingData]) => {
      setAssistant(profileData)
      setBusiness(businessData)
      setSchema(schemaData)
      setOnboarding(onboardingData)
      setWebsite(businessData.website_url || '')
      setStatus('ready')
      reloadMemories()
    }).catch((cause) => {
      setStatus('error')
      setError(cause instanceof Error ? cause.message : 'Chargement impossible.')
    })
  }, [open, reloadMemories])

  if (!open) return null

  const save = async () => {
    if (!assistant || !business) return
    setStatus('saving'); setError('')
    try {
      const savedAssistant = await api<AssistantProfile>('/v1/assistant/profile', {
        method: 'PATCH',
        body: JSON.stringify({
          name: assistant.name.trim() || 'EMEFA',
          interaction_style: assistant.interaction_style,
        }),
      })
      const { assistant_id: _ignored, ...fields } = business
      const savedBusiness = await api<BusinessProfile>('/v1/assistant/business', {
        method: 'PATCH',
        body: JSON.stringify(fields),
      })
      setAssistant(savedAssistant)
      setBusiness(savedBusiness)
      setStatus('saved')
      api<OnboardingStatus>('/v1/onboarding/status').then(setOnboarding).catch(() => undefined)
    } catch (cause) {
      setStatus('error')
      setError(cause instanceof Error ? cause.message : 'Enregistrement impossible.')
    }
  }

  const clearGroup = async (group: SchemaGroup) => {
    if (!business) return
    const cleared = Object.fromEntries(group.fields.map((field) => [field.field, '']))
    setStatus('saving')
    try {
      setBusiness(await api<BusinessProfile>('/v1/assistant/business', {
        method: 'PATCH', body: JSON.stringify(cleared),
      }))
      setStatus('saved')
    } catch (cause) {
      setStatus('error')
      setError(cause instanceof Error ? cause.message : 'Effacement impossible.')
    }
  }

  const importWebsite = async () => {
    const url = website.trim()
    if (!url) { setError('Indiquez l’adresse de votre site.'); return }
    setStatus('importing'); setError(''); setImportedPages(0)
    try {
      const result = await api<ImportResult>('/v1/assistant/business/import', {
        method: 'POST', body: JSON.stringify({ url }),
      })
      setBusiness(result.profile)
      setWebsite(result.profile.website_url)
      setImportedPages(result.pages_imported)
      setStatus('saved')
    } catch (cause) {
      setStatus('error')
      setError(cause instanceof Error ? cause.message : 'EMEFA n’a pas pu analyser ce site.')
    }
  }

  const forget = async (memoryId: string) => {
    setBusyMemory(memoryId)
    try {
      await api<void>(`/v1/memories/${memoryId}`, { method: 'DELETE' })
      reloadMemories()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Suppression impossible.')
    } finally { setBusyMemory('') }
  }

  const resumeInterview = async () => {
    try { await api<OnboardingStatus>('/v1/onboarding/reopen', { method: 'POST' }) } catch { /* best effort */ }
    onClose()
    onStartInterview()
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="config-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="config-title">Ce qu’EMEFA sait de vous</h2>
            <p>Tout ce qui est enregistré est visible ici. Vous pouvez le corriger, le compléter ou l’effacer.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer la configuration">✕</button>
        </header>

        {status === 'loading' && <p className="profile-status">Chargement…</p>}

        {assistant && business && status !== 'loading' && (
          <div className="profile-form">
            {onboarding && (
              <section className="onboarding-choice featured">
                <span className="choice-icon" aria-hidden="true">⌁</span>
                <div>
                  <strong>Entretien d’accueil — {Math.round(onboarding.progress * 100)} %</strong>
                  <p>
                    {onboarding.known_field_count} information(s) apprises sur {onboarding.total_field_count}.
                    {' '}{onboarding.completed ? 'Terminé — vous pouvez le reprendre à tout moment.' : 'EMEFA continuera à apprendre en conversant.'}
                  </p>
                  <div className="chip-grid">
                    {onboarding.topics.map((topic) => (
                      <span key={topic.topic_id} className={`chip chip-${topic.status}`}>
                        {topic.title} · {TOPIC_STATUS[topic.status] ?? topic.status}
                      </span>
                    ))}
                  </div>
                </div>
                <button type="button" className="primary-button" onClick={() => void resumeInterview()}>
                  {onboarding.completed ? 'Reprendre l’entretien' : 'Continuer l’entretien'}
                </button>
              </section>
            )}

            <section className="onboarding-choice">
              <span className="choice-icon" aria-hidden="true">↗</span>
              <div>
                <strong>Importer votre site</strong>
                <p>EMEFA lit les pages publiques utiles et préremplit votre contexte professionnel.</p>
              </div>
              <label className="sr-only" htmlFor="business-website-import">Adresse de votre site</label>
              <div className="website-import-row">
                <input
                  id="business-website-import" type="url" value={website} placeholder="https://votre-site.com"
                  onChange={(event) => setWebsite(event.target.value)}
                />
                <button type="button" onClick={() => void importWebsite()} disabled={status === 'importing'}>
                  {status === 'importing' ? 'Analyse…' : 'Analyser'}
                </button>
              </div>
              {importedPages > 0 && (
                <p className="profile-saved" role="status">
                  {importedPages} page{importedPages > 1 ? 's' : ''} analysée{importedPages > 1 ? 's' : ''}.
                </p>
              )}
            </section>

            <span className="profile-section">Votre assistante</span>
            <div className="profile-field">
              <label htmlFor="assistant-name">Nom de l’assistante</label>
              <input
                id="assistant-name" value={assistant.name} maxLength={80}
                onChange={(event) => setAssistant({ ...assistant, name: event.target.value })}
              />
            </div>
            <div className="profile-field">
              <label htmlFor="assistant-style">Style d’interaction</label>
              <input
                id="assistant-style" value={assistant.interaction_style} maxLength={2000}
                placeholder="Ex. : directe, chaleureuse, réponses courtes"
                onChange={(event) => setAssistant({ ...assistant, interaction_style: event.target.value })}
              />
            </div>

            {schema.map((group) => (
              <details key={group.group} className="profile-advanced">
                <summary>{group.title}</summary>
                {group.fields.map(({ field, label, long }) => (
                  <div key={field} className="profile-field">
                    <label htmlFor={`business-${field}`}>{label}</label>
                    {long ? (
                      <textarea
                        id={`business-${field}`} rows={2} maxLength={8000} value={business[field] ?? ''}
                        onChange={(event) => setBusiness({ ...business, [field]: event.target.value })}
                      />
                    ) : (
                      <input
                        id={`business-${field}`} maxLength={2000} value={business[field] ?? ''}
                        onChange={(event) => setBusiness({ ...business, [field]: event.target.value })}
                      />
                    )}
                  </div>
                ))}
                <button type="button" className="row-delete" onClick={() => void clearGroup(group)}>
                  Effacer « {group.title} »
                </button>
              </details>
            ))}

            <span className="profile-section">Voix clonée</span>
            <VoiceCheckRow />

            <span className="profile-section">Souvenirs durables</span>
            {memories.length === 0 && (
              <p className="profile-status">Aucun souvenir enregistré pour l’instant.</p>
            )}
            {memories.map((memory) => (
              <div key={memory.memory_id} className="task-row">
                <div>
                  <strong>{memory.content}</strong>
                  <small>{memory.category} · {memory.created_at.slice(0, 10)}</small>
                </div>
                <button
                  className="row-delete"
                  onClick={() => void forget(memory.memory_id)}
                  disabled={busyMemory === memory.memory_id}
                  aria-label={`Oublier : ${memory.content}`}
                >{busyMemory === memory.memory_id ? '…' : 'Oublier'}</button>
              </div>
            ))}

            {error && <div className="form-error" role="alert">{error}</div>}
            <footer className="profile-actions">
              {status === 'saved' && importedPages === 0 && (
                <span className="profile-saved" role="status">Enregistré</span>
              )}
              <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
              <button
                type="button" className="primary-button"
                onClick={() => void save()} disabled={status === 'saving'}
              >{status === 'saving' ? 'Enregistrement…' : 'Enregistrer'}</button>
            </footer>
          </div>
        )}
        {status === 'error' && !assistant && <div className="form-error" role="alert">{error}</div>}
      </section>
    </div>
  )
}
