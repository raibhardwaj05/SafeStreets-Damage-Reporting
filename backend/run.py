from app import create_app, db
from app.models import User, DamageReport, WorkReport

app = create_app()

# Ensure tables exist when server starts
with app.app_context():
    try:
        print("Initializing database...")
        db.create_all()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == '__main__':
    print("Starting Flask server on port 5000...")
    app.run(debug=True, port=5000)