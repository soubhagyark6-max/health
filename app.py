import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Import database module
from database import init_db, query_db, check_db_health, get_db_connection, DB_BACKEND

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-for-healthcare-system")

# Custom authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                flash(f"Access denied. Only {role}s are authorized to view this page.", "danger")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Global routing: Landing Page
@app.route('/')
def index():
    return render_template('index.html')

# Database Setup Check/Helper Page (Failsafe layout if DB is not configured)
@app.route('/db-setup')
def db_setup():
    is_healthy = check_db_health()
    if is_healthy:
        flash("Database is connected and healthy!", "success")
        return redirect(url_for('index'))
    return render_template('index.html') # In index, we'll tell them to check connections

# User Authentication: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Verify db is accessible
        if not check_db_health():
            flash("Database connection failed. Please ensure MySQL is running and credentials in .env are correct.", "danger")
            return render_template('login.html')

        user = query_db(
            "SELECT * FROM users WHERE username = %s AND role = %s", 
            (username, role), 
            one=True
        )
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Fetch profile name
            if role == 'admin':
                admin = query_db("SELECT name FROM admins WHERE user_id = %s", (user['id'],), one=True)
                session['name'] = admin['name'] if admin else "System Admin"
            elif role == 'doctor':
                doctor = query_db("SELECT name FROM doctors WHERE user_id = %s", (user['id'],), one=True)
                session['name'] = doctor['name'] if doctor else "Doctor"
            elif role == 'patient':
                patient = query_db("SELECT name FROM patients WHERE user_id = %s", (user['id'],), one=True)
                session['name'] = patient['name'] if patient else "Patient"
                
            flash(f"Welcome back, {session['name']}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username, password, or role combination.", "danger")
            
    return render_template('login.html')

# User Authentication: Register (Patients Only)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        phone = request.form.get('phone')
        age = request.form.get('age')
        gender = request.form.get('gender')
        blood_group = request.form.get('blood_group')
        address = request.form.get('address')
        
        if not check_db_health():
            flash("Database connection error. Unable to process registration.", "danger")
            return render_template('register.html')

        # Check if username or email exists
        user_exists = query_db("SELECT id FROM users WHERE username = %s OR email = %s", (username, email), one=True)
        if user_exists:
            flash("Username or email already registered.", "danger")
            return render_template('register.html')
            
        try:
            # Create user login
            pass_hash = generate_password_hash(password)
            user_id = query_db(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'patient')",
                (username, email, pass_hash),
                commit=True
            )
            # Create patient profile details
            query_db(
                "INSERT INTO patients (user_id, name, phone, age, gender, blood_group, address) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, name, phone, age, gender, blood_group, address),
                commit=True
            )
            flash("Registration successful! Please login below.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Error during registration: {e}", "danger")
            
    return render_template('register.html')

# User Authentication: Logout
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('login'))

# Dispatcher Route for Dashboard Redirects
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    elif role == 'patient':
        return redirect(url_for('patient_dashboard'))
    return redirect(url_for('index'))


# ==========================================
# ADMIN PORTAL MODULE ROUTES
# ==========================================

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    # Counts
    doc_count = query_db("SELECT COUNT(*) as count FROM doctors", one=True)['count']
    patient_count = query_db("SELECT COUNT(*) as count FROM patients", one=True)['count']
    app_count = query_db("SELECT COUNT(*) as count FROM appointments", one=True)['count']
    pending_count = query_db("SELECT COUNT(*) as count FROM appointments WHERE status = 'pending'", one=True)['count']
    unassigned_count = query_db("SELECT COUNT(*) as count FROM appointments WHERE doctor_id IS NULL AND status != 'cancelled'", one=True)['count']
    
    # Detailed listings
    doctors = query_db("SELECT * FROM doctors")
    patients = query_db("SELECT * FROM patients")
    appointments = query_db("""
        SELECT a.*, p.name as patient_name, d.name as doctor_name 
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        LEFT JOIN doctors d ON a.doctor_id = d.id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """)
    
    return render_template(
        'admin_dashboard.html',
        admin_name=session.get('name'),
        doc_count=doc_count,
        patient_count=patient_count,
        app_count=app_count,
        pending_count=pending_count,
        unassigned_count=unassigned_count,
        doctors=doctors,
        patients=patients,
        appointments=appointments
    )

