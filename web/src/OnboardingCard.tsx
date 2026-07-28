import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

type Topic = {
  topic_id: string; title: string; status: string
  missing_fields: Array<{ label: string; essential: boolean }>
}
type Status = {
  started: boolean; completed: boolean; progress: number
  address_as: string; topics: Topic[]; next_topic: Topic | null; next_question: string | null
}

/**
 * The welcome interview, surfaced without ever becoming a form.
 *
 * The card only shows where the conversation stands and offers the next
 * natural question; answering happens by talking or typing to EMEFA like any
 * other exchange, so a single conversation feeds a single memory.
 */
export function OnboardingCard({ onAsk, onOpenConfig }: {
  onAsk: (prompt: string) => void
  onOpenConfig: () => void
}) {
  const [status, setStatus] = useState<Status | null>(null)
  const [dismissed, setDismissed] = useState(false)

  const reload = useCallback(() => {
    api<Status>('/v1/onboarding/status').then(setStatus).catch(() => undefined)
  }, [])

  useEffect(() => { reload() }, [reload])

  // Refresh after each exchange: the interview advances by conversation, so
  // the card must follow what EMEFA has just learned.
  useEffect(() => {
    const timer = window.setInterval(reload, 15000)
    return () => window.clearInterval(timer)
  }, [reload])

  if (dismissed || !status || status.completed || !status.next_topic) return null

  const start = () => {
    void api<Status>('/v1/onboarding/start', { method: 'POST' }).catch(() => undefined)
    onAsk(
      status.started
        ? 'Reprenons notre entretien : que dois-tu encore apprendre sur moi et mon entreprise ?'
        : 'Faisons connaissance. Pose-moi tes questions une par une pour bien comprendre qui je suis et ce que fait mon entreprise.',
    )
    setDismissed(true)
  }

  const skip = () => {
    if (status.next_topic) {
      void api<Status>('/v1/onboarding/skip', {
        method: 'POST', body: JSON.stringify({ topic_id: status.next_topic.topic_id }),
      }).then(setStatus).catch(() => undefined)
    }
  }

  const missing = status.next_topic.missing_fields.slice(0, 3).map((field) => field.label).join(', ')

  return (
    <aside className="onboarding-card" role="complementary" aria-labelledby="onboarding-card-title">
      <header>
        <span className="onboarding-progress" aria-hidden="true">
          <i style={{ width: `${Math.round(status.progress * 100)}%` }} />
        </span>
        <strong id="onboarding-card-title">
          {status.started
            ? `Entretien d’accueil — ${status.next_topic.title}`
            : `Bonjour${status.address_as ? ` ${status.address_as}` : ''}, faisons connaissance`}
        </strong>
        <button
          className="onboarding-dismiss"
          onClick={() => setDismissed(true)}
          aria-label="Masquer l’entretien d’accueil"
        >✕</button>
      </header>
      <p>{status.next_question ?? 'Parlons de vous et de votre activité.'}</p>
      {missing && <small>À découvrir : {missing}</small>}
      <div className="onboarding-card-actions">
        <button className="primary-button" onClick={start}>Répondre à EMEFA</button>
        <button className="profile-later" onClick={skip}>Passer ce sujet</button>
        <button className="profile-later" onClick={onOpenConfig}>Renseigner moi-même</button>
      </div>
    </aside>
  )
}
