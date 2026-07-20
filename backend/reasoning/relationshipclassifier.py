import logging
import ollama

logger = logging.getLogger("RelationshipClassifier")

VALID_LABELS = {"CONFLICT", "COMPLIANT", "SUPPORTING", "REDUNDANT"}


def classify_relationship(trigger: str, clause: str, model: str = "llama3") -> str:
    """
    Classifies how a policy clause relates to a regulatory trigger, using a
    zero-shot prompt against the local Llama 3 model via Ollama.

    Returns exactly one of: CONFLICT, COMPLIANT, SUPPORTING, REDUNDANT.
    Falls back to "UNKNOWN" if the model returns something unexpected,
    so the caller never crashes on a malformed LLM response.
    """
    prompt = f"""You are an insurance compliance expert.

Regulation:
{trigger}

Policy Clause:
{clause}

Classify the relationship. Choose exactly one:
CONFLICT
COMPLIANT
SUPPORTING
REDUNDANT

Definitions:
CONFLICT: Policy violates or contradicts regulation.
COMPLIANT: Policy already satisfies regulation.
SUPPORTING: Policy partially supports regulation.
REDUNDANT: Policy and regulation say essentially the same thing.

Return ONLY the label, nothing else."""

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        label = response["message"]["content"].strip().upper()

        # Guard against the model wrapping the label in extra text
        for candidate in VALID_LABELS:
            if candidate in label:
                return candidate

        logger.warning(f"Unrecognized relationship label from model: {label!r}")
        return "UNKNOWN"
    except Exception as e:
        logger.error(f"Relationship classification failed: {e}")
        return "UNKNOWN"
