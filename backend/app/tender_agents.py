"""
Pothole Accountability Agent Pipeline
Agents 1-3: Tender Extraction → Geocoding → Pothole Match
Model: grok-3-mini via xAI API (OpenAI-compatible)
"""

import os
import json
import time
import requests
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, timedelta
from openai import OpenAI

# =====================================================
# GEMINI CLIENT (Google GenAI, OpenAI-compatible)
# =====================================================

def _get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing env var: GEMINI_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

GEMINI_MODEL = "gemini-2.5-flash"


# ============================================================
# AGENT 1: TENDER EXTRACTION
# ============================================================

TENDER_EXTRACTION_SYSTEM_PROMPT = """
You are a Maharashtra government tender document parser.
You receive raw OCR text from tender PDFs. These can be in Marathi, Hindi, or English.
Your ONLY job is to extract location and work information and return it as valid JSON.

RULES:
- Return ONLY raw JSON. No explanation, no markdown, no preamble.
- If a field is not found, use null.
- Translate all Marathi/Hindi place names into their English equivalents.
- For landmark_route: extract every named place mentioned in the work description in order.
- A single tender may have MULTIPLE work items (rows in a table) — extract each as a separate object in the "works" array.
- CRITICAL FILTER: ONLY extract works that involve digging, trenching, or could cause surface road damage (e.g., water pipelines, drainage, electrical cables, gas pipelines, road construction). IGNORE and DO NOT include work items that are strictly for gardens, buildings, indoor maintenance, or other unrelated tasks.
- For work_type use ONLY: gas_pipeline | water_pipeline | electrical | road | drainage | other_road_damage_risk
- For location_type use ONLY: landmark_to_landmark | area_name | survey_number | road_stretch

OUTPUT FORMAT (return exactly this structure):
{
  "tender_meta": {
    "tender_id": "string — unique reference number",
    "organization": "string — issuing body name in English",
    "district": "string — district name in English",
    "city_or_taluka": "string — city/taluka in English",
    "state": "Maharashtra",
    "issued_date": "YYYY-MM-DD or null",
    "signed_by": "string or null",
    "portal": "mahatenders.gov.in"
  },
  "works": [
    {
      "work_index": 1,
      "work_type": "gas_pipeline",
      "department": "string — responsible department in English",
      "description_english": "string — plain English summary of what work is being done",
      "location_type": "landmark_to_landmark",
      "location_summary": "string — single human-readable location in English",
      "landmark_route": [
        "Govind Chitra Mandir, Savantvadi, Sindhudurg, Maharashtra",
        "Laxminarayan Mandir, Savantvadi, Sindhudurg, Maharashtra"
      ],
      "primary_search_query": "string — BEST single Google Maps search query for this location",
      "fallback_search_queries": [
        "string — second best query if primary fails",
        "string — third best query (broader area)"
      ],
      "work_start_date": "YYYY-MM-DD or null",
      "work_end_date": "YYYY-MM-DD or null",
      "duration_days": null,
      "amount_inr": null,
      "noc_reference": "string — NOC/tender number"
    }
  ]
}

LOCATION EXTRACTION RULES BY TENDER TYPE:

TYPE: landmark_to_landmark
- Extract every named place in route order
- landmark_route = array of all named places with city+district+state appended
- primary_search_query = "FROM [first landmark] TO [last landmark], [city], Maharashtra"

TYPE: area_name
- primary_search_query = "[Industrial Area name], [city], Maharashtra"
- fallback_search_queries[0] = "[city] MIDC, Maharashtra"

TYPE: survey_number
- primary_search_query = "[society/building name], [taluka], Maharashtra"
- fallback_search_queries[0] = "[taluka], [district], Maharashtra"

TYPE: road_stretch
- primary_search_query = "[road name], [city], Maharashtra"
"""

TENDER_EXTRACTION_USER_PROMPT = """Parse this tender document and return structured JSON:

{ocr_text}"""


