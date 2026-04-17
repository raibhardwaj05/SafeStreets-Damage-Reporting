"""
One-time migration: add waterlogging_pothole_risk column to damage_reports.
Run once with: python migration_add_waterlogging_risk.py
"""
import sqlite3
import os
import glob

# Try to find the SQLite DB automatically
search_paths = [
    os.path.join("instance", "infra_damage.db"),
    "infra_damage.db",
]
# Also check parent directories
search_paths += glob.glob("../**/*infra_damage*.db", recursive=True)
search_paths += glob.glob("./**/*infra_damage*.db", recursive=True)

db_path = None
for p in search_paths:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    print("ERROR: Could not locate infra_damage.db. Please provide the path manually.")
    exit(1)

print(f"Found database at: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("PRAGMA table_info(damage_reports)")
cols = [row[1] for row in cur.fetchall()]
print(f"Existing columns: {cols}")

if "waterlogging_pothole_risk" not in cols:
    cur.execute("ALTER TABLE damage_reports ADD COLUMN waterlogging_pothole_risk REAL")
    conn.commit()
    print("SUCCESS: Column 'waterlogging_pothole_risk' added to damage_reports.")
else:
    print("Column already exists — nothing to do.")

conn.close()
