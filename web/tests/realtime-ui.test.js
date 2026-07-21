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

test('HUD telemetry reflects real system state instead of decorative numbers', () => {
  assert.match(source, /\/v1\/system\/status/)
  assert.match(source, /compétences actives/)
  assert.match(source, /NON CONFIGURÉ/)
  assert.match(source, /ENGAGEMENTS/)
  assert.doesNotMatch(source, /98\.7%/)
  assert.doesNotMatch(source, /sources synchronisées/)
  assert.doesNotMatch(source, /16 NŒUDS/)
})

test('tasks panel lists commitments and offers the daily brief', () => {
  const tasksPanel = readFileSync(new URL('../src/TasksPanel.tsx', import.meta.url), 'utf8')
  assert.match(tasksPanel, /\/v1\/tasks/)
  assert.match(tasksPanel, /complete/)
  assert.match(tasksPanel, /En retard/)
  assert.match(tasksPanel, /Brief du jour/)
  assert.match(source, /TasksPanel/)
  assert.match(source, /askBrief/)
  assert.match(source, /Qu’est-ce qui mérite mon attention aujourd’hui/)
})

test('memory panel exposes durable memory with user-controlled forgetting', () => {
  const memoryPanel = readFileSync(new URL('../src/MemoryPanel.tsx', import.meta.url), 'utf8')
  assert.match(memoryPanel, /\/v1\/memories/)
  assert.match(memoryPanel, /DELETE/)
  assert.match(memoryPanel, /Oublier/)
  assert.match(memoryPanel, /\/v1\/memories\/export/)
  assert.match(memoryPanel, /\/v1\/agent\/conversation/)
  assert.match(memoryPanel, /Effacer la conversation/)
  assert.match(source, /MemoryPanel/)
  assert.match(source, /Mémoire/)
})

test('consequential actions surface an explicit approval card', () => {
  assert.match(source, /\/v1\/agent\/approvals/)
  assert.match(source, /decideApproval/)
  assert.match(source, /Approuver/)
  assert.match(source, /Refuser/)
  assert.match(source, /APPROBATION REQUISE/)
  assert.match(holographicCss, /approval-card/)
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

test('pipeline panel shows the sales funnel with due follow-ups', () => {
  const pipelinePanel = readFileSync(new URL('../src/PipelinePanel.tsx', import.meta.url), 'utf8')
  assert.match(pipelinePanel, /\/v1\/prospects/)
  assert.match(pipelinePanel, /Relance due/)
  assert.match(pipelinePanel, /Qualifié/)
  assert.match(source, /PipelinePanel/)
  assert.match(source, /Pipeline/)
})

test('pending approvals are polled during a live voice session', () => {
  assert.match(source, /setInterval/)
  assert.match(source, /email_send: 'Envoyer un e-mail'/)
})

test('proactive morning brief surfaces as a dismissible strip', () => {
  assert.match(source, /\/v1\/briefings\/today/)
  assert.match(source, /brief du jour est prêt/)
  assert.match(holographicCss, /brief-strip/)
})

test('integrated demo: guided scenarios and honest availability badges', () => {
  assert.match(source, /\/v1\/demo\/scenarios/)
  assert.match(source, /runScenario/)
  assert.match(source, /scenarioStatusLabel/)
  assert.match(source, /RÉEL/)
  assert.match(source, /APERÇU/)
  assert.match(holographicCss, /scenario-tray/)
})

test('visual states reflect backend outcomes including awaiting and success', () => {
  assert.match(app, /awaiting: 'EN ATTENTE DE VOTRE APPROBATION'/)
  assert.match(app, /success: 'TERMINÉ'/)
  assert.match(source, /settleState/)
  assert.match(source, /outcome: VoiceState = 'success'/)
  assert.match(hologram, /awaiting: 0xff9d57/)
})
