from flask import Blueprint, send_from_directory, current_app, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from .models import DamageReport
import os

files_bp = Blueprint('files', __name__, url_prefix='/api/files')

@files_bp.route('/<file_type>/<filename>')
@jwt_required()
def get_file(file_type, filename):
    claims = get_jwt()
    role = claims.get('role')
    user_id = get_jwt_identity()

    # ---------------------------
    # Validate file type
    # ---------------------------
    if file_type not in ['images', 'videos', 'docs']:
        return jsonify({"msg": "Invalid file type"}), 400

    upload_root = current_app.config['UPLOAD_FOLDER']
    directory = os.path.join(upload_root, file_type)

    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({"msg": "File not found"}), 404

    # ---------------------------
    # OFFICIAL ACCESS (FULL)
    # ---------------------------
    if role == 'official':
        return send_from_directory(directory, filename)

    # ---------------------------
    # CITIZEN ACCESS (OWN FILES ONLY)
    # ---------------------------
    if role == 'citizen':
        report = DamageReport.query.filter_by(image_path=filename).first()

        if report and report.citizen_id == user_id:
            return send_from_directory(directory, filename)

        return jsonify({"msg": "Access denied"}), 403

    return jsonify({"msg": "Unauthorized"}), 403
