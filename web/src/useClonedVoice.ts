import { useCallback, useEffect, useRef, useState } from 'react'
import { remapAnalyserSpectrum } from './face/audioSpectrum.ts'

type QueuedAudio = {
  generation: number
  controller: AbortController
  prepared: Promise<AudioBuffer>
}

type ClonedVoiceOptions = {
  onFailure: (message: string) => void
}

const EMPTY_FREQUENCIES = new Uint8Array(128)

export function useClonedVoice({ onFailure }: ClonedVoiceOptions) {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const contextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)
  const sourceRef = useRef<AudioBufferSourceNode | null>(null)
  const queueRef = useRef<QueuedAudio[]>([])
  const controllersRef = useRef(new Set<AbortController>())
  const generationRef = useRef(0)
  const drainingRef = useRef(false)
  const enabledRef = useRef(false)
  const failureRef = useRef(onFailure)

  useEffect(() => { failureRef.current = onFailure }, [onFailure])

  const ensureAudioGraph = useCallback(async () => {
    let context = contextRef.current
    if (!context) {
      context = new AudioContext()
      const analyser = context.createAnalyser()
      const gain = context.createGain()
      analyser.fftSize = 512
      // Keep enough temporal detail for consonants; the viseme solver performs
      // its own short attack/release smoothing after frequency classification.
      analyser.smoothingTimeConstant = 0.18
      analyser.connect(gain)
      gain.connect(context.destination)
      contextRef.current = context
      analyserRef.current = analyser
      gainRef.current = gain
    }
    if (context.state === 'suspended') await context.resume()
    return context
  }, [])

  const interrupt = useCallback(() => {
    generationRef.current += 1
    queueRef.current = []
    for (const controller of controllersRef.current) controller.abort()
    controllersRef.current.clear()
    const source = sourceRef.current
    sourceRef.current = null
    if (source) {
      source.onended = null
      try { source.stop() } catch { /* already stopped */ }
      source.disconnect()
    }
    setIsSpeaking(false)
  }, [])

  const disable = useCallback(() => {
    enabledRef.current = false
    interrupt()
  }, [interrupt])

  const activate = useCallback(async () => {
    await ensureAudioGraph()
    interrupt()
    enabledRef.current = true
  }, [ensureAudioGraph, interrupt])

  const fetchAudio = useCallback(async (text: string, controller: AbortController) => {
    const response = await fetch('/v1/realtime/speech', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null
      throw new Error(body?.detail || `Synthèse vocale refusée (${response.status}).`)
    }
    const encoded = await response.arrayBuffer()
    const context = await ensureAudioGraph()
    return context.decodeAudioData(encoded.slice(0))
  }, [ensureAudioGraph])

  const playBuffer = useCallback(async (buffer: AudioBuffer, generation: number) => {
    if (!enabledRef.current || generation !== generationRef.current) return
    const context = await ensureAudioGraph()
    const analyser = analyserRef.current
    if (!analyser) throw new Error('Sortie audio indisponible.')
    await new Promise<void>((resolve) => {
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(analyser)
      sourceRef.current = source
      setIsSpeaking(true)
      source.onended = () => {
        source.disconnect()
        if (sourceRef.current === source) sourceRef.current = null
        resolve()
      }
      source.start()
    })
  }, [ensureAudioGraph])

  const drain = useCallback(async () => {
    if (drainingRef.current) return
    drainingRef.current = true
    try {
      while (queueRef.current.length > 0 && enabledRef.current) {
        const item = queueRef.current.shift()
        if (!item || item.generation !== generationRef.current) continue
        try {
          const buffer = await item.prepared
          controllersRef.current.delete(item.controller)
          if (item.generation !== generationRef.current) continue
          await playBuffer(buffer, item.generation)
        } catch (cause) {
          controllersRef.current.delete(item.controller)
          if (cause instanceof DOMException && cause.name === 'AbortError') continue
          enabledRef.current = false
          queueRef.current = []
          for (const controller of controllersRef.current) controller.abort()
          controllersRef.current.clear()
          setIsSpeaking(false)
          failureRef.current(
            cause instanceof Error
              ? `La nouvelle voix est indisponible (${cause.message}). L’ancienne voix reste active.`
              : 'La nouvelle voix est indisponible. L’ancienne voix reste active.',
          )
          break
        }
      }
    } finally {
      drainingRef.current = false
      if (!sourceRef.current) setIsSpeaking(false)
    }
  }, [playBuffer])

  const enqueue = useCallback((rawText: string) => {
    const text = rawText.replace(/\s+/g, ' ').trim()
    if (!enabledRef.current || !text) return
    const controller = new AbortController()
    const generation = generationRef.current
    controllersRef.current.add(controller)
    queueRef.current.push({
      generation,
      controller,
      // Start preparing every sentence immediately. Playback still drains in
      // order, which removes most provider gaps without mixing segments.
      prepared: fetchAudio(text, controller),
    })
    void drain()
  }, [drain, fetchAudio])

  const getOutputVolume = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser || !sourceRef.current) return 0
    const samples = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(samples)
    let energy = 0
    for (const sample of samples) {
      const normalized = (sample - 128) / 128
      energy += normalized * normalized
    }
    return Math.min(1, Math.sqrt(energy / samples.length) * 2.4)
  }, [])

  const getOutputByteFrequencyData = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser || !sourceRef.current) return EMPTY_FREQUENCIES
    const frequencies = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(frequencies)
    const context = contextRef.current
    return context
      ? remapAnalyserSpectrum(frequencies, context.sampleRate, EMPTY_FREQUENCIES.length)
      : EMPTY_FREQUENCIES
  }, [])

  useEffect(() => () => {
    disable()
    const context = contextRef.current
    contextRef.current = null
    if (context) void context.close()
  }, [disable])

  return {
    activate,
    disable,
    enqueue,
    interrupt,
    isSpeaking,
    getOutputVolume,
    getOutputByteFrequencyData,
  }
}
