import test from 'node:test'
import assert from 'node:assert/strict'

import { alertLocation, alertTimestamp } from '../src/services/alertPresentation.js'
import {
  ASSISTANT_CONVERSATION_KEY,
  ASSISTANT_DRAFT_KEY,
  clearAssistantConversation,
  getAssistantStorage,
  INITIAL_ASSISTANT_MESSAGE,
  loadAssistantDraft,
  loadAssistantConversation,
  saveAssistantDraft,
  saveAssistantConversation,
} from '../src/services/assistantConversation.js'

test('alert card fields match the persisted API alert schema', () => {
  const alert = {
    latitude: 9.9312,
    longitude: 76.2673,
    created_at: '2026-10-11T10:00:00Z',
  }
  assert.equal(alertLocation(alert), '9.9312, 76.2673')
  assert.equal(alertTimestamp(alert), new Date(alert.created_at).toLocaleString())
})

test('alerts without coordinates or valid timestamps render an explicit unavailable state', () => {
  assert.equal(alertLocation({ latitude: null, longitude: null }), 'Location unavailable')
  assert.equal(alertTimestamp({ created_at: 'not-a-date' }), 'Timestamp unavailable')
})

test('assistant history persists and restores ordered roles and timestamps', () => {
  const values = new Map()
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  }
  const messages = [
    INITIAL_ASSISTANT_MESSAGE,
    { role: 'user', text: 'Question', created_at: '2026-10-27T00:00:00Z' },
    { role: 'assistant', text: 'Answer', created_at: '2026-10-27T00:00:01Z' },
  ]

  assert.equal(saveAssistantConversation(storage, messages), true)
  assert.equal(saveAssistantDraft(storage, 'Unsent question'), true)
  assert.deepEqual(loadAssistantConversation(storage), messages)
  assert.equal(loadAssistantDraft(storage), 'Unsent question')
  assert.ok(values.has(ASSISTANT_CONVERSATION_KEY))
  assert.equal(clearAssistantConversation(storage), true)
  assert.deepEqual(loadAssistantConversation(storage), [INITIAL_ASSISTANT_MESSAGE])
  assert.equal(loadAssistantDraft(storage), '')
  assert.equal(values.has(ASSISTANT_DRAFT_KEY), false)
})

test('assistant history redacts common credential formats before browser persistence', () => {
  let saved
  const storage = {
    setItem: (key, value) => { saved = value },
  }
  saveAssistantConversation(storage, [
    { role: 'user', text: 'API_KEY=examplesecret Bearer abc.def.token' },
  ])
  assert.doesNotMatch(saved, /examplesecret|abc\.def\.token/)
  assert.match(saved, /\[REDACTED\]/)
})

test('assistant history recovers safely from malformed browser storage', () => {
  const storage = { getItem: () => '{bad json' }
  assert.deepEqual(loadAssistantConversation(storage), [INITIAL_ASSISTANT_MESSAGE])
})

test('assistant history handles unavailable browser storage without crashing', () => {
  assert.equal(getAssistantStorage(), null)
  assert.deepEqual(loadAssistantConversation(null), [INITIAL_ASSISTANT_MESSAGE])
  assert.equal(saveAssistantConversation(null, []), false)
  assert.equal(loadAssistantDraft(null), '')
  assert.equal(saveAssistantDraft(null, 'Question'), false)
  assert.equal(clearAssistantConversation(null), false)
})
