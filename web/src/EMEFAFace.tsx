import { useEffect, useRef } from 'react'
import type { VoiceState } from './App'
import './EMEFAFace.css'

type EMEFAFaceProps = {
  state: VoiceState
  onClick: () => void
  getOutputVolume: () => number
}

/**
 * Zero-cost local avatar prototype.
 *
 * The face is pure SVG/CSS and runs on the user's device. During speech, the
 * mouth is driven by the real ElevenLabs output volume instead of a decorative
 * loop. This component can later be replaced by a WebRTC avatar provider
 * without changing EMEFA's voice/agent pipeline.
 */
export function EMEFAFace({ state, onClick, getOutputVolume }: EMEFAFaceProps) {
  const rootRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let frame = 0
    let smoothed = 0

    const animate = () => {
      const raw = state === 'speaking' ? Math.min(1, Math.max(0, getOutputVolume())) : 0
      smoothed += (raw - smoothed) * (raw > smoothed ? 0.52 : 0.24)
      rootRef.current?.style.setProperty('--voice-level', smoothed.toFixed(3))
      frame = requestAnimationFrame(animate)
    }

    animate()
    return () => cancelAnimationFrame(frame)
  }, [getOutputVolume, state])

  const active = state !== 'idle' && state !== 'error'
  return (
    <button
      ref={rootRef}
      className={`emefa-face state-${state}`}
      onClick={onClick}
      aria-label={state === 'idle' ? 'Démarrer une conversation vocale avec EMEFA' : 'Arrêter la conversation vocale avec EMEFA'}
    >
      <span className="emefa-hologram-stage" aria-hidden="true">
        <span className="emefa-projection-cone" />
        <span className="emefa-projection-floor" />
      </span>
      <span className="emefa-face-halo halo-a" aria-hidden="true" />
      <span className="emefa-face-halo halo-b" aria-hidden="true" />
      <span className="emefa-orbit orbit-a" aria-hidden="true"><i /><i /><i /></span>
      <span className="emefa-orbit orbit-b" aria-hidden="true"><i /><i /></span>
      <span className="emefa-tech-ring" aria-hidden="true" />
      <span className="emefa-hologram-veil" aria-hidden="true" />
      <span className="emefa-hud-corners" aria-hidden="true"><i /><i /><i /><i /></span>
      <span className="emefa-scan-beam" aria-hidden="true" />
      <span className="emefa-hud-data data-left" aria-hidden="true">
        <b>NEURAL LINK</b><i /><i /><i /><small>AFR-228</small>
      </span>
      <span className="emefa-hud-data data-right" aria-hidden="true">
        <b>VOICE CORE</b><span className="emefa-voice-bars"><i /><i /><i /><i /><i /></span><small>SYNC</small>
      </span>
      <svg className="emefa-face-portrait" viewBox="0 0 200 230" role="img" aria-label={`Visage d’EMEFA — ${state}`}>
        <defs>
          <linearGradient id="emefa-skin" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#9b5d3f" />
            <stop offset="0.48" stopColor="#7b432f" />
            <stop offset="1" stopColor="#4b271f" />
          </linearGradient>
          <linearGradient id="emefa-neck" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#75402f" />
            <stop offset="1" stopColor="#3c2020" />
          </linearGradient>
          <linearGradient id="emefa-suit" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#112b3e" />
            <stop offset="1" stopColor="#020a12" />
          </linearGradient>
          <radialGradient id="emefa-cheek" cx="50%" cy="50%" r="50%">
            <stop offset="0" stopColor="#d7796b" stopOpacity=".28" />
            <stop offset="1" stopColor="#d7796b" stopOpacity="0" />
          </radialGradient>
          <filter id="emefa-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <path className="emefa-shoulders" d="M19 230c5-41 28-55 61-60h40c33 5 56 19 61 60z" fill="url(#emefa-suit)" />
        <path className="emefa-collar-light" d="M56 184l28-18 16 34 16-34 28 18-19 46H75z" fill="none" stroke="currentColor" strokeOpacity=".42" />
        <path d="M79 142h42v41c-10 14-32 14-42 0z" fill="url(#emefa-neck)" />

        <path className="emefa-hair-back" d="M48 54c3-36 34-50 56-48 34 3 54 23 52 61l-3 69-27 31H67l-23-36z" fill="#100d16" />
        <path className="emefa-ear left" d="M52 92c-14-5-16 14-8 28 3 6 8 7 13 3z" fill="#70402f" />
        <path className="emefa-ear right" d="M148 92c14-5 16 14 8 28-3 6-8 7-13 3z" fill="#70402f" />
        <path className="emefa-skin" d="M55 68c3-31 22-47 46-47 27 0 45 18 45 49v38c0 35-19 63-46 63s-46-28-46-63z" fill="url(#emefa-skin)" />

        <ellipse cx="72" cy="125" rx="22" ry="18" fill="url(#emefa-cheek)" />
        <ellipse cx="128" cy="125" rx="22" ry="18" fill="url(#emefa-cheek)" />
        <path className="emefa-hair-front" d="M51 74C43 36 66 5 103 6c28 1 49 19 54 48-17-13-30-20-51-22-13 19-32 30-55 31z" fill="#17111d" />
        <path d="M54 69c16-3 37-14 51-34 15 0 31 6 47 19" fill="none" stroke="#33243a" strokeWidth="4" strokeLinecap="round" />

        <g className="emefa-brows">
          <path d="M65 81c9-6 18-5 27 0" fill="none" stroke="#291a1a" strokeWidth="4" strokeLinecap="round" />
          <path d="M108 81c9-5 18-6 27 0" fill="none" stroke="#291a1a" strokeWidth="4" strokeLinecap="round" />
        </g>
        <g className="emefa-eye left-eye">
          <path d="M65 94c7-8 19-8 27 0-8 7-20 7-27 0z" fill="#f1e6df" />
          <ellipse cx="79" cy="94" rx="5" ry="6" fill="#251b18" />
          <circle cx="80.5" cy="92.5" r="1.4" fill="#9ff6ff" />
          <path className="emefa-eyelid" d="M64 93c8-8 20-8 29 0v6H64z" fill="#7c4935" />
        </g>
        <g className="emefa-eye right-eye">
          <path d="M108 94c7-8 19-8 27 0-8 7-20 7-27 0z" fill="#f1e6df" />
          <ellipse cx="121" cy="94" rx="5" ry="6" fill="#251b18" />
          <circle cx="122.5" cy="92.5" r="1.4" fill="#9ff6ff" />
          <path className="emefa-eyelid" d="M107 93c8-8 20-8 29 0v6h-29z" fill="#7c4935" />
        </g>

        <path className="emefa-nose" d="M101 94c-2 12-5 24-3 29 3 3 8 2 11-1" fill="none" stroke="#542d27" strokeWidth="2.3" strokeLinecap="round" />
        <path d="M93 127c5 3 10 3 15 0" fill="none" stroke="#b8755e" strokeOpacity=".5" strokeWidth="1.5" />

        <g className="emefa-mouth">
          <ellipse className="emefa-mouth-cavity" cx="100" cy="145" rx="14" ry="4.5" fill="#241016" />
          <path className="emefa-upper-lip" d="M84 144c7-2 10-7 16-3 6-4 10 1 16 3-9 3-23 3-32 0z" fill="#733a45" />
          <path className="emefa-lower-lip" d="M85 145c9 2 21 2 30 0-7 10-23 10-30 0z" fill="#9d5360" />
          <path className="emefa-teeth" d="M88 145c8 1 16 1 24 0-2 4-21 4-24 0z" fill="#f5e7dd" />
        </g>

        <path d="M62 149c8 19 21 31 38 31s31-12 39-31" fill="none" stroke="#d78c78" strokeOpacity=".12" />
        <g className="emefa-interface-light" filter="url(#emefa-glow)">
          <path d="M42 105h-8m132 0h-8M100 8V0" stroke="currentColor" strokeWidth="1" />
          <circle cx="35" cy="105" r="2" fill="currentColor" />
          <circle cx="165" cy="105" r="2" fill="currentColor" />
        </g>
      </svg>
      <span className="emefa-face-name">EMEFA</span>
      <span className="emefa-face-signal" aria-hidden="true">{active ? '● LIAISON ACTIVE' : 'TOUCHER POUR PARLER'}</span>
    </button>
  )
}
