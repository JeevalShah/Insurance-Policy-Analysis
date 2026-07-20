import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SESSIONS_DIR = os.path.join(BASE_DIR, "data", "sessions")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Ollama model names (must be pulled locally: `ollama pull <name>`)
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3")

# Retrieval tuning
SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", 5))
SEARCH_DISTANCE_THRESHOLD = float(os.environ.get("SEARCH_DISTANCE_THRESHOLD", 1.0))

# Chat retrieval tuning (slightly looser than impact analysis so the chatbot
# doesn't go silent on borderline-relevant follow-up questions)
CHAT_TOP_K = int(os.environ.get("CHAT_TOP_K", 4))
CHAT_DISTANCE_THRESHOLD = float(os.environ.get("CHAT_DISTANCE_THRESHOLD", 1.3))

MAX_CHAT_HISTORY_TURNS = 8
