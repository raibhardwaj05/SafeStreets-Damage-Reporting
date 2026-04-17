import sqlite3
import json
conn=sqlite3.connect('infra_damage.db')
conn.row_factory=sqlite3.Row
cur=conn.cursor()
cur.execute("SELECT accountability_dept, accountability_evidence FROM damage_reports WHERE id='2661b11f-eee0-4c4a-aee6-7d9638a79dab'")
rows = [dict(r) for r in cur.fetchall()]
with open('db_out_damage.json', 'w') as f:
    json.dump(rows, f, indent=2)
print("Done")
