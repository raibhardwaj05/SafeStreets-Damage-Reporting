from .models import db, AuditLog
from flask import request

def log_audit(user_id, action):
    try:
        log = AuditLog(user_id=user_id, action=action, ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Audit log failed: {e}")
