""" graph_store.py """
import os
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load .env from backend directory explicitly so it works regardless of cwd
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)
load_dotenv()  # Fallback to cwd
logger = logging.getLogger(__name__)

NODE_REGULATORY = "RegulatoryClause"
NODE_POLICY     = "PolicyClause"
REL_CONFLICTS_WITH = "CONFLICTS_WITH"
REL_COMPLIES_WITH  = "COMPLIES_WITH"
REL_SUPPORTS       = "SUPPORTS"
REL_IS_REDUNDANT   = "IS_REDUNDANT"
REL_NOT_RELATED    = "NOT_RELATED"
EDGE_DEPENDS_ON = "DEPENDS_ON"

LABEL_TO_REL_TYPE = {
    # Short names
    "CONFLICT": REL_CONFLICTS_WITH,
    "COMPLIANT": REL_COMPLIES_WITH,
    "SUPPORTING": REL_SUPPORTS,
    "REDUNDANT": REL_IS_REDUNDANT,
    "NOT_RELATED": REL_NOT_RELATED,

    # Full relationship names (from prompt)
    "CONFLICTS_WITH": REL_CONFLICTS_WITH,
    "COMPLIES_WITH": REL_COMPLIES_WITH,
    "SUPPORTS": REL_SUPPORTS,
    "IS_REDUNDANT": REL_IS_REDUNDANT,
    "NONE": REL_NOT_RELATED,
    "NOT RELATED": REL_NOT_RELATED,
}
ALL_COMPLIANCE_RELS = [REL_CONFLICTS_WITH, REL_COMPLIES_WITH, REL_SUPPORTS, REL_IS_REDUNDANT]

def _get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        logger.warning("Missing Neo4j credentials. Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")
        return None
    return GraphDatabase.driver(uri, auth=(user, password))

driver = _get_driver()

if driver:
    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j successfully.")
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
        driver = None

def close_driver():
    if driver:
        driver.close()

def ensure_indexes() -> None:
    if not driver:
        logger.warning("Cannot ensure indexes: Neo4j driver is not initialized.")
        return
        
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