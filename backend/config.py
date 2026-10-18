import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SESSIONS_DIR = os.path.join(BASE_DIR, "data", "sessions")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Ollama model names (must be pulled locally: `ollama pull <name>`)
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3")

# --- Retrieval tuning ---
# SEARCH_TOP_K is the final number of candidates handed to the LLM classifier
# per regulatory trigger. SEARCH_CANDIDATE_K is the raw number of nearest
# neighbours pulled from FAISS *before* distance filtering (two-stage
# retrieval: cheap FAISS filter first, LLM only sees what survives).
SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", 4))
SEARCH_CANDIDATE_K = int(os.environ.get("SEARCH_CANDIDATE_K", 4))

# NOTE ON THIS THRESHOLD: embeddings are now L2-normalized before being added
# to / queried against the FAISS IndexFlatL2 index (see embeddings/embedder.py).
# For unit vectors, L2_distance^2 = 2 - 2*cos_similarity, so distance lives in
# [0, 4] instead of the previous unnormalized range (observed ~185-207).
# FAISS uses squared L2 distance on normalized vectors, so lower is stricter.
# Keep this at the requested value; the classifier only sees candidates at or
# below this distance.
SEARCH_DISTANCE_THRESHOLD = float(os.environ.get("SEARCH_DISTANCE_THRESHOLD", 0.6))

# Chat retrieval tuning (slightly looser than impact analysis so the chatbot
# doesn't go silent on borderline-relevant follow-up questions)
CHAT_TOP_K = int(os.environ.get("CHAT_TOP_K", 4))
CHAT_DISTANCE_THRESHOLD = float(os.environ.get("CHAT_DISTANCE_THRESHOLD", 1.3))

MAX_CHAT_HISTORY_TURNS = 8

# --- Qualitative match-quality bands, used ONLY for debug logging in
# secure_search (does not change what's returned or filtered). Same
# normalized-distance space as above.
STRONG_MATCH_DISTANCE = float(os.environ.get("STRONG_MATCH_DISTANCE", 0.6))   # cos_sim >= 0.7
WEAK_MATCH_DISTANCE = float(os.environ.get("WEAK_MATCH_DISTANCE", 1.2))       # cos_sim >= 0.4

# --- Embedding generation ---
EMBED_MAX_WORKERS = int(os.environ.get("EMBED_MAX_WORKERS", 4))

# --- LLM call concurrency across independent regulatory triggers ---
# Kept conservative by default: local Ollama inference does not necessarily
# get faster with more concurrent requests, and can start thrashing RAM/VRAM.
# Raise this only if you've verified it helps on your hardware.
LLM_MAX_CONCURRENCY = int(os.environ.get("LLM_MAX_CONCURRENCY", 2))

# --- Trigger summarization ---
MAX_QUERY_WORDS = int(os.environ.get("MAX_QUERY_WORDS", 350))
ENABLE_TRIGGER_SUMMARIZATION = os.environ.get("ENABLE_TRIGGER_SUMMARIZATION", "true").lower() != "false"

# --- Dependency graph ---
MAX_DEPENDENCY_HOPS = int(os.environ.get("MAX_DEPENDENCY_HOPS", 2))

# --- Reasoning generation ---
# When False, reasoning generation is skipped entirely (relationship labels
# are still produced) -- useful for a fast "classification only" pass.
ENABLE_REASONING = os.environ.get("ENABLE_REASONING", "true").lower() != "false"

# Experimental: combine classification + reasoning into a single LLM call per
# trigger instead of two. Off by default -- see the docstring on
# reasoning.impact_analysis.classify_and_reason_batch for why.
ENABLE_COMBINED_CLASSIFY_REASON = os.environ.get("ENABLE_COMBINED_CLASSIFY_REASON", "false").lower() == "true"

# --- Debug / test mode ---
# If set, only the first N regulatory clauses are processed by analyze_impact.
# Useful for smoke-testing the pipeline without a full 30-60 minute run.
# Unset (None) means "process everything".
_max_test_clauses = os.environ.get("MAX_REGULATORY_CLAUSES_FOR_TEST")
MAX_REGULATORY_CLAUSES_FOR_TEST = int(_max_test_clauses) if _max_test_clauses else None
