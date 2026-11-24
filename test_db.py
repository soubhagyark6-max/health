# Diagnostic Test Script for Smart Healthcare Management System
import os
import sys

print("--------------------------------------------------")
print("APEXCARE SYSTEM DIAGNOSTICS & VERIFICATION")
print("--------------------------------------------------")

# 1. Check Python requirements
try:
    import flask
    import mysql.connector
    import dotenv
    print("[SUCCESS] All required Python libraries are installed.")
except ImportError as e:
    print(f"[FAIL] Missing required libraries: {e}")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

# 2. Check configuration file
if not os.path.exists(".env"):
    print("[FAIL] Configuration file '.env' is missing.")
    sys.exit(1)
else:
    print("[SUCCESS] Config file '.env' detected.")

# 3. Test Database Connectivity
from dotenv import load_dotenv
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "smart_healthcare")

print(f"\nAttempting connection to MySQL: {DB_USER}@{DB_HOST} ...")
try:
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()[0]
    print(f"[SUCCESS] Connected to MySQL Server version: {version}")
    
    # Check if database exists
    cursor.execute(f"SHOW DATABASES LIKE '{DB_NAME}'")
    db_exists = cursor.fetchone()
    if db_exists:
        print(f"[SUCCESS] Database '{DB_NAME}' already exists.")
        conn.close()
        
        # Test full query module
        from database import query_db, get_db_connection
        try:
            users_count = query_db("SELECT COUNT(*) as count FROM users", one=True)['count']
            print(f"[SUCCESS] Database initialized. Count of users: {users_count}")
        except Exception as q_err:
            print(f"[WARNING] Database exists but table query failed: {q_err}")
    else:
        print(f"[INFO] Database '{DB_NAME}' does not exist yet. It will be created on app startup.")
        conn.close()
except Exception as e:
    print(f"[WARNING] Could not connect to MySQL: {e}")
    print("\n--------------------------------------------------")
    print("Troubleshooting Tips:")
    print("1. Ensure MySQL is running on your system (e.g., via XAMPP, WAMP, Docker or local service).")
    print("2. Check credentials inside your project root '.env' file.")
    print("3. Note: The Flask app will still launch even if MySQL is offline. When MySQL is online, it will auto-create tables.")
    print("--------------------------------------------------")

print("\nRunning Flask configuration syntax verification...")
try:
    from app import app
    print("[SUCCESS] Flask application loaded with zero syntax errors!")
except Exception as app_err:
    print(f"[FAIL] Flask import compilation failed: {app_err}")
    sys.exit(1)

print("\nDiagnostics complete. Ready for launch!")
print("--------------------------------------------------")
