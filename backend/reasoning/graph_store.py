"""
graph_store.py

Central Neo4j connection and schema definitions.
Exports the `driver` singleton. Other modules should import `driver`
and use `with driver.session() as session:` for transactions.
"""

import os
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load .env from backend directory explicitly so it works regardless of cwd
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)
load_dotenv()  # Fallback to cwd
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants 
# ---------------------------------------------------------------------------

NODE_REGULATORY = "RegulatoryClause"
NODE_POLICY     = "PolicyClause"

# Specific relationship types replace the generic EDGE_COMPLIANCE
REL_CONFLICTS_WITH = "CONFLICTS_WITH"
REL_COMPLIES_WITH  = "COMPLIES_WITH"
REL_SUPPORTS       = "SUPPORTS"
REL_IS_REDUNDANT   = "IS_REDUNDANT"
REL_NOT_RELATED    = "NOT_RELATED"

EDGE_DEPENDS_ON = "DEPENDS_ON"

# Map the legacy classifier labels (from LLM) to our new specific Cypher relationship types
LABEL_TO_REL_TYPE = {
    "CONFLICT": REL_CONFLICTS_WITH,
    "COMPLIANT": REL_COMPLIES_WITH,
    "SUPPORTING": REL_SUPPORTS,
    "REDUNDANT": REL_IS_REDUNDANT,
    "NOT_RELATED": REL_NOT_RELATED
}

# Helper list for querying all compliance-related edges
ALL_COMPLIANCE_RELS = list(LABEL_TO_REL_TYPE.values())


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not password:
        raise EnvironmentError(
            "Missing Neo4j credentials. "
            "Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env"
        )

    # The driver maintains a thread-safe connection pool
    return GraphDatabase.driver(uri, auth=(user, password))

try:
    driver = _get_driver()
    driver.verify_connectivity()
    logger.info("Connected to Neo4j successfully.")
except Exception as e:
    logger.error(f"Neo4j connection failed: {e}")
    raise

def close_driver():
    """Optional cleanup hook for graceful shutdowns."""
    if driver:
        driver.close()

# ---------------------------------------------------------------------------
# Index bootstrap 
# ---------------------------------------------------------------------------

def ensure_indexes() -> None:
    """
    Creates composite indexes on (id, session_id) for O(log n) lookups.
    Safe to call multiple times (CREATE INDEX IF NOT EXISTS).
    """
    index_cmds = [
        "CREATE INDEX reg_id_session IF NOT EXISTS FOR (n:RegulatoryClause) ON (n.id, n.session_id)",
        "CREATE INDEX pol_id_session IF NOT EXISTS FOR (n:PolicyClause) ON (n.id, n.session_id)",
        "CREATE INDEX reg_source IF NOT EXISTS FOR (n:RegulatoryClause) ON (n.source_doc)",
        "CREATE INDEX pol_source IF NOT EXISTS FOR (n:PolicyClause) ON (n.source_doc)"
    ]
    
    with driver.session() as session:
        for cmd in index_cmds:
            try:
                session.run(cmd)
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
                
    logger.info("Neo4j indexes confirmed.")