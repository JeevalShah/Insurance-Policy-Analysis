import os
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

db_client = FalkorDB(
    host=os.getenv('FALKORDB_HOST'),
    port=int(os.getenv('FALKORDB_PORT', 63718)),
    username=os.getenv('FALKORDB_USER'),
    password=os.getenv('FALKORDB_PASSWORD')
)

# Initialize the graph
policy_graph = db_client.select_graph("insurance_impact_graph")