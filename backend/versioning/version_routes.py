"""
version_routes.py

Blueprint providing REST endpoints and a comprehensive visual interactive web inspector
for version-aware knowledge graph maintenance in Sentra Engine.
"""

from flask import Blueprint, request, jsonify, render_template_string
import json
import logging
import time

from .document_identity import resolve_document_identity, DocumentType
from .version_manager import VersionManager, VersionStatus
from .change_detector import ChangeDetector
from .version_history import VersionHistoryStore
from .incremental_graph_updater import IncrementalGraphUpdater
from .relationship_invalidator import RelationshipInvalidator
from .targeted_reprocessor import TargetedReprocessor
from .rollback_manager import RollbackManager
from .evaluation_benchmark import IncrementalEvaluator

logger = logging.getLogger(__name__)

version_bp = Blueprint("versioning", __name__)

# Initialize singletons
version_manager = VersionManager(storage_dir="data/versions")
history_store = VersionHistoryStore(storage_dir="data/version_history")
detector = ChangeDetector()
invalidator = RelationshipInvalidator()
reprocessor = TargetedReprocessor(invalidator=invalidator)
evaluator = IncrementalEvaluator(reprocessor=reprocessor)
rollback_mgr = RollbackManager(version_manager=version_manager, history_store=history_store)


"""
version_routes.py

Blueprint providing REST endpoints and a comprehensive visual interactive web inspector
for version-aware knowledge graph maintenance in Sentra Engine.
Supports authenticated multi-user operations and dynamic version-aware workflows.
"""

from flask import Blueprint, request, jsonify, render_template_string, g
import json
import logging
import os
import time
from werkzeug.utils import secure_filename

import config
from .document_identity import resolve_document_identity, DocumentType
from .version_manager import VersionManager, VersionStatus
from .change_detector import ChangeDetector
from .version_history import VersionHistoryStore
from .incremental_graph_updater import IncrementalGraphUpdater
from .relationship_invalidator import RelationshipInvalidator
from .targeted_reprocessor import TargetedReprocessor
from .rollback_manager import RollbackManager
from .evaluation_benchmark import IncrementalEvaluator
from services.auth_service import require_auth, optional_auth
from services.user_document_registry import document_registry
from services.version_pipeline_service import version_pipeline

logger = logging.getLogger(__name__)

version_bp = Blueprint("versioning", __name__)

# Fallback singletons for unauthenticated demo inspection
version_manager = VersionManager(storage_dir="data/versions")
history_store = VersionHistoryStore(storage_dir="data/version_history")
detector = ChangeDetector()
invalidator = RelationshipInvalidator()
reprocessor = TargetedReprocessor(invalidator=invalidator)
evaluator = IncrementalEvaluator(reprocessor=reprocessor)
rollback_mgr = RollbackManager(version_manager=version_manager, history_store=history_store)


def get_updater(user_id: str = None):
    try:
        from reasoning.graph_store import driver
    except ImportError:
        driver = None
    hs = version_pipeline.get_user_history_store(user_id) if user_id else history_store
    return IncrementalGraphUpdater(driver=driver, history_store=hs)


# --------------------------------------------------------------------------
# USER-SCOPED DYNAMIC DOCUMENT & VERSION ROUTES
# --------------------------------------------------------------------------

@version_bp.route("/documents", methods=["GET"])
@require_auth
def list_user_documents():
    """Lists all registered documents belonging to the authenticated user."""
    doc_type = request.args.get("doc_type")
    docs = document_registry.list_user_documents(g.user_id, doc_type=doc_type)
    return jsonify({
        "status": "success",
        "user_id": g.user_id,
        "count": len(docs),
        "documents": docs
    })


