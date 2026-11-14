import React, { useState, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import {
  getUserDocuments,
  uploadVersionDocument,
  getDocumentVersions,
  getDocumentHistory,
  computeVersionDiff,
  executeVersionRollback,
  getVersionGraph,
  extractErrorMessage,
} from '../api.js'

export default function VersionConsole({ user }) {
  const [activeTab, setActiveTab] = useState('documents') // 'documents' | 'upload' | 'diff' | 'graph'
  const [documents, setDocuments] = useState([])
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [docVersions, setDocVersions] = useState([])
  const [docHistory, setDocHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Upload Form State
  const [uploadMode, setUploadMode] = useState('new') // 'new' | 'update'
  const [targetDocId, setTargetDocId] = useState('')
  const [docType, setDocType] = useState('policy')
  const [explicitDocId, setExplicitDocId] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadProgressStep, setUploadProgressStep] = useState(null)
  const [uploadResult, setUploadResult] = useState(null)

  // Diff & Rollback State
  const [diffOldVer, setDiffOldVer] = useState(1)
  const [diffNewVer, setDiffNewVer] = useState(2)
  const [diffManifest, setDiffManifest] = useState(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [rollbackReport, setRollbackReport] = useState(null)

  // Graph State
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [graphLoading, setGraphLoading] = useState(false)

  // Load user documents on mount or user change
  useEffect(() => {
    if (user) {
      loadDocuments()
    } else {
      setDocuments([])
      setSelectedDocId(null)
    }
  }, [user])

  async function loadDocuments() {
    setLoading(true)
    setError(null)
    try {
      const docs = await getUserDocuments()
      setDocuments(docs)
      if (docs.length > 0 && !selectedDocId) {
        setSelectedDocId(docs[0].doc_id)
        loadDocDetails(docs[0].doc_id)
      }
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function loadDocDetails(docId) {
    if (!docId) return
    try {
      const [versions, history] = await Promise.all([
        getDocumentVersions(docId),
        getDocumentHistory(docId),
      ])
      setDocVersions(versions)
      setDocHistory(history)
      if (versions.length >= 2) {
        setDiffOldVer(versions[versions.length - 2].version_num)
        setDiffNewVer(versions[versions.length - 1].version_num)
      } else if (versions.length === 1) {
        setDiffOldVer(versions[0].version_num)
        setDiffNewVer(versions[0].version_num)
      }
    } catch (err) {
      console.error('Failed to load document details', err)
    }
  }

  function handleSelectDoc(docId) {
    setSelectedDocId(docId)
    setTargetDocId(docId)
    loadDocDetails(docId)
  }

  // Handle Document Upload / Incremental Update
  async function handleUploadSubmit(e) {
    e.preventDefault()
    if (!selectedFile) {
      setError('Please select a file to upload.')
      return
    }

    setError(null)
    setUploadResult(null)
    setUploadProgressStep('Resolving document identity and checking existing versions…')

    const formData = new FormData()
    formData.append('file', selectedFile)
    formData.append('doc_type', docType)

    if (uploadMode === 'update' && targetDocId) {
      formData.append('target_doc_id', targetDocId)
    } else if (explicitDocId) {
      formData.append('doc_id', explicitDocId)
    }

    try {
      setTimeout(() => setUploadProgressStep('Comparing content fingerprints & detecting changes…'), 300)
      setTimeout(() => setUploadProgressStep('Executing targeted graph update & reusing embeddings…'), 700)

      const result = await uploadVersionDocument(formData)
      setUploadResult(result)
      setUploadProgressStep(null)
      setSelectedFile(null)

      // Refresh documents
      await loadDocuments()
      if (result.document_id) {
        setSelectedDocId(result.document_id)
        loadDocDetails(result.document_id)
      }
    } catch (err) {
      setUploadProgressStep(null)
      setError(extractErrorMessage(err))
    }
  }

  // Run Version Diff
  async function handleRunDiff() {
    if (!selectedDocId) return
    setDiffLoading(true)
    setError(null)
    try {
      const manifest = await computeVersionDiff(selectedDocId, parseInt(diffOldVer), parseInt(diffNewVer))
      setDiffManifest(manifest)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setDiffLoading(false)
    }
  }

  // Execute Rollback
  async function handleRollback(dryRun = true) {
    if (!selectedDocId || !diffOldVer) return
    setLoading(true)
    setError(null)
    try {
      const report = await executeVersionRollback(selectedDocId, parseInt(diffOldVer), dryRun)
      setRollbackReport(report)
      if (!dryRun) {
        await loadDocuments()
        loadDocDetails(selectedDocId)
      }
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // Load Document Graph
  async function handleLoadGraph() {
    if (!selectedDocId) return
    setGraphLoading(true)
    try {
      const data = await getVersionGraph(selectedDocId)
      setGraphData(data)
    } catch (err) {
      console.error('Failed to load version graph', err)
    } finally {
      setGraphLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'graph' && selectedDocId) {
      handleLoadGraph()
    }
  }, [activeTab, selectedDocId])

  if (!user) {
    return (
      <div className="empty-state" style={{ padding: '60px 20px', textAlign: 'center' }}>
        <div style={{ fontSize: '32px', marginBottom: '16px' }}>🔐</div>
        <h2>Multi-User Version-Aware Workspace</h2>
        <p style={{ maxWidth: '500px', margin: '0 auto 24px', color: 'var(--muted)' }}>
          Please sign in or create an account using the top bar to access isolated documents,
          automatic version tracking, intelligent graph reuse, and targeted incremental updates.
        </p>
      </div>
    )
  }

  const selectedDoc = documents.find((d) => d.doc_id === selectedDocId)

  return (
    <section className="version-console" style={{ marginTop: '24px' }}>
      {/* Metrics Banner */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '16px',
        marginBottom: '24px'
      }}>
        <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '16px', borderRadius: '4px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600 }}>
            Registered Documents
          </div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--ink)', marginTop: '4px' }}>
            {documents.length}
          </div>
        </div>

        <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '16px', borderRadius: '4px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600 }}>
            Active Document Versions
          </div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--ink)', marginTop: '4px' }}>
            {documents.reduce((acc, d) => acc + (d.current_version || 1), 0)}
          </div>
        </div>

        <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '16px', borderRadius: '4px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600 }}>
            Ownership & Isolation
          </div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#16a34a', marginTop: '8px' }}>
            ✓ Scoped to {user.username}
          </div>
        </div>
      </div>

      {/* Console Tab Navigation */}
      <div style={{ display: 'flex', borderBottom: '2px solid var(--line)', marginBottom: '24px', gap: '8px' }}>
        <button
          onClick={() => setActiveTab('documents')}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'documents' ? '2px solid var(--ink)' : '2px solid transparent',
            color: activeTab === 'documents' ? 'var(--ink)' : 'var(--muted)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '14px',
            marginBottom: '-2px',
          }}
        >
          My Documents & Versions
        </button>

        <button
          onClick={() => setActiveTab('upload')}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'upload' ? '2px solid var(--ink)' : '2px solid transparent',
            color: activeTab === 'upload' ? 'var(--ink)' : 'var(--muted)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '14px',
            marginBottom: '-2px',
          }}
        >
          Upload / Update Document
        </button>

        <button
          onClick={() => { setActiveTab('diff'); if (selectedDocId) handleRunDiff() }}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'diff' ? '2px solid var(--ink)' : '2px solid transparent',
            color: activeTab === 'diff' ? 'var(--ink)' : 'var(--muted)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '14px',
            marginBottom: '-2px',
          }}
        >
          Version Diff & Rollback
        </button>

        <button
          onClick={() => setActiveTab('graph')}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'graph' ? '2px solid var(--ink)' : '2px solid transparent',
            color: activeTab === 'graph' ? 'var(--ink)' : 'var(--muted)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '14px',
            marginBottom: '-2px',
          }}
        >
          Document Knowledge Graph
        </button>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: '16px' }}>
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 1: Documents & Versions List                              */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'documents' && (
        <div>
          {loading && <div className="empty-state"><span className="spinner" /> Loading documents…</div>}

          {!loading && documents.length === 0 && (
            <div className="empty-state">
              <p>No documents registered yet for your account.</p>
              <button className="btn btn-primary" onClick={() => setActiveTab('upload')}>
                Upload your first document
              </button>
            </div>
          )}

          {!loading && documents.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
              <div>
                <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px' }}>Your Registered Filings</h3>
                <div style={{ border: '1px solid var(--line)', borderRadius: '4px', overflow: 'hidden', backgroundColor: '#fff' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                    <thead>
                      <tr style={{ backgroundColor: 'var(--paper)', borderBottom: '1px solid var(--line)' }}>
                        <th style={{ padding: '10px 14px' }}>Document</th>
                        <th style={{ padding: '10px 14px' }}>ID</th>
                        <th style={{ padding: '10px 14px' }}>Type</th>
                        <th style={{ padding: '10px 14px' }}>Active Ver</th>
                        <th style={{ padding: '10px 14px' }}>Updated</th>
                        <th style={{ padding: '10px 14px' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc) => (
                        <tr
                          key={doc.doc_id}
                          style={{
                            borderBottom: '1px solid var(--line)',
                            backgroundColor: selectedDocId === doc.doc_id ? '#f0fdf4' : 'transparent',
                            cursor: 'pointer',
                          }}
                          onClick={() => handleSelectDoc(doc.doc_id)}
                        >
                          <td style={{ padding: '12px 14px', fontWeight: 600, color: 'var(--ink)' }}>{doc.filename}</td>
                          <td style={{ padding: '12px 14px', fontFamily: 'monospace', color: 'var(--muted)' }}>{doc.doc_id}</td>
                          <td style={{ padding: '12px 14px' }}>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '10px',
                              fontSize: '11px',
                              fontWeight: 600,
                              backgroundColor: doc.doc_type === 'regulatory' ? '#fee2e2' : '#e0e7ff',
                              color: doc.doc_type === 'regulatory' ? '#b91c1c' : '#3730a3',
                            }}>
                              {doc.doc_type.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '12px 14px', fontWeight: 600 }}>v{doc.current_version}</td>
                          <td style={{ padding: '12px 14px', color: 'var(--muted)', fontSize: '12px' }}>
                            {new Date(doc.updated_at * 1000).toLocaleDateString()}
                          </td>
                          <td style={{ padding: '12px 14px' }}>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '11px' }}
                              onClick={(e) => { e.stopPropagation(); handleSelectDoc(doc.doc_id); setActiveTab('diff') }}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Version History Sidebar for Selected Doc */}
              <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '18px', borderRadius: '4px', height: 'fit-content' }}>
                <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600 }}>
                  Version History: <span style={{ color: 'var(--ink)' }}>{selectedDoc?.filename || selectedDocId || 'Select a document'}</span>
                </h4>

                {docVersions.length === 0 ? (
                  <p style={{ fontSize: '13px', color: 'var(--muted)' }}>Select a document to inspect snapshots.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {docVersions.map((v) => (
                      <div
                        key={v.version_num}
                        style={{
                          border: '1px solid var(--line)',
                          padding: '10px 12px',
                          borderRadius: '4px',
                          backgroundColor: v.status === 'active' ? '#f0fdf4' : '#fafafa',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600, fontSize: '13px' }}>
                            {v.version_tag || `v${v.version_num}`}
                          </span>
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 600,
                            padding: '2px 6px',
                            borderRadius: '8px',
                            backgroundColor: v.status === 'active' ? '#bbf7d0' : '#e5e7eb',
                            color: v.status === 'active' ? '#166534' : '#4b5563',
                          }}>
                            {v.status.toUpperCase()}
                          </span>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
                          Clauses: {v.clause_count} &middot; {new Date(v.upload_timestamp * 1000).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 2: Upload / Update Document                               */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'upload' && (
        <div style={{ maxWidth: '680px', backgroundColor: '#fff', border: '1px solid var(--line)', padding: '28px', borderRadius: '4px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '17px', fontWeight: 600 }}>
            Dynamic Version-Aware Filing
          </h3>

          <div style={{ display: 'flex', gap: '16px', marginBottom: '20px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
              <input
                type="radio"
                name="uploadMode"
                value="new"
                checked={uploadMode === 'new'}
                onChange={() => setUploadMode('new')}
              />
              <strong>Register New Document</strong>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
              <input
                type="radio"
                name="uploadMode"
                value="update"
                checked={uploadMode === 'update'}
                onChange={() => setUploadMode('update')}
              />
              <strong>Update Existing Document Version</strong>
            </label>
          </div>

          <form onSubmit={handleUploadSubmit}>
            {uploadMode === 'update' && (
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                  Target Document to Update
                </label>
                <select
                  value={targetDocId}
                  onChange={(e) => setTargetDocId(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--line)', fontSize: '14px' }}
                  required
                >
                  <option value="">-- Choose document --</option>
                  {documents.map((d) => (
                    <option key={d.doc_id} value={d.doc_id}>
                      {d.filename} (current: v{d.current_version})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {uploadMode === 'new' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                    Document Type
                  </label>
                  <select
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--line)', fontSize: '14px' }}
                  >
                    <option value="policy">Policy Document (Internal Wording)</option>
                    <option value="regulatory">Regulatory Directive (Mandate / Circular)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                    Custom Document ID (Optional)
                  </label>
                  <input
                    type="text"
                    value={explicitDocId}
                    onChange={(e) => setExplicitDocId(e.target.value)}
                    placeholder="e.g. POLICY_HEALTH_CORP"
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--line)', fontSize: '14px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>
            )}

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                Select File (.pdf, .docx, .txt)
              </label>
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={(e) => setSelectedFile(e.target.files[0] || null)}
                style={{ width: '100%', padding: '8px', border: '1px dashed var(--line)', borderRadius: '4px', background: '#fafafa' }}
                required
              />
            </div>

            {uploadProgressStep && (
              <div style={{
                padding: '12px 16px',
                backgroundColor: '#f8fafc',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
                marginBottom: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                fontSize: '13px'
              }}>
                <span className="spinner" />
                <span>{uploadProgressStep}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={!!uploadProgressStep || !selectedFile}
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px' }}
            >
              {uploadProgressStep ? 'Processing Document…' : uploadMode === 'update' ? 'Submit Version Update' : 'Register & Process Document'}
            </button>
          </form>

          {/* Actual Execution Outcome */}
          {uploadResult && (
            <div style={{
              marginTop: '24px',
              padding: '18px',
              backgroundColor: uploadResult.status === 'unchanged' ? '#eff6ff' : '#f0fdf4',
              border: `1px solid ${uploadResult.status === 'unchanged' ? '#93c5fd' : '#86efac'}`,
              borderRadius: '4px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <strong style={{ fontSize: '15px' }}>
                  {uploadResult.status === 'unchanged' ? '⚡ Scenario B: Unchanged Document Reused' : uploadResult.status === 'created' ? '📄 Scenario A: First-Time Upload Registered' : '🔄 Scenario C: Targeted Incremental Update'}
                </strong>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)' }}>
                  Duration: {uploadResult.duration_seconds}s
                </span>
              </div>

              <p style={{ margin: '0 0 12px', fontSize: '13px' }}>{uploadResult.message}</p>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', fontSize: '12px' }}>
                <div style={{ backgroundColor: '#fff', padding: '8px', borderRadius: '3px', border: '1px solid var(--line)' }}>
                  <div style={{ color: 'var(--muted)' }}>Version</div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>v{uploadResult.version_num || uploadResult.new_version}</div>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '8px', borderRadius: '3px', border: '1px solid var(--line)' }}>
                  <div style={{ color: 'var(--muted)' }}>Embeddings Saved</div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#16a34a' }}>
                    {uploadResult.percentage_embeddings_saved ?? (uploadResult.reused ? 100 : 0)}%
                  </div>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '8px', borderRadius: '3px', border: '1px solid var(--line)' }}>
                  <div style={{ color: 'var(--muted)' }}>Nodes Created/Updated</div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>
                    {uploadResult.nodes_created ?? 0} / {uploadResult.nodes_updated ?? 0}
                  </div>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '8px', borderRadius: '3px', border: '1px solid var(--line)' }}>
                  <div style={{ color: 'var(--muted)' }}>LLM Calls</div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>{uploadResult.llm_calls_made ?? 0}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 3: Version Diff & Rollback Inspector                     */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'diff' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px', backgroundColor: '#fff', padding: '16px', border: '1px solid var(--line)', borderRadius: '4px' }}>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Document</label>
              <select
                value={selectedDocId || ''}
                onChange={(e) => handleSelectDoc(e.target.value)}
                style={{ padding: '6px 10px', fontSize: '13px' }}
              >
                {documents.map((d) => (
                  <option key={d.doc_id} value={d.doc_id}>{d.filename} ({d.doc_id})</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Base Version</label>
              <select
                value={diffOldVer}
                onChange={(e) => setDiffOldVer(e.target.value)}
                style={{ padding: '6px 10px', fontSize: '13px' }}
              >
                {docVersions.map((v) => (
                  <option key={v.version_num} value={v.version_num}>v{v.version_num}</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Target / New Version</label>
              <select
                value={diffNewVer}
                onChange={(e) => setDiffNewVer(e.target.value)}
                style={{ padding: '6px 10px', fontSize: '13px' }}
              >
                {docVersions.map((v) => (
                  <option key={v.version_num} value={v.version_num}>v{v.version_num}</option>
                ))}
              </select>
            </div>

            <div style={{ alignSelf: 'flex-end', display: 'flex', gap: '8px' }}>
              <button className="btn btn-primary" onClick={handleRunDiff} disabled={diffLoading}>
                {diffLoading ? 'Computing…' : 'Compute Version Diff'}
              </button>
              <button
                className="btn btn-secondary"
                style={{ color: '#b91c1c' }}
                onClick={() => handleRollback(true)}
              >
                Simulate Rollback to v{diffOldVer}
              </button>
            </div>
          </div>

          {rollbackReport && (
            <div style={{
              backgroundColor: '#fff7ed',
              border: '1px solid #fdba74',
              padding: '16px',
              borderRadius: '4px',
              marginBottom: '20px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ color: '#c2410c' }}>Rollback Plan (Target: v{rollbackReport.target_version})</strong>
                <button
                  className="btn btn-primary"
                  style={{ backgroundColor: '#c2410c', borderColor: '#c2410c', fontSize: '12px' }}
                  onClick={() => handleRollback(false)}
                >
                  Execute Live Rollback
                </button>
              </div>
              <p style={{ margin: '8px 0 0', fontSize: '13px' }}>
                Clauses to restore: <strong>{rollbackReport.clauses_restored}</strong> &middot;
                Clauses to deactivate: <strong>{rollbackReport.clauses_deactivated}</strong> &middot;
                Clauses to reactivate: <strong>{rollbackReport.clauses_reactivated}</strong>
              </p>
            </div>
          )}

          {/* Diff Manifest Breakdown */}
          {diffManifest && (
            <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '20px', borderRadius: '4px' }}>
              <h4 style={{ margin: '0 0 16px', fontSize: '15px' }}>
                Change Manifest: v{diffManifest.old_version} &rarr; v{diffManifest.new_version}
              </h4>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
                <div style={{ backgroundColor: '#dcfce7', padding: '12px', borderRadius: '4px', textAlign: 'center' }}>
                  <div style={{ color: '#166534', fontSize: '11px', fontWeight: 600 }}>ADDED</div>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: '#166534' }}>{diffManifest.summary.added_count}</div>
                </div>
                <div style={{ backgroundColor: '#fef3c7', padding: '12px', borderRadius: '4px', textAlign: 'center' }}>
                  <div style={{ color: '#92400e', fontSize: '11px', fontWeight: 600 }}>MODIFIED</div>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: '#92400e' }}>{diffManifest.summary.modified_count}</div>
                </div>
                <div style={{ backgroundColor: '#fee2e2', padding: '12px', borderRadius: '4px', textAlign: 'center' }}>
                  <div style={{ color: '#991b1b', fontSize: '11px', fontWeight: 600 }}>DELETED</div>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: '#991b1b' }}>{diffManifest.summary.deleted_count}</div>
                </div>
                <div style={{ backgroundColor: '#f3f4f6', padding: '12px', borderRadius: '4px', textAlign: 'center' }}>
                  <div style={{ color: '#4b5563', fontSize: '11px', fontWeight: 600 }}>UNCHANGED</div>
                  <div style={{ fontSize: '20px', fontWeight: 600, color: '#4b5563' }}>{diffManifest.summary.unchanged_count}</div>
                </div>
              </div>

              {/* Clause Records */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {diffManifest.records.map((r, i) => {
                  const bg = r.change_type === 'added' ? '#f0fdf4' : r.change_type === 'modified' ? '#fffbeb' : r.change_type === 'deleted' ? '#fef2f2' : '#f9fafb'
                  const color = r.change_type === 'added' ? '#166534' : r.change_type === 'modified' ? '#92400e' : r.change_type === 'deleted' ? '#991b1b' : '#374151'
                  return (
                    <div key={i} style={{ border: '1px solid var(--line)', padding: '10px 14px', borderRadius: '4px', backgroundColor: bg }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, fontSize: '13px', color }}>
                          [{r.change_type.toUpperCase()}] Clause {r.clause_id}
                        </span>
                        {r.similarity_score !== undefined && (
                          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                            Similarity: {(r.similarity_score * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '12px', color: '#1f2937' }}>{r.new_text || r.old_text}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 4: Document Knowledge Graph                               */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'graph' && (
        <div style={{ backgroundColor: '#fff', border: '1px solid var(--line)', padding: '20px', borderRadius: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px' }}>
                Document Graph: <span style={{ color: 'var(--ink)' }}>{selectedDoc?.filename || selectedDocId}</span>
              </h3>
              <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '4px' }}>
                Isolated to {user.username} &middot; Active nodes: {graphData.nodes?.length || 0} &middot; Edges: {graphData.links?.length || 0}
              </div>
            </div>
            <button className="btn btn-secondary" onClick={handleLoadGraph} disabled={graphLoading}>
              {graphLoading ? 'Refreshing…' : 'Refresh Graph'}
            </button>
          </div>

          <div style={{ height: '520px', border: '1px solid var(--line)', borderRadius: '4px', backgroundColor: '#fafafa' }}>
            {graphData.nodes?.length > 0 ? (
              <ForceGraph2D
                graphData={graphData}
                nodeAutoColorBy="group"
                nodeLabel="label"
                linkDirectionalArrowLength={3.5}
                linkDirectionalArrowRelPos={1}
                linkColor="color"
                linkLabel="label"
              />
            ) : (
              <div className="empty-state" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p>No graph nodes found for this document snapshot yet.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
