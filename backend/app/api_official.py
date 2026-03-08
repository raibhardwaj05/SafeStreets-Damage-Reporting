from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models import DamageReport
from app import db
from app.utils import log_audit
from flask import current_app


official_bp = Blueprint('official', __name__, url_prefix='/api/official')


# =====================================================
# ROLE GUARD — OFFICIAL ONLY
# =====================================================
@official_bp.before_request
@jwt_required()
def ensure_official():
    claims = get_jwt()
    if claims.get("role") != "official":
        return jsonify({"msg": "Officials only"}), 403


# =====================================================
# REPORTS — REAL DATA (USED NOW)
# =====================================================

@official_bp.route('/reports', methods=['GET'])
def get_all_reports():
    """
    Used by:
    - work-reports.html
    - dashboard KPIs
    """
    reports = DamageReport.query.order_by(
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


@official_bp.route('/reports/<report_id>', methods=['GET'])
def get_report(report_id):
    """
    Used by:
    - verification.html
    """
    report = DamageReport.query.get(report_id)
    if not report:
        return jsonify({"msg": "Report not found"}), 404

    return jsonify({
        "id": report.id,
        "location": report.location,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "damage_type": report.detected_damage_type,
        "confidence": report.confidence_score,
        "severity": report.severity,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
        "image_url": f"/api/files/images/{report.image_path}",
        "reported_by": "Citizen"  # replace later with user lookup
    }), 200


from app.models import WorkReport
from flask import send_from_directory, current_app
import os

# =====================================================
# 📋 WORK NOTICES (PDF EXTRACTED DATA)
# =====================================================
@official_bp.route('/work-reports', methods=['GET'])
def get_work_reports():
    reports = WorkReport.query.order_by(
        WorkReport.created_at.desc()
    ).all()

    return jsonify([
        {
            "id": r.id,
            "notice_id": r.notice_id,
            "department": r.department,
            "work_type": r.work_type,
            "location": r.location,
            "executing_agency": r.executing_agency,
            "contractor_contact": r.contractor_contact,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "pdf_filename": r.pdf_filename,
            "pdf_url": f"/api/official/work-reports/{r.id}/download"
        }
        for r in reports
    ]), 200


# =====================================================
# ⬇️ DOWNLOAD WORK NOTICE PDF
# =====================================================
@official_bp.route('/work-reports/<report_id>/download', methods=['GET'])
def download_work_report_pdf(report_id):
    report = WorkReport.query.get(report_id)
    if not report or not report.pdf_filename:
        return jsonify({"msg": "PDF not found"}), 404

    pdf_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'work_notices')

    return send_from_directory(
        pdf_dir,
        report.pdf_filename,
        as_attachment=True
    )

from werkzeug.utils import secure_filename
from app.models import WorkReport
import pdfplumber
import re

@official_bp.route('/work-reports/upload', methods=['POST'])
def upload_work_notice():
    if 'pdf' not in request.files:
        return jsonify({"msg": "No PDF uploaded"}), 400

    file = request.files['pdf']
    if file.filename == '':
        return jsonify({"msg": "Empty filename"}), 400

    filename = secure_filename(file.filename)

    pdf_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'work_notices')
    os.makedirs(pdf_dir, exist_ok=True)

    save_path = os.path.join(pdf_dir, filename)
    file.save(save_path)

    # -------------------------------
    # 📄 REAL PDF EXTRACTION (FIXED FORMAT)
    # -------------------------------
    def extract_from_pdf(path):
        try:
            text = ""
            if not os.path.exists(path):
                return None
                
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    extracted_text = page.extract_text()
                    if extracted_text:
                        text += extracted_text + "\n"

            if not text.strip():
                return None

            def find(label):
                match = re.search(fr"{label}\s*:\s*(.+)", text, re.IGNORECASE)
                return match.group(1).strip() if match else None

            return {
                "notice_id": find("Notice ID"),
                "department": find("Department"),
                "work_type": find("Work Type"),
                "location": find("Location"),
                "executing_agency": find("Executing Agency"),
                "contractor_contact": find("Contractor Contact")
            }
        except Exception as e:
            current_app.logger.error(f"PDF extraction error: {e}")
            return None

    extracted = extract_from_pdf(save_path)

    if not extracted:
        return jsonify({"msg": "Failed to extract data from PDF. Please check the file format."}), 400

    # -------------------------------
    # ❗ VALIDATION
    # -------------------------------
    required_fields = ["notice_id", "department", "work_type", "location"]
    missing = [k for k in required_fields if not extracted.get(k)]

    if missing:
        return jsonify({
            "msg": "Invalid notice format. Missing fields in PDF.",
            "missing_fields": missing
        }), 400

    # -------------------------------
    # 💾 SAVE TO DB
    # -------------------------------
    report = WorkReport(
        notice_id=extracted["notice_id"],
        department=extracted["department"],
        work_type=extracted["work_type"],
        location=extracted["location"],
        executing_agency=extracted["executing_agency"],
        contractor_contact=extracted["contractor_contact"],
        pdf_filename=filename,
        status="pending"
    )

    db.session.add(report)
    db.session.commit()

    return jsonify({
        "msg": "Work notice uploaded & extracted successfully",
        "notice_id": report.notice_id,
        "id": report.id
    }), 201


