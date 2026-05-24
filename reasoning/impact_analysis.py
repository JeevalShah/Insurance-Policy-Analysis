import sys
import os

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

def analyze_impact(query):

   

    retrieved = search(query)


   
    direct_impacts = set()


    for r in retrieved:

        clause_id = r["clause"]["clause_id"]

        direct_impacts.add(clause_id)


    

    indirect_impacts = set()


    for clause_id in direct_impacts:

        if clause_id in DEPENDENCIES:

            affected = DEPENDENCIES[clause_id]

            for dep in affected:

                if dep not in direct_impacts:

                    indirect_impacts.add(dep)


 

    return {

        "direct": list(direct_impacts),

        "indirect": list(indirect_impacts)
    }


if __name__ == "__main__":

    query = input(
        "\nEnter Regulatory Trigger:\n\n"
    )


    result = analyze_impact(query)


    print("\nDIRECTLY IMPACTED:\n")

    for d in result["direct"]:

        print(f"Clause {d}")


    print("\nINDIRECTLY IMPACTED:\n")

    for i in result["indirect"]:

        print(f"Clause {i}")