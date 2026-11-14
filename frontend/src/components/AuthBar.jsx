import React, { useState } from 'react'
import { login, signup, logout, extractErrorMessage } from '../api.js'

export default function AuthBar({ user, onAuthChange }) {
  const [showModal, setShowModal] = useState(false)
  const [mode, setMode] = useState('login') // 'login' or 'signup'
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      let data
      if (mode === 'signup') {
        data = await signup(username, email, password)
      } else {
        data = await login(username || email, password)
      }
      onAuthChange(data.user)
      setShowModal(false)
      setPassword('')
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleLogout() {
    await logout()
    onAuthChange(null)
  }

  return (
    <>
      <header className="auth-bar" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 24px',
        borderBottom: '1px solid var(--line)',
        backgroundColor: '#fff',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', fontSize: '13px', color: 'var(--ink)' }}>
            SENTRA ENGINE
          </span>
          <span style={{ color: 'var(--muted)', fontSize: '12px' }}>|</span>
          <span style={{ color: 'var(--muted)', fontSize: '12px' }}>Version-Aware Knowledge Graph</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                backgroundColor: 'var(--ink)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '13px',
                fontWeight: 600
              }}>
                {(user.username || user.email || 'U')[0].toUpperCase()}
              </div>
              <div style={{ textAlign: 'left', lineHeight: '1.2' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>{user.username}</div>
                <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{user.email}</div>
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: '6px 12px', fontSize: '12px', marginLeft: '8px' }}
                onClick={handleLogout}
              >
                Sign out
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '6px 14px', fontSize: '12px' }}
                onClick={() => { setMode('login'); setError(null); setShowModal(true) }}
              >
                Sign in
              </button>
              <button
                className="btn btn-primary"
                style={{ padding: '6px 14px', fontSize: '12px' }}
                onClick={() => { setMode('signup'); setError(null); setShowModal(true) }}
              >
                Create account
              </button>
            </div>
          )}
        </div>
      </header>

      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '6px',
            width: '100%',
            maxWidth: '420px',
            padding: '28px',
            boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--ink)' }}>
                {mode === 'signup' ? 'Create an Account' : 'Sign in to Sentra Engine'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--muted)' }}
              >
                &times;
              </button>
            </div>

            {error && (
              <div style={{
                backgroundColor: '#fef2f2',
                border: '1px solid #f87171',
                color: '#991b1b',
                padding: '10px 14px',
                borderRadius: '4px',
                fontSize: '13px',
                marginBottom: '16px'
              }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--ink)' }}>
                  {mode === 'signup' ? 'Username' : 'Username or Email'}
                </label>
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={mode === 'signup' ? 'johndoe' : 'johndoe or john@example.com'}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '4px',
                    border: '1px solid var(--line)',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                />
              </div>

              {mode === 'signup' && (
                <div style={{ marginBottom: '14px' }}>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--ink)' }}>
                    Email
                  </label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="john@example.com"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid var(--line)',
                      fontSize: '14px',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
              )}

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--ink)' }}>
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '4px',
                    border: '1px solid var(--line)',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn btn-primary"
                style={{ width: '100%', padding: '10px', fontSize: '14px' }}
              >
                {loading ? 'Please wait…' : mode === 'signup' ? 'Create Account' : 'Sign in'}
              </button>
            </form>

            <div style={{ marginTop: '16px', textAlign: 'center', fontSize: '13px', color: 'var(--muted)' }}>
              {mode === 'signup' ? (
                <>Already have an account? <a href="#signin" onClick={(e) => { e.preventDefault(); setMode('login'); setError(null) }} style={{ color: 'var(--ink)', fontWeight: 600 }}>Sign in</a></>
              ) : (
                <>Need an account? <a href="#signup" onClick={(e) => { e.preventDefault(); setMode('signup'); setError(null) }} style={{ color: 'var(--ink)', fontWeight: 600 }}>Create one</a></>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
