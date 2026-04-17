from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models import DamageReport
from app import db
from app.utils import log_audit
from flask import current_app
from app.models import User, Device

def get_reporter_info(report):
    if report.report_source == 'citizen':
        if not report.citizen_id:
            return "Anonymous Citizen"
        user = User.query.get(report.citizen_id)
        return user.email if user else "Unknown Citizen"
    elif report.report_source == 'dashcam':
        if not report.citizen_id:
            return "Anonymous Dashcam"
        device = Device.query.get(report.citizen_id)
        return device.device_id if device else "Unknown Dashcam"
    return "Unknown"


official_bp = Blueprint('official', __name__, url_prefix='/api/official')


# =====================================================
# ROLE GUARD — OFFICIAL ONLY
# =====================================================
@official_bp.before_request
# @jwt_required()
def ensure_official():
    # Bypass role check for accountability TESTING
    if request.path.endswith("/accountability"):
        return
    from flask_jwt_extended import verify_jwt_in_request
    verify_jwt_in_request()
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
            "report_source": r.report_source,
            "reported_by": get_reporter_info(r),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "image_url": f"/api/files/images/{r.image_path}",
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "persistedDescription": r.resolution_description,
            "persistedAfterPhoto": f"/api/files/images/{r.after_image_path}" if r.after_image_path else None,
            "persistedAfterPhotoLast": f"/api/files/images/{r.after_image_path_last}" if r.after_image_path_last else None,
            "waterlogging_pothole_risk": r.waterlogging_pothole_risk
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
        "report_source": report.report_source,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "image_url": f"/api/files/images/{report.image_path}",
        "reported_by": get_reporter_info(report),
        "resolved_at": report.resolved_at.isoformat() if report.resolved_at else None,
        "persistedDescription": report.resolution_description,
        "persistedAfterPhoto": f"/api/files/images/{report.after_image_path}" if report.after_image_path else None,
        "persistedAfterPhotoLast": f"/api/files/images/{report.after_image_path_last}" if report.after_image_path_last else None,
        "waterlogging_pothole_risk": report.waterlogging_pothole_risk
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

    # -----------------------------------------------
    # 🤖 AGENT PIPELINE: Grok Agent 1 + Agent 2
    # Extracts structured data & geocodes all works
    # -----------------------------------------------
    ocr_text = ""
    try:
        with pdfplumber.open(save_path) as pdf:
            for page in pdf.pages:
                extracted_text = page.extract_text()
                if extracted_text:
                    ocr_text += extracted_text + "\n"
    except Exception as e:
        current_app.logger.error(f"PDF OCR error: {e}")
        return jsonify({"msg": f"PDF read error: {e}"}), 400

    if not ocr_text.strip():
        return jsonify({"msg": "Could not extract text from PDF. Ensure it is a text-based (not scanned) PDF."}), 400

    try:
        from app.tender_agents import run_tender_pipeline, run_tender_extraction
        # Run full pipeline → saves WorkOrder rows
        saved_orders = run_tender_pipeline(ocr_text, db.session)
        # Also extract meta for backwards-compat WorkReport entry
        tender_data = run_tender_extraction(ocr_text)
        meta = tender_data.get("tender_meta", {})
        works = tender_data.get("works", [])
        first_work = works[0] if works else {}
    except Exception as e:
        current_app.logger.error(f"Tender agent error: {e}")
        return jsonify({"msg": f"AI extraction error: {e}"}), 500

    # -----------------------------------------------
    # 💾 BACKWARD-COMPAT: Save WorkReport row
    # (keeps existing PDF download / dashboard working)
    # -----------------------------------------------
    notice_id = meta.get("tender_id") or filename
    department = first_work.get("department", "Unknown Department")
    work_type  = first_work.get("work_type", "other")
    location   = first_work.get("location_summary", "")

    report = WorkReport(
        notice_id=notice_id,
        department=department,
        work_type=work_type,
        location=location,
        executing_agency=meta.get("organization"),
        contractor_contact=None,
        pdf_filename=filename,
        status="pending"
    )

    db.session.add(report)
    db.session.commit()

    return jsonify({
        "msg": "Work notice uploaded & extracted successfully",
        "notice_id": notice_id,
        "id": report.id,
        "works_geocoded": len(saved_orders),
        "agent_summary": [
            {
                "work_index": wo.work_index,
                "department": wo.department,
                "work_type": wo.work_type,
                "lat": wo.lat,
                "lng": wo.lng,
                "geo_status": wo.geo_status,
            }
            for wo in saved_orders
        ]
    }), 201