def run_tender_extraction(ocr_text: str) -> dict:
    """
    Agent 1: Extract structured location data from tender OCR text using Gemini.
    Returns parsed tender dict with 'tender_meta' and 'works' keys.
    """
    client = _get_gemini_client()

    response = client.chat.completions.create(
        model=GEMINI_MODEL,
        messages=[
            {"role": "system", "content": TENDER_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": TENDER_EXTRACTION_USER_PROMPT.format(ocr_text=ocr_text)}
        ]
    )

    raw = response.choices[0].message.content.strip()
    # Strip any accidental markdown fences
    raw = raw.replace("```json", "").replace("```", "").strip()

    tender_data = json.loads(raw)
    return tender_data


# ============================================================
# AGENT 2: GEOCODING (Google Maps — no LLM)
# ============================================================

def call_google_geocoding(query: str) -> dict | None:
    """Call Google Maps Geocoding API, return normalized result."""
    api_key = os.environ.get("GOOGLE_MAPS_KEY")
    if not api_key:
        print("    ⚠ GOOGLE_MAPS_KEY not set — skipping geocoding")
        return None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(url, params={
            "address": query,
            "key": api_key,
            "region": "in",
            "components": "country:IN|administrative_area:Maharashtra"
        }, timeout=10)
        data = resp.json()
    except Exception as e:
        print(f"    ✗ Geocoding request failed: {e}")
        return None

    if data.get("status") != "OK":
        return None

    result = data["results"][0]
    loc_type = result["geometry"]["location_type"]
    confidence_map = {
        "ROOFTOP": 0.95,
        "RANGE_INTERPOLATED": 0.80,
        "GEOMETRIC_CENTER": 0.60,
        "APPROXIMATE": 0.35,
    }
    return {
        "lat": result["geometry"]["location"]["lat"],
        "lng": result["geometry"]["location"]["lng"],
        "confidence": confidence_map.get(loc_type, 0.4),
        "formatted_address": result["formatted_address"],
        "location_type": loc_type,
    }


def geocode_work_item(work: dict, tender_meta: dict) -> dict:
    """
    Agent 2 (standard): Try primary_search_query then fallbacks.
    Returns work item enriched with geocoding sub-dict.
    """
    queries = [
        work.get("primary_search_query"),
        *work.get("fallback_search_queries", [])
    ]
    queries = [q for q in queries if q]

    for query in queries:
        result = call_google_geocoding(query)
        if result and result["confidence"] >= 0.4:
            work["geocoding"] = {
                "lat": result["lat"],
                "lng": result["lng"],
                "confidence": result["confidence"],
                "query_used": query,
                "formatted_address": result["formatted_address"],
                "status": "success"
            }
            print(f"    ✓ Geocoded: {query[:60]} → {result['lat']:.4f},{result['lng']:.4f} (conf={result['confidence']})")
            return work
        time.sleep(0.3)

    # Fallback: district centroid
    fallback_query = f"{tender_meta['city_or_taluka']}, {tender_meta['district']}, Maharashtra"
    result = call_google_geocoding(fallback_query)
    work["geocoding"] = {
        "lat": result["lat"] if result else None,
        "lng": result["lng"] if result else None,
        "confidence": 0.1,
        "query_used": fallback_query,
        "formatted_address": result["formatted_address"] if result else None,
        "status": "fallback_only"
    }
    print(f"    ⚠ Fallback geocode used for work {work['work_index']}")
    return work


def geocode_landmark_route(work: dict, tender_meta: dict) -> dict:
    """
    Agent 2 (route): Geocode each landmark in a landmark_to_landmark work.
    Midpoint used as primary location; all points stored for route drawing.
    """
    route_points = []
    landmarks = work.get("landmark_route", [])

    for landmark in landmarks:
        result = call_google_geocoding(landmark)
        if result and result["confidence"] >= 0.35:
            route_points.append({
                "landmark": landmark,
                "lat": result["lat"],
                "lng": result["lng"],
                "confidence": result["confidence"]
            })
        time.sleep(0.3)

    if not route_points:
        return geocode_work_item(work, tender_meta)

    avg_lat = sum(p["lat"] for p in route_points) / len(route_points)
    avg_lng = sum(p["lng"] for p in route_points) / len(route_points)
    avg_conf = sum(p["confidence"] for p in route_points) / len(route_points)

    work["geocoding"] = {
        "lat": avg_lat,
        "lng": avg_lng,
        "confidence": avg_conf,
        "query_used": work.get("primary_search_query"),
        "route_points": route_points,
        "status": "route_geocoded"
    }
    return work


# ============================================================
# PIPELINE ORCHESTRATOR (Agents 1 + 2 + DB Save)
# ============================================================

def run_tender_pipeline(ocr_text: str, db_session) -> list:
    """
    Full pipeline: OCR text → Agent 1 extraction → Agent 2 geocoding → DB save.
    db_session: SQLAlchemy db session (Flask-SQLAlchemy db.session)
    Returns list of saved WorkOrder objects.
    """
    from app.models import WorkOrder

    print("\n=== TENDER PIPELINE START ===")

    # Step 1: Extract
    print("[1/3] Extracting locations with Gemini...")
    tender_data = run_tender_extraction(ocr_text)
    meta = tender_data["tender_meta"]
    works = tender_data["works"]
    print(f"    Found {len(works)} work item(s) in tender {meta.get('tender_id')}")

    # Step 2: Geocode
    print("[2/3] Geocoding locations...")
    geocoded_works = []
    for work in works:
        if work.get("location_type") == "landmark_to_landmark":
            work = geocode_landmark_route(work, meta)
        else:
            work = geocode_work_item(work, meta)
        geocoded_works.append(work)

    # Step 3: Save
    print("[3/3] Saving to database...")
    saved = []
    for work in geocoded_works:
        geo = work.get("geocoding", {})
        if not geo.get("lat"):
            print(f"    ✗ Skipping work {work['work_index']} — no coordinates")
            continue
        wo = save_work_order(db_session, meta, work, geo)
        saved.append(wo)

    print(f"=== DONE: {len(saved)}/{len(works)} work items saved ===\n")
    return saved


def save_work_order(db_session, meta: dict, work: dict, geo: dict):
    """
    Upsert a geocoded work order into the WorkOrder table via SQLAlchemy.
    Returns the WorkOrder instance.
    """
    from app.models import WorkOrder

    tender_id = meta.get("tender_id", "UNKNOWN")
    work_index = work.get("work_index", 0)

    # Parse dates safely
    def parse_date(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return None

    # Check for existing (upsert)
    existing = WorkOrder.query.filter_by(
        tender_id=tender_id,
        work_index=work_index
    ).first()

    route_json = json.dumps(geo.get("route_points")) if geo.get("route_points") else None

    if existing:
        existing.lat = geo["lat"]
        existing.lng = geo["lng"]
        existing.geo_confidence = geo.get("confidence")
        existing.geo_status = geo.get("status")
        existing.geocode_query = geo.get("query_used")
        existing.route_points = route_json
        db_session.commit()
        print(f"    ↺ Updated work order {tender_id}#{work_index}")
        return existing

    wo = WorkOrder(
        tender_id=tender_id,
        work_index=work_index,
        organization=meta.get("organization"),
        district=meta.get("district"),
        city_or_taluka=meta.get("city_or_taluka"),
        work_type=work.get("work_type"),
        department=work.get("department"),
        description_english=work.get("description_english"),
        location_summary=work.get("location_summary"),
        location_type=work.get("location_type"),
        noc_reference=work.get("noc_reference"),
        work_start_date=parse_date(work.get("work_start_date")),
        work_end_date=parse_date(work.get("work_end_date")),
        duration_days=work.get("duration_days"),
        amount_inr=work.get("amount_inr"),
        lat=geo["lat"],
        lng=geo["lng"],
        geo_confidence=geo.get("confidence"),
        geo_status=geo.get("status"),
        geocode_query=geo.get("query_used"),
        route_points=route_json,
    )
    db_session.add(wo)
    db_session.commit()
    print(f"    ✓ Saved work order {tender_id}#{work_index}")
    return wo


# ============================================================
# AGENT 3: POTHOLE MATCH
# ============================================================

POTHOLE_MATCH_SYSTEM_PROMPT = """
You are an accountability assistant for a pothole detection app in Maharashtra, India.
You receive:
1. A pothole GPS location (lat, lng) detected by computer vision
2. A list of nearby government work orders from the database (within 3km)

Your job is to analyze which work order is MOST LIKELY responsible for the pothole,
considering proximity, recency, work type, and geocoding confidence.

SCORING RULES:
- Gas pipeline work = HIGHEST pothole risk (deep trenching required)
- Water pipeline work = HIGH pothole risk (deep trenching required)
- Electrical underground = MEDIUM-HIGH pothole risk
- Drainage work = MEDIUM-HIGH pothole risk
- Road work = MEDIUM (they should repair their own damage)
- Other road damage risk = LOW-MEDIUM pothole risk
- Score closer work orders higher (within 500m = max proximity score)
- Score recent work higher (last 6 months = max recency, 6-18 months = reduced)
- Multiply by geocoding confidence (if geo confidence is low, reduce overall score)

Return ONLY valid JSON:
{
  "top_match": {
    "work_index": 1,
    "tender_id": "string",
    "department": "string",
    "work_type": "string",
    "confidence_label": "HIGH | MEDIUM | LOW",
    "confidence_score": 0.85,
    "distance_meters": 45,
    "evidence": "string — one sentence explaining why this department is responsible",
    "noc_reference": "string"
  },
  "all_matches": [],
  "accountability_statement": "string — formal one-paragraph statement"
}
"""

POTHOLE_MATCH_USER_PROMPT = """
Pothole detected at: lat={pothole_lat}, lng={pothole_lng}
Detected on: {detection_date}

Nearby work orders (within 3km, last 18 months):
{work_orders_json}

Which department is most accountable for this pothole?
"""


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in meters between two lat/lng points."""
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def run_pothole_match(
    pothole_lat: float,
    pothole_lng: float,
    detection_date: str,
    db_session
) -> dict:
    """
    Agent 3: Given a pothole location, find responsible government department.
    Uses bounding-box pre-filter on SQLite (~200m), then Gemini for ranking.
    Returns accountability JSON dict.
    """
    from app.models import WorkOrder

    print(f"\n=== POTHOLE MATCH: {pothole_lat},{pothole_lng} ===")

    # ~3km bounding box: 0.03° ≈ 3.3km at Maharashtra latitudes
    DEGREE_MARGIN = 0.03
    cutoff_date = datetime.utcnow() - timedelta(days=18 * 30)

    from sqlalchemy import or_
    candidates = WorkOrder.query.filter(
        WorkOrder.lat.between(pothole_lat - DEGREE_MARGIN, pothole_lat + DEGREE_MARGIN),
        WorkOrder.lng.between(pothole_lng - DEGREE_MARGIN, pothole_lng + DEGREE_MARGIN),
        or_(WorkOrder.work_start_date >= cutoff_date.date(), WorkOrder.work_start_date == None)
    ).limit(30).all()

    # Precise haversine filter + distance annotation
    nearby = []
    for wo in candidates:
        dist = _haversine_meters(pothole_lat, pothole_lng, wo.lat, wo.lng)
        if dist <= 3000:
            nearby.append({
                "tender_id": wo.tender_id,
                "work_index": wo.work_index,
                "department": wo.department,
                "work_type": wo.work_type,
                "description_english": wo.description_english,
                "location_summary": wo.location_summary,
                "noc_reference": wo.noc_reference,
                "work_start_date": wo.work_start_date.isoformat() if wo.work_start_date else None,
                "work_end_date": wo.work_end_date.isoformat() if wo.work_end_date else None,
                "geo_confidence": wo.geo_confidence,
                "location_type": wo.location_type,
                "distance_meters": round(dist, 1),
            })

    nearby.sort(key=lambda x: x["distance_meters"])
    nearby = nearby[:10]

    if not nearby:
        print("    No nearby work orders found within 3km")
        return {
            "top_match": None,
            "all_matches": [],
            "accountability_statement": "No government work orders found near this pothole within the last 18 months."
        }

    print(f"    Found {len(nearby)} nearby work order(s)")

    client = _get_gemini_client()
    response = client.chat.completions.create(
        model=GEMINI_MODEL,
        messages=[
            {"role": "system", "content": POTHOLE_MATCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": POTHOLE_MATCH_USER_PROMPT.format(
                    pothole_lat=pothole_lat,
                    pothole_lng=pothole_lng,
                    detection_date=detection_date,
                    work_orders_json=json.dumps(nearby, indent=2)
                )
            }
        ]
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Error decoding JSON. Raw response: {raw}")
        return {
            "top_match": None,
            "all_matches": [],
            "accountability_statement": "Error analyzing accountability from the model output."
        }

    top = result.get("top_match", {})
    if top:
        print(f"    Top match: {top.get('department')} ({top.get('confidence_label')})")
    return result


# ============================================================
# AGENT 3 SWEEP — Run after every new tender batch
# ============================================================

def run_accountability_sweep(db_session, sleep_between: float = 2.0) -> dict:
    """
    After Agents 1+2 populate fresh WorkOrder rows from a new tender PDF,
    this function re-runs Agent 3 against EVERY DamageReport that has GPS
    coordinates, writing the result back to the DB.

    Call this from the cron scrapers immediately after run_tender_pipeline().

    Returns:
        { "total": int, "updated": int, "matched": int, "skipped": int }
    """
    from app.models import DamageReport

    print("\n=== AGENT 3 ACCOUNTABILITY SWEEP ===")

    reports = db_session.query(DamageReport).filter(
        DamageReport.latitude  != None,
        DamageReport.longitude != None
    ).all()

    total   = len(reports)
    updated = 0
    matched = 0
    skipped = 0

    print(f"    Found {total} geo-located damage report(s) to sweep.")

    for report in reports:
        try:
            detection_date = (
                report.created_at.date().isoformat()
                if report.created_at
                else datetime.utcnow().date().isoformat()
            )

            result = run_pothole_match(
                report.latitude,
                report.longitude,
                detection_date,
                db_session
            )

            top = result.get("top_match") or {}

            report.accountability_dept       = top.get("department")
            report.accountability_statement  = result.get("accountability_statement")
            report.accountability_evidence   = top.get("evidence")
            report.accountability_confidence = top.get("confidence_label")

            db_session.commit()
            updated += 1

            if top.get("department"):
                matched += 1
                print(f"    ✓ [{report.id[:8]}] → {top['department']} ({top.get('confidence_label')})")
            else:
                print(f"    – [{report.id[:8]}] No match found within 3km")

            time.sleep(sleep_between)   # Rate-limit Gemini calls

        except Exception as e:
            skipped += 1
            print(f"    ✗ [{report.id[:8]}] Error: {e}")
            db_session.rollback()

    summary = {
        "total":   total,
        "updated": updated,
        "matched": matched,
        "skipped": skipped
    }
    print(f"\n=== SWEEP DONE: {updated}/{total} reports updated, {matched} matched, {skipped} errors ===\n")
    return summary

