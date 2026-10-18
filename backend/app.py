import logging
import traceback
import os
import ollama
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

import config
from benchmark import run_benchmark
from services.session_store import store  # Updated to import global instance
from services.pipeline_service import UploadPipelineService
from services.chat_service import ChatService
from services.graph_ingestion import GraphIngestionPipeline
from reasoning.impact_analysis import ImpactAnalyzer
from reasoning.graph_store import driver
from reasoning.risk_scorer import compute_document_risk, compute_clause_risk
from reasoning.cross_impact import detect_regulatory_crossfire, detect_co_impact_clusters
from reasoning.dependency_graph import build_dependency_graph
from embeddings.embedder import PolicyEmbedder
from parsing import pdf_parsing, docx_parsing
from clause_extraction.clause_split import split_into_clauses

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("App")

app = Flask(__name__)
CORS(app)
MAX_CONTENT_LENGTH = 50 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# --- NEW: Simple LLM Client Wrapper to replace `None` ---
class LocalOllamaClient:
    def __init__(self, model_name):
        self.model_name = model_name

    def predict(self, prompt: str, format: str = None) -> str:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        if format:
            payload["format"] = format
            
        res = ollama.chat(**payload)
        return res.get("message", {}).get("content", "")

llm_client = LocalOllamaClient(config.CHAT_MODEL)

# Initialize core dependencies
embedder = PolicyEmbedder(model_name=config.EMBED_MODEL, max_workers=config.EMBED_MAX_WORKERS)
store.embedder = embedder # Attach embedder to the global store

graph_pipeline = GraphIngestionPipeline(
    embedder=embedder,
    classifier=llm_client, # Fixed: Replaced None with working LLM client
    index=None,
    top_k=config.SEARCH_TOP_K,
    model=config.CHAT_MODEL,
    distance_threshold=config.SEARCH_DISTANCE_THRESHOLD,
    max_embedding_workers=config.EMBED_MAX_WORKERS,
    max_llm_workers=config.LLM_MAX_CONCURRENCY 
)

pipeline_service = UploadPipelineService(session_store=store, graph_pipeline=graph_pipeline)

# Fixed: Pass the `store` instance directly, not `store.vector_store` (which is None at startup)
chat_service = ChatService(llm_client=llm_client, session_store=store, embedder=embedder)
impact_analyzer = ImpactAnalyzer()

def error_response(message: str, status: int = 400):
    return jsonify({"error": message}), status


def internal_error_response():
    return jsonify({"error": "Internal server error."}), 500

@app.errorhandler(413)
def too_large(e):
    return error_response("Uploaded file(s) too large (limit 50MB total).", 413)

def parse_files(files) -> list:
    parsed_docs = []
    for file in files:
        # Fixed: Path traversal vulnerability
        filename = secure_filename(file.filename.lower())
        if not filename:
            continue
            
        temp_path = os.path.join(config.UPLOAD_DIR, filename)
        file.save(temp_path)
        
        full_text = ""
        try:
            if filename.endswith('.pdf'):
                pages = pdf_parsing.extract_text(temp_path)
                full_text = "\n".join([p["text"] for p in pages])
            elif filename.endswith('.docx'):
                pages = docx_parsing.extract_text(temp_path)
                full_text = "\n".join([p["text"] for p in pages])
            
            clauses = split_into_clauses(full_text)
            for c in clauses:
                c["source_doc"] = filename
            parsed_docs.extend(clauses)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    return parsed_docs

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/api/session", methods=["POST"])
def create_session():
    session = store.create()
    return jsonify({"session_id": session.session_id, "status": session.status})

