from . import db
from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

# =====================================================
# USER MODEL (AUTH DB)
# =====================================================
class User(db.Model):
    __tablename__ = 'users'
    __bind_key__ = 'infra_auth_db'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # citizen | official
    department = db.Column(db.String(50), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    # -------------------------
    # Password helpers
    # -------------------------
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    

# =====================================================
# DEVICE MODEL (DASHCAM DEVICES)
# =====================================================
class Device(db.Model):
    __tablename__ = 'devices'
    __bind_key__ = 'infra_auth_db'   # same DB as users

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    vehicle_no = db.Column(db.String(20), nullable=False)

    device_id = db.Column(db.String(50), unique=True, nullable=False, index=True)

    email = db.Column(db.String(120), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )


# =====================================================
# DAMAGE REPORT MODEL (DAMAGE DB)
# =====================================================
class DamageReport(db.Model):
    __tablename__ = 'damage_reports'
    __bind_key__ = 'infra_damage_db'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    citizen_id = db.Column(db.String(36), nullable=True)

    device_id = db.Column(db.String(50), nullable=True)

    report_source = db.Column(db.String(20), nullable=False, default="citizen") 
    # citizen | dashcam

    user_email = db.Column(db.String(120), nullable=True)

    image_path = db.Column(db.String(255), nullable=False)

    location = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    detected_damage_type = db.Column(db.String(50))
    confidence_score = db.Column(db.Float)

    status = db.Column(
        db.String(20),
        default='submitted'
    )

    severity = db.Column(
        db.String(20),
        default='pending'
    )

    verified_by = db.Column(db.String(36), nullable=True)

    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_description = db.Column(db.Text, nullable=True)
    after_image_path = db.Column(db.String(255), nullable=True)
    after_image_path_last = db.Column(db.String(255), nullable=True)

    # -----------------------------------------------
    # Agent 3 Accountability Cache
    # Populated by run_accountability_sweep() in the
    # cron scraper after every new tender PDF ingestion.
    # -----------------------------------------------
    accountability_dept       = db.Column(db.Text, nullable=True)
    accountability_statement  = db.Column(db.Text, nullable=True)
    accountability_evidence   = db.Column(db.Text, nullable=True)
    accountability_confidence = db.Column(db.String(10), nullable=True)  # HIGH|MEDIUM|LOW

    # -----------------------------------------------
    # Waterlogging Risk (Physics-Based Prediction)
    # Populated at report-save time when waterlogging
    # is detected near a known pothole cluster.
    # Stores the Poisson recurrence probability (0–100)
    # that this waterlogged road will develop a pothole.
    # -----------------------------------------------
    waterlogging_pothole_risk = db.Column(db.Float, nullable=True)  # 0.0 – 100.0

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )



# =====================================================
# WORK REPORT MODEL (WORK DB)
# =====================================================
class WorkReport(db.Model):
    __tablename__ = 'work_reports'
    __bind_key__ = 'infra_work_db'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    notice_id = db.Column(db.String(50), unique=True)

    department = db.Column(db.String(50), nullable=False)
    work_type = db.Column(db.String(100))
    location = db.Column(db.String(255))

    # Execution details
    executing_agency = db.Column(db.String(100))
    contractor_contact = db.Column(db.String(50))

    status = db.Column(db.String(20), default='pending')

    pdf_filename = db.Column(db.String(255)) 

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )


# =====================================================
# AUDIT LOG MODEL (LOG DB)
# =====================================================
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __bind_key__ = 'infra_logs_db'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))


# =====================================================
# WORK ORDER MODEL (TENDER ACCOUNTABILITY PIPELINE)
# =====================================================
class WorkOrder(db.Model):
    """
    Geocoded work orders extracted from Maharashtra government tender PDFs.
    Created by the Pothole Accountability Agent pipeline (Agents 1+2).
    Used by Agent 3 for pothole–department matching.
    """
    __tablename__ = 'work_orders'
    __bind_key__ = 'infra_work_db'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Tender identity
    tender_id   = db.Column(db.String(100), nullable=False, index=True)
    work_index  = db.Column(db.Integer, nullable=False)

    # Tender metadata
    organization   = db.Column(db.String(255))
    district       = db.Column(db.String(100))
    city_or_taluka = db.Column(db.String(100))

    # Work details
    work_type           = db.Column(db.String(50), index=True)
    department          = db.Column(db.String(255))
    description_english = db.Column(db.Text)
    location_summary    = db.Column(db.Text)
    location_type       = db.Column(db.String(50))
    noc_reference       = db.Column(db.String(100))

    # Dates & financials
    work_start_date = db.Column(db.Date, index=True)
    work_end_date   = db.Column(db.Date)
    duration_days   = db.Column(db.Integer)
    amount_inr      = db.Column(db.BigInteger)

    # Geocoding output
    lat           = db.Column(db.Float)
    lng           = db.Column(db.Float)
    geo_confidence = db.Column(db.Float)
    geo_status    = db.Column(db.String(50))   # success | fallback_only | route_geocoded
    geocode_query = db.Column(db.Text)
    route_points  = db.Column(db.Text)          # JSON string of [{landmark, lat, lng, confidence}]

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Unique constraint — prevent duplicate extraction runs
    __table_args__ = (
        db.UniqueConstraint('tender_id', 'work_index', name='uq_tender_work'),
    )


# =====================================================
# ROAD RISK MODEL (LAYER 2: RISK PREDICTOR)
# =====================================================
class RoadRisk(db.Model):
    """
    Answers: "Which roads will need repair before monsoon?"
    Looks at 2 years of historical data, waterlogging, drainage, 
    and forecasted precipitation, temperature, and traffic volume.
    """
    __tablename__ = 'road_risks'
    __bind_key__ = 'infra_damage_db'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    road_name = db.Column(db.String(255), index=True)
    latitude  = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # -----------------------------------------------
    # Historical Data (2 Years)
    # -----------------------------------------------
    potholes_last_year   = db.Column(db.Integer, default=0)
    potholes_2_years_ago = db.Column(db.Integer, default=0)
    
    # -----------------------------------------------
    # Features (ScienceDirect Predictors)
    # -----------------------------------------------
    has_waterlogging_history = db.Column(db.Boolean, default=False)
    has_drainage             = db.Column(db.Boolean, default=True)
    traffic_volume           = db.Column(db.String(20), default="medium") # low | medium | high
    
    # -----------------------------------------------
    # Forecast Data (Dynamic)
    # -----------------------------------------------
    forecast_precipitation = db.Column(db.Float, default=0.0) # mm
    forecast_temperature   = db.Column(db.Float, default=30.0) # Celsius
    
    # -----------------------------------------------
    # Output Predictions
    # -----------------------------------------------
    risk_score = db.Column(db.Float, default=0.0)
    risk_level = db.Column(db.String(20), default="low") # low | medium | high | critical
    
    last_updated = db.Column(
        db.DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
