import os
import re
import sqlite3
from datetime import datetime, timedelta

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:  # pragma: no cover
    mysql.connector = None
    MySQLError = Exception

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "smart_healthcare")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "healthcare.db"))

db_pool = None


def _sqlite_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_connection_pool():
    global db_pool
    if DB_BACKEND == "sqlite":
        db_pool = None
        if not os.path.exists(DB_PATH):
            conn = _sqlite_connection()
            conn.close()
        print(f"SQLite database ready at {DB_PATH}")
        return True

    try:
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cursor.close()
        conn.close()
        db_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="healthcare_pool",
            pool_size=10,
            pool_reset_mode="session",
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
        print("Database connection pool initialized successfully.")
        return True
    except MySQLError as e:
        print(f"Error initializing connection pool: {e}")
        db_pool = None
        return False


def get_db_connection():
    global db_pool
    if DB_BACKEND == "sqlite":
        return _sqlite_connection()

    if db_pool is None:
        initialized = init_connection_pool()
        if not initialized:
            raise Exception("Database connection pool not initialized. Please verify MySQL configuration.")
    try:
        return db_pool.get_connection()
    except MySQLError as e:
        print(f"Error getting connection from pool: {e}")
        init_connection_pool()
        return db_pool.get_connection()


def _prepare_query(query, args):
    if DB_BACKEND == "sqlite":
        return re.sub(r"%s", "?", query), args
    return query, args


def query_db(query, args=(), one=False, commit=False):
    conn = get_db_connection()
    if DB_BACKEND == "sqlite":
        cursor = conn.cursor()
    else:
        cursor = conn.cursor(dictionary=True)
    result = None
    try:
        sql, params = _prepare_query(query, args)
        cursor.execute(sql, params)
        if commit:
            conn.commit()
            result = cursor.lastrowid
        else:
            result = cursor.fetchall()
            if one:
                result = result[0] if result else None
    except Exception as e:
        print(f"Database Query Error: {e}")
        if commit:
            conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
    return result


def check_db_health():
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False


