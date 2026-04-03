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
    """Send notifications to users with new matches."""
    import httpx

    results = context["ti"].xcom_pull(key="match_results")

    notifications_sent = 0
    for result in results:
        if len(result.get("matches", [])) > 0:
            try:
                httpx.post(
                    "http://backend:8000/api/v1/notifications/send",
                    json={
                        "user_id": result["user_id"],
                        "type": "new_matches",
                        "count": len(result["matches"]),
                    },
                    timeout=30,
                )
                notifications_sent += 1
            except Exception:
                pass

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
