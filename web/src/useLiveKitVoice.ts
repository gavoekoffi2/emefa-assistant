import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'
import { remapAnalyserSpectrum } from './face/audioSpectrum.ts'

export type LiveKitTicket = { token: string; url: string; room: string }
type LiveKitState = 'disconnected' | 'connecting' | 'listening' | 'speaking'
type LiveKitVoiceOptions = {
  onUserTranscript: (text: string) => void
  onAgentTranscript: (text: string) => void
  onError: (message: string) => void
}

const EMPTY_FREQUENCIES = new Uint8Array(128)

export function useLiveKitVoice(options: LiveKitVoiceOptions) {
  const [status, setStatus] = useState<LiveKitState>('disconnected')
  const roomRef = useRef<Room | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const optionsRef = useRef(options)

  useEffect(() => { optionsRef.current = options }, [options])

  const releaseAudio = useCallback(() => {
    sourceRef.current?.disconnect()
    analyserRef.current?.disconnect()
    sourceRef.current = null
    analyserRef.current = null
    const audio = audioRef.current
    audioRef.current = null
    if (audio) {
      audio.pause()
      audio.srcObject = null
      audio.remove()
    }
    const context = contextRef.current
    contextRef.current = null
    if (context) void context.close()
  }, [])

  const stop = useCallback(async () => {
    const room = roomRef.current
    roomRef.current = null
    if (room) await room.disconnect()
    releaseAudio()
    setStatus('disconnected')
  }, [releaseAudio])

  const start = useCallback(async (ticket: LiveKitTicket) => {
    await stop()
    setStatus('connecting')
    const room = new Room({ adaptiveStream: true, dynacast: true })
    roomRef.current = room

    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current === room) roomRef.current = null
      releaseAudio()
      setStatus('disconnected')
    })
    room.on(RoomEvent.TrackSubscribed, async (track) => {
      if (track.kind !== Track.Kind.Audio) return
      releaseAudio()
      const audio = document.createElement('audio')
      audio.autoplay = true
      audio.hidden = true
      track.attach(audio)
      document.body.appendChild(audio)

      const context = new AudioContext()
      const source = context.createMediaElementSource(audio)
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.18
      source.connect(analyser)
      analyser.connect(context.destination)
      audioRef.current = audio
      contextRef.current = context
      sourceRef.current = source
      analyserRef.current = analyser
      if (context.state === 'suspended') await context.resume()
      await audio.play().catch(() => undefined)
    })
    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((element) => element.remove())
      releaseAudio()
    })
    room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      if (speakers.some((participant) => participant.isAgent)) setStatus('speaking')
      else setStatus('listening')
    })
    room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      for (const segment of segments) {
        if (!segment.final || !segment.text.trim()) continue
        if (participant?.isAgent) optionsRef.current.onAgentTranscript(segment.text.trim())
        else optionsRef.current.onUserTranscript(segment.text.trim())
      }
    })

    try {
      await room.connect(ticket.url, ticket.token, { autoSubscribe: true })
      await room.localParticipant.setMicrophoneEnabled(true)
      setStatus('listening')
    } catch (cause) {
      await stop()
      const message = cause instanceof Error ? cause.message : 'La liaison LiveKit a échoué.'
      optionsRef.current.onError(message)
      throw cause
    }
  }, [releaseAudio, stop])

  const getOutputVolume = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser || status !== 'speaking') return 0
    const samples = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(samples)
    let energy = 0
    for (const sample of samples) {
      const normalized = (sample - 128) / 128
      energy += normalized * normalized
    }
    return Math.min(1, Math.sqrt(energy / samples.length) * 2.4)
  }, [status])

  const getOutputByteFrequencyData = useCallback(() => {
    const analyser = analyserRef.current
    const context = contextRef.current
    if (!analyser || !context || status !== 'speaking') return EMPTY_FREQUENCIES
    const frequencies = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(frequencies)
    return remapAnalyserSpectrum(frequencies, context.sampleRate, EMPTY_FREQUENCIES.length)
  }, [status])

  useEffect(() => () => { void stop() }, [stop])

  return {
    start,
    stop,
    status,
    connected: status !== 'disconnected' && status !== 'connecting',
    isSpeaking: status === 'speaking',
    getOutputVolume,
    getOutputByteFrequencyData,
  }
}
