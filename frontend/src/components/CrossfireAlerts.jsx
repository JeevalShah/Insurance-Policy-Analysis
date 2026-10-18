import React, { useEffect, useState } from 'react'
import { getCrossfire } from '../api.js'

export default function CrossfireAlerts({ sessionId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionId) return
    getCrossfire(sessionId)
      .then(setData)
      .catch((err) => console.error('Crossfire fetch failed', err))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return null
  if (!data || (!data.crossfire?.length && !data.co_impact_clusters?.length)) return null

  return (
    <section style={{ marginTop: '40px', borderTop: '2px solid var(--ink)', paddingTop: '24px' }}>
      <span className="eyebrow">Graph Intelligence</span>
      <h1 className="page-title">Regulatory Cross-Impact Analysis</h1>
      <p className="page-lede">
        Policy clauses caught between contradictory regulatory demands, and regulation pairs
        that jointly affect the same areas of the policy.
      </p>

      {/* Crossfire alerts */}
      {data.crossfire?.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: '600', marginBottom: '12px', color: '#E74C3C' }}>
            ⚖️ Regulatory Crossfire — {data.crossfire.length} clause{data.crossfire.length > 1 ? 's' : ''} caught
          </h3>
          {data.crossfire.map((cf, i) => (
            <div key={i} className="docket-entry" style={{ borderLeft: '3px solid #E74C3C' }}>
              <div style={{ padding: '16px' }}>
                <div style={{ fontWeight: '600', fontSize: '14px', marginBottom: '8px' }}>
                  Policy Clause {cf.caught_clause_id}
                  {cf.clause_section && <span style={{ color: '#666', fontWeight: '400' }}> — {cf.clause_section}</span>}
                </div>
                <div style={{ fontSize: '13px', color: '#555', marginBottom: '12px' }}>
                  {cf.clause_text?.slice(0, 200)}{cf.clause_text?.length > 200 ? '…' : ''}
                </div>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                  <div style={{
                    flex: 1,
                    minWidth: '200px',
                    padding: '10px',
                    backgroundColor: '#FFF5F5',
                    border: '1px solid #FED7D7',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}>
                    <div style={{ color: '#E74C3C', fontWeight: '600', marginBottom: '4px' }}>
                      ✕ CONFLICTS WITH — Reg {cf.conflict_reg_id}
                    </div>
                    {cf.conflict_reg_text?.slice(0, 150)}{cf.conflict_reg_text?.length > 150 ? '…' : ''}
                  </div>
                  <div style={{
                    flex: 1,
                    minWidth: '200px',
                    padding: '10px',
                    backgroundColor: '#F0FFF4',
                    border: '1px solid #C6F6D5',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}>
                    <div style={{ color: '#2ECC71', fontWeight: '600', marginBottom: '4px' }}>
                      ✓ COMPLIES WITH — Reg {cf.comply_reg_id}
                    </div>
                    {cf.comply_reg_text?.slice(0, 150)}{cf.comply_reg_text?.length > 150 ? '…' : ''}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Co-impact clusters */}
      {data.co_impact_clusters?.length > 0 && (
        <div style={{ marginTop: '28px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: '600', marginBottom: '12px' }}>
            🔗 Co-Impact Clusters — Regulation pairs sharing policy impact
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--ink)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 12px' }}>Regulation 1</th>
                  <th style={{ padding: '8px 12px' }}>Regulation 2</th>
                  <th style={{ padding: '8px 12px' }}>Shared Clauses</th>
                  <th style={{ padding: '8px 12px' }}>Clause IDs</th>
                </tr>
              </thead>
              <tbody>
                {data.co_impact_clusters.map((cl, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '8px 12px' }}>Reg {cl.reg1_id}</td>
                    <td style={{ padding: '8px 12px' }}>Reg {cl.reg2_id}</td>
                    <td style={{ padding: '8px 12px', fontWeight: '600' }}>{cl.shared_clauses}</td>
                    <td style={{ padding: '8px 12px' }}>
                      {(cl.shared_clause_ids || []).map((id) => (
                        <span key={id} className="indirect-tag" style={{ marginRight: '4px' }}>{id}</span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
