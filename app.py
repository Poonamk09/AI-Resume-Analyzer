import os
import fitz
from werkzeug.utils import secure_filename
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "ai_resume_analyzer_secret_key"


# Home Page
@app.route('/')
def home():
    return render_template('index.html')


# User Registration
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            query = """
            INSERT INTO users (full_name, email, password, phone)
            VALUES (%s, %s, %s, %s)
            """

            values = (full_name, email, hashed_password, phone)

            cursor.execute(query, values)
            connection.commit()

            flash("Registration Successful! Please Login.")
            return redirect(url_for('login'))

        except Exception:
            connection.rollback()
            flash("Email already exists or registration failed.")

        finally:
            cursor.close()
            connection.close()

    return render_template('register.html')


# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = "SELECT * FROM users WHERE email = %s"
        cursor.execute(query, (email,))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(user['password'], password):

            session['user_id'] = user['user_id']
            session['user_name'] = user['full_name']

            return redirect(url_for('dashboard'))

        else:
            flash("Invalid Email or Password!")

    return render_template('login.html')


# Extract Skills from Resume
def extract_skills(resume_text):

    connection = get_db_connection()
    cursor = connection.cursor()

    query = "SELECT skill_name FROM skills"
    cursor.execute(query)

    all_skills = cursor.fetchall()

    extracted_skills = []

    resume_text = resume_text.lower()

    for skill in all_skills:

        skill_name = skill[0]

        if skill_name.lower() in resume_text:
            extracted_skills.append(skill_name)

    cursor.close()
    connection.close()

    return extracted_skills


