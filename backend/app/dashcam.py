from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.ml_utils import detect_damage_with_frame
from app import db
from app.models import DamageReport
from app.utils import log_audit

import base64
import cv2
import numpy as np
import os
import time


dashcam_bp = Blueprint(
    "dashcam",
    __name__,
    url_prefix="/api/dashcam"
)


@dashcam_bp.route("/detect-frame", methods=["POST"])
@jwt_required()
def detect_frame():
    """
    Realtime dashcam detection endpoint.
    Receives base64 frame → runs ML detection → returns result.
    No disk I/O for speed.
    """

    data = request.get_json()

    if not data or "frame" not in data:
        return jsonify({"msg": "No frame provided"}), 400

    try:
        frame_data = data["frame"]

        # Remove base64 header if present
        if "," in frame_data:
            frame_data = frame_data.split(",")[1]

        # Decode base64 → numpy image
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"msg": "Failed to decode frame"}), 400

        # Run detection
        damage, confidence, annotated_b64 = detect_damage_with_frame(frame)

        detected = damage not in (
            "No Damage",
            "Model Error",
            "Detection Error",
            "Image Not Found"
        )

        return jsonify({
            "damage_type": damage,
            "confidence": round(confidence, 3),
            "detected": detected,
            "annotated_image": annotated_b64 if detected else None
        }), 200

    except Exception as e:
        return jsonify({"msg": str(e)}), 500
    
# =====================================================
# 🚗 DASHCAM AUTO REPORT (aggregated realtime detection)
# =====================================================
@dashcam_bp.route('/submit-dashcam-session', methods=['POST'])
@jwt_required()
def submit_dashcam_session():

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    user_id = get_jwt_identity()

    first = data.get("first_damage")
    last = data.get("last_damage")
    if not last:
        last = first
    locations_raw = data.get("intermediate_locations", [])

    # Only keep locations where detection confidence >= 0.5
    locations = [
        loc for loc in locations_raw
        if float(loc.get("confidence", 0)) >= 0.4
    ]

    valid_detection_count = len(locations)

    if not first:
        return jsonify({"msg": "No first detection"}), 400
    
    # create folder
    image_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
    os.makedirs(image_dir, exist_ok=True)

    # -------------------------
    # Save FIRST image
    # -------------------------
    first_filename = None
    if first.get("image"):
        raw = first["image"].split(",")[1] if "," in first["image"] else first["image"]
        img_bytes = base64.b64decode(raw)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        first_filename = f"dashcam_first_{user_id}_{int(time.time())}.jpg"
        cv2.imwrite(os.path.join(image_dir, first_filename), img)

    # -------------------------
    # Save LAST image
    # -------------------------
    last_filename = None
    if last and last.get("image"):

        raw = last["image"].split(",")[1] if "," in last["image"] else last["image"]
        img_bytes = base64.b64decode(raw)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        last_filename = f"dashcam_last_{user_id}_{int(time.time())}.jpg"
        cv2.imwrite(os.path.join(image_dir, last_filename), img)

    # -------------------------
    # Severity
    # -------------------------
    confidence = max(
        float(first.get("confidence", 0)),
        float(last.get("confidence", 0)) if last else 0
    )

    if confidence >= 0.8:
        severity = "high"
    elif confidence >= 0.5:
        severity = "medium"
    else:
        severity = "low"

    # -------------------------
    # Store report
    # -------------------------
    report = DamageReport(
        citizen_id=user_id,
        image_path=first_filename,
        location=f"{first.get('text','Unknown location')} | detections:{valid_detection_count} | last_image:{last_filename}",
        latitude=first.get("lat"),
        longitude=first.get("lng"),
        detected_damage_type=first.get("damage_type"),
        confidence_score=round(confidence, 3),
        severity=severity,
        status="submitted"
    )

    db.session.add(report)
    db.session.commit()

    log_audit(user_id, f"DASHCAM_AUTO_REPORT {report.id}")

    return jsonify({
    "msg": "Dashcam report saved",
    "report_id": report.id,
    "valid_detections": valid_detection_count,
}), 201