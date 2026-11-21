import re
import os
import fitz
import uuid

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from config import get_db_connection

app = Flask(__name__)
app.secret_key = "ai_resume_analyzer_secret_key"

UPLOAD_FOLDER = "uploads/resumes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==============================
# USER REGISTRATION
# ==============================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO users
                (full_name, email, password, phone)
                VALUES (%s, %s, %s, %s)
            """, (full_name, email, hashed_password, phone))

            connection.commit()

            flash("Registration Successful! Please Login.")
            return redirect(url_for('register'))

        except Exception as error:
            connection.rollback()
            print("Registration Error:", error)
            flash("Email already exists or registration failed.")

        finally:
            cursor.close()
            connection.close()

    return render_template('register.html')


# ==============================
# USER LOGIN
# ==============================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(user['password'], password):

            session['user_id'] = user['user_id']

            return redirect(url_for('dashboard'))

        else:
            flash("Invalid Email or Password!")

    return render_template('login.html')


# ==============================
# USER DASHBOARD
# ==============================

@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s",
        (session['user_id'],)
    )

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template('dashboard.html', user=user)


# ==============================
# USER PROFILE
# ==============================

@app.route('/profile')
def profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT user_id, full_name, email, phone, created_at
            FROM users
            WHERE user_id = %s
        """, (session['user_id'],))

        user = cursor.fetchone()

        cursor.execute("""
            SELECT resume_id, file_name, uploaded_at
            FROM resumes
            WHERE user_id = %s
            ORDER BY uploaded_at DESC
        """, (session['user_id'],))

        resumes = cursor.fetchall()

        return render_template(
            'profile.html',
            user=user,
            resumes=resumes
        )

    finally:
        cursor.close()
        connection.close()


# ==============================
# ADMIN LOGIN
# ==============================

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM admin WHERE username = %s",
            (username,)
        )

        admin = cursor.fetchone()

        cursor.close()
        connection.close()

        password_valid = False

        if admin:

            stored_password = admin['password']

            try:
                password_valid = check_password_hash(
                    stored_password, password
                )

            except (ValueError, TypeError):
                password_valid = False

            if not password_valid:
                password_valid = (stored_password == password)

        if admin and password_valid:

            session['admin_id'] = admin['admin_id']
            session['admin_username'] = admin['username']

            return redirect(url_for('admin_dashboard'))

        flash("Invalid username or password")

    return render_template('admin_login.html')


# ==============================
# ADMIN DASHBOARD
# ==============================

@app.route('/admin-dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()['total_users']

    cursor.execute("SELECT COUNT(*) AS total_resumes FROM resumes")
    total_resumes = cursor.fetchone()['total_resumes']

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

# ==============================
# ADMIN VIEW USERS
# ==============================

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


# ==============================
# ADMIN VIEW RESUMES
# ==============================

@app.route('/admin-resumes')
def admin_resumes():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            resumes.resume_id,
            users.full_name,
            users.email,
            resumes.file_name,
            resumes.uploaded_at
        FROM resumes
        JOIN users ON resumes.user_id = users.user_id
        ORDER BY resumes.resume_id DESC
    """)

    resumes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_resumes.html', resumes=resumes)

# ==============================
# ADMIN VIEW JOBS
# ==============================

@app.route('/admin-jobs')
def admin_jobs():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                j.*,
                GROUP_CONCAT(s.skill_name SEPARATOR ',') AS skills
            FROM jobs j
            LEFT JOIN job_skills js ON j.job_id = js.job_id
            LEFT JOIN skills s ON js.skill_id = s.skill_id
            GROUP BY j.job_id
            ORDER BY j.job_id DESC
        """)

        jobs = cursor.fetchall()

        for job in jobs:
            job['skills'] = (
                job['skills'].split(',')
                if job['skills']
                else []
            )

        return render_template('admin_jobs.html', jobs=jobs)

    finally:
        cursor.close()
        connection.close()

# ==============================
# ADMIN ADD JOB
# ==============================

