import os

class Config:
    # =====================================================
    # BASE
    # =====================================================
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'dev-secret-key-change-in-production'
    )

    # =====================================================
    # DATABASE (MULTI-BIND)
    # =====================================================
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
        BASE_DIR, 'infra_main.db'
    )

    SQLALCHEMY_BINDS = {
        'infra_auth_db':   'sqlite:///' + os.path.join(BASE_DIR, 'infra_auth.db'),
        'infra_damage_db': 'sqlite:///' + os.path.join(BASE_DIR, 'infra_damage.db'),
        'infra_work_db':   'sqlite:///' + os.path.join(BASE_DIR, 'infra_work.db'),
        'infra_logs_db':   'sqlite:///' + os.path.join(BASE_DIR, 'infra_logs.db')
    }

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =====================================================
    # JWT
    # =====================================================
    JWT_SECRET_KEY = os.environ.get(
        'JWT_SECRET_KEY',
        'jwt-secret-key-change-in-production'
    )

    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60  # 1 hour

    # =====================================================
    # FILE UPLOADS (CRITICAL FOR VERIFICATION PAGE)
    # =====================================================
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # Create upload directories automatically (DEV SAFE)
    try:
        os.makedirs(os.path.join(UPLOAD_FOLDER, 'images'), exist_ok=True)
        os.makedirs(os.path.join(UPLOAD_FOLDER, 'videos'), exist_ok=True)
        os.makedirs(os.path.join(UPLOAD_FOLDER, 'docs'), exist_ok=True)
        os.makedirs(os.path.join(UPLOAD_FOLDER, 'work_notices'), exist_ok=True)
    except Exception as e:
        print(f"Warning: Failed to create upload directories: {e}")

