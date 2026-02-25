# init_mock_db.py
import sqlite3
import json
import os
from pathlib import Path

# Get the path to access_control.json
script_dir = Path(__file__).parent
project_root = script_dir.parent
access_control_path = project_root / "data" / "access_control.json"
db_path = project_root / "data" / "hospital.db"

# Load access control configuration
with open(access_control_path, 'r', encoding='utf-8') as f:
    access_control = json.load(f)

# Get the schema from the first user (assuming all users have same schema structure)
# Try to get from u101, or get first user key
user_key = "u101" if "u101" in access_control else list(access_control.keys())[0]
allowed_schema = access_control[user_key]["allowed_schema"]

# Connect to database
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Helper function to determine SQLite data type from column name
def get_sqlite_type(column_name):
    """Determine appropriate SQLite data type based on column name."""
    column_lower = column_name.lower()
    
    # Primary keys and IDs
    if column_name in ['id', 'key'] or column_name.endswith('_id') or column_name.endswith('_key'):
        return 'TEXT'
    
    # Boolean-like columns
    if any(x in column_lower for x in ['is_', 'has_', 'can_', 'verified', 'activated', 'valid']):
        return 'INTEGER'  # SQLite uses INTEGER for booleans (0/1)
    
    # Date/time columns
    if any(x in column_lower for x in ['_date', '_at', 'dob', 'created_date', 'updated_date', 'expires', 'valid_until']):
        return 'TEXT'  # Store as ISO format strings
    
    # Numeric columns
    if any(x in column_lower for x in ['_count', '_number', 'quantity', 'amount', 'price', 'cost', 'dose', 'age', 'score', 'rate', 'duration', 'interval', 'distance', 'height', 'weight', 'bmi', 'volume', 'capacity']):
        return 'REAL'
    
    # Integer-like columns
    if any(x in column_lower for x in ['_id', '_key', 'order', 'priority', 'status', 'level', 'type']):
        return 'TEXT'  # Many are foreign keys stored as TEXT
    
    # Default to TEXT for everything else
    return 'TEXT'

# Generate DROP TABLE statements for all tables
print("Dropping existing tables...")
drop_statements = []
for table_name in allowed_schema.keys():
    drop_statements.append(f"DROP TABLE IF EXISTS {table_name};")

if drop_statements:
    cur.executescript("\n".join(drop_statements))

# Generate CREATE TABLE statements
print(f"Creating {len(allowed_schema)} tables...")
create_statements = []

for table_name, table_info in allowed_schema.items():
    columns = table_info.get("columns", [])
    if not columns:
        continue
    
    # Build column definitions
    column_defs = []
    for col in columns:
        col_type = get_sqlite_type(col)
        
        # Make id/key columns primary key if they're the first column
        if col in ['id', 'key'] and columns.index(col) == 0:
            if col_type == 'TEXT':
                column_defs.append(f"{col} TEXT PRIMARY KEY")
            else:
                column_defs.append(f"{col} INTEGER PRIMARY KEY AUTOINCREMENT")
        else:
            column_defs.append(f"{col} {col_type}")
    
    # Create table statement
    create_sql = f"CREATE TABLE {table_name} (\n    {',\n    '.join(column_defs)}\n);"
    create_statements.append(create_sql)

# Execute all CREATE TABLE statements
for stmt in create_statements:
    try:
        cur.execute(stmt)
    except sqlite3.Error as e:
        print(f"Warning: Error creating table: {e}")
        print(f"Statement: {stmt[:200]}...")

# Insert some sample data for key tables
print("Inserting sample data...")

