# Regulatory Impact Console — Full-Stack App

Flask backend + React (Vite) frontend around the existing hierarchical
clause extraction / FAISS retrieval / Llama-3 impact-analysis pipeline.
Upload a regulatory document and one or more company policy documents,
get a direct + indirect impact analysis, then keep asking follow-up
questions in a RAG-grounded chat.

## What changed vs. the original CLI scripts

The original scripts (`clause_split.py`, `embedder.py`, `impact_analysis.py`,
`relationshipclassifier.py`) assumed a single global run against files on
disk (`data/structured_clauses.json`, `data/faiss_index.bin`, etc.), and a
hardcoded `DEPENDENCIES` dict for indirect impacts.

This version keeps the same extraction/embedding/classification logic but:

- **Sessions replace globals.** Each upload gets a `session_id`; its clauses,
  FAISS index, and chat history live in `services/session_store.py` instead
  of module-level file paths, so multiple document sets can be analyzed
  concurrently without clobbering each other.
- **The regulation is parsed into clauses too**, instead of typing one
  trigger string at a prompt. Every regulatory clause is run as its own
  trigger against the policy index, so a whole circular gets analyzed in
  one pass.
- **Dependency graph is auto-built** (`reasoning/dependency_graph.py`) from
  cross-references inside the policy text (e.g. "as per Clause 4.4")
  instead of a hand-maintained dict. You can still add manual overrides in
  `MANUAL_DEPENDENCIES` if the auto-detected graph misses something.
- **A `/api/chat` endpoint** adds the conversational layer: it re-embeds the
  user's question, retrieves relevant policy clauses, and asks llama3 for
  an answer grounded in those clauses plus the prior analysis summary.

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) running locally with both models pulled:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3
  ```

## Running the backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
```

Runs on `http://localhost:5000`. `MAX_CONTENT_LENGTH` is capped at 50MB;
adjust in `app.py` if your policy PDFs are larger.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on `http://localhost:5173` and proxies `/api/*` to the Flask backend
(see `vite.config.js`), so no CORS setup is needed in dev.

## API summary

| Method | Route            | Body                                   | Purpose                                   |
|--------|------------------|-----------------------------------------|--------------------------------------------|
| POST   | `/api/session`   | —                                       | Create a session, returns `session_id`     |
| POST   | `/api/upload`    | multipart: `session_id`, `regulation[]`, `policy[]` | Parse, extract clauses, embed, index |
| POST   | `/api/analyze`   | `{ session_id }`                       | Run direct + indirect impact analysis      |
| POST   | `/api/chat`      | `{ session_id, message }`               | RAG follow-up question                     |
| GET    | `/api/session/:id` | —                                     | Session status/diagnostics                 |

## Notes / limitations carried over from the prototype

- FAISS index is `IndexFlatL2` (exact search) — fine at prototype scale,
  won't scale to huge corpora without swapping to an approximate index.
- Sessions are in-memory (a Python dict). Restarting the Flask process
  clears all sessions; the FAISS index + clause mapping are also written
  to `backend/data/sessions/<id>/` for inspection, but aren't reloaded
  automatically on restart.
- Classification/reasoning calls llama3 once per (regulatory clause ×
  matched policy clause) pair, so a large regulation against a large
  policy corpus can take a while — there's no batching or streaming yet.
- No authentication — this is meant to run locally/on a trusted network.
