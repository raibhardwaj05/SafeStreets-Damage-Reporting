from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config
import os

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app(config_class=Config):
    # Serve frontend from project root
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    app = Flask(
        __name__,
        static_folder=root_path,
        static_url_path=''
    )

    app.config.from_object(config_class)

    # ------------------------
    # Extensions
    # ------------------------
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    jwt.init_app(app)

    # ------------------------
    # CORS
    # ------------------------
    CORS(
        app,
        supports_credentials=True,
        resources={
            r"/api/*": {
                "origins": "*",
                "allow_headers": ["Authorization", "Content-Type"]
            }
        }
    )

    # ------------------------
    # JWT ERROR HANDLERS
    # ------------------------
    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"msg": "Missing authorization token"}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"msg": "Invalid token"}), 401

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({"msg": "Token expired"}), 401

    # ------------------------
    # BLUEPRINTS
    # ------------------------
    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.device_auth import auth_bp as device_auth_bp
    app.register_blueprint(device_auth_bp)

    from app.api_citizen import citizen_bp
    app.register_blueprint(citizen_bp, url_prefix='/api/citizen')

    from app.api_official import official_bp
    app.register_blueprint(official_bp, url_prefix='/api/official')

    # ✅ FILE SERVING (CORRECT)
    from app.api_files import files_bp
    app.register_blueprint(files_bp)

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.dashcam import dashcam_bp
    app.register_blueprint(dashcam_bp)



    return app