@app.route("/api/upload", methods=["POST"])
def upload_documents():
    session_id = request.form.get("session_id")
    if not session_id:
        return error_response("Missing 'session_id'.")
        
    try:
        session = store.require(session_id)
    except KeyError:
        return error_response("Unknown session_id. Create a session first.", 404)
        
    regulation_files = request.files.getlist("regulation")
    policy_files = request.files.getlist("policy")
    
    if not regulation_files or not policy_files:
        return error_response("Missing regulation or policy files.")
        
    try:
        reg_docs = parse_files(regulation_files)
        policy_docs = parse_files(policy_files)
        
        dependency_graph = build_dependency_graph(policy_docs)
        
        result = pipeline_service.process_upload(
            session_id=session_id, 
            reg_docs=reg_docs, 
            policy_docs=policy_docs, 
            dependency_graph=dependency_graph
        )
        
        if result.get("status") == "error":
            return internal_error_response()
            
        return jsonify({
            "session_id": session_id, 
            "status": "analyzed",
            "policy_clause_count": len(policy_docs),
            "regulation_clause_count": len(reg_docs),
            "metrics": result.get("ingestion_metrics", {})
        })
    except Exception as e:
        logger.error(traceback.format_exc())
        return internal_error_response()

@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    reg_clause_id = payload.get("regulatory_clause_id")
    
    if not session_id:
        return error_response("Missing 'session_id'.")
        
    try:
        # If specific clause requested, return just that one
        if reg_clause_id:
            result = impact_analyzer.analyze_regulatory_impact(session_id, reg_clause_id)
            if result.get("status") == "error":
                return internal_error_response()
            return jsonify(result)
            
        # BULK ANALYSIS: Fetch all impacts for the frontend
        with driver.session() as session:
            res = session.run(
                "MATCH (r:RegulatoryClause {session_id: $sid}) RETURN r.id as id, r.text as text", 
                {"sid": session_id}
            )
            triggers = [{"id": rec["id"], "text": rec["text"]} for rec in res]
            
        aggregated_results = []
        for t in triggers:
            impact = impact_analyzer.analyze_regulatory_impact(session_id, t["id"])
            
            # Reshape direct impacts into a dict keyed by policy_id for the frontend
            direct_dict = {}
            for d in impact.get("direct_impacts", []):
                direct_dict[d["policy_id"]] = {
                    "relationship": d["relationship"],
                    "text": d["text"],
                    "reasoning": d["reasoning"]
                }
                
            aggregated_results.append({
                "trigger_id": t["id"],
                "trigger_text": t["text"],
                "direct": direct_dict,
                "indirect": impact.get("indirect_impacts", [])
            })
            
        return jsonify({"result": aggregated_results})
        
    except Exception as e:
        logger.error(traceback.format_exc())
        return internal_error_response()

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    message = (payload.get("message") or "").strip()
    chat_history = payload.get("chat_history", [])
    
    if not session_id or not message:
        return error_response("Missing 'session_id' or 'message'.")
        
    try:
        result = chat_service.generate_response(session_id, message, chat_history)
        if result.get("status") == "error":
            return internal_error_response()
        return jsonify(result)
    except Exception as e:
        logger.error(traceback.format_exc())
        return internal_error_response()

@app.route("/api/graph/<session_id>", methods=["GET"])
def get_graph_data(session_id):
    if not driver:
        return error_response("Graph database is currently offline.", 503)
        
    try:
        with driver.session() as session:
            query = """
            MATCH (n) WHERE n.session_id = $sid
            OPTIONAL MATCH (n)-[r]->(m) WHERE m.session_id = $sid
            RETURN n, r, m
            """
            result = session.run(query, {"sid": session_id})
            
            nodes, edges = {}, []
            for record in result:
                n, r, m = record.get("n"), record.get("r"), record.get("m")
                
                if n and n["id"] not in nodes:
                    nodes[n["id"]] = {"id": n["id"], "label": n.get("section", n["id"]), "group": list(n.labels)[0]}
                if m and m["id"] not in nodes:
                    nodes[m["id"]] = {"id": m["id"], "label": m.get("section", m["id"]), "group": list(m.labels)[0]}
                    
                if r:
                    edges.append({
                        "source": n["id"],
                        "target": m["id"],
                        "label": r.type,
                        "color": "#C0392B" if r.type == "CONFLICTS_WITH" else "#2ECC71" if r.type == "COMPLIES_WITH" else "#BDC3C7"
                    })
            return jsonify({"nodes": list(nodes.values()), "links": edges})
    except Exception as e:
        logger.error(f"Graph fetch failed: {e}")
        return internal_error_response()

