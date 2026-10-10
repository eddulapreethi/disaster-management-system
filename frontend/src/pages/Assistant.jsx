import { useState } from 'react'
import { apiPost } from '../services/api'

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
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Ask about disaster-management concepts, this project, or its latest stored system data.',
    },
  ])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function ask(value = question) {
    const submitted = value.trim()
    if (!submitted || loading) return

    const nextUserMessage = { role: 'user', text: submitted }
    const recentHistory = messages
      .filter(message => message.role === 'assistant' || message.role === 'user')
      .slice(-8)
      .map(message => ({ role: message.role, text: message.text }))

    setMessages(current => [...current, nextUserMessage])
    setQuestion('')
    setError('')
    setLoading(true)
    try {
      const response = await apiPost('/assistant/chat', { question: submitted, history: recentHistory })
      setMessages(current => [
        ...current,
        {
          role: 'assistant',
          text: response.answer,
          category: response.category,
          disclaimer: response.disclaimer,
          sources: response.sources || [],
        },
      ])
    } catch (requestError) {
      setError(requestError.message || 'Could not get an assistant response.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="title">DisasterGuard assistant</h2>
      <p className="sub">Deterministic answers about hazards and the project, with read-only live context from stored system data. It is not an emergency authority.</p>
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
          {loading && <div className="msg bot" role="status">Checking the project data…</div>}
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
            onChange={event => setQuestion(event.target.value)}
            maxLength={1000}
            placeholder="Ask about hazards, readiness, or latest stored data…"
            disabled={loading}
          />
          <button className="btn" type="submit" disabled={loading || !question.trim()}>{loading ? 'Checking…' : 'Ask'}</button>
        </form>
      </section>
      {error && <p role="alert" className="error">{error}</p>}
    </div>
  )
}
