import axios from 'axios'

const client = axios.create({ baseURL: '/api' })
const api = axios

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