@app.route("/api/risk/<session_id>", methods=["GET"])
def get_document_risk(session_id):
    """Returns aggregate compliance risk score for the session."""
    try:
        result = compute_document_risk(session_id)
        if not result:
            return error_response("No graph data found for this session.", 404)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Risk computation failed: {e}")
        return internal_error_response()


@app.route("/api/risk/<session_id>/<clause_id>", methods=["GET"])
def get_clause_risk(session_id, clause_id):
    """Returns risk score for a specific policy clause."""
    try:
        result = compute_clause_risk(session_id, clause_id)
        if not result:
            return error_response("Clause not found.", 404)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Clause risk computation failed: {e}")
        return internal_error_response()


@app.route("/api/crossfire/<session_id>", methods=["GET"])
def get_crossfire(session_id):
    """Finds policy clauses caught between contradictory regulatory demands."""
    try:
        crossfire = detect_regulatory_crossfire(session_id)
        clusters = detect_co_impact_clusters(session_id)
        return jsonify({
            "crossfire": crossfire,
            "co_impact_clusters": clusters,
        })
    except Exception as e:
        logger.error(f"Cross-impact detection failed: {e}")
        return internal_error_response()


@app.route("/api/graph/<session_id>/neighbourhood/<clause_id>", methods=["GET"])
def get_clause_neighbourhood(session_id, clause_id):
    """Returns the 1-hop neighbourhood of a specific clause for progressive graph exploration."""
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (center {id: $cid, session_id: $sid})
                OPTIONAL MATCH (center)-[r]-(neighbour)
                WHERE neighbour.session_id = $sid
                RETURN center, r, neighbour, labels(center) AS center_labels, 
                       CASE WHEN neighbour IS NOT NULL THEN labels(neighbour) ELSE [] END AS neighbour_labels
                """,
                {"cid": clause_id, "sid": session_id}
            )
            
            nodes, edges = {}, []
            for record in result:
                center = record.get("center")
                r = record.get("r")
                neighbour = record.get("neighbour")
                center_labels = record.get("center_labels", [])
                neighbour_labels = record.get("neighbour_labels", [])
                
                if center and center["id"] not in nodes:
                    nodes[center["id"]] = {
                        "id": center["id"],
                        "label": center.get("section", center["id"]),
                        "group": center_labels[0] if center_labels else "Unknown",
                        "text": center.get("text", "")[:200],
                    }
                if neighbour and neighbour["id"] not in nodes:
                    nodes[neighbour["id"]] = {
                        "id": neighbour["id"],
                        "label": neighbour.get("section", neighbour["id"]),
                        "group": neighbour_labels[0] if neighbour_labels else "Unknown",
                        "text": neighbour.get("text", "")[:200],
                    }
                
                if r and center and neighbour:
                    edge_color = "#C0392B" if r.type == "CONFLICTS_WITH" else "#2ECC71" if r.type == "COMPLIES_WITH" else "#3498DB" if r.type == "SUPPORTS" else "#F39C12" if r.type == "DEPENDS_ON" else "#BDC3C7"
                    edges.append({
                        "source": center["id"],
                        "target": neighbour["id"],
                        "label": r.type,
                        "color": edge_color,
                    })
            
            return jsonify({"nodes": list(nodes.values()), "links": edges, "center": clause_id})
    except Exception as e:
        logger.error(f"Neighbourhood fetch failed: {e}")
        return internal_error_response()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)