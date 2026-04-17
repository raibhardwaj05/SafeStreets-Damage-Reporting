from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, decode_token
from app.ml_utils import detect_damage_with_frame, calculate_severity
from app.risk_predictor import get_hidden_pothole_prob
from app import db
from app.models import DamageReport, Device
from app.utils import log_audit
from app import sock

import base64
import cv2
import numpy as np
import os
import time
import json


dashcam_bp = Blueprint(
    "dashcam",
    __name__,
    url_prefix="/api/dashcam"
)



@sock.route("/ws-detect")
def ws_detect(ws):
    """
    WebSocket route for real-time dashcam processing at 640x640 with zero HTTP overhead.
    """
    # 1) Wait for auth
    auth_data = ws.receive()
    if not auth_data:
        ws.close(message="No auth provided")
        return
        
    try:
        msg = json.loads(auth_data)
        if msg.get("type") != "auth" or "token" not in msg:
            raise ValueError("Invalid auth payload")
        
        token = msg["token"]
        decoded = decode_token(token)
        user_id = decoded["sub"]
        
    except Exception as e:
        ws.close(message=f"Auth error: {e}")
        return

    device = Device.query.get(user_id)
    user_email = device.email if device else None

    # Track GPS session state for this socket connection
    session_gps = {
        "location": "",
        "latitude": None,
        "longitude": None,
        "track_ids": set()
    }

    # 2) Loop receiving frames
    while True:
        try:
            data = ws.receive()
            if data is None:
                break
            
            # Text data = GPS update
            if isinstance(data, str):
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "gps":
                        session_gps["location"] = payload.get("location", "")
                        session_gps["latitude"] = payload.get("lat")
                        session_gps["longitude"] = payload.get("lng")
                except:
                    pass
                continue
                
            # Binary data = Image frame
            # Decode binary jpeg -> numpy image
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                continue

            # Run detection
            damage, confidence, area, count, annotated_b64, track_ids = detect_damage_with_frame(frame)

            detected = damage not in (
                "No Damage",
                "Model Error",
                "Detection Error",
                "Image Not Found"
            )
            
            # Evaluate tracking duplicate prevention
            is_new_object = False
            if track_ids:
                for tid in track_ids:
                    if tid not in session_gps["track_ids"]:
                        session_gps["track_ids"].add(tid)
                        is_new_object = True
            else:
                is_new_object = True # Fallback if tracker offline


            # Build WS response
            hidden_prob = None
            if "Waterlogging" in damage and session_gps.get("latitude") and session_gps.get("longitude"):
                prob = get_hidden_pothole_prob(session_gps["latitude"], session_gps["longitude"])
                if prob > 0:
                    hidden_prob = prob

            resp = {
                "damage_type": damage,
                "confidence": round(confidence, 3),
                "detected": detected,
                "annotated_image": annotated_b64 if detected else None,
                "report_id": None,
                "hidden_pothole_prob": hidden_prob
            }

            # Optional Auto-save logic (if confidence is very high, can trigger save)
            # We enforce a threshold here so the user isn't spammed with identical records, 
            # Or the user can manually trigger saves from the UI via save_detection later.
            # We'll save automatically if we hit 60+% threshold like the original logic intended.
            if detected and confidence > 0.6 and is_new_object:
                severity = calculate_severity(confidence, area, count)
                
                # Save the annotated frame image once for both reports
                image_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
                os.makedirs(image_dir, exist_ok=True)
                img_filename = f"dashcam_ws_{user_id}_{int(time.time() * 1000)}.jpg"
                
                if annotated_b64:
                    try:
                        raw = annotated_b64.split(',')[1] if ',' in annotated_b64 else annotated_b64
                        img_bytes = base64.b64decode(raw)
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is not None:
                            cv2.imwrite(os.path.join(image_dir, img_filename), img)
                        else:
                            img_filename = "DASHCAM_NO_IMAGE"
                    except Exception as e:
                        current_app.logger.warning(f"Could not save WS detection image: {e}")
                        img_filename = "DASHCAM_NO_IMAGE"
                else:
                    img_filename = "DASHCAM_NO_IMAGE"
                
                # Split damages into individual reports for the official dashboard database
                individual_damages = [d.strip() for d in damage.split(",")]
                first_report_id = None
                
                for single_damage_type in individual_damages:
                    # Compute and attach waterlogging risk for waterlogging reports
                    wlog_risk = None
                    if single_damage_type.lower() == "waterlogging" and session_gps.get("latitude") and session_gps.get("longitude"):
                        wlog_risk = get_hidden_pothole_prob(session_gps["latitude"], session_gps["longitude"])
                        if wlog_risk == 0.0:
                            wlog_risk = None  # Don't store 0 — no cluster nearby

                    report = DamageReport(
                        citizen_id=user_id,
                        user_email=user_email,
                        image_path=img_filename,
                        location=session_gps.get("location", ""),
                        latitude=session_gps.get("latitude"),
                        longitude=session_gps.get("longitude"),
                        detected_damage_type=single_damage_type,
                        confidence_score=round(confidence, 3),
                        severity=severity,
                        status="submitted",
                        report_source="dashcam",
                        waterlogging_pothole_risk=wlog_risk
                    )
                    db.session.add(report)
                    db.session.flush() # Secure ID before commit
                    
                    if not first_report_id:
                        first_report_id = report.id
                        
                    log_audit(user_id, f"DASHCAM_WS_DETECTION_REPORT_{single_damage_type.upper()} {report.id}")
                
                db.session.commit()
                resp["report_id"] = first_report_id

            ws.send(json.dumps(resp))
            
        except Exception as e:
            current_app.logger.error(f"WS loop error: {e}")
            break

