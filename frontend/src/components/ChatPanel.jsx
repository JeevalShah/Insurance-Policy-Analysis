import React, { useState, useRef, useEffect } from 'react'
import { sendChatMessage, extractErrorMessage } from '../api.js'

export default function ChatPanel({ sessionId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState(null)
  const logRef = useRef(null)

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [messages, isSending])

  async function handleSend() {
    const message = input.trim()
    if (!message || isSending) return

    setMessages((prev) => [...prev, { role: 'user', content: message }])
    setInput('')
    setIsSending(true)
    setError(null)

    try {
      const data = await sendChatMessage(sessionId, message)
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer, sources: data.sources }])
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="chat-panel">
      <span className="eyebrow">Step 03</span>
      <h1 className="page-title">Query the file</h1>
      <p className="page-lede">
        Ask about specific clauses, why a relationship was classified a certain
        way, or what else the regulation touches. Answers are grounded in the
        retrieved policy clauses.
      </p>

      {error && <div className="error-banner">{error}</div>}

      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="chat-typing">No questions yet — ask about a clause or classification above.</div>
        )}
        {messages.map((m, i) => (
          <div className={`chat-bubble ${m.role}`} key={i}>
            {m.content}
            {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
              <div className="chat-sources">
                Grounded in: {m.sources.map((s) => `Clause ${s.clause_id}`).join(', ')}
              </div>
            )}
          </div>
        ))}
        {isSending && <div className="chat-typing">Thinking…</div>}
      </div>

      <div className="chat-input-row">
        <input
          type="text"
          placeholder="e.g. Why was Clause 2.1 marked redundant?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSend() }}
        />
        <button className="btn btn-primary" onClick={handleSend} disabled={isSending || !input.trim()}>
          Ask
        </button>
      </div>
    </div>
  )
}