# =====================================================
# VERIFICATION — REAL DATA (USED NOW)
# =====================================================

@official_bp.route('/reports/<report_id>/verify', methods=['POST'])
def verify_report(report_id):
    """
    Approve / Reject report
    """
    data = request.get_json() or {}
    decision = data.get("status")   # approved | rejected
    reason = data.get("reason", "")

    if decision not in ["approved", "rejected"]:
        return jsonify({"msg": "Invalid status"}), 400

    report = DamageReport.query.get(report_id)
    if not report:
        return jsonify({"msg": "Report not found"}), 404

    report.status = decision
    report.verified_by = get_jwt_identity()

    db.session.commit()

    log_audit(
        get_jwt_identity(),
        f"VERIFY_REPORT {decision.upper()} {report_id} | {reason}"
    )

    return jsonify({"msg": f"Report {decision}"}), 200


# =====================================================
# ASSIGNMENT — PARTIAL (STATUS REAL, CONTRACTOR LATER)
# =====================================================

@official_bp.route('/reports/<report_id>/assign', methods=['POST'])
def assign_work(report_id):
    """
    Status update is real.
    Contractor linkage will be added later.
    """
    data = request.get_json() or {}
    contractor_id = data.get("contractor_id")

    report = DamageReport.query.get(report_id)
    if not report:
        return jsonify({"msg": "Report not found"}), 404

    report.status = "assigned"
    db.session.commit()

    log_audit(
        get_jwt_identity(),
        f"ASSIGN_WORK report={report_id} contractor={contractor_id}"
    )

    return jsonify({"msg": "Work assigned"}), 200


# =====================================================
# CONTRACTORS — PLACEHOLDER (INTENTIONAL)
# =====================================================
@official_bp.route('/contractors', methods=['GET'])
def get_contractors():
    """
    Placeholder.
    Replace with Contractor model later.
    """
    return jsonify([
        {"id": "C1", "name": "ABC Road Works", "specialization": "Potholes", "rating": 4.5},
        {"id": "C2", "name": "XYZ Infra", "specialization": "Resurfacing", "rating": 4.8},
        {"id": "C3", "name": "City Builders", "specialization": "General", "rating": 4.2}
    ]), 200


# =====================================================
# SECTORS — PLACEHOLDER
# =====================================================
@official_bp.route('/sectors', methods=['GET'])
def get_sectors():
    """
    Placeholder.
    Sector table can be added later.
    """
    return jsonify([
        {"id": "S1", "name": "Sector 1 (North)"},
        {"id": "S2", "name": "Sector 2 (South)"},
        {"id": "S3", "name": "Sector 3 (East)"},
        {"id": "S4", "name": "Sector 4 (West)"}
    ]), 200


# =====================================================
# ANALYTICS — PLACEHOLDER
# =====================================================
@official_bp.route('/analytics', methods=['GET'])
def get_analytics():
    """
    Placeholder.
    Will be replaced with DB aggregation queries.
    """
    return jsonify({
        "summary": {
            "total_reports": 156,
            "completed_repairs": 142,
            "avg_repair_time": 2.8,
            "total_spent": "2.4M"
        },
        "repair_time": [
            {"sector": "S1", "days": 3.2},
            {"sector": "S2", "days": 2.1},
            {"sector": "S3", "days": 4.5},
            {"sector": "S4", "days": 1.8}
        ],
        "contractors": [
            {"name": "ABC Road Works", "score": 92},
            {"name": "XYZ Infra", "score": 88},
            {"name": "City Builders", "score": 75}
        ],
        "health_index": [
            {"sector": "S1", "index": 8.5, "status": "Good"},
            {"sector": "S2", "index": 6.0, "status": "Fair"},
            {"sector": "S3", "index": 4.5, "status": "Poor"},
            {"sector": "S4", "index": 9.0, "status": "Excellent"}
        ]
    }), 200
