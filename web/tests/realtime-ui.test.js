import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../src/VoiceRoom.tsx', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const hologram = readFileSync(new URL('../src/HolographicUniverse.tsx', import.meta.url), 'utf8')
const holographicCss = readFileSync(new URL('../src/Holographic.css', import.meta.url), 'utf8')
const appCss = readFileSync(new URL('../src/App.css', import.meta.url), 'utf8')
const deliverablesPanel = readFileSync(new URL('../src/DeliverablesPanel.tsx', import.meta.url), 'utf8')
const face = readFileSync(new URL('../src/EMEFAFace.tsx', import.meta.url), 'utf8')
const faceCss = readFileSync(new URL('../src/EMEFAFace.css', import.meta.url), 'utf8')

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

test('3D holographic face mesh follows real assistant output audio', () => {
  assert.match(source, /EMEFAFace/)
  assert.match(source, /getOutputVolume=\{conversation\.getOutputVolume\}/)
  assert.match(source, /getOutputFrequencyData=\{conversation\.getOutputByteFrequencyData\}/)
  assert.match(source, /visualMode/)
  assert.match(face, /outputRef\.current\(\)/)
  assert.match(face, /frequencyRef\.current\(\)/)
  assert.match(face, /requestAnimationFrame/)
  assert.match(face, /THREE\.WebGLRenderer/)
  assert.match(face, /THREE\.LineLoop/)
  assert.match(face, /THREE\.Points/)
  assert.match(face, /lowerPosition\.setXYZ/)
  assert.match(face, /spectral centroid|centroid/)
  assert.match(face, /targetRound/)
  assert.match(face, /targetWide/)
  assert.match(face, /Tiny deterministic saccades/)
  assert.match(face, /--voice-level/)
  assert.match(face, /Visage holographique 3D d’EMEFA/)
  assert.match(face, /FACIAL MESH/)
  assert.match(faceCss, /var\(--voice-level\)/)
  assert.match(faceCss, /emefa-wireframe-canvas/)
  assert.match(faceCss, /emefa-projection-cone/)
  assert.match(faceCss, /repeating-linear-gradient/)
})

test('holographic entity uses a tall, wider human feminine head instead of a spherical cage', () => {
  assert.match(face, /HEAD_WIDTH_PROFILE/)
  assert.match(face, /FACE_DEPTH_PROFILE/)
  assert.match(face, /visibly elongated skull, broad forehead/)
  assert.match(face, /VISIBLE_CROWN/)
  assert.match(face, /HEAD_WIDTH_SCALE = 1\.8/)
  assert.match(face, /FEATURE_WIDTH_SCALE = 1\.65/)
  assert.match(face, /features\.scale\.x = FEATURE_WIDTH_SCALE/)
  assert.match(face, /prevent the cranium from reading as a striped fruit/)
  assert.match(face, /colorWrite: false, depthWrite: true/)
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

test('live voice can execute governed EMEFA actions through the authenticated client tool', () => {
  assert.match(source, /clientTools:\s*\{[\s\S]*emefa_execute:/)
  assert.match(source, /emefa_execute:[\s\S]*\/v1\/agent\/runs/)
  assert.match(source, /JSON\.stringify\(\{ message: request \}\)/)
  assert.match(source, /credentials: 'include'/)
  assert.match(source, /setApproval\(\{[\s\S]*action_id: run\.action_id/)
  assert.match(source, /conversation\.sendContextualUpdate\(run\.answer\)/)
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

test('personalization is conversational or imported from one website URL', () => {
  const panel = readFileSync(new URL('../src/ProfilePanel.tsx', import.meta.url), 'utf8')
  assert.match(panel, /Parler avec EMEFA/)
  assert.match(panel, /Importer votre site/)
  assert.match(panel, /\/v1\/assistant\/business\/import/)
  assert.match(panel, /onStartInterview/)
  assert.match(panel, /profile-advanced/)
  assert.match(source, /startProfileInterview/)
  assert.match(source, /Pose une seule question courte à la fois/)
  assert.match(source, /appelle emefa_execute/)
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
  assert.match(source, /tool_execution_failed:/)
  assert.match(source, /Rien n’a été confirmé comme exécuté/)
  assert.match(hologram, /awaiting: 0xff9d57/)
})

test('a WebGL failure keeps the voice interface available in simplified mode', () => {
  assert.match(hologram, /try \{/)
  assert.match(hologram, /new THREE\.WebGLRenderer/)
  assert.match(hologram, /catch \{/)
  assert.match(hologram, /webgl-fallback/)
  assert.match(hologram, /mode visuel simplifié/)
})

test('deliverables workspace persistently lists generated results and source files', () => {
  assert.match(source, /DeliverablesPanel/)
  assert.match(source, /openDeliverables/)
  assert.match(source, /\/v1\/documents/)
  assert.match(source, /dock-deliverables/)
  assert.match(deliverablesPanel, /Résultats d’EMEFA/)
  assert.match(deliverablesPanel, /Fichiers envoyés/)
  assert.match(deliverablesPanel, /Télécharger/)
  assert.match(deliverablesPanel, /download/)
  assert.match(deliverablesPanel, /Les résultats restent disponibles après la conversation/)
  assert.match(holographicCss, /deliverables-panel/)
})

test('upload confirmation can be closed and cannot cover mobile voice controls', () => {
  assert.match(source, /fileStripOpen/)
  assert.match(source, /setFileStripOpen\(false\)/)
  assert.match(source, /Fermer la confirmation de fichier/)
  assert.match(source, /Voir l’espace fichiers/)
  assert.match(holographicCss, /\.voice-controls\{position:relative;z-index:20\}/)
  assert.match(holographicCss, /\.file-strip\{position:fixed;[^}]*top:/)
  assert.match(holographicCss, /bottom:auto/)
  assert.doesNotMatch(appCss, /\.file-strip\{[^}]*pointer-events:none/)
})
