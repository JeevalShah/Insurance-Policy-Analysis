
# works on top of the 5 retrieved embedding
import ollama


def classify_relationship(trigger, clause):

    prompt = f"""
You are an insurance compliance expert.

Regulation:
{trigger}

Policy Clause:
{clause}

Classify the relationship.

Choose exactly one:

CONFLICT
COMPLIANT
SUPPORTING
REDUNDANT

Definitions:

CONFLICT:
Policy violates or contradicts regulation.

COMPLIANT:
Policy already satisfies regulation.

SUPPORTING:
Policy partially supports regulation.

REDUNDANT:
Policy and regulation say essentially the same thing.

Return ONLY the label.
"""

    response = ollama.chat(
        model="llama3",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"].strip()