# Insurance Policy Regulatory Impact Analysis System

## Overview

This project is an AI-assisted regulatory impact analysis pipeline designed for the insurance sector.

The system analyzes insurance compliance and policy documents, semantically retrieves affected clauses when a new regulation is introduced, classifies their compliance relationship, generates context-grounded reasoning, and identifies downstream indirect impacts using dependency-aware propagation.

---

# Core Features

- **Document Parsing**: Text extraction from DOCX/PDF insurance policies with layout reconstruction.
- **Hierarchical Clause Extraction**: Structured parsing of clauses (e.g., `2.1`) and sub-clauses (e.g., `2.1.1`) to preserve parent-child relationships.
- **Parallel Ingestion**: Multi-threaded concurrent embedding generation via a `ThreadPoolExecutor` and local Ollama.
- **FAISS Vector Indexing**: Flat L2 indexing for fast, semantic search.
- **Secure Retrieval**: Strict distance thresholding to filter out low-confidence vector matches.
- **Compliance Classification**: Zero-shot relationship classification (`CONFLICT`, `COMPLIANT`, `SUPPORTING`, `REDUNDANT`) using Llama 3.
- **Context-Grounded Reasoning**: LLM-generated compliance explanations explaining why the classified relationship exists (bounded to under 50 words).
- **Indirect Cascade Analysis**: Trace downstream operational impact using dependency graph propagation.

---

# Current Architecture

```text
Insurance Documents (PDF/DOCX)
        ↓
Document Parsing (reconstruct lines, strip headers/footers)
        ↓
Hierarchical Clause Extraction (preserves parent-child structure)
        ↓
Concurrent Embedding Generation (nomic-embed-text via thread pool)
        ↓
FAISS Vector Indexing & Map Generation
        ↓
Regulatory Trigger Input
        ↓
Secure Semantic Search (L2 distance thresholding)
        ↓
Relationship Classification (Llama 3 zero-shot categorization)
        ↓
Direct Impact Detection & Compliance Reasoning (under 50 words)
        ↓
Dependency Graph Traversal (cascading indirect impact detection)
```

---

# Tech Stack

| Component | Technology |
|---|---|
| Embeddings Model | Ollama (`nomic-embed-text`) |
| Generative LLM | Ollama (`llama3`) |
| Vector Database | FAISS (`faiss-cpu`) |
| Parsing | python-docx / pdfplumber |
| Language | Python |
| Retrieval | Secure Semantic Search with L2 Distance Guardrails |
| Reasoning | Compliance Relationship Classification + Dependency Propagation |

---

# Project Structure

```text
Insurance-Policy-Analysis/
│
├── data/
│   ├── raw/                  # Raw policy documents (PDF/DOCX)
│   ├── extracted_text/       # Extracted plain text (output.txt)
│   ├── structured_clauses.json
│   ├── clause_mapping.json
│   └── faiss_index.bin
│
├── parsing/
│   ├── document_parsing.py   # PDF text extraction and cleanup
│   └── docx_parsing.py       # DOCX text extraction
│
├── clause_extraction/
│   └── clause_split.py       # Hierarchical clause segmenter
│
├── embeddings/
│   └── embedder.py           # Parallel embedder & FAISS builder
│
├── retrieval/
│   └── semanticsearch.py     # Semantic search module
│
├── reasoning/
│   ├── dependency_graph.py   # Static mapping of operational dependencies
│   ├── relationshipclassifier.py # LLM relationship classifier (CONFLICT, etc.)
│   └── impact_analysis.py    # Direct & indirect impact orchestrator
│
├── requirements.txt
└── README.md
```

---

# Installation

## Step 1 — Clone Repository

```bash
git clone <your-repo-url>
cd Insurance-Policy-Analysis
```

---

## Step 2 — Create Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Installing Ollama

Download and install Ollama from:

https://ollama.com

---

# Pull Embedding & Chat Models

Run:

```bash
ollama pull nomic-embed-text
ollama pull llama3
```

Verify installation:

```bash
ollama list
```

You should see:

```text
nomic-embed-text
llama3
```

---

# Running the Pipeline

## Step 1 — Parse Documents

Place insurance documents inside `data/raw/` (e.g., `DOC_1.docx`).

To parse DOCX:
```bash
python parsing/docx_parsing.py
```
To parse PDF:
```bash
python parsing/pdf_parsing.py
```
This extracts text to `data/extracted_text/output.txt`.

---

## Step 2 — Split into Hierarchical Clauses

Run:
```bash
python clause_extraction/clause_split.py
```
This processes the text file, extracts clauses hierarchically, and generates `data/structured_clauses.json`.

---

## Step 3 — Generate Embeddings

Run:
```bash
python embeddings/embedder.py
```
This concurrently vectorizes the clauses, builds the FAISS index, and saves:
* `data/faiss_index.bin`
* `data/clause_mapping.json` (1-to-1 index-to-clause metadata mapping)

---

## Step 4 — Run Regulatory Impact Analysis

Run:
```bash
python reasoning/impact_analysis.py
```

Input a regulatory trigger query when prompted. For example:
```text
All claims exceeding INR 2,00,000 must undergo fraud risk evaluation.
```

---

# Example Output

```text
Enter Regulatory Trigger:
claims exceeding INR 2,00,000

DIRECTLY IMPACTED:

Clause 2.1

Text:
Clause 2.1
All claims exceeding INR 2,00,000 must undergo fraud risk evaluation.

Relationship:
REDUNDANT

Reasoning:
The clause already requires fraud risk evaluation for claims over INR 2,00,000, mirroring the regulation exactly.

============================================================

INDIRECTLY IMPACTED:

Clause 2.2
Clause 2.3
Clause 2.4
```

---

# Direct vs Indirect Impact Analysis

## Direct Impact
Clauses retrieved directly through semantic similarity. These are classified for compliance (e.g. `CONFLICT`, `REDUNDANT`) and explained by Llama 3.

## Indirect Impact
Clauses operationally affected through dependency propagation as modeled in `dependency_graph.py`.

Example:
```text
Claim Audit Trail Policy (2.4)
        ↓
affects
        ↓
Explainability Rule (4.4)
```

---

# Why Semantic Embeddings Instead of TF-IDF?

TF-IDF relies on keyword overlap and struggles with paraphrased legal language.

Embedding-based retrieval captures contextual semantic meaning, improving regulatory traceability and clause matching even when terminology differs.

---

# Future Scope

## Knowledge Graph Integration
Replace hardcoded dependency mappings with Neo4j or graph databases to dynamically traverse complex legal structures.

## Multi-Hop Dependency Traversal
Support deeper clause relationship propagation.

## Automated Compliance Reporting
Generate audit-ready compliance impact summaries.

## Real Regulatory Integration
Connect with IRDAI circulars and policy notifications.

---

# Current Limitations

- Dependency graph is manually modeled in a dictionary.
- No automatic legal graph generation from documents yet.
- Prototype-scale corpus.

---

# Research Direction

This project explores the intersection of:
- Legal-Tech / RegTech
- Regulatory AI
- Semantic Retrieval (RAG)
- Compliance Automation
- Graph-Based Reasoning
- Insurance Technology (InsurTech)

---

# License

MIT License