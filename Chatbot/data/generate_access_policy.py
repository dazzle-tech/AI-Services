import json
import psycopg2
from collections import defaultdict

DB = {
    "host": "localhost",
    "port": 5432,
    "dbname": "DBLocal",
    "user": "postgres",
    "password": "123456"  
}

OUTPUT_FILE = "access-policy.json"
SCHEMA = "public"

conn = psycopg2.connect(**DB)
cur = conn.cursor()

cur.execute("""
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = %s
ORDER BY table_name, ordinal_position;
""", (SCHEMA,))

tables = defaultdict(list)
for table, col in cur.fetchall():
    tables[table].append(col)

policy = {
    "allowed_operations": ["SELECT"],
    "allowed_schema": {
        t: {"columns": cols, "row_filter": None}
        for t, cols in tables.items()
    },
    "relationships": {},
    "derived_fields": {},
    "restrictions": {
        "allow_aggregation": True,
        "allow_nested_queries": True
    }
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(policy, f, indent=2, ensure_ascii=False)

print(f"✅ Wrote {OUTPUT_FILE} with {len(tables)} tables.")