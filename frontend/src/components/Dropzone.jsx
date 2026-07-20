import React, { useRef, useState } from 'react'

export default function Dropzone({ title, description, files, onFilesChange, accept = '.pdf,.docx' }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  function addFiles(newFiles) {
    const list = Array.from(newFiles)
    onFilesChange([...files, ...list])
  }

  function removeFile(index) {
    onFilesChange(files.filter((_, i) => i !== index))
  }

  return (
    <div
      className={`dropzone ${dragOver ? 'drag-over' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files)
      }}
      role="button"
      tabIndex={0}
    >
      <h3>{title}</h3>
      <p>{description}</p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={accept}
        onChange={(e) => {
          if (e.target.files?.length) addFiles(e.target.files)
          e.target.value = ''
        }}
      />

      {files.length > 0 ? (
        <ul className="file-list">
          {files.map((f, i) => (
            <li className="file-chip" key={`${f.name}-${i}`}>
              <span>{f.name}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                aria-label={`Remove ${f.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <span className="file-chip" style={{ opacity: 0.5, justifyContent: 'center' }}>
          Click or drop PDF / DOCX files
        </span>
      )}
    </div>
  )
}
