"""
auth_routes.py

Flask Blueprint providing authentication endpoints:
- POST /api/auth/signup
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me
"""

from flask import Blueprint, request, jsonify, make_response, g
from .auth_service import auth_service, require_auth, get_token_from_request

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["POST"])
def signup():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    email = payload.get("email")
    password = payload.get("password")

    user, token, error = auth_service.signup(username, email, password)
    if error:
        return jsonify({"error": error}), 400

    resp = make_response(jsonify({
        "status": "success",
        "message": "User registered successfully.",
        "user": user,
        "token": token
    }), 201)

    # Set secure HttpOnly cookie
    resp.set_cookie(
        "sentra_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=86400 * 7,
        path="/"
    )
    return resp


@auth_bp.route("/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    ident = payload.get("username") or payload.get("email") or payload.get("username_or_email")
    password = payload.get("password")

    user, token, error = auth_service.login(ident, password)
    if error:
        return jsonify({"error": error}), 401

    resp = make_response(jsonify({
        "status": "success",
        "message": "Logged in successfully.",
        "user": user,
        "token": token
    }), 200)

    resp.set_cookie(
        "sentra_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=86400 * 7,
        path="/"
    )
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    token = get_token_from_request()
    if token:
        auth_service.revoke_token(token)

    resp = make_response(jsonify({
        "status": "success",
        "message": "Logged out successfully."
    }), 200)
    resp.set_cookie("sentra_token", "", expires=0, path="/")
    return resp


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user():
    return jsonify({
        "status": "success",
        "user": g.current_user
    })