# =====================================================
# ACCOUNTABILITY — AGENT 3 INVESTIGATION
# =====================================================
@official_bp.route('/reports/<report_id>/accountability', methods=['GET'])
# @jwt_required()  # REMOVED FOR TESTING
def get_accountability(report_id):
    """
    Returns Agent 3 accountability result for a damage report.

    Fast path (< 1 ms):  reads cached columns written by the cron sweep.
    Slow path (5-10 s):  falls back to a live Gemini call if cache is empty
                         (e.g. before the first cron run).
    """
    report = DamageReport.query.get(report_id)
    if not report:
        return jsonify({"msg": "Report not found"}), 404

    if report.latitude is None or report.longitude is None:
        return jsonify({
            "top_match": None,
            "all_matches": [],
            "accountability_statement": "Location data is unavailable for this report.",
            "department": None,
            "evidence": None,
            "cached": False
        }), 200

    # ── Fast path: return cached cron sweep result ──────────────────
    if report.accountability_statement:
        top_match = None
        if report.accountability_dept:
            top_match = {
                "department":        report.accountability_dept,
                "evidence":          report.accountability_evidence,
                "confidence_label":  report.accountability_confidence,
            }
        return jsonify({
            "top_match":              top_match,
            "all_matches":            [],
            "accountability_statement": report.accountability_statement,
            "department":             report.accountability_dept,
            "evidence":               report.accountability_evidence,
            "cached":                 True
        }), 200

    # ── Slow path: live Gemini call (first time, before cron ran) ───
    from datetime import date
    detection_date = (
        report.created_at.date().isoformat()
        if report.created_at
        else date.today().isoformat()
    )

    try:
        from app.tender_agents import run_pothole_match
        result = run_pothole_match(
            report.latitude,
            report.longitude,
            detection_date,
            db.session
        )
    except Exception as e:
        current_app.logger.error(f"Accountability agent error: {e}")
        return jsonify({"msg": f"Agent error: {e}"}), 500

    top = result.get("top_match") or {}

    # Persist result to cache so future calls are instant
    report.accountability_dept       = top.get("department")
    report.accountability_statement  = result.get("accountability_statement")
    report.accountability_evidence   = top.get("evidence")
    report.accountability_confidence = top.get("confidence_label")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    result["department"] = top.get("department")
    result["evidence"]   = top.get("evidence")
    result["cached"]     = False

    return jsonify(result), 200


# =====================================================
# 🗺️ ROAD RISK PREDICTIONS (LAYER 2 — Legacy RoadRisk table)
# =====================================================
from app.risk_predictor import get_risk_summary, update_all_road_risks, get_predictive_risk, invalidate_cache

@official_bp.route('/road-risks', methods=['GET'])
def get_road_risks():
    """
    Returns risk analysis for road segments (legacy RoadRisk table).
    Used by: analytics.html (Layer 2)
    """
    summary = get_risk_summary()
    return jsonify(summary), 200


@official_bp.route('/road-risks/update', methods=['POST'])
def update_road_risks():
    """
    Triggers a re-calculation of road risks (legacy).
    """
    success = update_all_road_risks()
    if success:
        return jsonify({"msg": "Road risk scores updated successfully"}), 200
    else:
        return jsonify({"msg": "Error updating road risk scores"}), 500


# =====================================================
# 🔮 PREDICTIVE RISK LAYER — Live DamageReport clustering
# =====================================================

@official_bp.route('/predictive-risk', methods=['GET'])
def get_predictive_risk_data():
    """
    Predictive Risk Layer — powered by historical DamageReport data.

    Clusters all Pothole reports within 1 km radius, computes
    frequency / recency / severity / growth-trend features, and
    returns a risk score (0‒1) + classification (low/medium/high)
    for each geographic cluster.

    Results are cached for 1 hour to avoid repeated DB scans.

    Response shape:
    [
      {
        "latitude": float,
        "longitude": float,
        "total_reports": int,
        "severity_score": float,
        "avg_severity": float,
        "reports_last_30": int,
        "reports_last_90": int,
        "growth_trend": int,
        "risk_score": float,          // 0.0 – 1.0
        "risk_level": "high|medium|low",
        "reason": "Human-readable explanation"
      },
      ...
    ]
    """
    try:
        data = get_predictive_risk()
        return jsonify({
            "clusters": data,
            "total_clusters": len(data),
            "high_risk":   sum(1 for c in data if c["risk_level"] == "high"),
            "medium_risk": sum(1 for c in data if c["risk_level"] == "medium"),
            "low_risk":    sum(1 for c in data if c["risk_level"] == "low"),
        }), 200
    except Exception as exc:
        current_app.logger.error(f"Predictive risk error: {exc}")
        return jsonify({"msg": f"Error computing predictive risk: {exc}"}), 500


