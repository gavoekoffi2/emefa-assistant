import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createPlaybackLatch } from '../src/voicePlayback.ts'
import { splitSpeakableText } from '../src/voiceText.ts'

const clonedVoiceSource = readFileSync(new URL('../src/useClonedVoice.ts', import.meta.url), 'utf8')

test('interrupting playback resolves the active wait so the next turn can drain', async () => {
  const latch = createPlaybackLatch()
  let resolved = false
  const waiting = latch.promise.then(() => { resolved = true })

  latch.settle()
  await waiting

  assert.equal(resolved, true)
  assert.equal(latch.settle(), false, 'settlement must be idempotent')
})

test('punctuation-only stream tails never create a TTS request', () => {
  assert.deepEqual(splitSpeakableText('.', true), { segments: [], remainder: '' })
  assert.deepEqual(splitSpeakableText('…', true), { segments: [], remainder: '' })
  assert.deepEqual(splitSpeakableText('Réponse utile.', true).segments, ['Réponse utile.'])
})

test('the cloned voice settles active playback when the user interrupts', () => {
  assert.match(clonedVoiceSource, /playbackLatchRef/)
  assert.match(clonedVoiceSource, /playbackLatchRef\.current\?\.settle\(\)/)
  assert.match(clonedVoiceSource, /createPlaybackLatch\(\)/)
})
