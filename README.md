# Sentra Engine — Regulatory Impact & Version-Aware Knowledge Graph Management

Sentra Engine is an AI-assisted compliance analysis and knowledge graph maintenance platform designed for regulatory intelligence in the insurance and financial sectors.

The platform provides two integrated operational modules:
1. **Regulatory Impact & Crossfire Console**: Hierarchical clause extraction, semantic retrieval via FAISS, Llama-3 compliance classification, indirect cascading impact analysis, and grounded RAG conversational search.
2. **Dynamic, Multi-User, Version-Aware Graph Subsystem**: Production-grade multi-user authentication, document identity resolution, user/document isolation in Neo4j and storage, intelligent zero-diff graph reuse for unchanged uploads, targeted incremental graph updates for modified filings, and safe transactional rollback.

---

## Key Features

### 1. Multi-User Authentication & Data Isolation
- **Cryptographic Security**: Zero-dependency user management using standard library `sqlite3`, PBKDF2 with SHA-256 (100,000 iterations, unique salts), and environment-managed signing secrets (`SENTRA_SECRET_KEY`).
- **Token Management**: Stateless HMAC-SHA256 bearer tokens with expiration and server-side revocation, supporting both `Authorization: Bearer <token>` headers and secure `HttpOnly` cookies.
- **Strict Multi-Tenant Isolation**:
  - **Neo4j Graph Store**: Nodes and relationships tagged with `user_id` and `doc_id`; queries and index lookups strictly scoped to prevent cross-user leakage.
  - **Vector Store & Sessions**: Session registries and FAISS vector retrieval enforce user ownership filters.
  - **File Storage**: Version snapshots and update logs partitioned into user-specific directories (`data/versions/users/<user_id>/` and `data/version_history/users/<user_id>/`).
  - **Document Identicality**: Two users uploading identical filenames (e.g. `policy.docx`) operate in isolated namespaces with distinct document IDs and version histories.

### 2. Intelligent Graph Reuse & Version-Aware Processing
- **Scenario A (First-Time Upload)**:
  - Establishes document identity via explicit identifiers, header extraction, or alias registries.
  - Parses clauses, computes content fingerprints, registers `v1`, and ingests nodes and relationships into Neo4j.
- **Scenario B (Re-upload of Unchanged Document)**:
  - Matches content fingerprint against the active registered version.
  - Bypasses LLM classification, FAISS candidate generation, and Neo4j re-writes.
  - Reuses existing graph and embeddings, returning results in milliseconds with **100% embeddings saved and 0 redundant LLM calls**.
- **Scenario C (Re-upload of Modified Document)**:
  - Compares new content with the latest version using hybrid clause matching (`ChangeDetector`).
  - Generates a structured `ChangeManifest` classifying clauses into Added, Modified, Deleted, and Unchanged.
  - Increments version dynamically (`v2`, `v3`, ...).
  - Preserves historical snapshots in `HistoricalClause` nodes linked via `[:PREVIOUS_VERSION]`.
  - Soft-deactivates deleted clauses (`status = 'inactive'`) and deactivates stale relationships attached to affected clauses.
  - Runs targeted incremental updates: generates embeddings and assesses relationships **only for affected clauses**, retaining 100% of unchanged clause data.
- **Scenario D (Different Users Uploading Same Document)**:
  - Even if content or filenames match across users, each user operates in their own isolated document universe.

### 3. Safe Document Rollback
- Reverts a document's active state to any historical version without destroying session graphs or impacting other documents.
- Reactivates former clauses, restores modified text, soft-deactivates newer clauses, and updates document registry pointers.
- Preserves a complete, immutable audit trail in `VersionHistoryStore`.

### 4. Interactive Frontend UI
- **Auth Bar**: User registration, login modal, session status, and one-click logout.
- **Dynamic Version Console**:
  - **Document Registry**: Lists registered filings, types, active version tags, and timestamps.
  - **Upload & Update Workflow**: Dedicated UI for registering new documents vs. updating existing versions.
  - **Real-Time Processing Stepper**: Live feedback across identity resolution, fingerprint matching, change detection, and targeted graph ingestion.
  - **Version Diff Inspector**: Visual breakdown of Added, Modified (with text diff and similarity score), Deleted, and Unchanged clauses.
  - **Rollback Manager**: Dry-run simulation and one-click execution.
  - **Document Knowledge Graph**: 2D Force-Directed visualizer scoped to the authenticated user's selected document and version.
- **Analysis Console**: Seamless switcher to the regulatory impact, crossfire detection, and RAG chat console.

---

## Architecture

