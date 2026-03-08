from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from datetime import timedelta
from . import db
from .models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# =================================================
# REGISTER
# =================================================
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    if not data:
        return jsonify({"msg": "Missing JSON body"}), 400

    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role     = data.get("role", "citizen")

    if not name or not email or not password:
        return jsonify({"msg": "Name, email and password are required"}), 400

    if role not in ("citizen", "official"):
        return jsonify({"msg": "Invalid role"}), 400

    # Check duplicate
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 409

    user = User(name=name, email=email, role=role)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "Registration successful"}), 201


# =================================================
# LOGIN
# =================================================
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"msg": "Missing JSON body"}), 400

    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"msg": "Invalid credentials"}), 401

    claims = {"role": user.role}

    access_token = create_access_token(
        identity=user.id,
        additional_claims=claims,
        expires_delta=timedelta(days=1)
    )

    return jsonify(
        access_token=access_token,
        role=user.role,
        name=user.name
    ), 200


# =================================================
# CURRENT USER
# =================================================
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    claims  = get_jwt()

    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(
        id=user.id,
        email=user.email,
        role=claims["role"],
        name=user.name
    ), 200
