import axios from 'axios'

const client = axios.create({ baseURL: '/api' })

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

export async function sendChatMessage(sessionId, message) {
  const { data } = await client.post('/chat', { session_id: sessionId, message })
  return data
}

export function extractErrorMessage(err) {
  return err?.response?.data?.error || err?.message || 'Something went wrong.'
}