```text
[ Uploaded Filing (.pdf / .docx) ]
                │
                ▼
  [ Authenticated User Verification ]  (Bearer Token / HttpOnly Cookie)
                │
                ▼
  [ Document Identity Resolution ]   (User-scoped Document Registry)
                │
                ├──► Content Fingerprint Matches Active Version?
                │    │
                │    ├── YES [Scenario B: Zero-Diff Fast-Path]
                │    │   └── Reuse existing graph & embeddings (0 LLM calls, <0.01s)
                │    │
                │    └── NO [Scenario A: New Doc OR Scenario C: Modified Version]
                │        │
                │        ├── Parse Clauses & Detect Differences (ChangeDetector)
                │        │   └── Generates ChangeManifest (Added, Modified, Deleted, Unchanged)
                │        │
                │        ├── Incremental Graph Update (Neo4j)
                │        │   ├── Archive modified clauses to (h:HistoricalClause)
                │        │   ├── Link active nodes: (n)-[:PREVIOUS_VERSION]->(h)
                │        │   ├── Deactivate stale relationships for affected clauses
                │        │   ├── Soft-deactivate deleted clauses
                │        │   └── Create added & update modified clauses in-place
                │        │
                │        └── Targeted Reprocessing
                │            ├── Reuse embeddings for unchanged clauses
                │            ├── Generate embeddings ONLY for affected clauses
                │            └── Re-evaluate candidate pairs and dependency edges
                │
                ▼
  [ Scoped Graph Visualization & Audit Log Persistence ]
```

---

## Directory Structure

```text
Chanakya/
├── backend/
│   ├── app.py                             # Flask application entry point
│   ├── config.py                          # Server, model, and search tuning configurations
│   ├── clause_extraction/
│   │   └── clause_split.py                # Hierarchical clause segmenter
│   ├── parsing/
│   │   ├── pdf_parsing.py                 # PDF layout and text extractor
│   │   └── docx_parsing.py                # DOCX text extractor
│   ├── embeddings/
│   │   └── embedder.py                    # Parallel PolicyEmbedder
│   ├── reasoning/
│   │   ├── graph_store.py                 # Neo4j driver and schema indexes
│   │   ├── impact_analysis.py             # Direct & indirect impact orchestrator
│   │   ├── relationshipclassifier.py      # LLM compliance classifier
│   │   ├── cross_impact.py                # Regulatory crossfire detector
│   │   ├── risk_scorer.py                 # Clause and document risk scoring
│   │   └── dependency_graph.py            # Automatic cross-reference dependency parser
│   ├── services/
│   │   ├── auth_service.py                # PBKDF2 hashing, HMAC token generator & decorators
│   │   ├── auth_routes.py                 # REST endpoints: /api/auth/*
│   │   ├── user_document_registry.py      # SQLite document registry and ownership tracking
│   │   ├── version_pipeline_service.py    # Multi-user version upload and reuse orchestrator
│   │   ├── session_store.py               # In-memory session and FAISS retriever manager
│   │   ├── pipeline_service.py            # Full-ingestion pipeline service (legacy compatibility)
│   │   ├── graph_ingestion.py             # Neo4j batch ingestion pipeline
│   │   └── chat_service.py                # Conversational RAG service
│   ├── versioning/
│   │   ├── document_identity.py           # DocumentIdentity model & resolution logic
│   │   ├── version_manager.py             # Snapshot manager & clause fingerprinting
│   │   ├── change_detector.py             # Clause-level change detection coordinator
│   │   ├── change_manifest.py             # Structured ChangeManifest and change models
│   │   ├── clause_matcher.py              # Exact, fuzzy, split, and merge clause matcher
│   │   ├── incremental_graph_updater.py   # Transaction-safe Neo4j incremental mutations
│   │   ├── relationship_invalidator.py    # Stale relationship invalidation planner
│   │   ├── targeted_reprocessor.py        # Embeddings & relationship targeted reprocessor
│   │   ├── rollback_manager.py            # Safe version rollback manager
│   │   ├── version_history.py             # Immutable audit log store
│   │   ├── version_routes.py              # REST API: /api/version/*
│   │   └── tests/                         # 37 existing versioning unit tests
│   └── tests/
│       ├── test_auth_service.py           # Auth service unit tests
│       ├── test_document_registry.py      # Document registry & multi-user tests
│       ├── test_version_pipeline.py       # Scenarios A, B, C pipeline tests
│       └── test_e2e_multiuser_versioning.py # 10-case end-to-end architectural test suite
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── api.js                         # Axios client with auth interceptors & API routes
│       ├── App.jsx                        # Workspace switcher, layout, and state manager
│       ├── styles.css                     # Editorial typography & theme styling
│       └── components/
│           ├── AuthBar.jsx                # Authentication bar and Sign in / Sign up modal
│           ├── VersionConsole.jsx         # Document registry, diff, graph & rollback console
│           ├── UploadPanel.jsx            # Dual-document upload dropzone (analysis mode)
│           ├── RiskDashboard.jsx          # Aggregate compliance risk score cards
│           ├── ImpactResults.jsx          # Impact analysis results accordion
│           ├── CrossfireAlerts.jsx        # Contradictory regulatory demand alerts
│           ├── GraphVisualizer.jsx        # Force-directed dependency & compliance graph
│           └── ChatPanel.jsx              # Grounded conversational RAG interface
└── README.md
```

