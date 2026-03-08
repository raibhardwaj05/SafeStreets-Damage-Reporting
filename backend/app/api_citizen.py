from flask import Blueprint, jsonify, request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from werkzeug.utils import secure_filename
from app.models import DamageReport
from app import db
from app.utils import log_audit
from app.ml_utils import detect_damage, detect_damage_with_image
import os
import cv2
import numpy as np
import base64
import time

citizen_bp = Blueprint('citizen', __name__, url_prefix='/api/citizen')


# =====================================================
# ROLE GUARD — CITIZEN ONLY
# =====================================================
@citizen_bp.before_request
@jwt_required(optional=True)
def ensure_citizen():
    # /get-video/<token> is fetched by the browser video player / download link
    # which cannot send an Authorization header. The opaque token is the secret.
    if request.endpoint == 'citizen.get_video':
        return  # skip auth — token is the access control

    # All other endpoints require a valid citizen JWT
    claims = get_jwt()
    if not claims:
        return jsonify({"msg": "Missing or invalid token"}), 401
    if claims.get("role") != "citizen":
        return jsonify({"msg": "Citizens only"}), 403



# =====================================================
# 🔍 DETECT ONLY (PREVIEW — NO DB SAVE)
# =====================================================
@citizen_bp.route('/detect', methods=['POST'])
def detect_only():
    if 'image' not in request.files:
        return jsonify({"msg": "No image"}), 400

    file = request.files['image']
    user_id = get_jwt_identity()

    filename = secure_filename(f"preview_{user_id}_{file.filename}")

    temp_dir = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        'temp'
    )
    os.makedirs(temp_dir, exist_ok=True)

    path = os.path.join(temp_dir, filename)
    file.save(path)

    damage, confidence, annotated_b64 = detect_damage_with_image(path)

    return jsonify({
        "damage_type": damage,
        "confidence": confidence,
        "annotated_image": annotated_b64
    }), 200


# =====================================================
# 📹 REALTIME FRAME DETECT (POLLING)
# =====================================================
@citizen_bp.route('/detect-frame', methods=['POST'])
# =====================================================
# 📹 REALTIME FRAME DETECT (ULTRA FAST)
# =====================================================
@citizen_bp.route('/detect-frame', methods=['POST'])
def detect_frame():
    """
    Accepts base64 webcam frame.
    Runs detection in memory with optimized frame size.
    """

    data = request.get_json()

    if not data or 'frame' not in data:
        return jsonify({"msg": "No frame provided"}), 400

    try:
        frame_data = data['frame']

        if ',' in frame_data:
            frame_data = frame_data.split(',')[1]

        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)

        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"msg": "Frame decode failed"}), 400

        # --------------------------------------------------
        # ⚡ SPEED OPTIMIZATION
        # Resize frame for faster inference
        # --------------------------------------------------

        h, w = frame.shape[:2]

        MAX_WIDTH = 640

        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        # --------------------------------------------------
        # FAST DETECTION
        # --------------------------------------------------

        damage, confidence, annotated_b64 = detect_damage_with_image(frame)

        detected = damage not in (
            "No Damage",
            "Model Error",
            "Detection Error"
        )

        # --------------------------------------------------
        # Only send annotated image when damage detected
        # --------------------------------------------------

        if not detected:
            annotated_b64 = None

        return jsonify({
            "damage_type": damage,
            "confidence": round(float(confidence), 3),
            "detected": detected,
            "annotated_image": annotated_b64
        }), 200

    except Exception as e:
        current_app.logger.error(f"Realtime detect error: {e}")
        return jsonify({"msg": str(e)}), 500


# =====================================================
# 🎥 VIDEO FILE DETECT (FULL VIDEO — GPU BATCH INFERENCE)
# =====================================================
# @citizen_bp.route('/detect-video', methods=['POST'])
# def detect_video():
#     """
#     Accepts a video file upload.
#     Runs YOLO on EVERY frame (GPU stream=True), writes a fully annotated
#     output MP4, saves a DB report, and returns stats + a token to fetch the video.
#     """
#     if 'video' not in request.files:
#         return jsonify({"msg": "No video file provided"}), 400

#     file = request.files['video']
#     if file.filename == '':
#         return jsonify({"msg": "Empty filename"}), 400

#     allowed_exts = {'mp4', 'avi', 'mov', 'mkv'}
#     ext = file.filename.rsplit('.', 1)[-1].lower()
#     if ext not in allowed_exts:
#         return jsonify({"msg": "Invalid video format. Allowed: mp4, avi, mov, mkv"}), 400

