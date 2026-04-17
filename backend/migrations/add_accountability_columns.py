"""
add_accountability_columns.py
One-off migration: adds accountability cache columns to damage_reports.
Run once: python backend/migrations/add_accountability_columns.py
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from sqlalchemy import text

def migrate():
    app = create_app()
    with app.app_context():
        engine = db.get_engine(bind='infra_damage_db')
        with engine.connect() as conn:
            # Add columns only if they don't exist (SQLite-safe approach)
            try:
                conn.execute(text(
                    "ALTER TABLE damage_reports ADD COLUMN accountability_dept TEXT"
                ))
                print("✓ Added column: accountability_dept")
            except Exception:
                print("  (accountability_dept already exists)")

            try:
                conn.execute(text(
                    "ALTER TABLE damage_reports ADD COLUMN accountability_statement TEXT"
                ))
                print("✓ Added column: accountability_statement")
            except Exception:
                print("  (accountability_statement already exists)")

            try:
                conn.execute(text(
                    "ALTER TABLE damage_reports ADD COLUMN accountability_evidence TEXT"
                ))
                print("✓ Added column: accountability_evidence")
            except Exception:
                print("  (accountability_evidence already exists)")

            try:
                conn.execute(text(
                    "ALTER TABLE damage_reports ADD COLUMN accountability_confidence TEXT"
                ))
                print("✓ Added column: accountability_confidence")
            except Exception:
                print("  (accountability_confidence already exists)")

            conn.commit()

    print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