---

## API Reference

### 1. Authentication Endpoints (`/api/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/signup` | Registers a new user. Body: `{ username, email, password }` |
| `POST` | `/api/auth/login` | Authenticates credentials and returns a secure token + HttpOnly cookie |
| `POST` | `/api/auth/logout` | Revokes the active token and clears authentication cookie |
| `GET` | `/api/auth/me` | Returns profile for the currently authenticated user (`@require_auth`) |

### 2. Versioning & Document Management Endpoints (`/api/version`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/version/documents` | Lists all documents owned by the authenticated user (`@require_auth`) |
| `POST` | `/api/version/upload` | Uploads file for version-aware processing (supports new, unchanged, or update) |
| `GET` | `/api/version/versions/<doc_id>` | Returns all version snapshots registered for a document |
| `GET` | `/api/version/history/<doc_id>` | Returns the complete audit log of version updates for a document |
| `POST` | `/api/version/diff` | Computes the `ChangeManifest` between two versions |
| `POST` | `/api/version/rollback` | Executes dry-run or live rollback to a target version without session deletion |
| `GET` | `/api/version/graph/<doc_id>` | Returns nodes and edges scoped to the authenticated user's document |
| `GET` | `/api/version/demo` | Renders the isolated sample demo inspector (explicitly labeled demo fixture) |

### 3. Regulatory Impact Analysis Endpoints (`/api`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session` | Initializes an analysis session |
| `POST` | `/api/upload` | Full ingestion pipeline for regulatory and policy files |
| `POST` | `/api/analyze` | Computes direct and indirect regulatory impacts |
| `POST` | `/api/chat` | RAG-grounded conversational follow-up |
| `GET` | `/api/risk/<session_id>` | Aggregate document compliance risk score |
| `GET` | `/api/crossfire/<session_id>` | Policy clauses caught between conflicting regulatory rules |
| `GET` | `/api/graph/<session_id>` | Full compliance and dependency graph for an analysis session |

---

## Prerequisites

- **Python**: 3.10+
- **Node.js**: 18+
- **Neo4j Database**: Running on `bolt://127.0.0.1:7687` (configured in `.env`)
- **Ollama**: Running locally with required models:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3
  ```

---

## Configuration (`backend/.env`)

Create a `.env` file inside `backend/`:

```env
# Neo4j Database
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_secure_password

# Authentication & Signing
SENTRA_SECRET_KEY=your_production_secret_key_change_me
SENTRA_TOKEN_TTL=604800

# Retrieval & Search Tuning
SEARCH_TOP_K=4
SEARCH_DISTANCE_THRESHOLD=0.6
EMBED_MAX_WORKERS=4
LLM_MAX_CONCURRENCY=2
```

---

## Getting Started

### 1. Start Backend Server
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```
Backend runs on `http://localhost:5000`.

### 2. Start Frontend Application
```bash
cd frontend
npm install
npm run dev
```
Frontend runs on `http://localhost:5173`. Proxies `/api/*` requests to the Flask server.

---

## Testing & Verification

The test suite covers unit tests, multi-user isolation tests, and 10 core architectural scenarios:

```bash
# Set PYTHONPATH to backend
# On Windows (PowerShell):
$env:PYTHONPATH="backend"

# Run all 37 core versioning unit tests
python backend/versioning/tests/run_all_tests.py

# Run Auth, Document Registry, Version Pipeline, and E2E multi-user test suites
python -m unittest backend/tests/test_auth_service.py backend/tests/test_document_registry.py backend/tests/test_version_pipeline.py backend/tests/test_e2e_multiuser_versioning.py
```

### Verified Test Scenarios
1. **User A signs up and uploads Document A**: Registers `v1` and persists initial graph nodes (`A_FIRST_TIME_UPLOAD`).
2. **User A uploads Document B**: Document-level isolation ensures independent lifecycles for the same user.
3. **User A re-uploads unchanged Document A**: Content fingerprint match triggers Scenario B; reuses 100% of embeddings and graph nodes with zero redundant LLM calls in < 0.01s.
4. **User A uploads modified Document A**: Computes `ChangeManifest`; updates modified clauses in-place, creates added clauses, soft-deactivates deleted clauses, archives historical clauses, and re-evaluates relationships strictly for affected clauses.
5. **User A views and compares previous versions**: Computes diffs between snapshots with clause change records and similarity scores.
6. **User B signs up and uploads document with same filename**: Registered independently as User B's `v1`.
7. **User B cannot access User A's data**: Strict user isolation across Neo4j, storage, and registries.
8. **Updating or rolling back Document A does not affect Document B**: Independent document updates and rollbacks.
9. **Safe, recoverable updates**: Transaction rollback and dry-run execution preserve database integrity without data corruption.
10. **Backward compatibility**: The existing `/api/upload` endpoint, parsing routines, and analysis workflows remain fully functional.
