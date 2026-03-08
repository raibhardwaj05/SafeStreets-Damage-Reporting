from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity
)
from datetime import timedelta
from . import db
from .models import Device

auth_bp = Blueprint("device_auth", __name__, url_prefix="/api/device")


# =================================================
# REGISTER DEVICE
# =================================================
@auth_bp.route("/register", methods=["POST"])
def register_device():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"msg": "Missing JSON body"}), 400

    vehicle_no = data.get("vehicle_no", "").strip().upper()
    device_id = data.get("device_id", "").strip().upper()

    if not vehicle_no or not device_id:
        return jsonify({"msg": "Vehicle number and device id required"}), 400


    # Check duplicate device
    existing = Device.query.filter_by(device_id=device_id).first()

    if existing:
        return jsonify({"msg": "Device already registered"}), 409


    try:

        device = Device(
            vehicle_no=vehicle_no,
            device_id=device_id
        )

        db.session.add(device)
        db.session.commit()

        return jsonify({
            "msg": "Device registered successfully"
        }), 201

    except Exception as e:

        db.session.rollback()

        return jsonify({
            "msg": "Database error",
            "error": str(e)
        }), 500


# =================================================
# DEVICE LOGIN
# =================================================
@auth_bp.route("/login", methods=["POST"])
def device_login():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"msg": "Missing JSON body"}), 400

    device_code = data.get("device_code", "").strip().upper()

    if not device_code:
        return jsonify({"msg": "Device code required"}), 400


    device = Device.query.filter_by(device_id=device_code).first()

    if not device:
        return jsonify({"msg": "Invalid device code"}), 401


    access_token = create_access_token(
        identity=str(device.id),
        expires_delta=timedelta(days=7)
    )

    return jsonify({
        "token": access_token,
        "device_id": device.device_id,
        "vehicle_no": device.vehicle_no
    }), 200


# =================================================
# CURRENT DEVICE
# =================================================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def current_device():

    device_id = get_jwt_identity()

    device = Device.query.get(device_id)

    if not device:
        return jsonify({"msg": "Device not found"}), 404

    return jsonify({
        "id": device.id,
        "device_id": device.device_id,
        "vehicle_no": device.vehicle_no
    }), 200