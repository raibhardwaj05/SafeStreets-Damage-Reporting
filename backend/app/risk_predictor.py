"""
risk_predictor.py
=================
Predictive Risk Layer for SafeStreets.

Answers: "Which locations are likely to develop potholes again?"

Pipeline
--------
1. Fetch all Pothole DamageReports from DB
2. Cluster them by proximity (DBSCAN, ~1 km radius) using Haversine distance
3. Compute severity scores and temporal features per cluster
4. Engineer frequency / recency / growth_trend / severity_index features
5. Produce a weighted risk_score (0‒1) and classify into low/medium/high
6. Cache results for 1 hour to avoid hammering the DB on every page load

Author  : SafeStreets Backend Team
Version : 2.0  (rule-based, no external ML deps beyond numpy/sklearn)
"""

import logging
import math
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports — graceful degradation if sklearn / numpy missing
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from sklearn.cluster import DBSCAN
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning(
        "scikit-learn / numpy not installed. "
        "Falling back to simple grid-based clustering (less accurate)."
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEVERITY_WEIGHTS = {
    "low":      1,
    "medium":   2,
    "high":     3,
    "critical": 4,
}

# Earth radius in km (for Haversine)
EARTH_RADIUS_KM = 6371.0

# DBSCAN clustering radius  ≈ 1 km expressed in radians
CLUSTER_RADIUS_KM   = 1.0
CLUSTER_EPS_RAD     = CLUSTER_RADIUS_KM / EARTH_RADIUS_KM   # ~0.000157 rad
CLUSTER_MIN_SAMPLES = 1   # every lone pothole forms its own cluster

# Cache TTL
CACHE_TTL_SECONDS = 3600   # 1 hour

# ---------------------------------------------------------------------------
# In-memory cache (dict with 'data' + 'expires_at')
# ---------------------------------------------------------------------------
_cache: dict = {
    "data":       None,
    "expires_at": 0.0,
}


# ===========================================================================
# Public API
# ===========================================================================

def get_predictive_risk() -> list[dict]:
    """
    Main entry-point called by the Flask route.

    Returns a cached (up to 1 hour) list of cluster dicts, each with:
        latitude, longitude, total_reports, severity_score,
        risk_score, risk_level, reason
    """
    now = time.time()
    if _cache["data"] is not None and now < _cache["expires_at"]:
        logger.debug("risk_predictor: returning cached result")
        return _cache["data"]

    result = _compute_predictive_risk()
    _cache["data"]       = result
    _cache["expires_at"] = now + CACHE_TTL_SECONDS
    return result


def invalidate_cache():
    """Force next call to recompute (useful after new reports ingested)."""
    _cache["data"]       = None
    _cache["expires_at"] = 0.0


def get_hidden_pothole_prob(lat: float, lon: float) -> float:
    """
    Fast-lookup: returns the highest prediction_pct (0-100) of any known
    pothole cluster within the radius of the given coordinates.
    """
    if lat is None or lon is None:
        return 0.0

    clusters = get_predictive_risk()  # uses cache
    highest_prob = 0.0

    for c in clusters:
        if _haversine_km(lat, lon, c["latitude"], c["longitude"]) <= CLUSTER_RADIUS_KM:
            if c["prediction_pct"] > highest_prob:
                highest_prob = c["prediction_pct"]

    return highest_prob


# ===========================================================================
# Core computation
# ===========================================================================

def _compute_predictive_risk() -> list[dict]:
    """Full pipeline: fetch → cluster → score → classify → explain."""
    # ── Step 1: fetch pothole reports ──────────────────────────────────────
    reports = _fetch_pothole_reports()
    if not reports:
        logger.info("risk_predictor: no pothole reports found")
        return []

    logger.info(f"risk_predictor: processing {len(reports)} pothole reports")

    # ── Step 1b: fetch recent waterlogging events (last 30 days) ─────────────
    waterlogging_reports = _fetch_waterlogging_reports(days=30)
    if waterlogging_reports:
        logger.info(f"risk_predictor: found {len(waterlogging_reports)} recent waterlogging events")

    # ── Step 2: cluster by proximity ───────────────────────────────────────
    clusters = _cluster_reports(reports)
    logger.info(f"risk_predictor: formed {len(clusters)} clusters")

    # ── Steps 3‒5: score + classify + explain ──────────────────────────────
    now_utc = datetime.now(timezone.utc)

    raw_clusters = []
    for cluster_reports in clusters:
        raw = _compute_cluster_features(cluster_reports, now_utc, waterlogging_reports)
        raw_clusters.append(raw)

    # Normalise across all clusters before computing final score
    result = _normalise_and_score(raw_clusters)

    # Sort highest risk first
    result.sort(key=lambda x: x["risk_score"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Step 1 — Data fetching
# ---------------------------------------------------------------------------

def _fetch_pothole_reports() -> list:
    """
    Query DamageReport table for Pothole records that have valid coordinates.
    Returns plain list of model instances.
    """
    try:
        from .models import DamageReport
        from sqlalchemy import func
        rows = (
            DamageReport.query
            .filter(
                func.lower(DamageReport.detected_damage_type) == "pothole",
                DamageReport.latitude  != None,   # noqa: E711
                DamageReport.longitude != None,
            )
            .all()
        )
        return rows
    except Exception as exc:
        logger.error(f"risk_predictor: DB fetch error — {exc}")
        return []


def _fetch_waterlogging_reports(days: int = 30) -> list:
    """
    Query DamageReport table for Waterlogging records within the last N days.
    Used to apply a physics-based multiplier to nearby pothole clusters.
    """
    try:
        from .models import DamageReport
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            DamageReport.query
            .filter(
                func.lower(DamageReport.detected_damage_type) == "waterlogging",
                DamageReport.latitude  != None,   # noqa: E711
                DamageReport.longitude != None,
                DamageReport.created_at >= cutoff,
            )
            .all()
        )
        return rows
    except Exception as exc:
        logger.error(f"risk_predictor: waterlogging fetch error — {exc}")
        return []


# ---------------------------------------------------------------------------
# Step 2 — Clustering
# ---------------------------------------------------------------------------

def _cluster_reports(reports: list) -> list[list]:
    """
    Group reports into geographic clusters (≈1 km radius).

    Uses DBSCAN with Haversine metric when sklearn is available,
    otherwise falls back to a simple greedy grouping.

    Returns a list of lists, where each inner list contains
    DamageReport instances belonging to the same cluster.
    """
    if _HAS_SKLEARN:
        return _dbscan_cluster(reports)
    return _greedy_cluster(reports)


def _dbscan_cluster(reports: list) -> list[list]:
    """sklearn DBSCAN with Haversine metric."""
    coords_rad = np.radians(
        [(r.latitude, r.longitude) for r in reports]
    )

    db = DBSCAN(
        eps=CLUSTER_EPS_RAD,
        min_samples=CLUSTER_MIN_SAMPLES,
        algorithm="ball_tree",
        metric="haversine",
    ).fit(coords_rad)

    labels = db.labels_

    # Organise by label (noise points get label -1; treat each as its own cluster)
    buckets: dict[int, list] = {}
    noise_idx = max(labels) + 1  # start noise cluster IDs after named ones

    for idx, label in enumerate(labels):
        if label == -1:
            # Noise → own cluster
            buckets[noise_idx] = [reports[idx]]
            noise_idx += 1
        else:
            buckets.setdefault(label, []).append(reports[idx])

    return list(buckets.values())


def _greedy_cluster(reports: list) -> list[list]:
    """
    Fallback O(n²) greedy clustering when sklearn not available.
    Good enough for <500 reports; performance degrades linearly after that.
    """
    assigned = [False] * len(reports)
    clusters: list[list] = []

    for i, r in enumerate(reports):
        if assigned[i]:
            continue
        cluster = [r]
        assigned[i] = True
        for j in range(i + 1, len(reports)):
            if assigned[j]:
                continue
            if _haversine_km(r.latitude, r.longitude,
                             reports[j].latitude, reports[j].longitude) <= CLUSTER_RADIUS_KM:
                cluster.append(reports[j])
                assigned[j] = True
        clusters.append(cluster)

    return clusters


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Steps 3 & 4 — Severity scoring + feature engineering
# ---------------------------------------------------------------------------

def _compute_cluster_features(reports: list, now_utc: datetime, waterlogging_reports: list = None) -> dict:
    """
    Compute all raw features for a single cluster, including a
    Poisson-based recurrence probability — the real prediction score.

    Key insight:
      If a cluster has been generating potholes at rate λ per month,
      the probability of at least one NEW pothole appearing in the
      next 30 days is:

          P(recurrence) = 1 − e^(−λ)    [Poisson CDF]

      λ = total_reports / max(months_active, 1)

      Physics enhancement: if a waterlogging event has been detected
      within CLUSTER_RADIUS_KM in the last 30 days, λ is multiplied
      by 1.5x. Water saturates the road sub-base, dramatically
      accelerating pothole formation (hydraulic pumping effect).
    """
    # ── Centroid ────────────────────────────────────────────────────────────
    valid_lats  = [r.latitude  for r in reports if r.latitude  is not None]
    valid_lons  = [r.longitude for r in reports if r.longitude is not None]
    centroid_lat = sum(valid_lats) / len(valid_lats)   if valid_lats else 0.0
    centroid_lon = sum(valid_lons) / len(valid_lons)   if valid_lons else 0.0

    # ── Timezone helper ─────────────────────────────────────────────────────
    def _ts(dt):
        """Make naive datetimes timezone-aware (UTC) for comparison."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    # ── Temporal boundaries ──────────────────────────────────────────────────
    cutoff_30 = now_utc - timedelta(days=30)
    cutoff_60 = now_utc - timedelta(days=60)
    cutoff_90 = now_utc - timedelta(days=90)

    ts_list = [_ts(r.created_at) for r in reports if _ts(r.created_at) is not None]
    earliest = min(ts_list) if ts_list else now_utc
    latest   = max(ts_list) if ts_list else now_utc

    # How many months has this cluster been active?
    days_span    = max((now_utc - earliest).days, 1)
    months_active = days_span / 30.0

    # Days since the most recent report in this cluster
    days_since_last = (now_utc - latest).days

    # ── Severity weights ──────────────────────────────────────────────────────
    weights = []
    for r in reports:
        sev = (r.severity or "low").lower()
        weights.append(SEVERITY_WEIGHTS.get(sev, 1))

    total_reports  = len(reports)
    severity_score = sum(weights)
    avg_severity   = severity_score / total_reports if total_reports else 0.0

    # ── Temporal window counts ───────────────────────────────────────────────
    last_30 = sum(1 for t in ts_list if t >= cutoff_30)
    prev_30 = sum(1 for t in ts_list if cutoff_60 <= t < cutoff_30)
    last_90 = sum(1 for t in ts_list if t >= cutoff_90)

    # Unresolved reports (still open) — indicates ongoing problem
    unresolved = sum(
        1 for r in reports
        if (r.status or "").lower() not in ("resolved", "completed", "fixed")
    )
    unresolved_ratio = unresolved / total_reports if total_reports else 0.0

    # ── 🔮 POISSON RECURRENCE PROBABILITY ───────────────────────────────────
    # λ = average potholes per month for this cluster
    monthly_rate = total_reports / months_active

    # Adjust λ for recency: if NO reports in last 90 days, the road may
    # have been repaired — halve the rate as a staleness penalty.
    if days_since_last > 90:
        monthly_rate *= 0.3   # major staleness discount
    elif days_since_last > 30:
        monthly_rate *= 0.6   # moderate staleness discount
    # else: road is actively generating reports → use full rate

    # Boost rate if the trend is worsening (more potholes recently)
    if last_30 > prev_30 and prev_30 > 0:
        growth_boost = min(last_30 / prev_30, 2.0)   # cap at 2× boost
        monthly_rate *= growth_boost

    # Boost for unresolved reports (problem still active)
    monthly_rate *= (1 + 0.5 * unresolved_ratio)

    # Severity boosts the rate (high/critical roads deteriorate faster)
    severity_multiplier = 1.0 + 0.25 * (avg_severity - 1)  # 1.0 at low, 1.75 at critical
    monthly_rate *= max(severity_multiplier, 1.0)

    # ── 💧 WATERLOGGING MULTIPLIER (Physics-Based) ─────────────────────────
    # Water saturates the road's sub-base → hydraulic pumping destroys
    # asphalt from inside out. If waterlogging was detected within 1 km
    # of this cluster in the last 30 days, the decay rate is 1.5× higher.
    WATERLOGGING_MULTIPLIER = 1.5
    has_recent_waterlogging = False

    if waterlogging_reports:
        for wlog in waterlogging_reports:
            if wlog.latitude is None or wlog.longitude is None:
                continue
            dist_km = _haversine_km(centroid_lat, centroid_lon, wlog.latitude, wlog.longitude)
            if dist_km <= CLUSTER_RADIUS_KM:
                has_recent_waterlogging = True
                break

    if has_recent_waterlogging:
        monthly_rate *= WATERLOGGING_MULTIPLIER
        logger.debug(
            f"risk_predictor: waterlogging multiplier applied to cluster "
            f"({centroid_lat:.4f}, {centroid_lon:.4f}) — λ ×{WATERLOGGING_MULTIPLIER}"
        )
    
    # ── Seasonal Weighting (Mumbai Context) ─────────────────────────────────
    MONTHLY_WEIGHTS = {
        1: 0.6,   # January   — dry, low risk
        2: 0.6,   # February
        3: 0.7,   # March
        4: 0.8,   # April
        5: 1.0,   # May       — pre-monsoon
        6: 1.8,   # June      — monsoon starts
        7: 2.2,   # July      — peak monsoon
        8: 2.2,   # August
        9: 1.6,   # September — monsoon receding
        10: 1.0,  # October
        11: 0.7,  # November
        12: 0.6,  # December
    }
    current_month = now_utc.month
    monthly_rate *= MONTHLY_WEIGHTS.get(current_month, 1.0)

    # P(at least 1 new pothole in next 30 days) = 1 − e^(−λ)
    import math as _math
    recurrence_probability = 1.0 - _math.exp(-monthly_rate)
    recurrence_probability = min(max(recurrence_probability, 0.0), 0.99)  # cap at 99%

    # ── Legacy feature engineering (used in weighted risk_score) ────────────
    frequency    = total_reports
    recency      = last_30 / total_reports if total_reports > 0 else 0.0
    growth_trend = last_30 - prev_30

    return {
        # Cluster identity
        "latitude":        centroid_lat,
        "longitude":       centroid_lon,
        # Counts
        "total_reports":   total_reports,
        "severity_score":  severity_score,
        "avg_severity":    avg_severity,
        "reports_last_30": last_30,
        "reports_last_90": last_90,
        "unresolved":      unresolved,
        "unresolved_ratio": unresolved_ratio,
        "days_since_last": days_since_last,
        "months_active":   round(months_active, 1),
        # 🔮 Core prediction metric
        "monthly_rate":          round(monthly_rate, 3),
        "recurrence_probability": recurrence_probability,   # 0.0 – 0.99
        # Features for weighted risk_score
        "frequency":       frequency,
        "recency":         recency,
        "growth_trend":    growth_trend,
        "severity_index":  avg_severity,
    }


# ---------------------------------------------------------------------------
# Step 5 — Risk scoring (normalise + weighted sum + classify)
# ---------------------------------------------------------------------------

def _normalise_and_score(raw_clusters: list[dict]) -> list[dict]:
    """
    Two-tier scoring:

    1. recurrence_probability  (Poisson model — the TRUE prediction)
       "X% chance this road gets a new pothole in the next 30 days"

    2. risk_score  (weighted composite — used for ranking/colouring)
       Combines frequency + severity + recency + trend, normalised
       across the cluster population so relative hotspots stand out.

    risk_level is driven by recurrence_probability, not risk_score,
    so the label reflects the forward-looking prediction.
    """
    if not raw_clusters:
        return []

    def _norm_field(key: str) -> list[float]:
        """Min-max normalise a field across all clusters."""
        vals = [c[key] for c in raw_clusters]
        mn, mx = min(vals), max(vals)
        span = mx - mn
        if span == 0:
            return [0.5] * len(vals)
        return [(v - mn) / span for v in vals]

    n_freq  = _norm_field("frequency")
    n_sev   = _norm_field("severity_index")
    n_rec   = _norm_field("recency")
    n_trend = _norm_field("growth_trend")

    results = []
    for i, raw in enumerate(raw_clusters):
        # ── Composite risk_score (relative ranking) ──────────────────────
        risk_score = (
            0.4 * n_freq[i]
            + 0.3 * n_sev[i]
            + 0.2 * n_rec[i]
            + 0.1 * n_trend[i]
        )
        risk_score = round(min(max(risk_score, 0.0), 1.0), 4)

        # ── Poisson recurrence probability (the core prediction) ─────────
        p = raw["recurrence_probability"]
        prediction_pct = round(p * 100, 1)   # e.g. 74.3

        # ── Classification driven by recurrence probability ───────────────
        # > 70% chance → high    (likely to recur next month)
        # 40–70%       → medium
        # < 40%        → low
        if p > 0.70:
            risk_level = "high"
        elif p >= 0.40:
            risk_level = "medium"
        else:
            risk_level = "low"

        reason = _build_reason(raw, risk_level, prediction_pct)

        results.append({
            "latitude":          raw["latitude"],
            "longitude":         raw["longitude"],
            "total_reports":     raw["total_reports"],
            "severity_score":    raw["severity_score"],
            "avg_severity":      round(raw["avg_severity"], 2),
            "reports_last_30":   raw["reports_last_30"],
            "reports_last_90":   raw["reports_last_90"],
            "unresolved":        raw["unresolved"],
            "days_since_last":   raw["days_since_last"],
            "months_active":     raw["months_active"],
            "monthly_rate":      raw["monthly_rate"],
            "growth_trend":      raw["growth_trend"],
            # 🔮 Primary prediction output
            "prediction_pct":    prediction_pct,   # 0–100
            # Supporting score (relative ranking within this dataset)
            "risk_score":        risk_score,
            "risk_level":        risk_level,
            "reason":            reason,
        })

    return results


def _build_reason(raw: dict, risk_level: str, prediction_pct: float) -> str:
    """
    Human-readable explanation leading with the Poisson prediction,
    then supporting evidence.
    """
    parts = []

    # Lead with the core prediction
    parts.append(
        f"{prediction_pct:.0f}% chance of a new pothole here in the next 30 days"
    )

    # Monthly emission rate
    rate = raw.get("monthly_rate", 0)
    if rate >= 1:
        parts.append(f"generating ~{rate:.1f} potholes/month historically")

    # Staleness context
    days_last = raw.get("days_since_last", 0)
    if days_last > 90:
        parts.append(f"no new reports in {days_last} days (may have been repaired)")
    elif days_last <= 7:
        parts.append(f"last report just {days_last} day(s) ago — actively deteriorating")

    # Trend
    if raw["growth_trend"] > 0:
        parts.append(f"worsening trend (+{raw['growth_trend']} vs prior 30 days)")
    elif raw["growth_trend"] < 0:
        parts.append(f"improving trend ({raw['growth_trend']} vs prior 30 days)")

    # Severity
    avg_sev = raw["avg_severity"]
    if avg_sev >= 3.5:
        parts.append("predomin. critical/high severity")
    elif avg_sev >= 2.5:
        parts.append("mixed medium–high severity")

    # Unresolved
    unresolved = raw.get("unresolved", 0)
    if unresolved > 0:
        parts.append(f"{unresolved} report(s) still unresolved")

    # Waterlogging physics boost
    if raw.get("has_recent_waterlogging"):
        parts.append("recent waterlogging detected nearby (×1.5 decay rate — sub-base saturation)")

    prefix_map = {
        "high":   "🔴 High recurrence risk — ",
        "medium": "🟡 Moderate recurrence risk — ",
        "low":    "🟢 Low recurrence risk — ",
    }
    prefix = prefix_map.get(risk_level, "")
    return prefix + "; ".join(parts) + "."


# ===========================================================================
# Legacy helpers (kept for backward compatibility with existing road-risk API)
# ===========================================================================

def calculate_road_risk(road):
    """
    Calculates a risk score (0-100) for a RoadRisk model instance.
    Legacy function kept for the /api/official/road-risks endpoint.
    """
    score = 0

    # Historical potholes (max 40 pts)
    score += min(road.potholes_last_year * 10, 30)
    score += min(road.potholes_2_years_ago * 5, 10)

    # Environmental factors (max 35 pts)
    if road.has_waterlogging_history:
        score += 20
    if not road.has_drainage:
        score += 15

    # ScienceDirect predictors (max 45 pts)
    score += min(road.forecast_precipitation * 0.3, 25)
    temp_diff = abs(road.forecast_temperature - 30)
    score += min(temp_diff * 0.5, 10)

    traffic_weights = {"low": 0, "medium": 5, "high": 10}
    score += traffic_weights.get(road.traffic_volume.lower(), 5)

    final_score = min(max(score, 0), 100)

    if final_score >= 80:
        level = "critical"
    elif final_score >= 60:
        level = "high"
    elif final_score >= 40:
        level = "medium"
    else:
        level = "low"

    return final_score, level


def update_all_road_risks():
    """Legacy: update risk scores on all RoadRisk DB rows."""
    try:
        from .models import RoadRisk
        from . import db
        roads = RoadRisk.query.all()
        for road in roads:
            score, level = calculate_road_risk(road)
            road.risk_score = score
            road.risk_level = level
        db.session.commit()
        logger.info(f"Updated legacy risk scores for {len(roads)} roads.")
        return True
    except Exception as exc:
        try:
            from . import db
            db.session.rollback()
        except Exception:
            pass
        logger.error(f"Error updating legacy road risks: {exc}")
        return False


def get_risk_summary():
    """Legacy: summary list from RoadRisk table for /api/official/road-risks."""
    try:
        from .models import RoadRisk
        roads = RoadRisk.query.order_by(RoadRisk.risk_score.desc()).all()
        return [
            {
                "id":          r.id,
                "road_name":   r.road_name,
                "latitude":    r.latitude,
                "longitude":   r.longitude,
                "risk_score":  r.risk_score,
                "risk_level":  r.risk_level,
                "last_updated": r.last_updated.isoformat() if r.last_updated else None,
                "factors": {
                    "historical_potholes": r.potholes_last_year + r.potholes_2_years_ago,
                    "waterlogging":        r.has_waterlogging_history,
                    "drainage":            r.has_drainage,
                    "traffic":             r.traffic_volume,
                    "forecast_rain":       r.forecast_precipitation,
                },
            }
            for r in roads
        ]
    except Exception as exc:
        logger.error(f"get_risk_summary error: {exc}")
        return []
