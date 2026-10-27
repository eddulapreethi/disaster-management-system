export const ASSISTANT_CONVERSATION_KEY = 'disasterguard_assistant_messages'
export const ASSISTANT_DRAFT_KEY = 'disasterguard_assistant_draft'

export const INITIAL_ASSISTANT_MESSAGE = {
  role: 'assistant',
  text: 'Ask about disaster-management concepts, this project, or its latest stored system data.',
  created_at: new Date().toISOString(),
}

export function getAssistantStorage() {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

export function loadAssistantConversation(storage) {
  try {
    const saved = JSON.parse(storage.getItem(ASSISTANT_CONVERSATION_KEY) || 'null')
    if (!Array.isArray(saved)) return [INITIAL_ASSISTANT_MESSAGE]
    const messages = saved
      .filter(message => (
        message
        && (message.role === 'user' || message.role === 'assistant')
        && typeof message.text === 'string'
        && message.text.trim()
      ))
      .slice(-200)
    return messages.length ? messages : [INITIAL_ASSISTANT_MESSAGE]
  } catch {
    return [INITIAL_ASSISTANT_MESSAGE]
  }
}

export function loadAssistantDraft(storage) {
  try {
    return storage.getItem(ASSISTANT_DRAFT_KEY) || ''
  } catch {
    return ''
  }
}

function redactSensitiveText(text) {
  return text
    .replace(
      /((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|authorization)\s*[:=]\s*)[^\s,;]+/gi,
      '$1[REDACTED]',
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b/g, '[REDACTED]')
}

export function saveAssistantDraft(storage, draft) {
  try {
    if (draft) {
      storage.setItem(ASSISTANT_DRAFT_KEY, redactSensitiveText(draft))
    } else {
      storage.removeItem(ASSISTANT_DRAFT_KEY)
    }
    return true
  } catch {
    return false
  }
}

export function saveAssistantConversation(storage, messages) {
  try {
    const storedMessages = messages.slice(-200).map(message => ({
      ...message,
      text: redactSensitiveText(message.text),
    }))
    storage.setItem(ASSISTANT_CONVERSATION_KEY, JSON.stringify(storedMessages))
    return true
  } catch {
    return false
  }
}

export function clearAssistantConversation(storage) {
  try {
    storage.removeItem(ASSISTANT_CONVERSATION_KEY)
    storage.removeItem(ASSISTANT_DRAFT_KEY)
    return true
  } catch {
    return false
  }
}
