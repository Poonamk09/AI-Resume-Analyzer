import os
import fitz
import uuid

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from config import get_db_connection

app = Flask(__name__)
app.secret_key = "ai_resume_analyzer_secret_key"

UPLOAD_FOLDER = "uploads/resumes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ADMIN LOGIN
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

            # Support plain-text passwords also
            if not password_valid:
                password_valid = (stored_password == password)

        if admin and password_valid:
            session['admin_id'] = admin['admin_id']
            return redirect(url_for('admin_dashboard'))

        flash("Invalid username or password")

    return render_template('admin_login.html')


# ADMIN DASHBOARD
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


# ADMIN VIEW USERS
@app.route('/admin-users')
def admin_users():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT user_id, full_name, email, phone, created_at
        FROM users
        ORDER BY user_id DESC
    """)

    users = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_users.html', users=users)

# ADMIN VIEW RESUMES
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

# ADMIN VIEW JOBS
@app.route('/admin-jobs')
def admin_jobs():

    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM jobs ORDER BY job_id DESC")
    jobs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_jobs.html', jobs=jobs)


# ADMIN ADD JOB
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
                cursor.execute(
                    """
                    INSERT INTO job_skills (job_id, skill_id)
                    VALUES (%s, %s)
                    """,
                    (job_id, int(skill_id))
                )

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


# ADMIN LOGOUT
@app.route('/admin-logout')
def admin_logout():

    session.pop('admin_id', None)

    return redirect(url_for('admin_login'))


# RUN APPLICATION
if __name__ == "__main__":
    app.run(debug=True)