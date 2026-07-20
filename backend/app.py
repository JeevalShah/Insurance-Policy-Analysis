import logging
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS

import config
from services.session_store import store
from services import pipeline_service, chat_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("App")

app = Flask(__name__)
CORS(app)

MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def error_response(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.errorhandler(413)
def too_large(e):
    return error_response("Uploaded file(s) too large (limit 50MB total).", 413)


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

    if not regulation_files:
        return error_response("No regulatory document(s) provided under field 'regulation'.")
    if not policy_files:
        return error_response("No policy document(s) provided under field 'policy'.")

    try:
        pipeline_service.ingest_documents(session, regulation_files, policy_files)
    except ValueError as ve:
        return error_response(str(ve))
    except Exception as e:
        logger.error(traceback.format_exc())
        return error_response(f"Failed to process documents: {e}", 500)

    return jsonify({
        "session_id": session.session_id,
        "status": session.status,
        "policy_clause_count": len(session.policy_clauses),
        "regulation_clause_count": len(session.regulation_clauses),
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return error_response("Missing 'session_id'.")

    try:
        session = store.require(session_id)
    except KeyError:
        return error_response("Unknown session_id.", 404)

    if session.status not in ("ready", "analyzed"):
        return error_response(
            f"Session is not ready for analysis yet (status='{session.status}'). Upload documents first.",
            409,
        )

    try:
        result = pipeline_service.run_analysis(session)
    except Exception as e:
        logger.error(traceback.format_exc())
        return error_response(f"Impact analysis failed: {e}", 500)

    return jsonify({"session_id": session.session_id, "status": session.status, "result": result})


@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    message = (payload.get("message") or "").strip()

    if not session_id:
        return error_response("Missing 'session_id'.")
    if not message:
        return error_response("Missing 'message'.")

    try:
        session = store.require(session_id)
    except KeyError:
        return error_response("Unknown session_id.", 404)

    if session.index is None:
        return error_response("Upload and analyze documents before starting the chat.", 409)

    try:
        result = chat_service.chat(session, message)
    except ValueError as ve:
        return error_response(str(ve), 409)
    except RuntimeError as re_:
        return error_response(str(re_), 502)
    except Exception as e:
        logger.error(traceback.format_exc())
        return error_response(f"Chat failed: {e}", 500)

    return jsonify(result)


@app.route("/api/session/<session_id>", methods=["GET"])
def session_status(session_id):
    try:
        session = store.require(session_id)
    except KeyError:
        return error_response("Unknown session_id.", 404)

    return jsonify({
        "session_id": session.session_id,
        "status": session.status,
        "error": session.error,
        "policy_clause_count": len(session.policy_clauses),
        "regulation_clause_count": len(session.regulation_clauses),
        "has_analysis": session.analysis_result is not None,
        "chat_turns": len(session.chat_history) // 2,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
