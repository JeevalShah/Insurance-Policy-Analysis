import React, { useEffect, useState } from 'react'
import AuthBar from './components/AuthBar.jsx'
import VersionConsole from './components/VersionConsole.jsx'
import Rail from './components/Rail.jsx'
import UploadPanel from './components/UploadPanel.jsx'
import ImpactResults from './components/ImpactResults.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import GraphVisualizer from './components/GraphVisualizer.jsx'
import RiskDashboard from './components/RiskDashboard.jsx'
import CrossfireAlerts from './components/CrossfireAlerts.jsx'
import {
  getCurrentUser,
  createSession,
  uploadDocuments,
  runAnalysis,
  getSessionStatus,
  extractErrorMessage
} from './api.js'

export default function App() {
  const [currentUser, setCurrentUser] = useState(null)
  const [appMode, setAppMode] = useState('versioning') // 'versioning' | 'analysis'
  const [sessionId, setSessionId] = useState(null)
  const [stage, setStage] = useState('upload') // upload -> ready -> analyzing -> analyzed
  const [clauseCounts, setClauseCounts] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)

  // Check authenticated user on initial load
  useEffect(() => {
    async function checkAuth() {
      try {
        const user = await getCurrentUser()
        if (user) {
          setCurrentUser(user)
          setAppMode('versioning')
        }
      } catch (e) {
        console.warn('No active auth session', e)
      }
    }
    checkAuth()
  }, [])

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
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: 'var(--paper)' }}>
      {/* Top Authentication Bar */}
      <AuthBar user={currentUser} onAuthChange={setCurrentUser} />

      {/* Mode Navigation Bar */}
      <div style={{
        display: 'flex',
        gap: '12px',
        padding: '10px 24px',
        backgroundColor: '#fff',
        borderBottom: '1px solid var(--line)',
        alignItems: 'center'
      }}>
        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase' }}>
          Workspace View:
        </span>
        <button
          className={appMode === 'versioning' ? 'btn btn-primary' : 'btn btn-secondary'}
          style={{ padding: '6px 14px', fontSize: '13px' }}
          onClick={() => setAppMode('versioning')}
        >
          📂 Dynamic Version & Graph Management
        </button>
        <button
          className={appMode === 'analysis' ? 'btn btn-primary' : 'btn btn-secondary'}
          style={{ padding: '6px 14px', fontSize: '13px' }}
          onClick={() => setAppMode('analysis')}
        >
          ⚖️ Regulatory Impact & Crossfire Console
        </button>
      </div>

      {/* Main Content Area */}
      {appMode === 'versioning' ? (
        <main style={{ padding: '24px 32px', maxWidth: '1200px', margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
          <VersionConsole user={currentUser} />
        </main>
      ) : (
        <div className="app-shell" style={{ flex: 1 }}>
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
                <RiskDashboard sessionId={sessionId} />
                <ImpactResults result={result} />
                <CrossfireAlerts sessionId={sessionId} />
                <ChatPanel sessionId={sessionId} />
                <GraphVisualizer sessionId={sessionId} />
              </>
            )}
          </main>
        </div>
      )}
    </div>
  )
}
