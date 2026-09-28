import React, { useEffect, useState } from 'react'
import Rail from './components/Rail.jsx'
import UploadPanel from './components/UploadPanel.jsx'
import ImpactResults from './components/ImpactResults.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import GraphVisualizer from './components/GraphVisualizer.jsx' // Add this line
import { createSession, uploadDocuments, runAnalysis, getSessionStatus, extractErrorMessage } from './api.js'

export default function App() {
  const [sessionId, setSessionId] = useState(null)
  const [stage, setStage] = useState('upload') // upload -> ready -> analyzing -> analyzed
  const [clauseCounts, setClauseCounts] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)

  useEffect(() => {
    async function initializeSession() {
      const savedSessionId = localStorage.getItem('rag_session_id')
      
      if (savedSessionId) {
        try {
          const statusData = await getSessionStatus(savedSessionId)
          setSessionId(statusData.session_id)
          setClauseCounts({
            policy: statusData.policy_clause_count,
            regulation: statusData.regulation_clause_count,
          })

          if (statusData.has_analysis) {
            setStage('ready')
            await handleAnalyze(statusData.session_id) 
          } else if (statusData.policy_clause_count > 0) {
            setStage('ready')
          }
          return; 
        } catch (err) {
          console.warn("Could not restore session, creating a new one.", err)
          localStorage.removeItem('rag_session_id')
        }
      }

      createSession()
        .then((data) => {
          setSessionId(data.session_id)
          localStorage.setItem('rag_session_id', data.session_id)
        })
        .catch((err) => setError(extractErrorMessage(err)))
    }

    initializeSession()
  }, [])

  async function handleUpload(regulationFiles, policyFiles) {
    setError(null)
    setIsProcessing(true)
    try {
      const data = await uploadDocuments(sessionId, regulationFiles, policyFiles)
      setClauseCounts({
        policy: data.policy_clause_count,
        regulation: data.regulation_clause_count,
      })
      setStage('ready')
      await handleAnalyze(sessionId)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleAnalyze(activeSessionId = sessionId) {
    setError(null)
    setIsProcessing(true)
    setStage('analyzing')
    try {
      const data = await runAnalysis(activeSessionId)
      setResult(data.result)
      setStage('analyzed')
    } catch (err) {
      setError(extractErrorMessage(err))
      setStage('ready')
    } finally {
      setIsProcessing(false)
    }
  }

  const currentStep = stage === 'upload' || stage === 'ready' ? 'upload' : stage === 'analyzing' ? 'analyze' : 'chat'

  return (
    <div className="app-shell">
      <Rail currentStep={currentStep} />

      <main className="main">
        <div className="mobile-brand">Regulatory Impact Console</div>

        {error && <div className="error-banner">{error}</div>}

        {(stage === 'upload' || stage === 'ready') && (
          <UploadPanel onSubmit={handleUpload} isProcessing={isProcessing} />
        )}

        {stage === 'analyzing' && (
          <div className="empty-state">
            <div className="mark"><span className="spinner" style={{ borderTopColor: 'var(--ink)' }} />Running impact analysis…</div>
            <p>
              Matching {clauseCounts?.regulation ?? '—'} regulatory clauses against{' '}
              {clauseCounts?.policy ?? '—'} policy clauses, classifying each match, and
              tracing indirect impacts. This runs the local llama3 model once per match, so
              larger document sets take a few minutes.
            </p>
          </div>
        )}

        {stage === 'analyzed' && (
          <>
            <ImpactResults result={result} />
            <ChatPanel sessionId={sessionId} />
            <GraphVisualizer sessionId={sessionId} />
          </>
        )}
      </main>
    </div>
  )
}