@official_bp.route('/predictive-risk/refresh', methods=['POST'])
def refresh_predictive_risk():
    """
    Bust the 1-hour predictive risk cache and return fresh data immediately.
    Useful after a batch of new reports are ingested.
    """
    try:
        invalidate_cache()
        data = get_predictive_risk()
        return jsonify({
            "msg": "Predictive risk refreshed successfully",
            "clusters": data,
            "total_clusters": len(data),
            "high_risk":   sum(1 for c in data if c["risk_level"] == "high"),
            "medium_risk": sum(1 for c in data if c["risk_level"] == "medium"),
            "low_risk":    sum(1 for c in data if c["risk_level"] == "low"),
        }), 200
    except Exception as exc:
        current_app.logger.error(f"Predictive risk refresh error: {exc}")
        return jsonify({"msg": f"Error refreshing predictive risk: {exc}"}), 500




# =====================================================
# 🗓️ POTHOLE ACTIVITY HEATMAP
# =====================================================

@official_bp.route('/pothole-heatmap', methods=['GET'])
def pothole_heatmap():
    """
    Returns daily pothole report counts for a given year (default: current year)
    plus per-month statistics and Poisson recurrence predictions.

    Query params:
        year (int, optional) – defaults to current year

    Response shape:
    {
        "year": 2026,
        "total": 551,
        "max_daily": 42,
        "daily_counts": { "2026-03-15": 12, ... },
        "monthly_stats": {
            "1": { "month_name": "January", "count": 45, "daily_rate": 1.5,
                   "predicted_next": 48, "prediction_pct": 87.0 },
            ...
        }
    }
    """
    import calendar as _cal
    import math as _math
    from datetime import datetime
    from sqlalchemy import func
    from .models import DamageReport

    year = request.args.get('year', datetime.now().year, type=int)

    try:
        # ── Daily counts for the requested year ─────────────────────────
        rows = (
            db.session.query(
                func.strftime('%Y-%m-%d', DamageReport.created_at).label('day'),
                func.count(DamageReport.id).label('cnt')
            )
            .filter(
                func.lower(DamageReport.detected_damage_type) == 'pothole',
                func.strftime('%Y', DamageReport.created_at) == str(year),
            )
            .group_by(func.strftime('%Y-%m-%d', DamageReport.created_at))
            .all()
        )
        daily_counts = {r.day: r.cnt for r in rows}
        max_daily = max(daily_counts.values()) if daily_counts else 0

        # ── Monthly stats + Poisson predictions ─────────────────────────
        monthly_stats = {}
        for month in range(1, 13):
            prefix = f"{year}-{month:02d}-"
            month_count = sum(v for k, v in daily_counts.items() if k.startswith(prefix.rstrip('-')))
            days_in_month = _cal.monthrange(year, month)[1]
            daily_rate = month_count / days_in_month

            # Poisson: lambda = expected events per window
            lam = daily_rate * days_in_month  # events expected in similar month
            pred_pct = round((1 - _math.exp(-lam)) * 100, 1) if lam > 0 else 0.0
            pred_pct = min(pred_pct, 99.0)

            # Historical total for this calendar month (all years)
            hist = (
                db.session.query(func.count(DamageReport.id))
                .filter(
                    func.lower(DamageReport.detected_damage_type) == 'pothole',
                    func.strftime('%m', DamageReport.created_at) == f"{month:02d}",
                )
                .scalar() or 0
            )

            monthly_stats[str(month)] = {
                "month_name":     _cal.month_name[month],
                "month_abbr":     _cal.month_abbr[month],
                "count":          month_count,
                "daily_rate":     round(daily_rate, 2),
                "predicted_next": round(daily_rate * days_in_month),  # same rate → next year
                "prediction_pct": pred_pct,
                "historical_all": hist,
                "peak_day":       max(
                    (k for k in daily_counts if k.startswith(f"{year}-{month:02d}")),
                    key=lambda d: daily_counts[d],
                    default=None
                ),
                "peak_count": max(
                    (daily_counts[k] for k in daily_counts if k.startswith(f"{year}-{month:02d}")),
                    default=0
                ),
            }

        return jsonify({
            "year":          year,
            "total":         sum(daily_counts.values()),
            "max_daily":     max_daily,
            "daily_counts":  daily_counts,
            "monthly_stats": monthly_stats,
        }), 200

    except Exception as exc:
        current_app.logger.error(f"pothole-heatmap error: {exc}")
        return jsonify({"error": str(exc)}), 500


