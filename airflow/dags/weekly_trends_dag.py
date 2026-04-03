"""
Weekly Trends DAG

Aggregates skill demand trends from job postings.
"""

from datetime import datetime, timedelta

from airflow.operators.python import PythonOperator

from airflow import DAG

default_args = {
    "owner": "killmatch",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
}

dag = DAG(
    "weekly_trends",
    default_args=default_args,
    description="Weekly skill demand trend analysis",
    schedule_interval="0 6 * * 0",  # Every Sunday at 6 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["analytics", "trends"],
)


def analyze_trends(**context):
    """Analyze skill trends from job postings."""
    import httpx

    try:
        response = httpx.get(
            "http://mcp-jobmarket:8001/tools/get_skill_demand_trends",
            params={"timeframe": "week"},
            timeout=120,
        )
        response.raise_for_status()
        trends = response.json()
    except Exception as e:
        print(f"Error analyzing trends: {e}")
        trends = {}

    context["ti"].xcom_push(key="trends", value=trends)
    return bool(trends)


def store_trends(**context):
    """Store trend data in database."""
    import httpx

    trends = context["ti"].xcom_pull(key="trends")

    try:
        response = httpx.post(
            "http://backend:8000/api/v1/analytics/trends",
            json={"trends": trends, "week": datetime.now().isocalendar()[1]},
            timeout=60,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error storing trends: {e}")
        return False


analyze = PythonOperator(
    task_id="analyze_trends",
    python_callable=analyze_trends,
    dag=dag,
)

store = PythonOperator(
    task_id="store_trends",
    python_callable=store_trends,
    dag=dag,
)

analyze >> store