#     user_id = get_jwt_identity()

#     # Location fields (optional)
#     location   = request.form.get('location')
#     latitude   = request.form.get('latitude', type=float)
#     longitude  = request.form.get('longitude', type=float)

#     temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
#     os.makedirs(temp_dir, exist_ok=True)

#     token = f"annotated_{user_id}_{int(time.time())}"
#     temp_input  = os.path.join(temp_dir, f"input_{token}.{ext}")
#     temp_output = os.path.join(temp_dir, f"{token}.mp4")

#     file.save(temp_input)

#     try:
#         stats = detect_video_to_file(temp_input, temp_output)
#         stats["video_token"] = token
        
#         # No auto-save. User must click "Submit Report".
#         return jsonify(stats), 200

#     except Exception as e:
#         try:
#             os.remove(temp_output)
#         except Exception:
#             pass
#         return jsonify({"msg": str(e)}), 500
#     finally:
#         try:
#             os.remove(temp_input)
#         except Exception:
#             pass


# =====================================================
# 📥 SERVE ANNOTATED VIDEO
# =====================================================
# @citizen_bp.route('/get-video/<token>', methods=['GET'])
# def get_video(token):
#     """
#     Serves the annotated output video for a given token.
#     Cleans up the temp file after sending.
#     """
#     # Sanitize token — only allow safe characters
#     import re
#     if not re.match(r'^[\w\-]+$', token):
#         return jsonify({"msg": "Invalid token"}), 400

#     temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
#     video_path = os.path.join(temp_dir, f"{token}.mp4")

#     if not os.path.exists(video_path):
#         return jsonify({"msg": "Video not found or already downloaded"}), 404

#     def generate():
#         with open(video_path, 'rb') as f:
#             while True:
#                 chunk = f.read(65536)
#                 if not chunk:
#                     break
#                 yield chunk

#     from flask import Response
#     return Response(
#         generate(),
#         mimetype='video/mp4',
#         headers={
#             'Content-Disposition': 'attachment; filename="pothole_detection.mp4"',
#             'Content-Length': str(os.path.getsize(video_path))
#         }
#     )


# =====================================================
# 📤 SUBMIT VIDEO REPORT (manual submit after analysis)
# =====================================================
# @citizen_bp.route('/submit-video', methods=['POST'])
# def submit_video_report():
#     """
#     Saves a damage report for a video detection result.
#     Accepts JSON: { damage_type, confidence, location, latitude, longitude, description }
#     """
#     data = request.get_json()
#     if not data:
#         return jsonify({"msg": "No data provided"}), 400

#     user_id = get_jwt_identity()
#     damage_type = data.get('damage_type')
#     confidence  = data.get('confidence', 0.0)

#     if not damage_type or damage_type == 'No Damage':
#         return jsonify({"msg": "No damage detected — nothing to submit"}), 400

#     if confidence >= 0.8:
#         severity = "high"
#     elif confidence >= 0.5:
#         severity = "medium"
#     else:
#         severity = "low"

#     report = DamageReport(
#         citizen_id=user_id,
#         image_path="VIDEO_REPORT",  # Placeholder to satisfy NOT NULL constraint
#         location=data.get('location'),
#         latitude=data.get('latitude'),
#         longitude=data.get('longitude'),
#         detected_damage_type=damage_type,
#         confidence_score=round(float(confidence), 3),
#         severity=severity,
#         status="submitted"
#     )
#     db.session.add(report)
#     db.session.commit()
#     log_audit(user_id, f"SUBMIT_VIDEO_REPORT {report.id}")

#     return jsonify({"msg": "Report submitted successfully", "report_id": report.id}), 201


