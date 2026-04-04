"""
Daily Headhunter DAG

Runs every morning to match users with new jobs and store recommendations.
"""

from datetime import datetime, timedelta

from airflow.operators.python import PythonOperator

from airflow import DAG

default_args = {
    "owner": "killmatch",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    "daily_headhunter",
    default_args=default_args,
    description="Daily job matching for all users",
    schedule_interval="0 7 * * *",  # Every day at 7 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["matching", "headhunter"],
)


def get_active_users(**context):
    """Fetch all active users with profiles."""
    import httpx

    try:
        response = httpx.get(
            "http://backend:8000/api/v1/users/active",
            timeout=60,
        )
        response.raise_for_status()
        users = response.json().get("users", [])
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []

    context["ti"].xcom_push(key="active_users", value=users)
    return len(users)


def run_matching(**context):
    """Run agent pipeline for each user."""
    import httpx

    users = context["ti"].xcom_pull(key="active_users")

    results = []
    for user in users:
        try:
            response = httpx.post(
                "http://backend:8000/api/v1/headhunter/match",
                json={"user_id": user["id"]},
                timeout=180,
            )
            if response.status_code == 200:
                results.append(
                    {
                        "user_id": user["id"],
                        "matches": response.json().get("matches", []),
                    }
                )
        except Exception as e:
            print(f"Error matching user {user['id']}: {e}")

    context["ti"].xcom_push(key="match_results", value=results)
    return len(results)


def store_recommendations(**context):
    """Store recommendations in database."""
    import httpx

    results = context["ti"].xcom_pull(key="match_results")

    try:
        response = httpx.post(
            "http://backend:8000/api/v1/recommendations/batch",
            json={"recommendations": results},
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("stored_count", 0)
    except Exception as e:
        print(f"Error storing recommendations: {e}")
        return 0


def send_notifications(**context):
    """Send email notifications to users with new matches."""
    import os
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    results = context["ti"].xcom_pull(key="match_results")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        print("[notify] SMTP not configured, skipping emails")
        return 0

    notifications_sent = 0
    for result in results:
        matches = result.get("matches", [])
        user_email = result.get("email")
        user_name = result.get("name", "there")

        if not matches or not user_email:
            continue

        # Build job list HTML
        job_rows = ""
        for match in matches[:10]:
            title = match.get("title", "Unknown Role")
            company = match.get("company", "Unknown Company")
            job_rows += f"<li><strong>{title}</strong> at {company}</li>"

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 30px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0;">Jobzilla AI</h1>
                <p style="color: rgba(255,255,255,0.9);">Your Daily Job Matches</p>
            </div>
            <div style="background: white; padding: 30px; border: 1px solid #eee;
                        border-radius: 0 0 12px 12px;">
                <p>Hi <strong>{user_name}</strong>,</p>
                <p>We found <strong>{len(matches)} new job matches</strong> for you today!</p>
                <ul>{job_rows}</ul>
                <p style="color: #666; font-size: 14px;">
                    Log in to Jobzilla AI to view details and generate cover letters.
                </p>
            </div>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Jobzilla: {len(matches)} new job matches for you!"
        msg["From"] = f"Jobzilla AI <{smtp_user}>"
        msg["To"] = user_email
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_user, user_email, msg.as_string())
            print(f"[notify] Sent email to {user_email}")
            notifications_sent += 1
        except Exception as e:
            print(f"[notify] Failed to send to {user_email}: {e}")

    print(f"[notify] Total emails sent: {notifications_sent}")
    return notifications_sent


get_users = PythonOperator(
    task_id="get_active_users",
    python_callable=get_active_users,
    dag=dag,
)

match = PythonOperator(
    task_id="run_matching",
    python_callable=run_matching,
    dag=dag,
)

store = PythonOperator(
    task_id="store_recommendations",
    python_callable=store_recommendations,
    dag=dag,
)

notify = PythonOperator(
    task_id="send_notifications",
    python_callable=send_notifications,
    dag=dag,
)

get_users >> match >> store >> notify
