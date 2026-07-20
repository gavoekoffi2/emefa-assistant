import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../src/VoiceRoom.tsx', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const hologram = readFileSync(new URL('../src/HolographicUniverse.tsx', import.meta.url), 'utf8')
const holographicCss = readFileSync(new URL('../src/Holographic.css', import.meta.url), 'utf8')

test('voice room uses ElevenLabs continuous live conversation SDK', () => {
  assert.match(source, /useConversation/)
  assert.match(source, /conversation\.startSession\(\{[\s\S]*signedUrl:/)
  assert.match(source, /workletPaths:/)
  assert.match(source, /raw-audio-processor\.js/)
  assert.match(source, /audio-concat-processor\.js/)
  assert.match(source, /\/v1\/realtime\/session/)
  assert.match(source, /getUserMedia/)
  assert.match(app, /ConversationProvider/)
})

test('voice room uses provider VAD and true barge-in instead of browser speech APIs', () => {
  assert.doesNotMatch(source, /SpeechRecognition/)
  assert.doesNotMatch(source, /speechSynthesis/)
  assert.doesNotMatch(source, /MediaRecorder/)
  assert.match(source, /onModeChange/)
  assert.match(source, /conversation\.isSpeaking/)
})

test('voice room supports a continuous session, typed turns, and clean shutdown', () => {
  assert.match(source, /conversation\.sendUserMessage/)
  assert.match(source, /conversation\.sendUserActivity/)
  assert.match(source, /conversation\.endSession/)
  assert.match(source, /Conversation continue · interrompez EMEFA à tout moment/)
})

test('typed input reaches the EMEFA runtime when the voice session is offline', () => {
  assert.match(source, /\/v1\/agent\/runs/)
  assert.match(source, /confirmation_required/)
  assert.match(source, /blocked/)
  assert.match(source, /agentErrorCopy/)
})

test('profile panel lets the user view and edit assistant and business context', () => {
  const panel = readFileSync(new URL('../src/ProfilePanel.tsx', import.meta.url), 'utf8')
  assert.match(panel, /\/v1\/assistant\/profile/)
  assert.match(panel, /\/v1\/assistant\/business/)
  assert.match(panel, /method: 'PATCH'/)
  assert.match(panel, /isBusinessEmpty/)
  assert.match(source, /ProfilePanel/)
  assert.match(source, /firstRun/)
  assert.match(holographicCss, /profile-panel/)
})

test('interface renders a state-reactive WebGL holographic HUD', () => {
  assert.match(source, /HolographicUniverse/)
  assert.match(source, /telemetry-panel/)
  assert.match(source, /core-reticle/)
  assert.match(hologram, /THREE\.WebGLRenderer/)
  assert.match(hologram, /TorusGeometry/)
  assert.match(hologram, /PointsMaterial/)
  assert.match(hologram, /STATE_COLORS/)
  assert.match(holographicCss, /prefers-reduced-motion/)
  assert.match(holographicCss, /@media\(max-width:800px\)/)
})
