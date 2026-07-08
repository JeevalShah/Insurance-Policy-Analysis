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
        const directEntries = Object.entries(entry.direct)
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
                <div className="reasoning">No policy clause matched closely enough to flag.</div>
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

            {entry.indirect.length > 0 && (
              <div className="indirect-footer">
                <strong>Indirectly affected:</strong>{' '}
                {entry.indirect.map((id) => (
                  <span className="indirect-tag" key={id}>Clause {id}</span>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