# Keeping old detect_frame around for backward compatibility
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
        damage, confidence, area, count, annotated_b64, track_ids = detect_damage_with_frame(frame)

        detected = damage not in (
            "No Damage",
            "Model Error",
            "Detection Error",
            "Image Not Found"
        )
        
        hidden_prob = None
        if "Waterlogging" in damage and data.get("latitude") and data.get("longitude"):
            prob = get_hidden_pothole_prob(float(data.get("latitude")), float(data.get("longitude")))
            if prob > 0:
                hidden_prob = prob

        report_id = None
        if detected and data.get("auto_save"):
            user_id = get_jwt_identity()
            device = Device.query.get(user_id)
            user_email = device.email if device else None

            # Save the annotated frame image
            image_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
            os.makedirs(image_dir, exist_ok=True)
            img_filename = f"dashcam_det_{user_id}_{int(time.time() * 1000)}.jpg"

            if annotated_b64:
                try:
                    raw = annotated_b64.split(',')[1] if ',' in annotated_b64 else annotated_b64
                    img_bytes = base64.b64decode(raw)
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        cv2.imwrite(os.path.join(image_dir, img_filename), img)
                    else:
                        img_filename = "DASHCAM_NO_IMAGE"
                except Exception as e:
                    current_app.logger.warning(f"Could not save detection image: {e}")
                    img_filename = "DASHCAM_NO_IMAGE"
            else:
                img_filename = "DASHCAM_NO_IMAGE"

            # Severity is based on Box Area Size, Confidence score, and quantity of damages simultaneously
            severity = calculate_severity(confidence, area, count)

            report = DamageReport(
                citizen_id=user_id,
                user_email=user_email,
                image_path=img_filename,
                location=data.get('location', ''),
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                detected_damage_type=damage,
                confidence_score=round(confidence, 3),
                severity=severity,
                status="submitted",
                report_source="dashcam"
            )
            db.session.add(report)
            db.session.commit()
            log_audit(user_id, f"DASHCAM_DETECTION_REPORT {report.id}")
            report_id = report.id

        return jsonify({
            "damage_type": damage,
            "confidence": round(confidence, 3),
            "detected": detected,
            "annotated_image": annotated_b64 if detected else None,
            "report_id": report_id,
            "hidden_pothole_prob": hidden_prob
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
        if float(loc.get("confidence", 0)) >= 0.3
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
    # Severity based on detections
    # -------------------------
    confidence = max(
        float(first.get("confidence", 0)),
        float(last.get("confidence", 0)) if last else 0
    )

    if valid_detection_count >= 10:
        severity = "critical"
    elif valid_detection_count >= 5:
        severity = "high"
    elif valid_detection_count >= 2:
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
        status="submitted",
        report_source="dashcam"
    )

    db.session.add(report)
    db.session.commit()

    log_audit(user_id, f"DASHCAM_AUTO_REPORT {report.id}")

    return jsonify({
    "msg": "Dashcam report saved",
    "report_id": report.id,
    "valid_detections": valid_detection_count,
}), 201


# =====================================================
# 📸 SAVE INDIVIDUAL DETECTION AS REPORT
# =====================================================
@dashcam_bp.route('/save-detection', methods=['POST'])
@jwt_required()
def save_detection():
    """
    Saves a single detected frame as its own individual DamageReport.
    Receives: damage_type, confidence, annotated_image (base64),
              location, latitude, longitude
    """
    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    user_id = get_jwt_identity()

    # Look up device to get email
    device = Device.query.get(user_id)
    user_email = device.email if device else None

    damage_type = data.get('damage_type')
    confidence = float(data.get('confidence', 0.0))
    annotated_image = data.get('annotated_image', '')
    location_text = data.get('location', '')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not damage_type or damage_type in ("No Damage", "Model Error", "Detection Error"):
        return jsonify({"msg": "No damage to save"}), 400

    # Save the annotated frame image
    image_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
    os.makedirs(image_dir, exist_ok=True)

    img_filename = f"dashcam_det_{user_id}_{int(time.time() * 1000)}.jpg"

    if annotated_image:
        try:
            raw = annotated_image.split(',')[1] if ',' in annotated_image else annotated_image
            img_bytes = base64.b64decode(raw)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                cv2.imwrite(os.path.join(image_dir, img_filename), img)
            else:
                img_filename = "DASHCAM_NO_IMAGE"
        except Exception as e:
            current_app.logger.warning(f"Could not save detection image: {e}")
            img_filename = "DASHCAM_NO_IMAGE"
    else:
        img_filename = "DASHCAM_NO_IMAGE"

    # Severity
    if confidence >= 0.8:
        severity = "critical"
    elif confidence >= 0.5:
        severity = "high"
    elif confidence >= 0.3:
        severity = "medium"
    else:
        severity = "low"

    report = DamageReport(
        citizen_id=user_id,
        user_email=user_email,
        image_path=img_filename,
        location=location_text,
        latitude=latitude,
        longitude=longitude,
        detected_damage_type=damage_type,
        confidence_score=round(confidence, 3),
        severity=severity,
        status="submitted",
        report_source="dashcam"
    )

    db.session.add(report)
    db.session.commit()

    log_audit(user_id, f"DASHCAM_DETECTION_REPORT {report.id}")

    return jsonify({
        "msg": "Detection saved as report",
        "report_id": report.id,
    }), 201


@dashcam_bp.route("/reports", methods=["GET"])
@jwt_required()
def get_reports():
    """
    Returns all reports associated with this dashcam device.
    Uses citizen_id column as it stores the user_id (device ID) for dashcams.
    """
    try:
        device_id = get_jwt_identity()

        reports = DamageReport.query.filter_by(citizen_id=device_id).order_by(DamageReport.created_at.desc()).all()

        results = []
        for r in reports:
            results.append({
                "id": r.id,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "location": r.location,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "status": r.status,
                "severity": r.severity,
                "damage_type": r.detected_damage_type,
                "image_url": f"/api/files/images/{r.image_path}" if r.image_path and r.image_path != "REALTIME_NO_IMAGE" else None
            })

        return jsonify(results), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching dashcam reports: {e}")
        return jsonify({"msg": "Failed to fetch reports"}), 500