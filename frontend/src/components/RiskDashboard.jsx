import React, { useEffect, useState } from 'react'
import { getDocumentRisk } from '../api.js'

const RISK_COLORS = {
  LOW: '#2ECC71',
  MEDIUM: '#F39C12',
  HIGH: '#E74C3C',
  CRITICAL: '#8B0000',
}

export default function RiskDashboard({ sessionId }) {
  const [risk, setRisk] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionId) return
    getDocumentRisk(sessionId)
      .then(setRisk)
      .catch((err) => console.error('Risk fetch failed', err))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="empty-state"><span className="spinner" />Computing risk score…</div>
  if (!risk) return null

  const barColor = RISK_COLORS[risk.risk_level] || '#BDC3C7'

  return (
    <section style={{ marginBottom: '32px' }}>
      <span className="eyebrow">Compliance Health</span>
      <h1 className="page-title">Risk Dashboard</h1>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '16px',
        marginTop: '20px',
      }}>
        {/* Health gauge */}
        <div style={{
          gridColumn: 'span 2',
          background: '#fafafa',
          border: '1px solid var(--line)',
          borderRadius: '6px',
          padding: '20px',
        }}>
          <div style={{ fontSize: '14px', color: '#666', marginBottom: '8px' }}>Policy Health Score</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '48px', fontWeight: '700', color: barColor }}>
              {risk.health_pct}%
            </span>
            <span style={{
              fontSize: '13px',
              fontWeight: '600',
              padding: '2px 10px',
              borderRadius: '3px',
              backgroundColor: barColor,
              color: '#fff',
            }}>
              {risk.risk_level}
            </span>
          </div>
          {/* Progress bar */}
          <div style={{
            marginTop: '12px',
            height: '8px',
            backgroundColor: '#e0e0e0',
            borderRadius: '4px',
            overflow: 'hidden',
          }}>
            <div style={{
              width: `${risk.health_pct}%`,
              height: '100%',
              backgroundColor: barColor,
              borderRadius: '4px',
              transition: 'width 0.6s ease',
            }} />
          </div>
        </div>

        {/* Stat cards */}
        <StatCard label="Conflicts" value={risk.conflict_count} color="#E74C3C" />
        <StatCard label="Compliant" value={risk.compliant_count} color="#2ECC71" />
        <StatCard label="Supporting" value={risk.supporting_count} color="#3498DB" />
        <StatCard label="Redundant" value={risk.redundant_count} color="#F39C12" />
        <StatCard label="Classified unrelated" value={risk.unrelated_count} color="#7F8C8D" />
        <StatCard label="Unmatched" value={risk.unmatched_count} color="#95A5A6" />
        <StatCard label="Total Policy" value={risk.total_policy_clauses} color="#2C3E50" />
      </div>

      {/* High risk clauses */}
      {risk.high_risk_clauses && risk.high_risk_clauses.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <div style={{ fontSize: '13px', fontWeight: '600', color: '#E74C3C', marginBottom: '8px' }}>
            ⚠ High-Risk Clauses ({risk.high_risk_clauses.length})
          </div>
          {risk.high_risk_clauses.map((c) => (
            <div key={c.clause_id} style={{
              padding: '8px 12px',
              margin: '4px 0',
              backgroundColor: '#FFF5F5',
              border: '1px solid #FED7D7',
              borderRadius: '4px',
              fontSize: '13px',
            }}>
              <strong>Clause {c.clause_id}</strong>
              {c.section && <span style={{ color: '#666' }}> — {c.section}</span>}
              <span style={{ marginLeft: '8px', color: '#E74C3C' }}>
                ({c.conflict_count} conflict{c.conflict_count > 1 ? 's' : ''})
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: '#fafafa',
      border: '1px solid var(--line)',
      borderRadius: '6px',
      padding: '16px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: '28px', fontWeight: '700', color }}>{value ?? '—'}</div>
      <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>{label}</div>
    </div>
  )
}