@app.route('/admin-add-job', methods=['GET', 'POST'])
def admin_add_job():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':

        job_title = request.form['job_title']
        company_name = request.form['company_name']
        location = request.form['location']
        description = request.form['description']
        experience = request.form['experience']
        job_type = request.form['job_type']
        apply_link = request.form['apply_link']

        selected_skills = request.form.getlist('skills')

        try:
            query = """
                INSERT INTO jobs
                (job_title, company_name, location, description,
                 experience, job_type, apply_link)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            values = (
                job_title, company_name, location, description,
                experience, job_type, apply_link
            )

            cursor.execute(query, values)

            job_id = cursor.lastrowid

            for skill_id in selected_skills:

                cursor.execute("""
                    INSERT INTO job_skills (job_id, skill_id)
                    VALUES (%s, %s)
                """, (job_id, int(skill_id)))

            connection.commit()

            flash("Job Added Successfully!")

        except Exception as error:
            connection.rollback()
            flash("Unable to add job. Please check the details.")
            print("Admin Add Job Error:", error)

        finally:
            cursor.close()
            connection.close()

        return redirect(url_for('admin_jobs'))

    cursor.execute(
        "SELECT skill_id, skill_name FROM skills ORDER BY skill_name"
    )

    skills = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_add_job.html', skills=skills)

# ==============================
# ADMIN EDIT JOB
# ==============================

@app.route('/admin-edit-job/<int:job_id>', methods=['GET', 'POST'])
def admin_edit_job(job_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if request.method == 'POST':

            job_title = request.form['job_title']
            company_name = request.form['company_name']
            location = request.form['location']
            description = request.form['description']
            experience = request.form['experience']
            job_type = request.form['job_type']
            apply_link = request.form['apply_link']

            selected_skills = request.form.getlist('skills')

            cursor.execute("""
                UPDATE jobs
                SET job_title = %s,
                    company_name = %s,
                    location = %s,
                    description = %s,
                    experience = %s,
                    job_type = %s,
                    apply_link = %s
                WHERE job_id = %s
            """, (
                job_title,
                company_name,
                location,
                description,
                experience,
                job_type,
                apply_link,
                job_id
            ))

            # Remove old skills
            cursor.execute("""
                DELETE FROM job_skills
                WHERE job_id = %s
            """, (job_id,))

            # Add updated skills
            for skill_id in selected_skills:

                cursor.execute("""
                    INSERT INTO job_skills (job_id, skill_id)
                    VALUES (%s, %s)
                """, (job_id, int(skill_id)))

            connection.commit()

            flash("Job Updated Successfully!")

            return redirect(url_for('admin_jobs'))

        # Get job details
        cursor.execute("""
            SELECT *
            FROM jobs
            WHERE job_id = %s
        """, (job_id,))

        job = cursor.fetchone()

        if not job:
            flash("Job not found!")
            return redirect(url_for('admin_jobs'))

        # Get all skills
        cursor.execute("""
            SELECT skill_id, skill_name
            FROM skills
            ORDER BY skill_name
        """)

        skills = cursor.fetchall()

        # Get already selected skills
        cursor.execute("""
            SELECT skill_id
            FROM job_skills
            WHERE job_id = %s
        """, (job_id,))

        selected_skills = [
            item['skill_id'] for item in cursor.fetchall()
        ]

        return render_template(
            'admin_edit_job.html',
            job=job,
            skills=skills,
            selected_skills=selected_skills
        )

    except Exception as error:

        connection.rollback()
        print("Edit Job Error:", error)

        flash("Unable to update job.")

        return redirect(url_for('admin_jobs'))

    finally:
        cursor.close()
        connection.close()


# ==============================
# ADMIN DELETE JOB
# ==============================

@app.route('/admin-delete-job/<int:job_id>', methods=['POST'])
def admin_delete_job(job_id):

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Delete related analysis records first
        cursor.execute("""
            DELETE FROM analysis_results
            WHERE job_id = %s
        """, (job_id,))

        # Delete job skills
        cursor.execute("""
            DELETE FROM job_skills
            WHERE job_id = %s
        """, (job_id,))

        # Delete job
        cursor.execute("""
            DELETE FROM jobs
            WHERE job_id = %s
        """, (job_id,))

        connection.commit()

        flash("Job Deleted Successfully!")

    except Exception as error:

        connection.rollback()

        print("Delete Job Error:", error)

        flash("Unable to delete job.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('admin_jobs'))

# ==============================
# RESUME SKILLS ANALYSIS
# ==============================

@app.route('/analysis-result')
def analysis_result():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM resumes
            WHERE user_id = %s
            ORDER BY resume_id DESC
            LIMIT 1
        """, (session['user_id'],))

        resume = cursor.fetchone()

        if not resume:
            flash("Please upload your resume first.")
            return redirect(url_for('upload_resume'))

        cursor.execute("""
            SELECT skill_id, skill_name, category
            FROM skills
            ORDER BY skill_name
        """)

        all_skills = cursor.fetchall()

        extracted_text = resume['extracted_text'] or ""

        matched_skills = []

        for skill in all_skills:

            skill_name = skill['skill_name']

            pattern = r'(?<!\w)' + re.escape(skill_name) + r'(?!\w)'

            if re.search(pattern, extracted_text, re.IGNORECASE):
                matched_skills.append(skill_name)

        return render_template(
            'analysis_result.html',
            resume=resume,
            matched_skills=matched_skills
        )

    except Exception as error:

        print("Skills Analysis Error:", error)

        flash("Unable to analyze resume.")

        return redirect(url_for('dashboard'))

    finally:
        cursor.close()
        connection.close()


