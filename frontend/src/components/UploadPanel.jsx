import React, { useState } from 'react'
import Dropzone from './Dropzone.jsx'

export default function UploadPanel({ onSubmit, isProcessing }) {
  const [regulationFiles, setRegulationFiles] = useState([])
  const [policyFiles, setPolicyFiles] = useState([])

  const canSubmit = regulationFiles.length > 0 && policyFiles.length > 0 && !isProcessing

  return (
    <section>
      <span className="eyebrow">Step 01</span>
      <h1 className="page-title">Bring in the filings</h1>
      <p className="page-lede">
        Upload the regulatory circular you need to comply with, and the company
        policy wording it applies to. The system extracts clauses from both,
        embeds the policy corpus, and indexes it for retrieval.
      </p>

      <div className="upload-grid">
        <Dropzone
          title="Regulatory document"
          description="The circular, amendment, or master direction introducing the new rule."
          files={regulationFiles}
          onFilesChange={setRegulationFiles}
        />
        <Dropzone
          title="Company policy document(s)"
          description="Policy wording to check against the regulation. Multiple files are combined into one corpus."
          files={policyFiles}
          onFilesChange={setPolicyFiles}
        />
      </div>

      <button
        className="btn btn-primary"
        disabled={!canSubmit}
        onClick={() => onSubmit(regulationFiles, policyFiles)}
      >
        {isProcessing ? (<><span className="spinner" />Processing…</>) : 'Extract & index clauses'}
      </button>
    </section>
  )
}