def init_db():
    try:
        if not init_connection_pool():
            return False

        if DB_BACKEND == "sqlite":
            conn = get_db_connection()
            cursor = conn.cursor()
            statements = [
                """CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','doctor','patient')), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
                """CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS doctors (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL, name TEXT NOT NULL, specialization TEXT NOT NULL, phone TEXT NOT NULL, fees REAL NOT NULL, availability TEXT DEFAULT 'Mon-Fri (9:00 AM - 5:00 PM)', FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL, age INTEGER, gender TEXT, blood_group TEXT, address TEXT, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS appointments (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL, appointment_date TEXT NOT NULL, appointment_time TEXT NOT NULL, status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','completed','cancelled')), symptoms TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE, FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS medical_records (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL, appointment_id INTEGER NOT NULL, symptoms TEXT, diagnosis TEXT NOT NULL, treatment TEXT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE, FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE, FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS prescriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, medical_record_id INTEGER NOT NULL, appointment_id INTEGER NOT NULL, patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL, medicine_name TEXT NOT NULL, dosage TEXT NOT NULL, duration TEXT NOT NULL, instructions TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE CASCADE, FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE, FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE, FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE)""",
            ]
            for statement in statements:
                cursor.execute(statement)
            conn.commit()
            cursor.close()
            conn.close()
            seed_data()
            return True

        schema_path = os.path.join(os.path.dirname(__file__), "database.sql")
        if not os.path.exists(schema_path):
            return False
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor()
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_statements = f.read().split(";")
        for statement in sql_statements:
            if statement.strip():
                try:
                    cursor.execute(statement)
                except MySQLError as se:
                    print(f"Statement execution warning: {se}")
        conn.commit()
        cursor.close()
        conn.close()
        seed_data()
        return True
    except Exception as e:
        print(f"Database initialization failed: {e}")
        return False


def seed_data():
    try:
        user_count = query_db("SELECT COUNT(*) as count FROM users", one=True)['count']
        if user_count > 0:
            print("Database already has data. Skipping seeding.")
            return

        print("Seeding database with sample data...")
        admin_pass_hash = generate_password_hash("admin123")
        admin_user_id = query_db("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)", ("admin", "admin@healthcare.com", admin_pass_hash, "admin"), commit=True)
        query_db("INSERT INTO admins (user_id, name, phone) VALUES (%s, %s, %s)", (admin_user_id, "System Administrator", "+1-555-0100"), commit=True)

        doc1_pass_hash = generate_password_hash("doc123")
        doc1_user_id = query_db("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)", ("doctor1", "sarah.jenkins@healthcare.com", doc1_pass_hash, "doctor"), commit=True)
        doc1_id = query_db("INSERT INTO doctors (user_id, name, specialization, phone, fees, availability) VALUES (%s, %s, %s, %s, %s, %s)", (doc1_user_id, "Dr. Sarah Jenkins", "Cardiology", "+1-555-0199", 150.00, "Mon-Wed (9:00 AM - 1:00 PM)"), commit=True)

        doc2_pass_hash = generate_password_hash("doc123")
        doc2_user_id = query_db("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)", ("doctor2", "james.carter@healthcare.com", doc2_pass_hash, "doctor"), commit=True)
        doc2_id = query_db("INSERT INTO doctors (user_id, name, specialization, phone, fees, availability) VALUES (%s, %s, %s, %s, %s, %s)", (doc2_user_id, "Dr. James Carter", "Pediatrics", "+1-555-0188", 120.00, "Tue-Thu (2:00 PM - 6:00 PM)"), commit=True)

        pat1_pass_hash = generate_password_hash("pat123")
        pat1_user_id = query_db("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)", ("patient1", "john.doe@email.com", pat1_pass_hash, "patient"), commit=True)
        pat1_id = query_db("INSERT INTO patients (user_id, name, phone, age, gender, blood_group, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (pat1_user_id, "John Doe", "+1-555-0144", 34, "Male", "O+", "123 Main St, Springfield"), commit=True)

        pat2_pass_hash = generate_password_hash("pat123")
        pat2_user_id = query_db("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)", ("patient2", "jane.smith@email.com", pat2_pass_hash, "patient"), commit=True)
        pat2_id = query_db("INSERT INTO patients (user_id, name, phone, age, gender, blood_group, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (pat2_user_id, "Jane Smith", "+1-555-0177", 29, "Female", "A-", "456 Oak Ave, Metropolis"), commit=True)

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        app1_id = query_db("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, symptoms) VALUES (%s, %s, %s, %s, %s, %s)", (pat1_id, doc1_id, yesterday, "10:00:00", "completed", "Mild chest tightness, palpitations during mild exertion."), commit=True)
        query_db("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, symptoms) VALUES (%s, %s, %s, %s, %s, %s)", (pat2_id, doc2_id, tomorrow, "14:30:00", "confirmed", "Child having mild allergic skin rash and runny nose."), commit=True)
        query_db("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, symptoms) VALUES (%s, %s, %s, %s, %s, %s)", (pat1_id, doc2_id, today, "11:00:00", "pending", "Consultation for throat infection and sore tonsils."), commit=True)

        record_id = query_db("INSERT INTO medical_records (patient_id, doctor_id, appointment_id, symptoms, diagnosis, treatment, notes) VALUES (%s, %s, %s, %s, %s, %s, %s)", (pat1_id, doc1_id, app1_id, "Mild chest tightness, palpitations during mild exertion.", "Aortic valve sclerosis check. Normal resting ECG. Palpitations likely due to excessive caffeine intake and mild anxiety.", "Reduce caffeine intake. Structured cardiovascular exercise (walking 30m daily). Aspirin 81mg if discomfort recurs.", "Return for checkup if symptoms worsen. Schedule echocardiogram in 6 months if palpitations persist."), commit=True)
        query_db("INSERT INTO prescriptions (medical_record_id, appointment_id, patient_id, doctor_id, medicine_name, dosage, duration, instructions) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (record_id, app1_id, pat1_id, doc1_id, "Aspirin EC", "81mg", "90 days", "Take one tablet daily after lunch. Do not take on empty stomach."), commit=True)
        print("Database seeded successfully!")
    except Exception as e:
        print(f"Error seeding database: {e}")
        raise e