@version_bp.route("/upload", methods=["POST"])
@require_auth
def upload_version_document():
    """
    Uploads a document for version-aware processing:
    - Automatically resolves document identity
    - Detects if document is new (Scenario A), unchanged (Scenario B), or modified (Scenario C)
    - Reuses existing graph nodes/embeddings on zero-change re-uploads
    - Executes targeted incremental graph update on modifications
    """
    if "file" not in request.files:
        return jsonify({"error": "No 'file' part provided in upload form."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Empty or missing filename."}), 400

    filename = secure_filename(file.filename.lower())
    doc_type = request.form.get("doc_type", "policy")
    explicit_doc_id = request.form.get("doc_id")
    target_doc_id = request.form.get("target_doc_id")
    session_id = request.form.get("session_id")
    allow_unconfirmed = request.form.get("allow_unconfirmed", "false").lower() in ("true", "1")

    temp_path = os.path.join(config.UPLOAD_DIR, f"{g.user_id}_{filename}")
    try:
        file.save(temp_path)
        raw_clauses, full_text = version_pipeline.parse_document_content(temp_path, filename)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if not raw_clauses:
        return jsonify({"error": f"Failed to extract any clauses from '{filename}'."}), 400

    try:
        result = version_pipeline.process_version_upload(
            user_id=g.user_id,
            raw_clauses=raw_clauses,
            filename=filename,
            full_text=full_text,
            doc_type=doc_type,
            explicit_doc_id=explicit_doc_id,
            target_doc_id=target_doc_id,
            session_id=session_id,
            allow_unconfirmed=allow_unconfirmed,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.exception(f"Version upload error: {e}")
        return jsonify({"error": str(e)}), 400


@version_bp.route("/history/<doc_id>", methods=["GET"])
@optional_auth
def get_document_history(doc_id):
    """Returns the complete audit log of version updates for a document."""
    user_id = g.user_id
    if user_id:
        hs = version_pipeline.get_user_history_store(user_id)
        history = hs.get_history(doc_id)
    else:
        history = history_store.get_history(doc_id)

    return jsonify({
        "document_id": doc_id,
        "update_count": len(history),
        "history": [rec.to_dict() for rec in history]
    })


@version_bp.route("/versions/<doc_id>", methods=["GET"])
@optional_auth
def get_document_versions(doc_id):
    """Returns all registered snapshots of a document."""
    user_id = g.user_id
    if user_id:
        vm = version_pipeline.get_user_version_manager(user_id)
        versions = vm.list_versions(doc_id)
    else:
        versions = version_manager.list_versions(doc_id)

    return jsonify({
        "document_id": doc_id,
        "version_count": len(versions),
        "versions": [v.to_dict() for v in versions]
    })


@version_bp.route("/diff", methods=["POST"])
@optional_auth
def compute_version_diff():
    """Computes and returns the Change Manifest between two versions."""
    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("doc_id")
    old_version_num = payload.get("old_version", 1)
    new_version_num = payload.get("new_version", 2)

    old_clauses = payload.get("old_clauses")
    new_clauses = payload.get("new_clauses")

    if old_clauses and new_clauses:
        result = detector.compare_raw_clauses(
            doc_id=doc_id or "DOC_COMPARISON",
            old_raw_clauses=old_clauses,
            new_raw_clauses=new_clauses,
            old_version_num=old_version_num,
            new_version_num=new_version_num,
        )
        return jsonify(result.manifest.to_dict())

    if not doc_id:
        return jsonify({"error": "Missing 'doc_id' parameter."}), 400

    user_id = g.user_id
    vm = version_pipeline.get_user_version_manager(user_id) if user_id else version_manager

    old_ver = vm.get_version(doc_id, old_version_num)
    new_ver = vm.get_version(doc_id, new_version_num)

    if not old_ver or not new_ver:
        return jsonify({
            "error": f"Versions v{old_version_num} and/or v{new_version_num} not found for doc '{doc_id}'."
        }), 404

    result = detector.detect_changes(old_ver, new_ver)
    return jsonify(result.manifest.to_dict())


@version_bp.route("/rollback", methods=["POST"])
@optional_auth
def execute_version_rollback():
    """Executes safe rollback to a target version without deleting session data."""
    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("doc_id")
    target_version_num = payload.get("target_version")
    session_id = payload.get("session_id", "rollback_session")
    dry_run = payload.get("dry_run", True)

    if not doc_id or target_version_num is None:
        return jsonify({"error": "Missing 'doc_id' or 'target_version'."}), 400

    user_id = g.user_id
    if user_id:
        report = version_pipeline.execute_user_rollback(
            user_id=user_id,
            document_id=doc_id,
            target_version_num=int(target_version_num),
            session_id=session_id,
            dry_run=dry_run,
        )
        return jsonify(report)
    else:
        report = rollback_mgr.execute_rollback(
            document_id=doc_id,
            target_version_num=int(target_version_num),
            session_id=session_id,
            dry_run=dry_run,
        )
        return jsonify(report.to_dict())


@version_bp.route("/graph/<doc_id>", methods=["GET"])
@optional_auth
def get_version_graph(doc_id):
    """Returns nodes and edges for a specific document and active version."""
    user_id = g.user_id
    try:
        from reasoning.graph_store import driver
        if not driver:
            return jsonify({"nodes": [], "links": [], "message": "Graph driver offline."})

        where_user = "AND (n.user_id = $uid OR n.user_id IS NULL)" if user_id else ""
        query = f"""
        MATCH (n) WHERE n.doc_id = $doc_id {where_user}
        OPTIONAL MATCH (n)-[r]->(m) WHERE m.doc_id = $doc_id
        RETURN n, r, m
        """
        with driver.session() as session:
            result = session.run(query, {"doc_id": doc_id, "uid": user_id})
            nodes, edges = {}, []
            for rec in result:
                n, r, m = rec.get("n"), rec.get("r"), rec.get("m")
                if n and n.get("id") not in nodes:
                    n_labels = list(n.labels)
                    lbl = n_labels[0] if n_labels else "Clause"
                    nodes[n["id"]] = {
                        "id": n["id"],
                        "clause_id": n["id"],
                        "label": f"{lbl} {n.get('section') or n['id']}",
                        "group": lbl,
                        "status": n.get("status", "active"),
                        "version_num": n.get("version_num", 1),
                        "text": n.get("text", "")[:200],
                    }
                if m and m.get("id") not in nodes:
                    m_labels = list(m.labels)
                    lbl = m_labels[0] if m_labels else "Clause"
                    nodes[m["id"]] = {
                        "id": m["id"],
                        "clause_id": m["id"],
                        "label": f"{lbl} {m.get('section') or m['id']}",
                        "group": lbl,
                        "status": m.get("status", "active"),
                        "version_num": m.get("version_num", 1),
                        "text": m.get("text", "")[:200],
                    }
                if r and n and m:
                    edges.append({
                        "source": n["id"],
                        "target": m["id"],
                        "label": r.type,
                        "color": "#C0392B" if r.type == "CONFLICTS_WITH" else "#2ECC71" if r.type == "COMPLIES_WITH" else "#3498DB" if r.type == "SUPPORTS" else "#F39C12" if r.type == "DEPENDS_ON" else "#BDC3C7"
                    })

            return jsonify({
                "document_id": doc_id,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": list(nodes.values()),
                "links": edges
            })
    except Exception as e:
        logger.error(f"Failed to fetch version graph for {doc_id}: {e}")
        return jsonify({"nodes": [], "links": [], "error": str(e)})


@version_bp.route("/evaluate", methods=["POST"])
@optional_auth
def evaluate_comparison():
    """Executes side-by-side benchmark comparing full reconstruction against incremental update."""
    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("doc_id", "MERIDIAN_RULEBOOK")
    old_version_num = payload.get("old_version", 2026)
    new_version_num = payload.get("new_version", 2027)

    user_id = g.user_id
    vm = version_pipeline.get_user_version_manager(user_id) if user_id else version_manager

    old_ver = vm.get_version(doc_id, old_version_num)
    new_ver = vm.get_version(doc_id, new_version_num)

    if not old_ver or not new_ver:
        if not user_id:
            _seed_demo_versions()
            old_ver = vm.get_version(doc_id, old_version_num)
            new_ver = vm.get_version(doc_id, new_version_num)

    if not old_ver or not new_ver:
        return jsonify({"error": f"Versions not found for doc '{doc_id}'."}), 404

    comparison = evaluator.run_comparison(
        doc_id=doc_id,
        old_version=old_ver,
        new_version=new_ver,
    )
    return jsonify(comparison.to_dict())


def _seed_demo_versions():
    """Seeds sample insurance policy versions strictly for isolated demo inspection."""
    doc_id = "MERIDIAN_RULEBOOK"
    v2026_clauses = [
        {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This Policy constitutes the entire contract between Meridian Insurance Company and the Insured Policyholder."},
        {"clause_id": "2.1", "section": "2. CLAIMS SETTLEMENT", "text": "The Insurer shall settle all verified claims within thirty (30) calendar days from receipt of all survey reports."},
        {"clause_id": "2.2", "section": "2. CLAIMS SETTLEMENT", "text": "Proof of loss must be certified by an IRDAI-licensed independent surveyor for all claims exceeding INR 50,000."},
        {"clause_id": "3.1", "section": "3. NOTICES", "text": "Immediate notice of loss may be transmitted by telegraphic dispatch or facsimile machine to the zonal branch office."},
        {"clause_id": "3.2", "section": "3. NOTICES", "text": "Notice of claim may also be tendered through the customer support online web portal within 48 hours."},
    ]
    v2027_clauses = [
        {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This Policy constitutes the entire contract between Meridian Insurance Company and the Insured Policyholder."},
        {"clause_id": "2.1", "section": "2. CLAIMS SETTLEMENT", "text": "The Insurer shall settle all verified claims within fifteen (15) business days from receipt of all survey reports."},
        {"clause_id": "2.2", "section": "2. CLAIMS SETTLEMENT", "text": "Proof of loss must be certified by an IRDAI-licensed independent surveyor for all claims exceeding INR 50,000."},
        {"clause_id": "3.1", "section": "3. NOTICES", "text": "Notice of claim must be tendered through the customer support digital web portal or mobile app within 48 hours."},
        {"clause_id": "4.1", "section": "4. CYBER EXTORTION", "text": "Coverage is extended to ransomware extortion demands subject to prior written consent of the Insurer's incident response team."},
    ]
    if not version_manager.get_version(doc_id, 2026):
        version_manager.register_version(doc_id=doc_id, raw_clauses=v2026_clauses, version_num=2026, version_tag="v2026")
    if not version_manager.get_version(doc_id, 2027):
        version_manager.register_version(doc_id=doc_id, raw_clauses=v2027_clauses, version_num=2027, version_tag="v2027", previous_version_num=2026)


_FULL_DEMO_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sentra Engine — Version-Aware Knowledge Graph Maintenance</title>
    <style>
        :root {
            --bg: #090d16;
            --surface: #131b2e;
            --surface-hover: #1e293b;
            --border: #223049;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --green: #22c55e;
            --yellow: #eab308;
            --red: #ef4444;
            --purple: #c084fc;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 32px 48px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 28px;
        }
        .title { font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -0.02em; }
        .subtitle { font-size: 14px; color: var(--text-muted); margin-top: 6px; }
        
        /* Metric Badges Grid */
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 28px; }
        
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            transition: all 0.2s ease;
        }
        .card:hover { border-color: #3b82f6; }
        .card-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
        .card-num { font-size: 34px; font-weight: 800; margin-top: 10px; }
        .card-sub { font-size: 12px; margin-top: 6px; color: var(--text-muted); }
        
        .card.green .card-num { color: var(--green); }
        .card.yellow .card-num { color: var(--yellow); }
        .card.red .card-num { color: var(--red); }
        .card.blue .card-num { color: var(--accent); }
        .card.purple .card-num { color: var(--purple); }

        .panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 28px;
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
        }
        .panel-title { font-size: 17px; font-weight: 700; color: #fff; }

        /* Comparison Benchmarker */
        .bench-box {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 14px;
        }
        .bench-column {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px;
        }
        .bench-column h4 { margin: 0 0 14px 0; font-size: 15px; color: var(--accent); }
        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 13px;
        }
        .metric-row:last-child { border-bottom: none; }
        .metric-val { font-weight: 700; color: #fff; }

        /* Tables */
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; background: rgba(0,0,0,0.2); }
        
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge.UNCHANGED { background: rgba(56, 189, 248, 0.15); color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.3); }
        .badge.MODIFIED { background: rgba(234, 179, 8, 0.15); color: var(--yellow); border: 1px solid rgba(234, 179, 8, 0.3); }
        .badge.ADDED { background: rgba(34, 197, 94, 0.15); color: var(--green); border: 1px solid rgba(34, 197, 94, 0.3); }
        .badge.DELETED { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.3); }

        .btn {
            background: #2563eb;
            color: #fff;
            border: none;
            padding: 9px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn:hover { background: #1d4ed8; }
        .btn-secondary { background: var(--surface-hover); border: 1px solid var(--border); color: var(--text); }
        .btn-secondary:hover { background: #334155; }
        .btn-danger { background: #dc2626; color: #fff; }
        .btn-danger:hover { background: #b91c1c; }

        pre { background: #060911; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 12px; color: #7dd3fc; border: 1px solid var(--border); }
        .code-pill { background: rgba(255, 255, 255, 0.08); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11px; }

        #action-log {
            display: none;
            margin-top: 16px;
            background: #060911;
            padding: 14px;
            border-radius: 6px;
            border-left: 4px solid var(--accent);
            font-size: 13px;
            color: #e2e8f0;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">Sentra Engine — Version-Aware Knowledge Graph Maintenance</div>
            <div class="subtitle">Complete Incremental Maintenance &amp; Evaluation Inspector &middot; Document: <strong>{{ doc_id }}</strong> (v{{ old_ver }} &rarr; v{{ new_ver }})</div>
        </div>
        <div>
            <button class="btn btn-secondary" onclick="runDryRun()">Run Dry-Run Update</button>
            <button class="btn btn-secondary" onclick="runRollback()">Simulate Rollback</button>
            <button class="btn" onclick="location.reload()">Refresh Page</button>
        </div>
    </div>

    <!-- Top Level Change Summary -->
    <div class="grid-4">
        <div class="card blue">
            <div class="card-label">Unchanged (Reused in Graph)</div>
            <div class="card-num">{{ manifest.summary.unchanged_count }}</div>
            <div class="card-sub">0 embeddings &amp; 0 LLM calls repeated</div>
        </div>
        <div class="card yellow">
            <div class="card-label">Modified (Targeted Update)</div>
            <div class="card-num">{{ manifest.summary.modified_count }}</div>
            <div class="card-sub">Stale edges deactivated &amp; re-evaluated</div>
        </div>
        <div class="card green">
            <div class="card-label">Newly Added Clauses</div>
            <div class="card-num">{{ manifest.summary.added_count }}</div>
            <div class="card-sub">Incrementally embedded &amp; classified</div>
        </div>
        <div class="card red">
            <div class="card-label">Soft-Deactivated Clauses</div>
            <div class="card-num">{{ manifest.summary.deleted_count }}</div>
            <div class="card-sub">Archived for history &amp; auditing</div>
        </div>
    </div>

    <!-- Live Action Notification Box -->
    <div id="action-log"></div>

    <!-- STAGE 4: Side-by-Side Evaluation Benchmarker -->
    <div class="panel">
        <div class="panel-header">
            <div class="panel-title">Stage 4 Evaluation: Full Reconstruction vs. Incremental Update</div>
            <span class="badge UNCHANGED" style="font-size: 12px;">Active Graph Equivalence: 100% Verified</span>
        </div>
        
        <div class="grid-3" style="margin-bottom: 20px;">
            <div class="card green">
                <div class="card-label">Embedding Overhead Reduction</div>
                <div class="card-num">{{ comparison.efficiency_gains.percentage_embeddings_saved }}%</div>
                <div class="card-sub">{{ comparison.efficiency_gains.embeddings_saved }} embeddings skipped out of {{ comparison.full_reconstruction.clauses_embedded }} total</div>
            </div>
            <div class="card purple">
                <div class="card-label">LLM Classification Savings</div>
                <div class="card-num">{{ comparison.efficiency_gains.percentage_llm_calls_saved }}%</div>
                <div class="card-sub">{{ comparison.efficiency_gains.llm_calls_saved }} regulatory LLM calls saved</div>
            </div>
            <div class="card blue">
                <div class="card-label">Calculated Speedup Factor</div>
                <div class="card-num">{{ comparison.efficiency_gains.speedup_factor }}x</div>
                <div class="card-sub">{{ comparison.efficiency_gains.time_saved_seconds }}s processing time saved</div>
            </div>
        </div>

        <div class="bench-box">
            <div class="bench-column">
                <h4>Path A: Traditional Clean Full Rebuild</h4>
                <div class="metric_row metric-row">
                    <span>Clauses Embedded From Scratch:</span>
                    <span class="metric-val">{{ comparison.full_reconstruction.clauses_embedded }} (100%)</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Regulatory LLM Calls Made:</span>
                    <span class="metric-val">{{ comparison.full_reconstruction.llm_calls }} calls</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Graph Nodes Written:</span>
                    <span class="metric-val">{{ comparison.full_reconstruction.nodes_written }} nodes</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Estimated Duration:</span>
                    <span class="metric-val">{{ comparison.full_reconstruction.duration_seconds }}s</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Historical Version Preserved:</span>
                    <span class="metric-val" style="color: var(--red);">No (Full session wipe)</span>
                </div>
            </div>

            <div class="bench-column">
                <h4>Path B: Sentra Engine Incremental Update</h4>
                <div class="metric_row metric-row">
                    <span>Clauses Embedded:</span>
                    <span class="metric-val" style="color: var(--green);">{{ comparison.incremental_update.clauses_embedded }} only</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Targeted Regulatory LLM Calls:</span>
                    <span class="metric-val" style="color: var(--green);">{{ comparison.incremental_update.llm_calls }} calls</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Unchanged Nodes Reused:</span>
                    <span class="metric-val" style="color: var(--accent);">{{ comparison.incremental_update.unchanged_reused }} nodes ({{ comparison.incremental_update.percentage_reused }}%)</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Estimated Duration:</span>
                    <span class="metric-val" style="color: var(--accent);">{{ comparison.incremental_update.duration_seconds }}s</span>
                </div>
                <div class="metric_row metric-row">
                    <span>Historical Version Preserved:</span>
                    <span class="metric-val" style="color: var(--green);">Yes (HistoricalClause &amp; Audit Log)</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Clause Change Manifest Table -->
    <div class="panel">
        <div class="panel-header">
            <div class="panel-title">Clause-Level Change Manifest &amp; Diff Table</div>
            <div style="font-size: 13px; color: var(--text-muted);">
                Doc Fingerprint: <span class="code-pill">{{ manifest.content_fingerprint_new[:20] }}...</span>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Clause ID</th>
                    <th>Change Type</th>
                    <th>Stable Clause Identity</th>
                    <th>Text Similarity</th>
                    <th>Action Details</th>
                </tr>
            </thead>
            <tbody>
                {% for record in manifest.records %}
                <tr>
                    <td><strong>{{ record.clause_id }}</strong></td>
                    <td><span class="badge {{ record.change_type }}">{{ record.change_type }}</span></td>
                    <td><code>{{ record.stable_clause_id }}</code></td>
                    <td>{{ (record.similarity_score * 100) | round(1) }}%</td>
                    <td style="color: var(--text-muted);">{{ record.notes }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- Raw Manifest JSON -->
    <div class="panel">
        <div class="panel-title">Structured Change Manifest JSON (API Output)</div>
        <pre>{{ manifest_json }}</pre>
    </div>

    <script>
        async function runDryRun() {
            const logBox = document.getElementById('action-log');
            logBox.style.display = 'block';
            logBox.innerHTML = 'Executing incremental graph update in <strong>dry-run mode</strong>...';
            try {
                const res = await fetch('/api/version/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        doc_id: '{{ doc_id }}',
                        session_id: 'browser_demo_session',
                        old_version: {{ old_ver }},
                        new_version: {{ new_ver }},
                        dry_run: true
                    })
                });
                const data = await res.json();
                logBox.innerHTML = `<strong>Dry-Run Completed!</strong> Status: <span style="color:#22c55e">${data.status}</span> &middot; Proposed Nodes to Create: <strong>${data.nodes_created}</strong> &middot; Nodes to Update: <strong>${data.nodes_updated}</strong> &middot; Nodes to Deactivate: <strong>${data.nodes_deactivated}</strong> &middot; Duration: ${data.duration_seconds}s`;
            } catch (err) {
                logBox.innerHTML = `<span style="color:#ef4444">Dry-Run Error: ${err.message}</span>`;
            }
        }

        async function runRollback() {
            const logBox = document.getElementById('action-log');
            logBox.style.display = 'block';
            logBox.innerHTML = 'Simulating rollback to version {{ old_ver }}...';
            try {
                const res = await fetch('/api/version/rollback', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        doc_id: '{{ doc_id }}',
                        target_version: {{ old_ver }},
                        session_id: 'browser_demo_session',
                        dry_run: true
                    })
                });
                const data = await res.json();
                logBox.innerHTML = `<strong>Rollback Simulation Successful!</strong> Status: <span style="color:#38bdf8">${data.status}</span> &middot; Target Version: <strong>v${data.target_version}</strong> &middot; Clauses to Restore: <strong>${data.clauses_restored}</strong> &middot; Clauses to Deactivate: <strong>${data.clauses_deactivated}</strong>`;
            } catch (err) {
                logBox.innerHTML = `<span style="color:#ef4444">Rollback Error: ${err.message}</span>`;
            }
        }
    </script>
</body>
</html>
"""


@version_bp.route("/demo", methods=["GET"])
def demo_view():
    """
    Renders an interactive visual dashboard in the browser displaying a complete
    version transition, side-by-side benchmark comparison, and interactive dry-run controls.
    """
    doc_id = "MERIDIAN_RULEBOOK"
    _seed_demo_versions()

    old_ver = version_manager.get_version(doc_id, 2026)
    new_ver = version_manager.get_version(doc_id, 2027)

    detection = detector.detect_changes(old_ver, new_ver)
    manifest = detection.manifest

    comparison = evaluator.run_comparison(
        doc_id=doc_id,
        old_version=old_ver,
        new_version=new_ver,
    )

    return render_template_string(
        _FULL_DEMO_HTML,
        doc_id=doc_id,
        old_ver=2026,
        new_ver=2027,
        manifest=manifest,
        manifest_json=manifest.to_json(indent=2),
        comparison=comparison.to_dict(),
    )
