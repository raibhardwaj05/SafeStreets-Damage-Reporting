import sqlite3
import json

conn = sqlite3.connect('infra_work.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute('SELECT tender_id, work_type, lat, lng FROM work_orders')
rows = [dict(row) for row in cur.fetchall()]

with open('db_out_orders.json', 'w') as f:
    json.dump(rows, f, indent=2)

print("Done")
