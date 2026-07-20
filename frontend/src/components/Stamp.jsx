import React from 'react'

const LABELS = {
  CONFLICT: 'Conflict',
  COMPLIANT: 'Compliant',
  SUPPORTING: 'Supporting',
  REDUNDANT: 'Redundant',
  UNKNOWN: 'Unclassified',
}

export default function Stamp({ relationship }) {
  const key = (relationship || 'UNKNOWN').toUpperCase()
  const className = LABELS[key] ? key.toLowerCase() : 'unknown'
  return <span className={`stamp ${className}`}>{LABELS[key] || 'Unclassified'}</span>
}
