"""
Tender API Blueprint
Endpoints for the Pothole Accountability Agent pipeline.
All routes require official JWT.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.utils import secure_filename
from app import db
import os
import pdfplumber

tender_bp = Blueprint("tender", __name__, url_prefix="/api/tender")


# =====================================================
# ROLE GUARD — OFFICIAL ONLY
# =====================================================
@tender_bp.before_request
@jwt_required()
def ensure_official():
    claims = get_jwt()
    if claims.get("role") != "official":
        return jsonify({"msg": "Officials only"}), 403


# =====================================================
# POST /api/tender/process-pdf
# Upload a tender PDF → Agent 1 (extract) + Agent 2 (geocode) → save WorkOrders
# =====================================================
@tender_bp.route("/process-pdf", methods=["POST"])
def process_tender_pdf():
    """
    Accepts multipart/form-data with field 'pdf'.
    Runs the full Agent 1 + Agent 2 pipeline and saves WorkOrder rows.
    Returns summary of saved work orders.
    """
    if "pdf" not in request.files:
        return jsonify({"msg": "No PDF uploaded"}), 400

    file = request.files["pdf"]
    if not file.filename:
        return jsonify({"msg": "Empty filename"}), 400

    filename = secure_filename(file.filename)

    # Save PDF
    pdf_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "work_notices")
    os.makedirs(pdf_dir, exist_ok=True)
    save_path = os.path.join(pdf_dir, filename)
    file.save(save_path)

    # OCR the PDF
    ocr_text = ""
    try:
        with pdfplumber.open(save_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    ocr_text += extracted + "\n"
    except Exception as e:
        return jsonify({"msg": f"PDF read error: {e}"}), 400

    if not ocr_text.strip():
        return jsonify({"msg": "Could not extract text from PDF (empty or scanned image). Please use a text-based PDF."}), 400

    # Run full pipeline
    try:
        from app.tender_agents import run_tender_pipeline
        saved = run_tender_pipeline(ocr_text, db.session)
    except Exception as e:
        current_app.logger.error(f"Tender pipeline error: {e}")
        return jsonify({"msg": f"Pipeline error: {e}"}), 500

    if not saved:
        return jsonify({
            "msg": "Pipeline ran but no work orders could be geocoded and saved. Check OCR text quality.",
            "works_saved": 0
        }), 200

    first = saved[0]
    return jsonify({
        "msg": f"Tender processed successfully",
        "tender_id": first.tender_id,
        "works_saved": len(saved),
        "work_orders": [
            {
                "work_index": wo.work_index,
                "department": wo.department,
                "work_type": wo.work_type,
                "location_summary": wo.location_summary,
                "lat": wo.lat,
                "lng": wo.lng,
                "geo_confidence": wo.geo_confidence,
                "geo_status": wo.geo_status,
            }
            for wo in saved
        ]
    }), 201


# =====================================================
# GET /api/tender/work-orders
# List all geocoded work orders
# =====================================================
@tender_bp.route("/work-orders", methods=["GET"])
def list_work_orders():
    """
    Returns all WorkOrder rows, newest first.
    Optional query params:
      ?district=Sindhudurg
      ?work_type=gas_pipeline
      ?limit=50 (default 100)
    """
    from app.models import WorkOrder

    district = request.args.get("district")
    work_type = request.args.get("work_type")
    limit = request.args.get("limit", 100, type=int)

    query = WorkOrder.query

    if district:
        query = query.filter(WorkOrder.district.ilike(f"%{district}%"))
    if work_type:
        query = query.filter(WorkOrder.work_type == work_type)

    orders = query.order_by(WorkOrder.created_at.desc()).limit(limit).all()

    return jsonify([
        {
            "id": wo.id,
            "tender_id": wo.tender_id,
            "work_index": wo.work_index,
            "organization": wo.organization,
            "district": wo.district,
            "city_or_taluka": wo.city_or_taluka,
            "work_type": wo.work_type,
            "department": wo.department,
            "description_english": wo.description_english,
            "location_summary": wo.location_summary,
            "location_type": wo.location_type,
            "noc_reference": wo.noc_reference,
            "work_start_date": wo.work_start_date.isoformat() if wo.work_start_date else None,
            "work_end_date": wo.work_end_date.isoformat() if wo.work_end_date else None,
            "duration_days": wo.duration_days,
            "amount_inr": wo.amount_inr,
            "lat": wo.lat,
            "lng": wo.lng,
            "geo_confidence": wo.geo_confidence,
            "geo_status": wo.geo_status,
            "route_points": wo.route_points,
            "created_at": wo.created_at.isoformat() if wo.created_at else None,
        }
        for wo in orders
    ]), 200


# =====================================================
# POST /api/tender/match-pothole
# Agent 3: Given pothole lat/lng → find responsible department
# =====================================================
@tender_bp.route("/match-pothole", methods=["POST"])
def match_pothole():
    """
    Body JSON:
    {
      "lat": 15.9240,
      "lng": 73.8200,
      "detection_date": "2026-03-28"   (optional, defaults to today)
    }
    Returns accountability JSON from Agent 3.
    """
    data = request.get_json() or {}

    lat = data.get("lat")
    lng = data.get("lng")

    if lat is None or lng is None:
        return jsonify({"msg": "lat and lng are required"}), 400

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({"msg": "lat and lng must be numbers"}), 400

    from datetime import date
    detection_date = data.get("detection_date") or date.today().isoformat()

    try:
        from app.tender_agents import run_pothole_match
        result = run_pothole_match(lat, lng, detection_date, db.session)
    except Exception as e:
        current_app.logger.error(f"Pothole match error: {e}")
        return jsonify({"msg": f"Match error: {e}"}), 500

    return jsonify(result), 200
