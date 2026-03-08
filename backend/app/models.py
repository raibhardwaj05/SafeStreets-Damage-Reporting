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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =====================================================
# DAMAGE REPORT MODEL (DAMAGE DB)
# =====================================================
class DamageReport(db.Model):
    __tablename__ = 'damage_reports'
    __bind_key__ = 'infra_damage_db'

    # Primary Key
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Citizen reference (cross-DB, no FK)
    citizen_id = db.Column(db.String(36), nullable=False)

    # Image evidence (CRITICAL for verification page)
    image_path = db.Column(db.String(255), nullable=False)

    # Location details
    location = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # ML inference output
    detected_damage_type = db.Column(db.String(50))
    confidence_score = db.Column(db.Float)

    # Status lifecycle
    status = db.Column(
        db.String(20),
        default='submitted'
    )  # submitted → verified → assigned → resolved

    severity = db.Column(
        db.String(20),
        default='pending'
    )  # low | medium | high | critical

    # Verification
    verified_by = db.Column(db.String(36), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
