import { useEffect, useState } from 'react'
import { apiPost } from '../services/api'
import {
  clearAssistantConversation,
  getAssistantStorage,
  INITIAL_ASSISTANT_MESSAGE,
  loadAssistantDraft,
  loadAssistantConversation,
  saveAssistantDraft,
  saveAssistantConversation,
} from '../services/assistantConversation'

const QUICK_QUESTIONS = [
  'What is a flood?',
  'What does HYDROLOGY STALE mean?',
  'How does France manage flood risk?',
  'What is the latest weather?',
]

function formatMessageText(text) {
  return String(text || '').split(/\n+/).filter(Boolean).map((paragraph, index) => (
    <p key={`${paragraph.slice(0, 20)}-${index}`}>{paragraph}</p>
  ))
}

export default function Assistant() {
  const [messages, setMessages] = useState(() => loadAssistantConversation(getAssistantStorage()))
  const [question, setQuestion] = useState(() => loadAssistantDraft(getAssistantStorage()))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [failedQuestion, setFailedQuestion] = useState('')
  const [historySaveError, setHistorySaveError] = useState(false)
  const [draftSaveError, setDraftSaveError] = useState(false)

  useEffect(() => {
    setHistorySaveError(!saveAssistantConversation(getAssistantStorage(), messages))
  }, [messages])

  function startNewConversation() {
    setHistorySaveError(!clearAssistantConversation(getAssistantStorage()))
    setMessages([{ ...INITIAL_ASSISTANT_MESSAGE, created_at: new Date().toISOString() }])
    setQuestion('')
    setDraftSaveError(false)
    setError('')
    setFailedQuestion('')
  }

  async function ask(value = question, retry = false) {
    const submitted = value.trim()
    if (!submitted || loading) return

    const nextUserMessage = { role: 'user', text: submitted, created_at: new Date().toISOString() }
    const historyMessages = messages
      .filter((message, index) => index > 0 && (message.role === 'assistant' || message.role === 'user'))
      .map(message => ({ role: message.role, text: message.text }))
    const lastHistoryMessage = historyMessages[historyMessages.length - 1]
    if (retry && lastHistoryMessage?.role === 'user' && lastHistoryMessage.text === submitted) {
      historyMessages.pop()
    }
    const recentHistory = historyMessages.slice(-8)

    if (!retry) setMessages(current => [...current, nextUserMessage])
    setQuestion('')
    setDraftSaveError(!saveAssistantDraft(getAssistantStorage(), ''))
    setError('')
    setLoading(true)
    try {
      const response = await apiPost(
        '/assistant/chat',
        { question: submitted, history: recentHistory },
        { timeoutMs: 125000 },
      )
      if (response.category === 'assistant_unavailable') {
        setError(response.answer || 'The assistant could not answer. Please retry.')
        setFailedQuestion(submitted)
        return
      }
      setMessages(current => [
        ...current,
        {
          role: 'assistant',
          text: response.answer,
          created_at: new Date().toISOString(),
          category: response.category,
          disclaimer: response.disclaimer,
          sources: response.sources || [],
        },
      ])
      setFailedQuestion('')
    } catch (requestError) {
      setError(
        requestError.name === 'TimeoutError'
          ? 'The assistant request timed out. Please retry.'
          : requestError.message || 'Could not get an assistant response.',
      )
      setFailedQuestion(submitted)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="title">DisasterGuard assistant</h2>
      <p className="sub">Ask general questions or about DisasterGuard. Open-ended answers use the local Ollama model; project data is answered from stored records. It is not an emergency authority.</p>
      <button className="btn-outline" type="button" onClick={startNewConversation} disabled={loading}>New conversation</button>
      <section className="chatwrap" aria-label="DisasterGuard assistant chat">
        <div className="chatlog" aria-live="polite">
          {messages.map((message, index) => (
            <div className={`msg ${message.role === 'user' ? 'user' : 'bot'}`} key={`${index}-${message.role}`}>
              {message.category && <strong className="chat-category">{message.category.replaceAll('_', ' ')}</strong>}
              <div style={{ whiteSpace: 'pre-wrap' }}>{formatMessageText(message.text)}</div>
              {message.sources && message.sources.length > 0 && (
                <div style={{ marginTop: '0.75rem' }}>
                  <strong>Sources</strong>
                  <ul style={{ margin: '0.25rem 0 0 1.25rem', padding: 0 }}>
                    {message.sources.map((source, sourceIndex) => (
                      <li key={`${source.url || source.title}-${sourceIndex}`}>
                        <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {message.disclaimer && <small className="chat-disclaimer">{message.disclaimer}</small>}
            </div>
          ))}
          {loading && <div className="msg bot" role="status">Generating a response…</div>}
        </div>
        <div className="quickrow">
          {QUICK_QUESTIONS.map(item => (
            <button className="qbtn" key={item} type="button" disabled={loading} onClick={() => ask(item)}>{item}</button>
          ))}
        </div>
        <form className="chatinput" onSubmit={event => { event.preventDefault(); ask() }}>
          <input
            aria-label="Ask a question"
            value={question}
            onChange={event => {
              const draft = event.target.value
              setQuestion(draft)
              setDraftSaveError(!saveAssistantDraft(getAssistantStorage(), draft))
            }}
            maxLength={1000}
            placeholder="Ask anything, or ask about project and stored data…"
            disabled={loading}
          />
          <button className="btn" type="submit" disabled={loading || !question.trim()}>{loading ? 'Checking…' : 'Ask'}</button>
        </form>
      </section>
      {(historySaveError || draftSaveError) && <p role="alert" className="error">The prompt or conversation could not be saved in this browser tab; it may be lost when navigating away.</p>}
      {error && (
        <p role="alert" className="error">
          {error}
          {failedQuestion && (
            <button className="qbtn" type="button" disabled={loading} onClick={() => ask(failedQuestion, true)}>
              Retry
            </button>
          )}
        </p>
      )}
    </div>
  )
}
