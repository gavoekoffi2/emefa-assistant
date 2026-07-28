import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

type Report = { brief_date: string; content: Record<string, unknown>; text: string }
type AgendaEvent = { event_id: string; label: string; title: string; contact_id: string | null }
type Conflict = { first: { title: string }; second: { title: string } }
type Agenda = {
  event_count: number
  events: AgendaEvent[]
  conflicts: Conflict[]
  tomorrow_count: number
  tomorrow_first: string
}
type SectionOption = { key: string; label: string }
type Preferences = {
  morning_sections: string[]
  evening_sections: string[]
  available_morning: SectionOption[]
  available_evening: SectionOption[]
}

type Moment = 'morning' | 'evening'

const MOMENT_COPY: Record<Moment, { title: string; blurb: string; empty: string }> = {
  morning: {
    title: 'Briefing du matin',
    blurb: 'Ce qui mérite votre attention aujourd’hui, lu directement dans vos données.',
    empty: 'Rien à signaler ce matin.',
  },
  evening: {
    title: 'Rapport du soir',
    blurb: 'Ce que la journée a produit, ce qui reste, et par quoi commencer demain.',
    empty: 'Journée sans activité enregistrée.',
  },
}

/** Suggest the report the executive is most likely to want, by local hour. */
const currentMoment = (): Moment => (new Date().getHours() >= 17 ? 'evening' : 'morning')

export function DayPanel({ open, onClose, onAsk }: {
  open: boolean
  onClose: () => void
  onAsk: (prompt: string) => void
}) {
  const [moment, setMoment] = useState<Moment>(currentMoment)
  const [report, setReport] = useState<Report | null>(null)
  const [agenda, setAgenda] = useState<Agenda | null>(null)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [tuning, setTuning] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback((which: Moment) => {
    setReport(null); setError('')
    api<Report>(`/v1/briefings/${which}`)
      .then(setReport)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => {
    if (!open) return
    setMoment(currentMoment())
  }, [open])

  useEffect(() => {
    if (!open) return
    load(moment)
    api<Preferences>('/v1/briefings/preferences').then(setPreferences).catch(() => undefined)
    api<Agenda>('/v1/agenda').then(setAgenda).catch(() => undefined)
  }, [open, moment, load])

  if (!open) return null

  const toggleSection = async (key: string) => {
    if (!preferences) return
    const field = moment === 'morning' ? 'morning_sections' : 'evening_sections'
    const available = moment === 'morning' ? preferences.available_morning : preferences.available_evening
    const current = preferences[field]
    // An empty selection means "everything", so the first click has to start
    // from the full list rather than from nothing.
    const base = current.length === 0 ? available.map((item) => item.key) : current
    const next = base.includes(key) ? base.filter((item) => item !== key) : [...base, key]
    try {
      setPreferences(await api<Preferences>('/v1/briefings/preferences', {
        method: 'PUT',
        body: JSON.stringify({ [field]: next }),
      }))
      load(moment)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Préférence non enregistrée.')
    }
  }

  const options = preferences
    ? (moment === 'morning' ? preferences.available_morning : preferences.available_evening)
    : []
  const selected = preferences
    ? (moment === 'morning' ? preferences.morning_sections : preferences.evening_sections)
    : []
  const isOn = (key: string) => selected.length === 0 || selected.includes(key)
  const copy = MOMENT_COPY[moment]
  const lines = (report?.text ?? '').split('\n')

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="day-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="day-title">Votre journée</h2>
            <p>{copy.blurb}</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer la journée">✕</button>
        </header>

        <div className="segment-row" role="tablist" aria-label="Moment de la journée">
          {(['morning', 'evening'] as Moment[]).map((value) => (
            <button
              key={value}
              role="tab"
              aria-selected={moment === value}
              className={moment === value ? 'segment-active' : ''}
              onClick={() => setMoment(value)}
            >{MOMENT_COPY[value].title}</button>
          ))}
        </div>

        {error && <div className="form-error" role="alert">{error}</div>}

        {agenda && (
          <div className="task-group">
            <span className="profile-section">
              {moment === 'morning' ? 'Agenda du jour' : 'Agenda de demain'}
            </span>
            {moment === 'morning' && agenda.event_count === 0 && (
              <p className="profile-status">Aucun rendez-vous aujourd’hui.</p>
            )}
            {moment === 'morning' && agenda.events.map((event) => (
              <div key={event.event_id} className="task-row">
                <div><strong>{event.label}</strong></div>
                <button onClick={() => {
                  onClose()
                  onAsk(`Prépare mon rendez-vous « ${event.title} » : rappelle-moi le contexte et les points à aborder.`)
                }}>Préparer</button>
              </div>
            ))}
            {moment === 'morning' && agenda.conflicts.map((clash, index) => (
              <p key={index} className="form-error" role="alert">
                Chevauchement : « {clash.first.title} » et « {clash.second.title} ».
              </p>
            ))}
            {moment === 'evening' && (
              <p className="profile-status">
                {agenda.tomorrow_count
                  ? `${agenda.tomorrow_count} rendez-vous demain — le premier à ${agenda.tomorrow_first}.`
                  : 'Aucun rendez-vous demain.'}
              </p>
            )}
          </div>
        )}

        {!report && !error && <p className="profile-status">Composition en cours…</p>}

        {report && (
          <article className="report-body" aria-live="polite">
            {lines.length <= 1
              ? <p className="profile-status">{copy.empty}</p>
              : lines.map((line, index) => {
                if (!line.trim()) return <span key={index} className="report-gap" />
                if (line.startsWith('- ')) return <p key={index} className="report-item">{line.slice(2)}</p>
                if (index === 0) return <h3 key={index} className="report-title">{line}</h3>
                if (line.endsWith(':') || line.endsWith(' :')) return <span key={index} className="profile-section">{line.replace(/\s*:$/, '')}</span>
                return <p key={index} className="report-line">{line}</p>
              })}
          </article>
        )}

        <button type="button" className="tune-toggle" onClick={() => setTuning((value) => !value)}>
          {tuning ? 'Masquer les sections' : 'Choisir les sections de ce rapport'}
        </button>
        {tuning && (
          <div className="chip-grid">
            {options.map((option) => (
              <button
                key={option.key}
                type="button"
                className={isOn(option.key) ? 'chip chip-on' : 'chip'}
                aria-pressed={isOn(option.key)}
                onClick={() => void toggleSection(option.key)}
              >{option.label}</button>
            ))}
          </div>
        )}

        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              onClose()
              onAsk(moment === 'morning'
                ? 'Donne-moi mon briefing du matin et commente les points les plus urgents.'
                : 'Fais le point sur ma journée et dis-moi par quoi commencer demain.')
            }}
          >En parler avec EMEFA</button>
        </footer>
      </section>
    </div>
  )
}