# ==============================
# JOB RECOMMENDATIONS
# ==============================

@app.route('/job-recommendations')
def job_recommendations():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM resumes
            WHERE user_id = %s
            ORDER BY uploaded_at DESC
            LIMIT 1
        """, (session['user_id'],))

        resume = cursor.fetchone()

        if not resume:
            flash("Please upload your resume first.")
            return redirect(url_for('upload_resume'))

        resume_text = resume['extracted_text'] or ""

        # Detect skills from resume
        cursor.execute("SELECT skill_name FROM skills")
        all_skills = cursor.fetchall()

        matched_resume_skills = []

        for item in all_skills:

            skill = item['skill_name']

            pattern = r'(?<!\w)' + re.escape(skill) + r'(?!\w)'

            if re.search(pattern, resume_text, re.IGNORECASE):
                matched_resume_skills.append(skill)

        # Detect experience from resume
        experience_pattern = r'(\d+(?:\.\d+)?)\s*\+?\s*years?\s+of\s+experience'

        experience_found = re.search(
            experience_pattern,
            resume_text,
            re.IGNORECASE
        )

        if experience_found:
            resume_experience = float(experience_found.group(1))
        else:
            resume_experience = 0

        # Get all jobs and required skills
        cursor.execute("""
            SELECT
                j.job_id,
                j.job_title,
                j.company_name,
                j.location,
                j.description,
                j.experience,
                j.job_type,
                j.apply_link,
                s.skill_name
            FROM jobs j
            LEFT JOIN job_skills js ON j.job_id = js.job_id
            LEFT JOIN skills s ON js.skill_id = s.skill_id
            ORDER BY j.job_id DESC
        """)

        job_rows = cursor.fetchall()

        jobs = {}

        for row in job_rows:

            job_id = row['job_id']

            if job_id not in jobs:

                jobs[job_id] = {
                    'job_id': job_id,
                    'job_title': row['job_title'],
                    'company_name': row['company_name'],
                    'location': row['location'],
                    'description': row['description'],
                    'experience': row['experience'],
                    'job_type': row['job_type'],
                    'apply_link': row['apply_link'],
                    'required_skills': []
                }

            if row['skill_name']:
                jobs[job_id]['required_skills'].append(
                    row['skill_name']
                )

        recommendations = []

        for job in jobs.values():

            required_skills = job['required_skills']

            matched = [
                skill for skill in required_skills
                if skill.lower() in
                [s.lower() for s in matched_resume_skills]
            ]

            missing = [
                skill for skill in required_skills
                if skill.lower() not in
                [s.lower() for s in matched_resume_skills]
            ]

            if required_skills:
                percentage = (
                    len(matched) / len(required_skills)
                ) * 100
            else:
                percentage = 0

            job['matched_skills'] = matched
            job['missing_skills'] = missing
            job['match_percentage'] = round(percentage, 2)

            # Experience matching
            required_experience = job['experience'] or ""

            experience_range = re.search(
                r'(\d+)\s*[-to]+\s*(\d+)\s*years?',
                required_experience,
                re.IGNORECASE
            )

            if 'fresher' in required_experience.lower():
                job['experience_status'] = "Suitable for Fresher"
                job['experience_match'] = True

            elif experience_range:

                minimum_years = float(experience_range.group(1))

                if resume_experience >= minimum_years:
                    job['experience_status'] = "Experience Matched"
                    job['experience_match'] = True
                else:
                    job['experience_status'] = "Experience Gap"
                    job['experience_match'] = False

            else:
                job['experience_status'] = "Check Required Experience"
                job['experience_match'] = None

            recommendations.append(job)

        # Suitable experience jobs appear first
        recommendations.sort(
            key=lambda x: (
                x['experience_match'] is not True,
                -x['match_percentage']
            )
        )

        return render_template(
            'job_recommendations.html',
            recommendations=recommendations,
            matched_resume_skills=matched_resume_skills
        )

    finally:
        cursor.close()
        connection.close()

# ==============================
# USER LOGOUT
# ==============================

@app.route('/logout')
def logout():

    session.pop('user_id', None)

    flash("You have been logged out successfully!")

    return redirect(url_for('login'))


# ==============================
# USER RESUME UPLOAD
# ==============================

@app.route('/upload-resume', methods=['GET', 'POST'])
def upload_resume():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        if 'resume' not in request.files:
            flash("Please select a resume file.")
            return redirect(url_for('upload_resume'))

        file = request.files['resume']

        if file.filename == '':
            flash("No file selected.")
            return redirect(url_for('upload_resume'))

        if not file.filename.lower().endswith('.pdf'):
            flash("Only PDF files are allowed.")
            return redirect(url_for('upload_resume'))

        file_name = secure_filename(file.filename)

        unique_file_name = str(uuid.uuid4()) + "_" + file_name

        file_path = os.path.join(UPLOAD_FOLDER, unique_file_name)

        try:
            file.save(file_path)

            pdf_document = fitz.open(file_path)

            extracted_text = ""

            for page in pdf_document:
                extracted_text += page.get_text()

            pdf_document.close()

            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO resumes
                (user_id, file_name, file_path, extracted_text)
                VALUES (%s, %s, %s, %s)
            """, (
                session['user_id'],
                file_name,
                file_path,
                extracted_text
            ))

            connection.commit()

            cursor.close()
            connection.close()

            flash("Resume Uploaded Successfully!")

        except Exception as error:

            if os.path.exists(file_path):
                os.remove(file_path)

            print("Resume Upload Error:", error)

            flash("Resume upload failed. Please try again.")

        return redirect(url_for('upload_resume'))

    return render_template('upload_resume.html')


