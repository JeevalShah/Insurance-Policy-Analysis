import sys
import os
import ollama
from relationshipclassifier import classify_relationship

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
)

from retrieval.semanticsearch import search

from reasoning.dependency_graph import DEPENDENCIES
def generate_reasoning(trigger, clause_text,relationship):

    prompt = f"""
You are an insurance compliance analyst.

Regulatory Trigger:
{trigger}

Retrieved Clause:
{clause_text}
Relationship Classification:
{relationship}

Explain in 1-2 concise sentences why this relationship exists.

Do not speculate.
Base your answer only on the trigger and clause.
Maximum 50 words.
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

def analyze_impact(query):

    retrieved = search(query)

    direct_impacts = {}

    for r in retrieved:
        clause_id = r["clause"]["clause_id"]

        direct_impacts[clause_id] = {
            "text": r["clause"]["text"]
        }

    indirect_impacts = set()

    for clause_id in direct_impacts.keys():

        if clause_id in DEPENDENCIES:

            affected = DEPENDENCIES[clause_id]

            for dep in affected:
                if dep not in direct_impacts.keys():
                    indirect_impacts.add(dep)

    for clause_id in direct_impacts:

        clause_text = direct_impacts[clause_id]["text"]
        relationship = classify_relationship(
    query,
    clause_text
)

        reasoning = generate_reasoning(
            query,
            clause_text,
            relationship
        )
  

        direct_impacts[clause_id]["relationship"] = relationship
        direct_impacts[clause_id]["reasoning"] = reasoning

    return {
        "direct": direct_impacts,
        "indirect": indirect_impacts
    }

if __name__ == "__main__":

    query = input(
        "\nEnter Regulatory Trigger:\n\n"
    )


    result = analyze_impact(query)


    print("\nDIRECTLY IMPACTED:\n")

    for clause_id, data in result["direct"].items():

     print(f"Clause {clause_id}")

     print(f"\nText:")
     print(data["text"])

     print(f"\nRelationship:")
     print(data["relationship"])

     print(f"\nReasoning:")
     print(data["reasoning"])

    print("\n" + "="*60 + "\n")


    print("\nINDIRECTLY IMPACTED:\n")

    for i in result["indirect"]:

        print(f"Clause {i}")