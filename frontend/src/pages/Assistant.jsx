import { useState } from 'react'
import { apiPost } from '../services/api'

const QUICK_QUESTIONS = [
  'What is a flood?',
  'What does READY mean?',
  'Why is hydrology STALE?',
  'What is the latest weather?',
]

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

    setMessages(current => [...current, { role: 'user', text: submitted }])
    setQuestion('')
    setError('')
    setLoading(true)
    try {
      const response = await apiPost('/assistant/chat', { question: submitted })
      setMessages(current => [
        ...current,
        { role: 'assistant', text: response.answer, category: response.category, disclaimer: response.disclaimer },
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
              <div>{message.text}</div>
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