# ==============================
# EDIT PROFILE
# ==============================

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if request.method == 'POST':

            full_name = request.form['full_name']
            email = request.form['email']
            phone = request.form['phone']

            cursor.execute("""
                UPDATE users
                SET full_name = %s, email = %s, phone = %s
                WHERE user_id = %s
            """, (full_name, email, phone, session['user_id']))

            connection.commit()

            flash("Profile updated successfully!")

            return redirect(url_for('profile'))

        cursor.execute("""
            SELECT full_name, email, phone
            FROM users
            WHERE user_id = %s
        """, (session['user_id'],))

        user = cursor.fetchone()

        return render_template('edit_profile.html', user=user)

    finally:
        cursor.close()
        connection.close()


# ==============================
# CHANGE PASSWORD
# ==============================

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT password FROM users WHERE user_id = %s",
                (session['user_id'],)
            )

            user = cursor.fetchone()

            if not user or not check_password_hash(
                user['password'], current_password
            ):
                flash("Current password is incorrect!")

            elif new_password != confirm_password:
                flash("New password and confirm password do not match!")

            elif len(new_password) < 6:
                flash("Password must contain at least 6 characters!")

            else:
                hashed_password = generate_password_hash(new_password)

                cursor.execute(
                    "UPDATE users SET password = %s WHERE user_id = %s",
                    (hashed_password, session['user_id'])
                )

                connection.commit()

                flash("Password changed successfully!")

                return redirect(url_for('profile'))

        finally:
            cursor.close()
            connection.close()

    return render_template('change_password.html')


# ==============================
# DELETE RESUME
# ==============================

@app.route('/delete-resume/<int:resume_id>', methods=['POST'])
def delete_resume(resume_id):

    if 'user_id' not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT file_path
            FROM resumes
            WHERE resume_id = %s AND user_id = %s
        """, (resume_id, session['user_id']))

        resume = cursor.fetchone()

        if resume:

            cursor.execute(
                "DELETE FROM analysis_results WHERE resume_id = %s",
                (resume_id,)
            )

            cursor.execute("""
                DELETE FROM resumes
                WHERE resume_id = %s AND user_id = %s
            """, (resume_id, session['user_id']))

            connection.commit()

            file_path = resume['file_path']

            if file_path and os.path.isfile(file_path):
                os.remove(file_path)

            flash("Resume deleted successfully!")

        else:
            flash("Resume not found!")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('profile'))


# ==============================
# ADMIN LOGOUT
# ==============================

@app.route('/admin-logout')
def admin_logout():

    session.pop('admin_id', None)
    session.pop('admin_username', None)

    return redirect(url_for('admin_login'))


# ==============================
# RUN APPLICATION
# ==============================

if __name__ == "__main__":
    app.run(debug=True)