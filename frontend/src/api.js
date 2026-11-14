import axios from 'axios'

const client = axios.create({ baseURL: '/api', withCredentials: true })
const api = axios.create({ baseURL: '', withCredentials: true })

// Token management
let authToken = localStorage.getItem('sentra_auth_token') || null

export function setAuthToken(token) {
  authToken = token
  if (token) {
    localStorage.setItem('sentra_auth_token', token)
  } else {
    localStorage.removeItem('sentra_auth_token')
  }
}

export function getAuthToken() {
  return authToken
}

// Attach auth token to all outgoing requests if present
client.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
})

api.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
})

// -------------------------------------------------------------
// Authentication APIs
// -------------------------------------------------------------
export async function signup(username, email, password) {
  const { data } = await client.post('/auth/signup', { username, email, password })
  if (data.token) {
    setAuthToken(data.token)
  }
  return data
}

export async function login(usernameOrEmail, password) {
  const { data } = await client.post('/auth/login', { username_or_email: usernameOrEmail, password })
  if (data.token) {
    setAuthToken(data.token)
  }
  return data
}

export async function logout() {
  try {
    await client.post('/auth/logout')
  } finally {
    setAuthToken(null)
  }
}

export async function getCurrentUser() {
  if (!authToken) return null
  try {
    const { data } = await client.get('/auth/me')
    return data.user
  } catch (err) {
    setAuthToken(null)
    return null
  }
}

// -------------------------------------------------------------
// Versioning & Document Management APIs
// -------------------------------------------------------------
export async function getUserDocuments(docType = null) {
  const params = docType ? { doc_type: docType } : {}
  const { data } = await client.get('/version/documents', { params })
  return data.documents || []
}

export async function uploadVersionDocument(formData) {
  const { data } = await client.post('/version/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getDocumentVersions(docId) {
  const { data } = await client.get(`/version/versions/${encodeURIComponent(docId)}`)
  return data.versions || []
}

export async function getDocumentHistory(docId) {
  const { data } = await client.get(`/version/history/${encodeURIComponent(docId)}`)
  return data.history || []
}

export async function computeVersionDiff(docId, oldVersion, newVersion) {
  const { data } = await client.post('/version/diff', {
    doc_id: docId,
    old_version: oldVersion,
    new_version: newVersion,
  })
  return data
}

export async function executeVersionRollback(docId, targetVersion, dryRun = true) {
  const { data } = await client.post('/version/rollback', {
    doc_id: docId,
    target_version: targetVersion,
    dry_run: dryRun,
  })
  return data
}

export async function getVersionGraph(docId) {
  const { data } = await client.get(`/version/graph/${encodeURIComponent(docId)}`)
  return data
}

// -------------------------------------------------------------
// Existing Session / Analysis APIs (Backward Compatibility)
// -------------------------------------------------------------
export async function createSession() {
  const { data } = await client.post('/session')
  return data
}

export async function uploadDocuments(sessionId, regulationFiles, policyFiles) {
  const form = new FormData()
  form.append('session_id', sessionId)
  regulationFiles.forEach((f) => form.append('regulation', f))
  policyFiles.forEach((f) => form.append('policy', f))

  const { data } = await client.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function runAnalysis(sessionId) {
  const { data } = await client.post('/analyze', { session_id: sessionId })
  return data
}

export async function getSessionStatus(sessionId) {
  const { data } = await client.get(`/session/${sessionId}`)
  return data
}

export async function sendChatMessage(sessionId, message) {
  const { data } = await client.post('/chat', { session_id: sessionId, message })
  return data
}

export function extractErrorMessage(err) {
  return err?.response?.data?.error || err?.message || 'Something went wrong.'
}

export async function getDocumentRisk(sessionId) {
  const { data } = await api.get(`/api/risk/${sessionId}`)
  return data
}

export async function getClauseRisk(sessionId, clauseId) {
  const { data } = await api.get(`/api/risk/${sessionId}/${clauseId}`)
  return data
}

export async function getCrossfire(sessionId) {
  const { data } = await api.get(`/api/crossfire/${sessionId}`)
  return data
}

export async function getClauseNeighbourhood(sessionId, clauseId) {
  const { data } = await api.get(`/api/graph/${sessionId}/neighbourhood/${clauseId}`)
  return data
}
