import React, { useEffect, useState } from 'react'
import Rail from './components/Rail.jsx'
import UploadPanel from './components/UploadPanel.jsx'
import ImpactResults from './components/ImpactResults.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import { createSession, uploadDocuments, runAnalysis, extractErrorMessage } from './api.js'

export default function App() {
  const [sessionId, setSessionId] = useState(null)
  const [stage, setStage] = useState('upload') // upload -> ready -> analyzing -> analyzed
  const [clauseCounts, setClauseCounts] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)

  useEffect(() => {
    createSession().then((data) => setSessionId(data.session_id)).catch((err) => setError(extractErrorMessage(err)))
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
      await handleAnalyze()
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsProcessing(false)
    }
  }

  async function handleAnalyze() {
    setError(null)
    setIsProcessing(true)
    setStage('analyzing')
    try {
      const data = await runAnalysis(sessionId)
      const data = await runAnalysis(sessionId)
      console.log(data) 
      console.log(data.result)
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
          </>
        )}
      </main>
    </div>
  )
}