@app.route('/admin/add_doctor', methods=['POST'])
@login_required
@role_required('admin')
def admin_add_doctor():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    name = request.form.get('name')
    specialization = request.form.get('specialization')
    phone = request.form.get('phone')
    fees = request.form.get('fees')
    availability = request.form.get('availability')
    
    user_exists = query_db("SELECT id FROM users WHERE username = %s OR email = %s", (username, email), one=True)
    if user_exists:
        flash("Username or email already exists.", "danger")
        return redirect(url_for('admin_dashboard') + '#doctors')
        
    try:
        pass_hash = generate_password_hash(password)
        user_id = query_db(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'doctor')",
            (username, email, pass_hash),
            commit=True
        )
        query_db(
            "INSERT INTO doctors (user_id, name, specialization, phone, fees, availability) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, name, specialization, phone, fees, availability),
            commit=True
        )
        flash(f"Doctor {name} registered successfully!", "success")
    except Exception as e:
        flash(f"Error creating doctor: {e}", "danger")
        
    return redirect(url_for('admin_dashboard') + '#doctors')

@app.route('/admin/edit_doctor/<int:doc_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_doctor(doc_id):
    name = request.form.get('name')
    specialization = request.form.get('specialization')
    phone = request.form.get('phone')
    fees = request.form.get('fees')
    availability = request.form.get('availability')
    
    try:
        query_db(
            "UPDATE doctors SET name = %s, specialization = %s, phone = %s, fees = %s, availability = %s WHERE id = %s",
            (name, specialization, phone, fees, availability, doc_id),
            commit=True
        )
        flash("Doctor profile updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating doctor details: {e}", "danger")
        
    return redirect(url_for('admin_dashboard') + '#doctors')

@app.route('/admin/delete_doctor/<int:doc_id>')
@login_required
@role_required('admin')
def admin_delete_doctor(doc_id):
    try:
        # Fetch user_id to delete the user login record too (cascades)
        doc = query_db("SELECT user_id FROM doctors WHERE id = %s", (doc_id,), one=True)
        if doc:
            query_db("DELETE FROM users WHERE id = %s", (doc['user_id'],), commit=True)
            flash("Doctor account deleted successfully.", "success")
        else:
            flash("Doctor record not found.", "warning")
    except Exception as e:
        flash(f"Error deleting doctor account: {e}", "danger")
        
    return redirect(url_for('admin_dashboard') + '#doctors')

@app.route('/admin/delete_patient/<int:pat_id>')
@login_required
@role_required('admin')
def admin_delete_patient(pat_id):
    try:
        pat = query_db("SELECT user_id FROM patients WHERE id = %s", (pat_id,), one=True)
        if pat:
            query_db("DELETE FROM users WHERE id = %s", (pat['user_id'],), commit=True)
            flash("Patient account and clinical records deleted.", "success")
        else:
            flash("Patient record not found.", "warning")
    except Exception as e:
        flash(f"Error deleting patient details: {e}", "danger")
        
    return redirect(url_for('admin_dashboard') + '#patients')

@app.route('/admin/update_appointment/<int:app_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_appointment(app_id):
    status = request.form.get('status')
    doctor_id = request.form.get('doctor_id')

    if not doctor_id:
        flash("Please select a doctor to assign.", "danger")
        return redirect(url_for('admin_dashboard') + '#appointments')

    try:
        query_db(
            "UPDATE appointments SET doctor_id = %s, status = %s WHERE id = %s",
            (doctor_id, status, app_id),
            commit=True
        )
        flash("Appointment updated and doctor assigned successfully.", "success")
    except Exception as e:
        flash(f"Error updating appointment: {e}", "danger")

    return redirect(url_for('admin_dashboard') + '#appointments')

@app.route('/admin/stats_api')
@login_required
@role_required('admin')
def admin_stats_api():
    try:
        if DB_BACKEND == "sqlite":
            monthly_data = query_db("""
                SELECT strftime('%b', appointment_date) as month, COUNT(*) as count
                FROM appointments
                GROUP BY strftime('%Y-%m', appointment_date)
                ORDER BY strftime('%Y-%m', appointment_date) ASC
                LIMIT 6
            """)
        else:
            monthly_data = query_db("""
                SELECT DATE_FORMAT(appointment_date, '%b') as month, COUNT(*) as count 
                FROM appointments 
                GROUP BY MONTH(appointment_date), DATE_FORMAT(appointment_date, '%b')
                ORDER BY MONTH(appointment_date) ASC
                LIMIT 6
            """)
        
        # Aggregate specializations
        specializations = query_db("""
            SELECT specialization, COUNT(*) as count 
            FROM doctors 
            GROUP BY specialization
        """)
        
        months = [row['month'] for row in monthly_data]
        counts = [row['count'] for row in monthly_data]
        specs = {row['specialization']: row['count'] for row in specializations}
        
        return jsonify({
            'success': True,
            'months': months,
            'appointment_counts': counts,
            'specializations': specs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# DOCTOR PORTAL MODULE ROUTES
# ==========================================

@app.route('/doctor/dashboard')
@login_required
@role_required('doctor')
def doctor_dashboard():
    # Fetch active doctor profile
    doctor = query_db("SELECT * FROM doctors WHERE user_id = %s", (session.get('user_id'),), one=True)
    if not doctor:
        flash("Could not locate doctor profile configuration.", "danger")
        return redirect(url_for('logout'))
        
    # Get doctor appointments
    appointments = query_db("""
        SELECT a.*, p.name as patient_name, p.age as patient_age, p.gender as patient_gender
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        WHERE a.doctor_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (doctor['id'],))
    
    # Get patients database under this doctor
    patients_raw = query_db("""
        SELECT DISTINCT p.* 
        FROM patients p
        JOIN appointments a ON a.patient_id = p.id
        WHERE a.doctor_id = %s
    """, (doctor['id'],))
    
    patients = []
    for pat in patients_raw:
        # Fetch previous logs for each patient
        records = query_db("""
            SELECT mr.*, pr.medicine_name as prescription_medicine, 
                   pr.dosage as prescription_dosage, pr.duration as prescription_duration
            FROM medical_records mr
            LEFT JOIN prescriptions pr ON pr.medical_record_id = mr.id
            WHERE mr.patient_id = %s AND mr.doctor_id = %s
            ORDER BY mr.created_at DESC
        """, (pat['id'], doctor['id']))
        pat_copy = dict(pat)
        pat_copy['records'] = records
        patients.append(pat_copy)

    return render_template(
        'doctor_dashboard.html',
        doctor=doctor,
        appointments=appointments,
        patients=patients
    )

@app.route('/doctor/update_appointment', methods=['POST'])
@login_required
@role_required('doctor')
def doctor_update_appointment():
    data = request.get_json()
    appointment_id = data.get('appointmentId')
    status = data.get('status')
    
    # Verify doctor owns the appointment
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (session.get('user_id'),), one=True)
    appointment = query_db("SELECT doctor_id FROM appointments WHERE id = %s", (appointment_id,), one=True)
    
    if not doctor or not appointment or doctor['id'] != appointment['doctor_id']:
        return jsonify({'success': False, 'error': 'Unauthorized appointment operation.'})
        
    try:
        query_db("UPDATE appointments SET status = %s WHERE id = %s", (status, appointment_id), commit=True)
        return jsonify({'success': True, 'message': f'Status successfully updated to {status}.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/doctor/add_record/<int:app_id>', methods=['POST'])
@login_required
@role_required('doctor')
def doctor_add_record(app_id):
    diagnosis = request.form.get('diagnosis')
    treatment = request.form.get('treatment')
    notes = request.form.get('notes')
    
    # Prescription entries
    medicine_name = request.form.get('medicine_name')
    dosage = request.form.get('dosage')
    duration = request.form.get('duration')
    instructions = request.form.get('instructions')
    
    doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (session.get('user_id'),), one=True)
    appointment = query_db("SELECT * FROM appointments WHERE id = %s", (app_id,), one=True)
    
    if not doctor or not appointment or doctor['id'] != appointment['doctor_id']:
        flash("Unauthorized record modification request.", "danger")
        return redirect(url_for('doctor_dashboard'))
        
    try:
        # Create record transactionally
        # 1. Insert medical record
        record_id = query_db("""
            INSERT INTO medical_records (patient_id, doctor_id, appointment_id, symptoms, diagnosis, treatment, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (appointment['patient_id'], doctor['id'], app_id, appointment['symptoms'], diagnosis, treatment, notes), commit=True)
        
        # 2. Insert prescription if medicine is specified
        if medicine_name and medicine_name.strip():
            query_db("""
                INSERT INTO prescriptions (medical_record_id, appointment_id, patient_id, doctor_id, medicine_name, dosage, duration, instructions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (record_id, app_id, appointment['patient_id'], doctor['id'], medicine_name, dosage, duration, instructions), commit=True)
            
        # 3. Update appointment status to completed
        query_db("UPDATE appointments SET status = 'completed' WHERE id = %s", (app_id,), commit=True)
        flash("Diagnostics, treatment details, and prescriptions logged successfully.", "success")
    except Exception as e:
        flash(f"Error saving clinical records: {e}", "danger")
        
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/stats_api')
@login_required
@role_required('doctor')
def doctor_stats_api():
    try:
        doctor = query_db("SELECT id FROM doctors WHERE user_id = %s", (session.get('user_id'),), one=True)
        if not doctor:
            return jsonify({'success': False, 'error': 'Doctor context not found.'})
            
        stats = query_db("""
            SELECT status, COUNT(*) as count 
            FROM appointments 
            WHERE doctor_id = %s 
            GROUP BY status
        """, (doctor['id'],))
        
        res = {
            'success': True,
            'pending': 0,
            'confirmed': 0,
            'completed': 0,
            'cancelled': 0
        }
        for row in stats:
            res[row['status']] = row['count']
            
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# PATIENT PORTAL MODULE ROUTES
# ==========================================

@app.route('/patient/dashboard')
@login_required
@role_required('patient')
def patient_dashboard():
    patient = query_db("SELECT * FROM patients WHERE user_id = %s", (session.get('user_id'),), one=True)
    if not patient:
        flash("Patient profile not verified.", "danger")
        return redirect(url_for('logout'))
        
    # Get active lists
    doctors = query_db("SELECT * FROM doctors")
    appointments = query_db("""
        SELECT a.*, d.name as doctor_name, d.specialization as doctor_specialization
        FROM appointments a
        LEFT JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (patient['id'],))
    
    records = query_db("""
        SELECT mr.*, d.name as doctor_name
        FROM medical_records mr
        JOIN doctors d ON mr.doctor_id = d.id
        WHERE mr.patient_id = %s
        ORDER BY mr.created_at DESC
    """, (patient['id'],))
    
    prescriptions = query_db("""
        SELECT pr.*, d.name as doctor_name
        FROM prescriptions pr
        JOIN doctors d ON pr.doctor_id = d.id
        WHERE pr.patient_id = %s
        ORDER BY pr.created_at DESC
    """, (patient['id'],))

    return render_template(
        'patient_dashboard.html',
        patient=patient,
        doctors=doctors,
        appointments=appointments,
        records=records,
        prescriptions=prescriptions
    )

@app.route('/patient/book_appointment', methods=['POST'])
@login_required
@role_required('patient')
def patient_book_appointment():
    appointment_date = request.form.get('appointment_date')
    appointment_time = request.form.get('appointment_time')
    symptoms = request.form.get('symptoms')

    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (session.get('user_id'),), one=True)
    if not patient:
        flash("Error processing context.", "danger")
        return redirect(url_for('patient_dashboard'))

    if not appointment_date or not appointment_time or not symptoms:
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for('patient_dashboard') + '#book')

    try:
        query_db("""
            INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, symptoms)
            VALUES (%s, NULL, %s, %s, 'pending', %s)
        """, (patient['id'], appointment_date, appointment_time, symptoms), commit=True)
        flash("Appointment request submitted! An admin will assign a doctor shortly.", "success")
    except Exception as e:
        flash(f"Error booking consultation: {e}", "danger")

    return redirect(url_for('patient_dashboard') + '#overview')

@app.route('/patient/cancel_appointment/<int:app_id>')
@login_required
@role_required('patient')
def patient_cancel_appointment(app_id):
    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (session.get('user_id'),), one=True)
    appointment = query_db("SELECT patient_id FROM appointments WHERE id = %s", (app_id,), one=True)
    
    if not patient or not appointment or patient['id'] != appointment['patient_id']:
        flash("Unauthorized cancellation command.", "danger")
        return redirect(url_for('patient_dashboard'))
        
    try:
        query_db("UPDATE appointments SET status = 'cancelled' WHERE id = %s", (app_id,), commit=True)
        flash("Appointment cancelled successfully.", "success")
    except Exception as e:
        flash(f"Error during cancellation: {e}", "danger")
        
    return redirect(url_for('patient_dashboard') + '#overview')

@app.route('/patient/update_profile', methods=['POST'])
@login_required
@role_required('patient')
def patient_update_profile():
    name = request.form.get('name')
    phone = request.form.get('phone')
    age = request.form.get('age')
    gender = request.form.get('gender')
    blood_group = request.form.get('blood_group')
    address = request.form.get('address')
    
    patient = query_db("SELECT id FROM patients WHERE user_id = %s", (session.get('user_id'),), one=True)
    if not patient:
        flash("Could not resolve patient profile details.", "danger")
        return redirect(url_for('patient_dashboard'))
        
    try:
        query_db("""
            UPDATE patients 
            SET name = %s, phone = %s, age = %s, gender = %s, blood_group = %s, address = %s 
            WHERE id = %s
        """, (name, phone, age, gender, blood_group, address, patient['id']), commit=True)
        session['name'] = name # Update active session display name
        flash("Profile information updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating profile configurations: {e}", "danger")
        
    return redirect(url_for('patient_dashboard') + '#profile')


# Initialize application components
with app.app_context():
    print("Checking database health...")
    initialized = init_db()
    if initialized:
        print("Database schema loaded and verified.")
    else:
        print("WARNING: Database connection failed. Please ensure MySQL is configured correctly.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