# =====================================================
# 📍 HOTSPOTS BY PERIOD (day or month click)
# =====================================================

@official_bp.route('/hotspots-by-period', methods=['GET'])
def hotspots_by_period():
    """
    Returns cluster risk cards for potholes reported in a specific day or month.

    Query params (use one):
        date=YYYY-MM-DD          → single day
        year=YYYY&month=M        → full calendar month

    Response shape matches /predictive-risk clusters for easy card reuse:
    {
        "label": "March 28, 2026",
        "period_count": 233,
        "clusters": [ { ...same fields as predictive-risk cluster... } ]
    }
    """
    import calendar as _cal
    import math as _math
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from .models import DamageReport

    RADIUS_KM = 1.0
    EARTH_R   = 6371.0

    def _haversine(lat1, lon1, lat2, lon2):
        dlat = _math.radians(lat2 - lat1)
        dlon = _math.radians(lon2 - lon1)
        a = (_math.sin(dlat / 2) ** 2
             + _math.cos(_math.radians(lat1))
             * _math.cos(_math.radians(lat2))
             * _math.sin(dlon / 2) ** 2)
        return EARTH_R * 2 * _math.asin(_math.sqrt(a))

    date_str  = request.args.get('date')
    year_str  = request.args.get('year')
    month_str = request.args.get('month')

    try:
        if date_str:
            start = datetime.strptime(date_str, '%Y-%m-%d')
            end   = start + timedelta(days=1)
            label = start.strftime('%B %d, %Y')
        elif year_str and month_str:
            yr, mo = int(year_str), int(month_str)
            start  = datetime(yr, mo, 1)
            end    = datetime(yr, mo, _cal.monthrange(yr, mo)[1], 23, 59, 59)
            label  = f"{_cal.month_name[mo]} {yr}"
        else:
            return jsonify({'error': 'Provide date or year+month params'}), 400

        # ── 1. Fetch reports in the requested period ──────────────────
        period_reports = DamageReport.query.filter(
            func.lower(DamageReport.detected_damage_type) == 'pothole',
            DamageReport.created_at >= start,
            DamageReport.created_at <= end,
            DamageReport.latitude  != None,
            DamageReport.longitude != None,
        ).all()

        if not period_reports:
            return jsonify({'label': label, 'period_count': 0, 'clusters': []}), 200

        # ── 2. Greedy 1-km clustering of period reports ───────────────
        assigned = [False] * len(period_reports)
        raw_clusters = []

        for i, r in enumerate(period_reports):
            if assigned[i]:
                continue
            group = [r]
            assigned[i] = True
            for j, r2 in enumerate(period_reports):
                if not assigned[j] and _haversine(
                    r.latitude, r.longitude, r2.latitude, r2.longitude
                ) <= RADIUS_KM:
                    group.append(r2)
                    assigned[j] = True
            raw_clusters.append(group)

        # ── 3. For each cluster, pull ALL historical reports & score ──
        now_utc = datetime.utcnow()
        clusters_out = []

        for group in raw_clusters:
            lat = sum(x.latitude  for x in group) / len(group)
            lon = sum(x.longitude for x in group) / len(group)

            # ±0.009° ≈ 1 km bounding box
            all_hist = DamageReport.query.filter(
                func.lower(DamageReport.detected_damage_type) == 'pothole',
                DamageReport.latitude.between( lat - 0.009, lat + 0.009),
                DamageReport.longitude.between(lon - 0.009, lon + 0.009),
                DamageReport.latitude  != None,
                DamageReport.longitude != None,
            ).all()

            total = len(all_hist)
            if total == 0:
                continue

            # Temporal features
            timestamps = [r.created_at for r in all_hist if r.created_at]
            oldest     = min(timestamps, default=now_utc)
            latest     = max(timestamps, default=now_utc)
            days_span  = max((now_utc - oldest).days, 1)
            months_act = max(days_span / 30.0, 1.0)
            days_since = (now_utc - latest).days

            cut30 = now_utc - timedelta(days=30)
            cut60 = now_utc - timedelta(days=60)
            last30 = sum(1 for r in all_hist if r.created_at and r.created_at >= cut30)
            prev30 = sum(1 for r in all_hist if r.created_at and cut60 <= r.created_at < cut30)

            growth_trend = last30 - prev30
            unresolved   = sum(1 for r in all_hist
                               if r.status not in ('resolved','completed','approved'))
            unres_ratio  = unresolved / total

            # Severity
            SEV = {'low':1,'medium':2,'high':3,'critical':4}
            avg_sev = sum(SEV.get((r.severity or '').lower(), 1) for r in all_hist) / total

            # Poisson λ with adjustments (mirrors risk_predictor logic)
            lam = total / months_act
            if   days_since > 90: lam *= 0.3
            elif days_since > 30: lam *= 0.6
            if growth_trend > 0 and prev30 > 0:
                lam *= min(last30 / prev30, 2.0)
            lam *= (1 + 0.5 * unres_ratio)
            lam *= (1 + 0.25 * (avg_sev - 1))

            pred_pct   = min(round((1 - _math.exp(-lam)) * 100, 1), 99.0) if lam > 0 else 0.0
            risk_level = 'high' if pred_pct > 70 else ('medium' if pred_pct >= 40 else 'low')
            monthly_rate = round(lam, 3)

            sev_labels = {1:'low',2:'medium',3:'high',4:'critical'}
            dom_sev    = sev_labels.get(round(avg_sev), 'medium')
            trend_str  = f"+{growth_trend}" if growth_trend > 0 else str(growth_trend)

            reason = (
                f"{'🔴' if risk_level=='high' else '🟡' if risk_level=='medium' else '🟢'} "
                f"{risk_level.capitalize()} recurrence risk — {pred_pct}% chance of a new "
                f"pothole here in the next 30 days; generating ~{monthly_rate} potholes/month "
                f"historically; {'worsening' if growth_trend > 0 else 'improving'} trend "
                f"({trend_str} vs prior 30 days); {unresolved} report(s) still unresolved."
            )

            clusters_out.append({
                'latitude':       round(lat, 5),
                'longitude':      round(lon, 5),
                'total_reports':  total,
                'period_count':   len(group),
                'reports_last_30':last30,
                'unresolved':     unresolved,
                'growth_trend':   growth_trend,
                'days_since_last':days_since,
                'monthly_rate':   monthly_rate,
                'prediction_pct': pred_pct,
                'risk_score':     round(pred_pct / 100, 4),
                'risk_level':     risk_level,
                'reason':         reason,
            })

        # Sort by risk score desc, cap at top 10
        clusters_out.sort(key=lambda c: c['risk_score'], reverse=True)

        return jsonify({
            'label':        label,
            'period_count': len(period_reports),
            'clusters':     clusters_out[:10],
        }), 200

    except Exception as exc:
        current_app.logger.error(f'hotspots-by-period error: {exc}')
        return jsonify({'error': str(exc)}), 500









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
# RESOLVER
# =====================================================
@official_bp.route('/reports/<report_id>/resolve', methods=['POST'])
def resolve_report(report_id):
    from datetime import datetime
    import os
    import time
    from werkzeug.utils import secure_filename

    report = DamageReport.query.get(report_id)
    if not report:
        return jsonify({"msg": "Report not found"}), 404

    description = request.form.get("description", "")
    
    # Process After Image 1
    after_image_path = None
    if 'after_image' in request.files:
        file = request.files['after_image']
        if file.filename != '':
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            filename = f"resolved_{report_id}_{int(time.time())}.{ext}"
            img_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
            os.makedirs(img_dir, exist_ok=True)
            file.save(os.path.join(img_dir, filename))
            after_image_path = filename

    # Process After Image 2 (Dashcam last)
    after_image_path_last = None
    if 'after_image_last' in request.files:
        file = request.files['after_image_last']
        if file.filename != '':
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            filename = f"resolved_last_{report_id}_{int(time.time())}.{ext}"
            img_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
            os.makedirs(img_dir, exist_ok=True)
            file.save(os.path.join(img_dir, filename))
            after_image_path_last = filename

    # Update Report
    report.status = "resolved"
    report.resolved_at = datetime.utcnow()
    report.resolution_description = description
    if after_image_path:
        report.after_image_path = after_image_path
    if after_image_path_last:
        report.after_image_path_last = after_image_path_last

    db.session.commit()

    log_audit(
        get_jwt_identity(),
        f"RESOLVE_WORK report={report_id}"
    )

    return jsonify({"msg": "Report resolved successfully"}), 200


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
