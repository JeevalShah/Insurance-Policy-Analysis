import logging
import json
import config
from reasoning.graph_store import driver, ALL_COMPLIANCE_RELS, LABEL_TO_REL_TYPE
from embeddings.embedder import PolicyEmbedder
from services.graph_ingestion import GraphIngestionPipeline, IngestionReport
from app import llm_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestIngest")

sid = '419b9255-1d4b-4d4d-b685-ce1d1c21390b'

with driver.session() as session:
    regs = session.run("MATCH (r:RegulatoryClause {session_id: $s}) RETURN r.id as clause_id, r.text as text, r.section as section", s=sid).data()
    policies = session.run("MATCH (p:PolicyClause {session_id: $s}) RETURN p.id as clause_id, p.text as text, p.section as section", s=sid).data()

print(f"Loaded {len(regs)} regulatory clauses, {len(policies)} policy clauses")

embedder = PolicyEmbedder(model_name=config.EMBED_MODEL)
pipeline = GraphIngestionPipeline(
    embedder=embedder,
    classifier=llm_client,
    index=None,
    top_k=config.SEARCH_TOP_K,
    model=config.CHAT_MODEL,
    distance_threshold=config.SEARCH_DISTANCE_THRESHOLD
)

print(f"Pipeline config: distance_threshold={pipeline.distance_threshold}, top_k={pipeline.top_k}")

report = IngestionReport(session_id=sid, source_docs=["test"])
pipeline._classify_and_write_compliance_edges(regs, policies, sid, report)

print(f"Ingestion finished!")
print(f"Candidate pairs found: {report.candidate_pairs_found}")
print(f"Compliance edges written: {report.compliance_edges_written}")
print(f"LLM calls made: {report.llm_calls_made}")
print(f"Errors: {report.errors}")

with driver.session() as session:
    edges = session.run("MATCH (n {session_id: $s})-[r]->(m {session_id: $s}) RETURN type(r) as rel, count(r) as count", s=sid).data()
    print("Edges in Neo4j after test:", edges)
