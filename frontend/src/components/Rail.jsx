import React from 'react'

const STEPS = [
  { key: 'upload', label: 'Upload documents', sub: 'Regulation + policy files' },
  { key: 'analyze', label: 'Run impact analysis', sub: 'Direct + indirect impacts' },
  { key: 'chat', label: 'Query the file', sub: 'Ask follow-up questions' },
]

export default function Rail({ currentStep }) {
  const currentIndex = STEPS.findIndex((s) => s.key === currentStep)

  return (
    <aside className="rail">
      <div className="brand">
        <span className="brand-mark" />
        Regulatory<br />Impact Console
      </div>

      <div className="stepper">
        {STEPS.map((step, i) => {
          const stateClass = i < currentIndex ? 'complete' : i === currentIndex ? 'active' : ''
          return (
            <div className={`step ${stateClass}`} key={step.key}>
              <span className="step-index">{i < currentIndex ? '✓' : i + 1}</span>
              <div>
                <div className="step-label">{step.label}</div>
                <div className="step-sub">{step.sub}</div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="rail-footer">
        Local models via Ollama —<br />
        embeddings + llama3<br />
        run entirely on your machine.
      </div>
    </aside>
  )
}
