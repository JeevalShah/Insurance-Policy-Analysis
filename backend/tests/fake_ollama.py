"""
Drop-in fake for the `ollama` package used in unit tests, so we can exercise
classify_relationship_batch / generate_reasoning_batch / analyze_impact
logic without a real Ollama server.

Configure behavior via module-level state before each test.
"""
import numpy as np

CHAT_RESPONSES = []   # list of strings, popped in call order (or a callable)
CHAT_CALL_LOG = []
EMBED_CALL_LOG = []
EMBED_DIM = 8


def _fake_vector(seed_text: str):
    rng = np.random.default_rng(abs(hash(seed_text)) % (2**32))
    return (rng.random(EMBED_DIM) * 10).tolist()  # deliberately NOT unit norm


def embeddings(model, prompt):
    EMBED_CALL_LOG.append(prompt)
    return {"embedding": _fake_vector(prompt)}


def chat(model, messages):
    CHAT_CALL_LOG.append(messages[-1]["content"])
    if callable(CHAT_RESPONSES):
        content = CHAT_RESPONSES(messages)
    elif CHAT_RESPONSES:
        content = CHAT_RESPONSES.pop(0)
    else:
        content = "COMPLIANT"
    return {"message": {"content": content}}


def reset():
    global CHAT_RESPONSES
    CHAT_RESPONSES = []
    CHAT_CALL_LOG.clear()
    EMBED_CALL_LOG.clear()