# =====================================================
# 📤 SUBMIT REALTIME FRAME REPORT (manual submit)
# =====================================================
@citizen_bp.route('/submit-realtime-frame', methods=['POST'])
def submit_realtime_frame():
    """
    Saves a damage report from a realtime detection frame.
    Accepts multipart/form-data:
      - frame_b64: base64 JPEG of the detected frame
      - damage_type, confidence, location, latitude, longitude, description
    """
    user_id = get_jwt_identity()

    damage_type = request.form.get('damage_type')
    confidence  = request.form.get('confidence', 0.0, type=float)
    frame_b64   = request.form.get('frame_b64', '')

    if not damage_type or damage_type == 'No Damage':
        return jsonify({"msg": "No damage detected — nothing to submit"}), 400

    # Save the frame image
    img_filename = "REALTIME_NO_IMAGE"  # Fallback
    if frame_b64:
        try:
            raw = frame_b64.split(',')[1] if ',' in frame_b64 else frame_b64
            img_bytes = base64.b64decode(raw)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                image_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
                os.makedirs(image_dir, exist_ok=True)
                img_filename = f"rt_submit_{user_id}_{int(time.time())}.jpg"
                cv2.imwrite(os.path.join(image_dir, img_filename), img)
        except Exception as e:
            current_app.logger.warning(f"Could not save realtime frame image: {e}")

    if confidence >= 0.8:
        severity = "high"
    elif confidence >= 0.5:
        severity = "medium"
    else:
        severity = "low"

    report = DamageReport(
        citizen_id=user_id,
        image_path=img_filename,
        location=request.form.get('location'),
        latitude=request.form.get('latitude', type=float),
        longitude=request.form.get('longitude', type=float),
        detected_damage_type=damage_type,
        confidence_score=round(confidence, 3),
        severity=severity,
        status="submitted"
    )
    db.session.add(report)
    db.session.commit()
    log_audit(user_id, f"SUBMIT_REALTIME_REPORT {report.id}")

    return jsonify({"msg": "Report submitted successfully", "report_id": report.id}), 201


# =====================================================
# 📤 FINAL SUBMIT (SAVE IMAGE + DB RECORD)
# =====================================================
@citizen_bp.route('/submit', methods=['POST'])
def submit_report():
    if 'image' not in request.files:
        return jsonify({"msg": "No image"}), 400

    file = request.files['image']
    user_id = get_jwt_identity()

    if file.filename == '':
        return jsonify({"msg": "Empty filename"}), 400

    # -------------------------
    # SAVE IMAGE
    # -------------------------
    filename = secure_filename(f"{user_id}_{file.filename}")

    image_dir = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        'images'
    )
    os.makedirs(image_dir, exist_ok=True)

    file_path = os.path.join(image_dir, filename)
    file.save(file_path)

    # -------------------------
    # ML INFERENCE
    # -------------------------
    damage_type, confidence = detect_damage(file_path)

    # -------------------------
    # SEVERITY LOGIC
    # -------------------------
    if confidence >= 0.8:
        severity = "high"
    elif confidence >= 0.5:
        severity = "medium"
    else:
        severity = "low"

    # -------------------------
    # CREATE DB RECORD
    # IMPORTANT: store ONLY filename
    # -------------------------
    report = DamageReport(
        citizen_id=user_id,
        image_path=filename,  # 👈 critical for /api/files/images/<filename>
        location=request.form.get("location"),
        latitude=request.form.get("latitude", type=float),
        longitude=request.form.get("longitude", type=float),
        detected_damage_type=damage_type,
        confidence_score=confidence,
        severity=severity,
        status="submitted"
    )

    db.session.add(report)
    db.session.commit()

    # -------------------------
    # AUDIT LOG
    # -------------------------
    log_audit(
        user_id,
        f"SUBMIT_DAMAGE_REPORT {report.id}"
    )

    return jsonify({
        "msg": "Report submitted successfully",
        "report_id": report.id
    }), 201

# =====================================================
# 📋 GET USER'S REPORTS
# =====================================================
@citizen_bp.route('/reports', methods=['GET'])
def get_user_reports():
    """
    Fetch all reports submitted by the logged-in citizen.
    Used by: citizen/dashboard.html
    """
    user_id = get_jwt_identity()
    
    reports = DamageReport.query.filter_by(
        citizen_id=user_id
    ).order_by(
        DamageReport.created_at.desc()
    ).all()
    
    return jsonify([
        {
            "id": r.id,
            "location": r.location,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "damage_type": r.detected_damage_type,
            "confidence": r.confidence_score,
            "severity": r.severity,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "image_url": f"/api/files/images/{r.image_path}"
        }
        for r in reports
    ]), 200


# =====================================================
# 📊 USER REPORT STATUS SUMMARY
# =====================================================
@citizen_bp.route('/report-status-summary', methods=['GET'])
def report_status_summary():
    user_id = get_jwt_identity()

    reported_count = DamageReport.query.filter_by(
        citizen_id=user_id,
        status='submitted'
    ).count()

    in_progress_count = DamageReport.query.filter_by(
        citizen_id=user_id,
        status='in_progress'
    ).count()

    completed_count = DamageReport.query.filter_by(
        citizen_id=user_id,
        status='completed'
    ).count()

    return jsonify({
        "reported": reported_count,
        "in_progress": in_progress_count,
        "completed": completed_count
    }), 200