# Resume Upload
# Resume Upload
@app.route('/upload-resume', methods=['GET', 'POST'])
def upload_resume():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        if 'resume' not in request.files:
            flash("Please select a resume!")
            return redirect(url_for('upload_resume'))

        file = request.files['resume']

        if file.filename == '':
            flash("No file selected!")
            return redirect(url_for('upload_resume'))

        if not file.filename.lower().endswith('.pdf'):
            flash("Only PDF files are allowed!")
            return redirect(url_for('upload_resume'))

        filename = secure_filename(file.filename)

        unique_filename = str(uuid.uuid4()) + "_" + filename

        upload_folder = os.path.join('uploads', 'resumes')
        os.makedirs(upload_folder, exist_ok=True)

        file_path = os.path.join(upload_folder, unique_filename)

        file.save(file_path)

        # Extract Text from PDF
        pdf_document = fitz.open(file_path)

        extracted_text = ""

        for page in pdf_document:
            extracted_text += page.get_text()

        pdf_document.close()

        # Extract Skills from Resume
        extracted_skills = extract_skills(extracted_text)

        # Save Resume in Database
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
        INSERT INTO resumes (user_id, file_name, file_path, extracted_text)
        VALUES (%s, %s, %s, %s)
        """

        values = (
            session['user_id'],
            filename,
            file_path,
            extracted_text
        )

        cursor.execute(query, values)
        connection.commit()

        cursor.close()
        connection.close()

        flash("Resume uploaded successfully!")

        # Display Extracted Skills
        if extracted_skills:
            flash("Skills Found: " + ", ".join(extracted_skills))
        else:
            flash("No matching skills found in your resume.")

        return redirect(url_for('dashboard'))

    return render_template('upload_resume.html')
      
# Job Recommendations
@app.route('/job-recommendations')
def job_recommendations():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get Latest Uploaded Resume
    query = """
    SELECT resume_id, extracted_text
    FROM resumes
    WHERE user_id = %s
    ORDER BY resume_id DESC
    LIMIT 1
    """

    cursor.execute(query, (session['user_id'],))
    resume = cursor.fetchone()

    if not resume:
        cursor.close()
        connection.close()

        flash("Please upload your resume first!")
        return redirect(url_for('upload_resume'))

    resume_id = resume['resume_id']

    # Extract Skills from Resume
    extracted_skills = extract_skills(resume['extracted_text'])

    # Remove Previous Analysis Results for This Resume
    cursor.execute(
        "DELETE FROM analysis_results WHERE resume_id = %s",
        (resume_id,)
    )

    # Get All Jobs
    cursor.execute("SELECT * FROM jobs")
    jobs = cursor.fetchall()

    recommended_jobs = []

    for job in jobs:

        # Get Required Skills
        query = """
        SELECT s.skill_name
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        WHERE js.job_id = %s
        """

        cursor.execute(query, (job['job_id'],))
        required_skills = [row['skill_name'] for row in cursor.fetchall()]

        # Find Matched Skills
        matched_skills = [
            skill for skill in required_skills
            if skill in extracted_skills
        ]

        # Find Missing Skills
        missing_skills = [
            skill for skill in required_skills
            if skill not in extracted_skills
        ]

        # Calculate Match Percentage
        if required_skills:
            match_percentage = (
                len(matched_skills) / len(required_skills)
            ) * 100
        else:
            match_percentage = 0

        match_percentage = round(match_percentage, 2)

        # Save Analysis Result in Database
        insert_query = """
        INSERT INTO analysis_results
        (resume_id, job_id, match_percentage, matched_skills, missing_skills)
        VALUES (%s, %s, %s, %s, %s)
        """

        values = (
            resume_id,
            job['job_id'],
            match_percentage,
            ", ".join(matched_skills),
            ", ".join(missing_skills)
        )

        cursor.execute(insert_query, values)

        # Add Results to Job
        job['match_percentage'] = match_percentage
        job['matched_skills'] = matched_skills
        job['missing_skills'] = missing_skills

        recommended_jobs.append(job)

    # Save All Analysis Results
    connection.commit()

    # Sort Jobs by Match Percentage
    recommended_jobs.sort(
        key=lambda x: x['match_percentage'],
        reverse=True
    )

    cursor.close()
    connection.close()

    return render_template(
        'job_recommendations.html',
        jobs=recommended_jobs
    )
# Resume Analysis Results
@app.route('/analysis-result')
def analysis_result():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get Latest Uploaded Resume
    query = """
    SELECT resume_id
    FROM resumes
    WHERE user_id = %s
    ORDER BY resume_id DESC
    LIMIT 1
    """

    cursor.execute(query, (session['user_id'],))
    resume = cursor.fetchone()

    if not resume:
        cursor.close()
        connection.close()

        flash("Please upload your resume first!")
        return redirect(url_for('upload_resume'))

    # Get Analysis Results
    query = """
    SELECT
        ar.result_id,
        ar.match_percentage,
        ar.matched_skills,
        ar.missing_skills,
        ar.analyzed_at,
        j.job_title,
        j.company_name,
        j.location
    FROM analysis_results ar
    JOIN jobs j ON ar.job_id = j.job_id
    WHERE ar.resume_id = %s
    ORDER BY ar.match_percentage DESC
    """

    cursor.execute(query, (resume['resume_id'],))
    results = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'analysis_result.html',
        results=results
    )
    # Admin Login
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = "SELECT * FROM admin WHERE username = %s"
        cursor.execute(query, (username,))

        admin = cursor.fetchone()

        cursor.close()
        connection.close()

        if admin and check_password_hash(admin['password'], password):

            session['admin_id'] = admin['admin_id']
            session['admin_username'] = admin['username']

            flash("Admin Login Successful!")
            return redirect(url_for('admin_dashboard'))

        else:
            flash("Invalid Username or Password!")

    return render_template('admin_login.html')
    # Admin Dashboard
@app.route('/admin-dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get Total Users
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()['total_users']

    # Get Total Resumes
    cursor.execute("SELECT COUNT(*) AS total_resumes FROM resumes")
    total_resumes = cursor.fetchone()['total_resumes']

    # Get Total Jobs
    cursor.execute("SELECT COUNT(*) AS total_jobs FROM jobs")
    total_jobs = cursor.fetchone()['total_jobs']

    cursor.close()
    connection.close()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_resumes=total_resumes,
        total_jobs=total_jobs
    )
    # Admin Logout
@app.route('/admin-logout')
def admin_logout():

    session.pop('admin_id', None)
    session.pop('admin_username', None)

    flash("Admin Logged Out Successfully!")

    return redirect(url_for('admin_login'))
    # Admin View Users
@app.route('/admin-users')
def admin_users():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT user_id, full_name, email, phone, created_at
        FROM users
        ORDER BY user_id DESC
    """)

    users = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_users.html', users=users)
    # Admin View Resumes
@app.route('/admin-resumes')
def admin_resumes():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
    SELECT
        r.resume_id,
        r.file_name,
        r.uploaded_at,
        u.full_name,
        u.email
    FROM resumes r
    JOIN users u ON r.user_id = u.user_id
    ORDER BY r.resume_id DESC
    """

    cursor.execute(query)
    resumes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_resumes.html', resumes=resumes)
# Dashboard
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template(
        'dashboard.html',
        user_name=session['user_name']
    )


# User Profile
@app.route('/profile')
def profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = "SELECT * FROM users WHERE user_id = %s"
    cursor.execute(query, (session['user_id'],))

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template('profile.html', user=user)


# Logout
@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)