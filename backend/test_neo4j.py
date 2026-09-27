import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

# 1. Load environment variables
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def test_connection():
    # 2. Instantiate the Driver
    driver = GraphDatabase.driver(
        NEO4J_URI, 
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    
    try:
        # Verify connectivity before doing anything
        driver.verify_connectivity()
        print("Successfully connected to the Neo4j instance!")

        # 3. Open a Session to execute Cypher
        with driver.session() as session:
            
            # Write a test node
            write_query = """
            CREATE (t:ConnectionTest {message: 'Python to Neo4j works!'})
            RETURN t.message AS msg
            """
            result = session.run(write_query)
            record = result.single()
            print(f"Write successful. Node says: {record['msg']}")

            # Clean up the test node
            cleanup_query = "MATCH (t:ConnectionTest) DETACH DELETE t"
            session.run(cleanup_query)
            print("Cleanup successful. Test node deleted.")

    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        # 4. Close the Driver
        driver.close()

if __name__ == "__main__":
    test_connection()