# Insert sample patients if ap_patient table exists
if "ap_patient" in allowed_schema:
    try:
        # Update pat001 with complete patient information
        cur.execute("""
            INSERT OR REPLACE INTO ap_patient (
                key, patient_mrn, first_name, last_name, full_name, dob, gender_lkey,
                phone_number, mobile_number, email,
                emergency_contact_name, emergency_contact_phone,
                blood_group_lkey, is_valid
            )
            VALUES 
            ('pat001', 'MRN001', 'John', 'Doe', 'John Doe', '1985-04-12', 'male',
             '555-0101', '555-0102', 'john.doe@example.com',
             'Jane Doe', '555-0103',
             'O+', 1),
            ('pat002', 'MRN002', 'Jane', 'Smith', 'Jane Smith', '1990-07-25', 'female',
             NULL, NULL, NULL,
             NULL, NULL,
             NULL, 1),
            ('pat003', 'MRN003', 'Carlos', 'Nunez', 'Carlos Nunez', '1978-11-03', 'male',
             NULL, NULL, NULL,
             NULL, NULL,
             NULL, 1),
            ('pat004', 'MRN004', 'Emily', 'Johnson', 'Emily Johnson', '2002-02-14', 'female',
             NULL, NULL, NULL,
             NULL, NULL,
             NULL, 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert sample patients: {e}")

# Insert sample encounters if ap_encounter table exists
if "ap_encounter" in allowed_schema and "ap_patient" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_encounter (key, patient_key, encounter_status_lkey, encounter_type_lkey, actual_start_date, discharge_at, is_valid)
            VALUES 
            ('enc001', 'pat001', 'active', 'outpatient', '2025-01-10', NULL, 1),
            ('enc002', 'pat002', 'active', 'inpatient', '2025-01-09', NULL, 1),
            ('enc003', 'pat003', 'discharged', 'outpatient', '2025-01-05', '2025-01-08', 1),
            ('enc004', 'pat004', 'active', 'emergency', '2025-01-11', NULL, 1),
            ('enc005', 'pat001', 'active', 'inpatient', '2025-01-10', NULL, 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert sample encounters: {e}")

# Insert sample active ingredients if table exists
if "ap_active_ingredient" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_active_ingredient (key, code, name, is_valid)
            VALUES 
            ('ai001', 'AI001', 'Paracetamol', 1),
            ('ai002', 'AI002', 'Ibuprofen', 1),
            ('ai003', 'AI003', 'Amoxicillin', 1),
            ('ai004', 'AI004', 'Aspirin', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert sample active ingredients: {e}")

# Insert sample facilities if table exists
if "ap_facility" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_facility (key, facility_id, facility_name, is_valid)
            VALUES 
            ('fac001', 'FAC001', 'Main Hospital', 1),
            ('fac002', 'FAC002', 'Emergency Center', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert sample facilities: {e}")

# Add comprehensive patient details for pat001 (John Doe)
print("Adding comprehensive patient details for pat001...")

# Add patient allergies if table exists
if "ap_patient_allergies" in allowed_schema and "ap_allergens" in allowed_schema:
    try:
        # First, insert some allergens
        cur.execute("""
            INSERT OR IGNORE INTO ap_allergens (key, allergen_code, allergen_name, allergen_type_lkey, is_valid)
            VALUES 
            ('alg001', 'ALG001', 'Penicillin', 'drug', 1),
            ('alg002', 'ALG002', 'Peanuts', 'food', 1),
            ('alg003', 'ALG003', 'Latex', 'other', 1)
        """)
        # Then link patient to allergens (example: no allergies for now, but structure is ready)
        # cur.execute("""
        #     INSERT OR IGNORE INTO ap_patient_allergies (key, patient_key, allergy_key, allergen_type_lkey, severity_lkey, is_valid)
        #     VALUES 
        #     ('paa001', 'pat001', 'alg001', 'drug', 'moderate', 1)
        # """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient allergies: {e}")

# Add patient insurance if table exists
if "ap_patient_insurance" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_patient_insurance (
                key, patient_key, insurance_provider_lkey, primary_insurance,
                insurance_policy_number, insurance_plan_type_lkey, is_valid
            )
            VALUES 
            ('ins001', 'pat001', 'BlueCross', 1, 'POL-12345', 'PPO', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient insurance: {e}")

# Add patient observation summary (height, weight, BMI) if table exists
if "ap_patient_observation_summary" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_patient_observation_summary (
                key, patient_key, visit_key, last_date,
                latestweight, latestheight, latestbmi, is_valid
            )
            VALUES 
            ('obs001', 'pat001', 'enc005', '2025-01-14',
             75.5, 175.0, 24.7, 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient observation summary: {e}")

# Add patient social history (smoking, alcohol) if table exists
if "ap_patient_social_history" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_patient_social_history (
                key, patient_key, current_smoker, previous_smoker,
                alcohol_consumption, type_of_alcohol, is_valid
            )
            VALUES 
            ('psh001', 'pat001', 0, 0,
             'occasional', 'beer', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient social history: {e}")

# Add patient problems (chronic conditions) if table exists
if "ap_patient_problems" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_patient_problems (
                key, patient_key, condition, date_of_diagnosis,
                status_lkey, type_lkey, is_valid
            )
            VALUES 
            ('ppb001', 'pat001', 'Hypertension', '2020-03-15',
             'active', 'chronic', 1),
            ('ppb002', 'pat001', 'Type 2 Diabetes', '2021-06-20',
             'active', 'chronic', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient problems: {e}")

# Add patient diagnosis for the encounter if table exists
if "ap_patient_diagnose" in allowed_schema:
    try:
        cur.execute("""
            INSERT OR IGNORE INTO ap_patient_diagnose (
                key, patient_key, visit_key, diagnose_code,
                description, diagnose_status_lkey, is_valid
            )
            VALUES 
            ('pdiag001', 'pat001', 'enc005', 'I10',
             'Essential hypertension', 'confirmed', 1)
        """)
    except sqlite3.Error as e:
        print(f"Note: Could not insert patient diagnosis: {e}")

conn.commit()
conn.close()

print(f"SUCCESS: Mock hospital.db created successfully with {len(allowed_schema)} tables!")
print(f"   Database location: {db_path}")
