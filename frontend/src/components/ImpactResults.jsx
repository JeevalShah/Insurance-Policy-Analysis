import React from 'react'
import Stamp from './Stamp.jsx'

export default function ImpactResults({ result }) {
  if (!result || result.length === 0) {
    return (
      <div className="empty-state">
        <div className="mark">No impacts found</div>
        <p>No policy clauses matched any regulatory clause closely enough to flag.</p>
      </div>
    )
  }

  return (
    <section>
      <span className="eyebrow">Step 02</span>
      <h1 className="page-title">Impact analysis</h1>
      <p className="page-lede">
        Each regulatory clause below was matched against the policy corpus.
        Directly impacted clauses are classified and explained; indirectly
        impacted clauses were reached through cross-references in the policy text.
      </p>

      {result.map((entry, i) => {
        const directEntries = Object.entries(entry.direct || {})
        return (
          <div className="docket-entry" style={{ animationDelay: `${i * 40}ms` }} key={entry.trigger_id}>
            <div className="docket-header">
              <div>
                <span className="docket-number">Regulatory clause {entry.trigger_id}</span>
                <div className="docket-trigger">{entry.trigger_text}</div>
              </div>
            </div>

            {directEntries.length === 0 ? (
              <div className="clause-row">
                <div className="clause-id">—</div>
                <div className="reasoning">No related policy clause was identified. Retrieved unrelated candidates are shown in the graph.</div>
              </div>
            ) : (
              directEntries.map(([clauseId, data]) => (
                <div className="clause-row" key={clauseId}>
                  <div className="clause-id">Clause {clauseId}</div>
                  <div>
                    <Stamp relationship={data.relationship} />
                    <div className="clause-text">{data.text}</div>
                    <div className="reasoning">{data.reasoning}</div>
                  </div>
                </div>
              ))
            )}

            {(entry.indirect || []).length > 0 && (
              <div className="indirect-footer">
                <strong>Indirectly affected:</strong>
                {entry.indirect.map((item, idx) => {
                  // Support both old format (string ID) and new format (object with impact_chain)
                  if (typeof item === 'object' && item.impact_chain && item.impact_chain.length > 0) {
                    return (
                      <div key={item.clause_id || idx} style={{
                        margin: '6px 0',
                        padding: '6px 10px',
                        backgroundColor: '#F7FAFC',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        fontSize: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '4px',
                      }}>
                        {item.impact_chain.map((nodeId, ci) => (
                          <React.Fragment key={ci}>
                            <span style={{
                              padding: '2px 6px',
                              backgroundColor: ci === item.impact_chain.length - 1 ? '#FED7D7' : '#EBF8FF',
                              borderRadius: '3px',
                              fontWeight: ci === item.impact_chain.length - 1 ? '600' : '400',
                            }}>
                              {nodeId}
                            </span>
                            {ci < item.impact_chain.length - 1 && (
                              <span style={{ color: '#999', fontSize: '11px' }}>→</span>
                            )}
                          </React.Fragment>
                        ))}
                        <span style={{ color: '#666', marginLeft: '6px', fontSize: '11px' }}>
                          ({item.hop_count} hop{item.hop_count > 1 ? 's' : ''})
                        </span>
                      </div>
                    )
                  }
                  // Fallback: plain string ID
                  const id = typeof item === 'string' ? item : item.clause_id || item
                  return <span className="indirect-tag" key={id}>Clause {id}</span>
                })}
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
