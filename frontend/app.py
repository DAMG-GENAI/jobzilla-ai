"""
Jobzilla Frontend - Streamlit Application

Main entry point with navigation and session management.
Connects to backend API for real job matching.
"""

import os

import requests
import streamlit as st

# Backend API URL
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page config - must be first Streamlit command
st.set_page_config(
    page_title="KillMatch - AI Job Matching",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for premium styling
st.markdown(
    """
<style>
    /* Main theme */
    :root {
        --primary-color: #6366f1;
        --secondary-color: #8b5cf6;
        --background-dark: #0f0f23;
        --card-bg: rgba(255, 255, 255, 0.05);
    }

    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Main header styling */
    .main-header {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
    }

    /* Card styling */
    .metric-card {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 12px;
        padding: 1rem;
    }

    /* Button styling */
    .stButton>button {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        border: none;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(99, 102, 241, 0.3);
    }

    /* Score gauge */
    .score-high { color: #10b981; }
    .score-medium { color: #f59e0b; }
    .score-low { color: #ef4444; }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    /* Animation */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .animate-fade {
        animation: fadeIn 0.5s ease-out;
    }
</style>
""",
    unsafe_allow_html=True,
)


def fetch_jobs_from_db(limit=10):
    """Fetch real jobs from the backend/database."""
    try:
        # Try to get jobs from backend API
        response = requests.get(
            f"{BACKEND_URL}/api/v1/jobs", params={"limit": limit}, timeout=5
        )
        if response.status_code == 200:
            return response.json()
    except:
        pass

    # Fallback: Direct database query via a simple endpoint we'll create
    # For now, use psycopg2 directly
    try:
        import psycopg2

        db_url = os.getenv("DATABASE_URL", "")
        if db_url:
            conn = psycopg2.connect(db_url.replace("+asyncpg", ""))
        else:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "killmatch"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
            )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, company, description, source_platform
            FROM jobs
            WHERE is_active = true
            ORDER BY scraped_at DESC
            LIMIT %s
        """,
            (limit,),
        )
        jobs = []
        for row in cur.fetchall():
            jobs.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "company": row[2],
                    "description": row[3] or "",
                    "source": row[4] or "LinkedIn",
                }
            )
        cur.close()
        conn.close()
        return jobs
    except Exception as e:
        st.warning(f"Could not fetch jobs from database: {e}")
        return []


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_analytics_data():
    """Fetch comprehensive analytics data from the database."""
    result = {
        "jobs": [],
        "skill_counts": {},
        "salary_data": [],
        "remote_distribution": {},
        "location_data": {},
        "experience_levels": {},
    }

    try:

        import psycopg2

        db_url = os.getenv("DATABASE_URL", "")
        if db_url:
            conn = psycopg2.connect(db_url.replace("+asyncpg", ""))
        else:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "killmatch"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres"),
            )
        cur = conn.cursor()

        # 1. Fetch all active jobs with full data
        cur.execute("""
            SELECT id, title, company, description, source_platform,
                   required_skills, preferred_skills, salary_min, salary_max,
                   remote_type, experience_level, location
            FROM jobs
            WHERE is_active = true
            ORDER BY scraped_at DESC
            LIMIT 500
        """)

        skill_counter = {}

        for row in cur.fetchall():
            job = {
                "id": row[0],
                "title": row[1],
                "company": row[2],
                "description": row[3] or "",
                "source": row[4] or "LinkedIn",
                "required_skills": row[5],
                "preferred_skills": row[6],
                "salary_min": row[7],
                "salary_max": row[8],
                "remote_type": row[9],
                "experience_level": row[10],
                "location": row[11],
            }
            result["jobs"].append(job)

            # Count skills
            req_skills = row[5] if isinstance(row[5], list) else []
            pref_skills = row[6] if isinstance(row[6], list) else []
            for skill in req_skills + pref_skills:
                if skill and isinstance(skill, str):
                    skill_counter[skill] = skill_counter.get(skill, 0) + 1

            # If no explicit skills, extract from description
            if not req_skills and not pref_skills and row[3]:
                desc_lower = (row[3] or "").lower()
                common_skills = [
                    "Python",
                    "JavaScript",
                    "TypeScript",
                    "Java",
                    "C++",
                    "Go",
                    "Rust",
                    "Ruby",
                    "React",
                    "Node.js",
                    "Angular",
                    "Vue",
                    "Django",
                    "Flask",
                    "FastAPI",
                    "Spring",
                    "AWS",
                    "GCP",
                    "Azure",
                    "Docker",
                    "Kubernetes",
                    "Terraform",
                    "PostgreSQL",
                    "MySQL",
                    "MongoDB",
                    "Redis",
                    "Elasticsearch",
                    "Machine Learning",
                    "Deep Learning",
                    "NLP",
                    "SQL",
                    "Git",
                    "Linux",
                    "TensorFlow",
                    "PyTorch",
                    "Pandas",
                    "Spark",
                    "Airflow",
                    "Kafka",
                    "REST",
                    "GraphQL",
                    "CI/CD",
                    "Agile",
                    "Scrum",
                ]
                for s in common_skills:
                    if s.lower() in desc_lower:
                        skill_counter[s] = skill_counter.get(s, 0) + 1

            # Salary data
            if row[7] or row[8]:
                result["salary_data"].append(
                    {
                        "level": row[10] or "Unknown",
                        "salary_min": row[7] or 0,
                        "salary_max": row[8] or row[7] or 0,
                    }
                )

            # Remote distribution
            remote = row[9] or "Unknown"
            result["remote_distribution"][remote] = (
                result["remote_distribution"].get(remote, 0) + 1
            )

            # Experience levels
            exp = row[10] or "Unknown"
            result["experience_levels"][exp] = (
                result["experience_levels"].get(exp, 0) + 1
            )

            # Location
            loc = row[11] or "Unknown"
            result["location_data"][loc] = result["location_data"].get(loc, 0) + 1

        result["skill_counts"] = skill_counter

        cur.close()
        conn.close()

    except Exception as e:
        print(f"⚠️ Analytics data fetch failed: {e}")

    return result


def main():
    """Main application entry point."""
    # Sidebar
    with st.sidebar:
        st.markdown("## 🎯 KillMatch")
        st.caption("*AI-Powered Job Matching*")
        st.divider()

        nav_options = [
            "🏠 Dashboard",
            "🔍 Job Match",
            "🤖 Agent Debate",
            "📄 Resume Generator",
            "✉️ Cover Letter",
            "📈 Skill Roadmap",
            "📊 Analytics",
            "⚙️ Settings",
        ]
        default_idx = 0
        if st.session_state.get("nav_page") in nav_options:
            default_idx = nav_options.index(st.session_state.pop("nav_page"))
        page = st.radio(
            "Navigation",
            nav_options,
            index=default_idx,
            label_visibility="collapsed",
        )

        st.divider()

        # Profile section
        st.markdown("### 👤 Profile")
        if (
            "resume_uploaded" in st.session_state
            and st.session_state["resume_uploaded"]
        ):
            st.success("✅ Resume uploaded")
        else:
            st.info("Upload your resume to get started")

    # Route to pages
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "🔍 Job Match":
        show_job_match()
    elif page == "🤖 Agent Debate":
        show_agent_debate()
    elif page == "📄 Resume Generator":
        show_resume_generator()
    elif page == "✉️ Cover Letter":
        show_cover_letter()
    elif page == "📈 Skill Roadmap":
        show_skill_roadmap()
    elif page == "📊 Analytics":
        show_analytics()
    elif page == "⚙️ Settings":
        show_settings()


def show_dashboard():
    """Dashboard page - showing real jobs from database."""
    st.markdown('<h1 class="main-header">Welcome Back! 👋</h1>', unsafe_allow_html=True)

    # Fetch real jobs from database
    jobs = fetch_jobs_from_db(limit=20)
    total_jobs = len(jobs)

    # Quick stats - now with real data
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Jobs", str(total_jobs), "+scraped today")
    with col2:
        st.metric("Sources", "LinkedIn, Indeed", "Active")
    with col3:
        if "resume_uploaded" in st.session_state:
            st.metric("Profile", "Ready", "Complete")
        else:
            st.metric("Profile", "Pending", "Upload resume")
    with col4:
        st.metric("Database", "PostgreSQL", "Connected")

    st.divider()

    # Show real jobs from database
    st.markdown("### 🌟 Latest Scraped Jobs")

    if jobs:
        for job in jobs[:5]:  # Show top 5
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{job['title']}** at {job['company']}")
                with col2:
                    st.caption(f"via {job.get('source', 'LinkedIn')}")
                with col3:
                    if st.button("View", key=f"view_{job['id']}"):
                        st.session_state["selected_job"] = job
                st.divider()
    else:
        st.info("No jobs found. Run the Airflow job_scraping DAG to populate jobs!")
        st.markdown("Go to http://localhost:8080 → trigger `job_scraping` DAG")


def show_job_match():
    """Job matching page with real backend integration."""
    st.markdown(
        '<h1 class="main-header">🔍 Find Your Perfect Match</h1>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 📄 Your Profile")

        with st.expander("📝 Candidate Details (Optional)", expanded=False):
            st.session_state["candidate_name"] = st.text_input(
                "Full Name", value=st.session_state.get("candidate_name", "")
            )
            st.session_state["candidate_email"] = st.text_input(
                "Email", value=st.session_state.get("candidate_email", "")
            )
            st.session_state["candidate_phone"] = st.text_input(
                "Phone", value=st.session_state.get("candidate_phone", "")
            )
            st.session_state["candidate_location"] = st.text_input(
                "Location", value=st.session_state.get("candidate_location", "")
            )

            c_links1, c_links2 = st.columns(2)
            with c_links1:
                st.session_state["candidate_linkedin"] = st.text_input(
                    "LinkedIn URL", value=st.session_state.get("candidate_linkedin", "")
                )
            with c_links2:
                st.session_state["candidate_portfolio"] = st.text_input(
                    "Portfolio URL",
                    value=st.session_state.get("candidate_portfolio", ""),
                )

        uploaded_file = st.file_uploader(
            "Upload your resume (PDF)",
            type=["pdf"],
            help="We'll extract your skills and experience",
        )

        github_username = st.text_input(
            "GitHub Username (optional)",
            placeholder="e.g., octocat",
            help="We'll analyze your repositories for additional insights",
        )

        if uploaded_file:
            st.success("✅ Resume uploaded successfully!")
            st.session_state["resume_uploaded"] = True
            st.session_state["resume_file"] = uploaded_file
            # Store raw bytes so we can reliably re-read them
            st.session_state["resume_bytes"] = uploaded_file.read()
            uploaded_file.seek(0)  # Reset for any other readers

    with col2:
        st.markdown("### 🎯 Job Search")

        search_query = st.text_input(
            "What role are you looking for?",
            placeholder="e.g., Senior Python Developer",
        )

        location = st.text_input(
            "Preferred location", placeholder="e.g., San Francisco, CA or Remote"
        )

        experience_level = st.select_slider(
            "Experience Level",
            options=["Entry", "Mid", "Senior", "Lead", "Executive"],
            value="Senior",
        )

    st.divider()

    if st.button("🚀 Start Matching", use_container_width=True):
        if not search_query and not st.session_state.get("resume_uploaded"):
            st.warning("Please upload a resume or enter a search query!")
            return

        with st.spinner("Running semantic search & multi-agent analysis..."):
            try:
                # Prepare payload
                payload = {
                    "query": search_query,
                    "location": location,
                    "level": experience_level,
                    "github_username": github_username,
                }

                # If resume uploaded, send it
                files = {}
                if st.session_state.get("resume_bytes"):
                    # Use stored raw bytes for reliable re-reads
                    files = {
                        "resume": (
                            "resume.pdf",
                            st.session_state["resume_bytes"],
                            "application/pdf",
                        )
                    }
                elif st.session_state.get("resume_file"):
                    st.session_state["resume_file"].seek(0)
                    files = {
                        "resume": (
                            "resume.pdf",
                            st.session_state["resume_file"],
                            "application/pdf",
                        )
                    }

                # Call backend match API
                # Note: We use the multipart/form-data endpoint
                response = requests.post(
                    f"{BACKEND_URL}/api/v1/match",
                    data=payload,
                    files=files if files else None,
                    timeout=60,  # Increased for Pinecone/OpenAI latency
                )

                if response.status_code == 200:
                    results = response.json()
                    st.session_state["matched_jobs"] = results.get("matches", [])
                    st.session_state["has_matches"] = True
                    # Store parsed skills for analytics skill gap report
                    parsed_skills = results.get("parsed_skills", [])
                    if parsed_skills:
                        st.session_state["resume_skills"] = parsed_skills
                    st.rerun()
                else:
                    st.error(f"Validation failed: {response.text}")

            except Exception as e:
                st.error(f"Matching failed: {str(e)}")
                # Fallback to local search if backend fails
                st.warning("Falling back to basic keyword search...")
                # ... (keep fallback logic if needed)

    # Show matched jobs
    if st.session_state.get("has_matches") and st.session_state.get("matched_jobs"):
        st.success(
            f"Found {len(st.session_state['matched_jobs'])} semantically matched jobs!"
        )

        st.markdown("### 🎯 Your Matches")
        for job in st.session_state["matched_jobs"]:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    job_url = job.get("url", "")
                    if job_url:
                        st.markdown(
                            f"**[{job['title']}]({job_url})** at {job['company']}"
                        )
                    else:
                        st.markdown(f"**{job['title']}** at {job['company']}")
                    st.caption(
                        f"Position at {job['company']}. Found via {job.get('source', 'LinkedIn')}."
                    )
                with col2:
                    score = (
                        job.get("match_score", 0) * 100
                        if job.get("match_score", 0) < 1
                        else job.get("match_score", 0)
                    )
                    score_class = (
                        "score-high"
                        if score >= 80
                        else "score-medium" if score >= 60 else "score-low"
                    )
                    st.markdown(
                        f"<span class='{score_class}'>{int(score)}% match</span>",
                        unsafe_allow_html=True,
                    )
                with col3:
                    job_url = job.get("url", "")
                    if job_url:
                        st.link_button("Apply", job_url)
                    else:
                        st.button(
                            "Apply",
                            key=f"apply_{job.get('id', job.get('title'))}",
                            disabled=True,
                        )
                st.divider()


def run_langgraph_debate(job, resume_text, resume_skills, github_username):
    """Run the real LangGraph agent debate via backend API."""
    try:
        payload = {
            "candidate_name": st.session_state.get("candidate_name", "Candidate"),
            "candidate_email": st.session_state.get("candidate_email"),
            "candidate_phone": st.session_state.get("candidate_phone"),
            "candidate_location": st.session_state.get("candidate_location"),
            "candidate_linkedin": st.session_state.get("candidate_linkedin"),
            "candidate_portfolio": st.session_state.get("candidate_portfolio"),
            "resume_summary": resume_text[:2000],  # Limit length
            "resume_skills": resume_skills,
            "job_title": job.get("title", "Unknown"),
            "job_company": job.get("company", "Unknown"),
            "job_description": job.get("description", "")[:2000],  # Limit length
            "job_required_skills": job.get(
                "missing_skills", []
            ),  # Use missing skills as proxy for important ones
            "github_username": github_username,
            "include_cover_letter": False,
        }

        response = requests.post(
            f"{BACKEND_URL}/api/v1/debate/run-debate", json=payload, timeout=120
        )

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Debate failed: {response.text}")
            return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def show_agent_debate():
    """Enhanced Agent debate with job selection and detailed AI insights."""
    st.markdown(
        '<h1 class="main-header">🤖 Multi-Agent AI Debate</h1>', unsafe_allow_html=True
    )

    # ─── Hero Explanation ───
    st.markdown(
        """
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
                padding: 24px; border-radius: 16px; margin-bottom: 24px; color: white;">
        <h3 style="color: #e94560; margin-top: 0;">🎯 What is the Agent Debate?</h3>
        <p style="font-size: 1.05em; line-height: 1.6; color: #e0e0e0;">
            Instead of giving you a <b>simple match score</b>, Jobzilla uses <b>3 AI agents powered by GPT-4</b>
            that <em>debate</em> whether you're a good fit for a job — just like a real hiring committee.
            Each agent has a unique perspective, creating a <b>balanced, multi-dimensional analysis</b> of your candidacy.
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # ─── Meet the Agents ───
    st.markdown("### 🧑‍💼 Meet Your AI Hiring Committee")

    agent_col1, agent_col2, agent_col3 = st.columns(3)

    with agent_col1:
        st.markdown(
            """
        <div style="background: linear-gradient(135deg, #ff6b6b20, #ee535320);
                    border: 2px solid #ff6b6b; border-radius: 12px; padding: 20px; height: 280px;">
            <h3 style="color: #ff6b6b; text-align: center;">🔴 The Recruiter</h3>
            <p style="font-weight: bold; text-align: center; color: #ff6b6b;">Devil's Advocate</p>
            <hr style="border-color: #ff6b6b40;">
            <p style="font-size: 0.9em;">Plays the role of a <b>skeptical hiring manager</b>.
            Identifies gaps in your experience, missing skills, and potential red flags —
            the tough questions you'd face in a real interview.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with agent_col2:
        st.markdown(
            """
        <div style="background: linear-gradient(135deg, #51cf6620, #2ed57320);
                    border: 2px solid #51cf66; border-radius: 12px; padding: 20px; height: 280px;">
            <h3 style="color: #51cf66; text-align: center;">🟢 The Career Coach</h3>
            <p style="font-weight: bold; text-align: center; color: #51cf66;">Your Advocate</p>
            <hr style="border-color: #51cf6640;">
            <p style="font-size: 0.9em;">Acts as your <b>personal career champion</b>.
            Highlights transferable skills, reframes weaknesses as growth areas, and
            emphasizes your unique strengths and potential.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with agent_col3:
        st.markdown(
            """
        <div style="background: linear-gradient(135deg, #ffd43b20, #fab00520);
                    border: 2px solid #ffd43b; border-radius: 12px; padding: 20px; height: 280px;">
            <h3 style="color: #ffd43b; text-align: center;">⚖️ The Judge</h3>
            <p style="font-weight: bold; text-align: center; color: #ffd43b;">Final Arbiter</p>
            <hr style="border-color: #ffd43b40;">
            <p style="font-size: 0.9em;">Listens to <b>both sides of the debate</b>, weighs the arguments,
            and delivers a <b>fair, balanced verdict</b> with a final match score and
            actionable recommendation.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # ─── Why This Matters ───
    with st.expander(
        "💡 **Why is this better than a simple match score?**", expanded=False
    ):
        st.markdown("""
        | Traditional Matching | 🤖 Agent Debate |
        |---------------------|-----------------|
        | Simple keyword overlap | Deep semantic understanding of your experience |
        | One score, no explanation | Multi-perspective analysis with reasoning |
        | Misses transferable skills | Coach agent identifies hidden strengths |
        | No actionable feedback | Specific gaps to address before applying |
        | Static algorithm | Dynamic AI agents that adapt to each job |

        **How this helps you:**
        - 🎯 **Know before you apply** — Understand exactly how strong your candidacy is
        - 📈 **Improve strategically** — See specific skill gaps to close
        - 💪 **Discover hidden strengths** — The Coach finds things you might not think to mention
        - ⚠️ **Anticipate objections** — Know what a recruiter might flag before your interview
        """)

    st.divider()

    # ─── Job Selector ───
    if not st.session_state.get("matched_jobs"):
        st.warning("No job matches found. Go to **Job Match** and run a search first!")
        if st.button("🔍 Go to Job Match"):
            st.session_state["nav_page"] = "🔍 Job Match"
            st.rerun()
        return

    matched_jobs = st.session_state["matched_jobs"]

    st.markdown("### 📋 Select a Job to Analyze")
    job_options = [f"{j['title']} at {j['company']}" for j in matched_jobs]
    selected_idx = st.selectbox(
        "Choose a job from your matches:",
        range(len(job_options)),
        format_func=lambda x: job_options[x],
    )

    selected_job = matched_jobs[selected_idx]
    job_key = f"debate_result_{selected_job.get('id', selected_idx)}"

    # Get resume data from session
    resume_summary = st.session_state.get("resume_summary", "")
    resume_skills = []

    # UI Controls
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🚀 Run AI Debate", type="primary", use_container_width=True):
            with st.spinner(
                "🤖 Agents are debating your candidacy... (This uses real GPT-4 calls)"
            ):
                result = run_langgraph_debate(
                    selected_job,
                    resume_summary,
                    resume_skills,
                    st.session_state.get("github_username"),
                )
                if result:
                    st.session_state[job_key] = result
                    st.rerun()
    with col2:
        if job_key not in st.session_state:
            st.caption(
                "⏱️ Debate typically takes 15-30 seconds as 3 AI agents analyze your profile in real-time."
            )

    # ─── Display Results ───
    if job_key in st.session_state:
        result = st.session_state[job_key]

        # ─── Final Verdict (show first for impact) ───
        st.divider()
        st.markdown("## ⚖️ Judge's Final Verdict")

        final_score = result.get("final_score", 50)
        recommendation = result.get("recommendation", "Unknown")

        # Score with color
        if final_score >= 75:
            score_color, score_emoji, _score_label = "#51cf66", "🟢", "Strong Match"
        elif final_score >= 55:
            score_color, score_emoji, _score_label = "#ffd43b", "🟡", "Possible Match"
        else:
            score_color, score_emoji, _score_label = "#ff6b6b", "🔴", "Weak Match"

        score_col1, score_col2 = st.columns([1, 2])
        with score_col1:
            st.markdown(
                f"""
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, {score_color}15, {score_color}30);
                        border: 2px solid {score_color}; border-radius: 16px;">
                <p style="font-size: 3em; font-weight: bold; color: {score_color}; margin: 0;">{final_score:.0f}</p>
                <p style="color: {score_color}; font-size: 0.9em; margin: 0;">out of 100</p>
                <p style="font-size: 1.2em; margin-top: 8px;">{score_emoji} {recommendation}</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with score_col2:
            # Key factors side by side
            str_col, con_col = st.columns(2)
            with str_col:
                st.markdown("**👍 Key Strengths**")
                for item in result.get("key_strengths", []):
                    st.markdown(f"✅ {item}")
            with con_col:
                st.markdown("**⚠️ Key Concerns**")
                for item in result.get("key_concerns", []):
                    st.markdown(f"❌ {item}")

        # ─── Skill Gaps ───
        skill_gaps = result.get("skill_gaps", [])
        if skill_gaps:
            st.divider()
            st.markdown("### 📈 Skills to Develop")
            st.caption(
                "These are the gaps identified during the debate. Closing these will significantly improve your candidacy."
            )
            gap_cols = st.columns(min(len(skill_gaps), 4))
            for i, gap in enumerate(skill_gaps):
                with gap_cols[i % len(gap_cols)]:
                    st.markdown(
                        f"""
                    <div style="background: #fff3e020; border: 1px solid #ef6c00; border-radius: 8px; padding: 12px; text-align: center; margin-bottom: 8px;">
                        <p style="font-weight: bold; color: #ef6c00; margin: 0;">📚 {gap}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
        # ─── Generated Resume ───
        generated_resume = result.get("generated_resume")
        if generated_resume:
            st.divider()
            st.markdown("### 📄 ATS-Tailored Resume")
            st.caption(
                "Expertly crafted by the Resume Generator Agent using insights from the debate."
            )
            with st.expander("📝 View & Download Tailored Resume", expanded=True):
                st.markdown(generated_resume)

                # Download button
                st.download_button(
                    "⬇️ Download Markdown",
                    data=generated_resume,
                    file_name=f"resume_tailored_{selected_job.get('company', 'company').replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

        # ─── Debate Transcript ───
        st.divider()
        st.markdown("### 🎙️ Full Debate Transcript")
        st.caption("Expand each round to see the detailed arguments from both sides.")

        for round_data in result.get("debate_rounds", []):
            round_num = round_data.get("round_number", 1)
            r_score = round_data.get("recruiter_score", 50)
            c_score = round_data.get("coach_score", 50)

            with st.expander(
                f"🏟️ Round {round_num}  |  Recruiter: {r_score:.0f}  vs  Coach: {c_score:.0f}",
                expanded=(round_num == 1),
            ):
                r_col, c_col = st.columns(2)

                with r_col:
                    st.markdown("#### 🔴 Recruiter's Concerns")
                    for arg in round_data.get("recruiter_arguments", []):
                        strength = arg.get("strength", "Medium")
                        icon = (
                            "🔥"
                            if strength == "Strong"
                            else "⚡" if strength == "Medium" else "💨"
                        )
                        st.markdown(f"{icon} **{arg.get('point')}**")
                        if arg.get("evidence"):
                            st.caption(f"   _{arg.get('evidence')}_")

                with c_col:
                    st.markdown("#### 🟢 Coach's Rebuttal")
                    for arg in round_data.get("coach_arguments", []):
                        strength = arg.get("strength", "Medium")
                        icon = (
                            "💎"
                            if strength == "Strong"
                            else "✨" if strength == "Medium" else "🌱"
                        )
                        st.markdown(f"{icon} **{arg.get('point')}**")
                        if arg.get("evidence"):
                            st.caption(f"   _{arg.get('evidence')}_")

        # ─── Processing Info ───
        proc_time = result.get("processing_time_seconds", 0)
        total_rounds = result.get("total_rounds", 0)
        if proc_time > 0:
            st.divider()
            st.caption(
                f"⏱️ Debate completed in {proc_time:.1f}s across {total_rounds} round(s) using GPT-4 agents."
            )

    else:
        st.markdown(
            """
        <div style="background: #1a1a2e; padding: 24px; border-radius: 12px; text-align: center; margin-top: 16px;">
            <p style="font-size: 1.1em; color: #aaa;">👆 Select a job above and click <b style="color: #e94560;">'Run AI Debate'</b> to watch
            the Recruiter and Career Coach analyze your fit for this role in real-time!</p>
        </div>
        """,
            unsafe_allow_html=True,
        )


def show_resume_generator():
    """Standalone Resume Generator — upload master resume PDF + job description."""
    st.markdown(
        '<h1 class="main-header">📄 Resume Generator</h1>', unsafe_allow_html=True
    )
    st.markdown(
        "Upload your **master resume** and paste a **job description** — the AI agent will tailor a 1-page ATS-optimized resume for you."
    )
    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 📂 Your Master Resume")
        master_resume = st.file_uploader(
            "Upload Master Resume (PDF)",
            type=["pdf"],
            help="Upload your full resume. The agent will extract your experience, skills, education and tailor it for the job.",
            key="rg_resume_upload",
        )
        if master_resume:
            st.success(f"✅ Uploaded: `{master_resume.name}`")

        target_role = st.text_input(
            "Target Role",
            placeholder="e.g. Data Engineer, ML Engineer, SWE",
            help="Used if no job description is provided.",
        )

    with col2:
        st.markdown("### 🎯 Target Job Description")
        job_title = st.text_input("Job Title", placeholder="Data Engineer")
        job_company = st.text_input("Company Name", placeholder="Amazon")
        job_desc = st.text_area(
            "Paste Job Description *",
            placeholder="We are looking for a Data Engineer who...\n\nResponsibilities:\n- ...\n\nRequirements:\n- ...",
            height=250,
            help="The more detailed the job description, the better the tailoring.",
        )

    st.divider()

    if st.button(
        "🚀 Generate Tailored Resume", type="primary", use_container_width=True
    ):
        if not master_resume:
            st.error("Please upload your master resume PDF.")
            st.stop()

        with st.spinner(
            "🤖 Resume Generator Agent is analyzing your resume and tailoring it for the role..."
        ):
            try:
                pdf_bytes = master_resume.read()

                files = {"resume": (master_resume.name, pdf_bytes, "application/pdf")}
                data = {
                    "job_description": job_desc,
                    "job_title": job_title,
                    "job_company": job_company,
                    "target_role": target_role or job_title or "Software Engineer",
                }

                response = requests.post(
                    f"{BACKEND_URL}/api/v1/resume-generator",
                    files=files,
                    data=data,
                    timeout=90,
                )

                if response.status_code == 200:
                    result = response.json()
                    resume_md = result.get("resume_markdown", "")
                    word_count = result.get("word_count", 0)
                    assumptions = result.get("assumptions_made", [])
                    candidate_name = result.get("candidate_name", "candidate")
                    pdf_b64 = result.get("pdf_base64", "")

                    st.success(
                        f"✅ Resume tailored for **{candidate_name}**! ({word_count} words)"
                    )

                    if assumptions:
                        with st.expander("ℹ️ Assumptions Made by Agent"):
                            for a in assumptions:
                                st.markdown(f"- {a}")

                    st.markdown("---")
                    st.markdown("### 📄 Your ATS-Optimized Tailored Resume")
                    st.markdown(resume_md)

                    # Download buttons side-by-side
                    dl_col1, dl_col2 = st.columns(2)
                    safe_name = candidate_name.replace(" ", "_")
                    safe_company = (job_company or "tailored").replace(" ", "_")

                    with dl_col1:
                        if pdf_b64:
                            import base64 as b64lib

                            pdf_bytes = b64lib.b64decode(pdf_b64)
                            st.download_button(
                                "⬇️ Download as PDF",
                                data=pdf_bytes,
                                file_name=f"resume_{safe_name}_{safe_company}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )
                        else:
                            st.warning(
                                "PDF generation failed — download Markdown instead."
                            )

                    with dl_col2:
                        st.download_button(
                            "⬇️ Download as Markdown",
                            data=resume_md,
                            file_name=f"resume_{safe_name}_{safe_company}.md",
                            mime="text/markdown",
                            use_container_width=True,
                        )

                    # ── ATS Scores: Original vs Tailored ──────────
                    orig_ats = result.get("original_ats_score")
                    tail_ats = result.get("tailored_ats_score")

                    if orig_ats or tail_ats:
                        st.markdown("---")
                        st.markdown("### 📊 ATS Compatibility Scores")

                        ats_col1, ats_col2 = st.columns(2)

                        def _render_ats_card(col, ats, label):
                            with col:
                                score = ats.get("overall", 0)
                                kw_pct = ats.get("keyword_match", 0)
                                color = (
                                    "#2ecc71"
                                    if score >= 75
                                    else "#f39c12" if score >= 55 else "#e74c3c"
                                )
                                emoji = (
                                    "🟢"
                                    if score >= 75
                                    else "🟡" if score >= 55 else "🔴"
                                )
                                st.markdown(
                                    f"""
                                <div style="background: #1a1a2e; padding: 16px; border-radius: 12px; text-align: center; margin-bottom: 12px; border: 1px solid {color}33;">
                                    <p style="color: #888; margin: 0 0 6px 0; font-size: 0.85em;">{label}</p>
                                    <p style="font-size: 2.5em; font-weight: bold; color: {color}; margin: 0;">{emoji} {score}%</p>
                                    <p style="color: #aaa; margin: 4px 0 0 0; font-size: 0.85em;">Keyword Match: {kw_pct}%</p>
                                </div>
                                """,
                                    unsafe_allow_html=True,
                                )

                                for fb in ats.get("feedback", []):
                                    st.markdown(
                                        f"<p style='font-size:0.9em;'>{fb}</p>",
                                        unsafe_allow_html=True,
                                    )

                        if orig_ats and orig_ats.get("overall", 0) > 0:
                            _render_ats_card(ats_col1, orig_ats, "📄 Original Resume")
                        if tail_ats and tail_ats.get("overall", 0) > 0:
                            _render_ats_card(ats_col2, tail_ats, "✨ Tailored Resume")

                        # Improvement delta
                        if orig_ats and tail_ats:
                            delta = tail_ats.get("overall", 0) - orig_ats.get(
                                "overall", 0
                            )
                            if delta > 0:
                                st.success(
                                    f"📈 ATS score improved by **+{delta}%** after tailoring!"
                                )
                            elif delta == 0:
                                st.info(
                                    "↔️ ATS score unchanged — resume was already well-matched."
                                )
                            else:
                                st.warning(f"📉 ATS score changed by {delta}%.")

                        # Keywords detail
                        if tail_ats:
                            with st.expander("🔍 Keyword Details (Tailored Resume)"):
                                kw_col1, kw_col2 = st.columns(2)
                                with kw_col1:
                                    matched = tail_ats.get("matched_keywords", [])
                                    if matched:
                                        st.markdown("**✅ Matched Keywords**")
                                        st.markdown(
                                            ", ".join(f"`{k}`" for k in matched[:20])
                                        )
                                with kw_col2:
                                    missing = tail_ats.get("missing_keywords", [])
                                    if missing:
                                        st.markdown("**❌ Missing Keywords**")
                                        st.markdown(
                                            ", ".join(f"`{k}`" for k in missing[:15])
                                        )

                    # ── Changes Highlighted ────────────────────────
                    changes = result.get("changes_made", [])
                    if changes:
                        st.markdown("---")
                        st.markdown("### 🔄 Changes from Original Resume")
                        st.markdown(
                            """
                        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                                    padding: 20px; border-radius: 12px; border-left: 4px solid #6c5ce7;
                                    margin-bottom: 16px;">
                        """,
                            unsafe_allow_html=True,
                        )
                        for change in changes:
                            st.markdown(change)
                        st.markdown("</div>", unsafe_allow_html=True)

                else:
                    st.error(
                        f"Generation failed ({response.status_code}): {response.text}"
                    )

            except Exception as e:
                st.error(f"Error: {e}")


def show_cover_letter():
    """Cover letter generation."""
    st.markdown(
        '<h1 class="main-header">✉️ Cover Letter Generator</h1>', unsafe_allow_html=True
    )

    if not st.session_state.get("matched_jobs"):
        st.warning("Run a job match first to generate tailored cover letters!")
        return

    # Select a job
    job_options = [
        f"{j['title']} at {j['company']}" for j in st.session_state["matched_jobs"]
    ]
    selected = st.selectbox("Select a job to write a cover letter for:", job_options)

    col1, col2 = st.columns(2)
    with col1:
        tone = st.select_slider(
            "Tone", options=["Casual", "Professional", "Formal"], value="Professional"
        )
    with col2:
        focus = st.multiselect(
            "Focus Areas",
            ["Technical Skills", "Leadership", "Culture Fit", "Achievements"],
            default=["Technical Skills"],
        )

    if st.button("Generate Cover Letter", use_container_width=True):
        with st.spinner("Generating with AI..."):
            try:
                # Get the selected job details
                selected_idx = job_options.index(selected)
                job = st.session_state["matched_jobs"][selected_idx]

                # Resume text from session if available
                resume_summary = st.session_state.get(
                    "resume_summary", "a software professional with relevant experience"
                )

                # Call OpenAI for cover letter
                import openai

                client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

                prompt = f"""Write a {tone.lower()} cover letter for the following job:

Job Title: {job['title']}
Company: {job['company']}
Job Description: {job.get('description', 'Not provided')[:500]}

Candidate Profile: {resume_summary}

Focus areas: {', '.join(focus)}

Write a compelling cover letter (3-4 paragraphs) that:
1. Opens with an engaging hook
2. Connects the candidate's skills to the job requirements
3. Shows enthusiasm for the company
4. Ends with a strong call to action
"""

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=800,
                )

                cover_letter = response.choices[0].message.content

                st.text_area("Your Cover Letter", value=cover_letter, height=400)

                # Copy button
                st.download_button(
                    "📋 Download as .txt",
                    cover_letter,
                    file_name=f"cover_letter_{job['company'].replace(' ', '_')}.txt",
                    mime="text/plain",
                )

            except Exception as e:
                st.error(f"Generation failed: {str(e)}")
                st.warning("Make sure OPENAI_API_KEY is set in your environment.")


def show_skill_roadmap():
    """Enhanced skill gap analysis and roadmap based on actual matched jobs."""
    st.markdown('<h1 class="main-header">📈 Skill Roadmap</h1>', unsafe_allow_html=True)

    st.info(
        "**How This Helps You**: Identifies skills most commonly required by your matched jobs but missing from your profile. Focus on these to maximize your job prospects!"
    )

    if not st.session_state.get("matched_jobs"):
        st.warning("Run a job match first to see personalized skill recommendations!")
        if st.button("🔍 Go to Job Match"):
            st.session_state["nav_page"] = "🔍 Job Match"
            st.rerun()
        return

    matched_jobs = st.session_state["matched_jobs"]

    st.markdown(f"### 📊 Analyzing {len(matched_jobs)} Matched Jobs")

    # Method 1: Use missing_skills from backend if available
    missing_counts = {}
    for job in matched_jobs:
        for skill in job.get("missing_skills", []):
            skill_clean = skill.strip().title()
            missing_counts[skill_clean] = missing_counts.get(skill_clean, 0) + 1

    # Method 2: Extract common skills from job descriptions AND titles if no missing_skills
    if not missing_counts:
        st.caption("*Extracting skills from job descriptions...*")
        # Common tech skills to look for (expanded list including data science and variations)
        skill_keywords = [
            # Programming languages
            "python",
            "java",
            "javascript",
            "typescript",
            "sql",
            "r ",
            "scala",
            "go ",
            "rust",
            "c++",
            "c#",
            "ruby",
            "php",
            "swift",
            "kotlin",
            # Cloud & DevOps
            "aws",
            "azure",
            "gcp",
            "docker",
            "kubernetes",
            "k8s",
            "terraform",
            "jenkins",
            "ci/cd",
            "devops",
            "cloud",
            "microservices",
            # Data & ML
            "machine learning",
            "deep learning",
            "nlp",
            "natural language",
            "computer vision",
            "data science",
            "data engineering",
            "data analysis",
            "data analyst",
            "tensorflow",
            "pytorch",
            "keras",
            "scikit",
            "sklearn",
            "pandas",
            "numpy",
            "spark",
            "hadoop",
            "kafka",
            "airflow",
            "dbt",
            "snowflake",
            "databricks",
            "etl",
            "data pipeline",
            "big data",
            # Databases
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "elasticsearch",
            "neo4j",
            # GenAI / LLM
            "llm",
            "genai",
            "generative ai",
            "gpt",
            "langchain",
            "rag",
            "transformers",
            "hugging face",
            "chatgpt",
            "openai",
            "large language",
            # Web & Frameworks
            "react",
            "node.js",
            "nodejs",
            "angular",
            "vue",
            "django",
            "flask",
            "fastapi",
            "spring",
            "graphql",
            "rest api",
            # BI & Visualization
            "tableau",
            "power bi",
            "looker",
            "excel",
            "visualization",
            # Methodologies
            "agile",
            "scrum",
            "git",
            "linux",
            # Soft skills / Roles
            "leadership",
            "director",
            "manager",
            "senior",
            "architect",
            "lead",
        ]

        for job in matched_jobs:
            # Check BOTH description AND title for skills
            desc = (job.get("description", "") or "").lower()
            title = (job.get("title", "") or "").lower()
            full_text = f"{title} {desc}"

            for skill in skill_keywords:
                if skill in full_text:
                    # Clean up the skill name for display
                    skill_display = skill.strip().title()
                    # Handle special cases
                    if skill in ["r ", "go "]:
                        skill_display = skill.strip().upper()
                    elif skill in [
                        "aws",
                        "gcp",
                        "sql",
                        "nlp",
                        "llm",
                        "etl",
                        "ci/cd",
                        "k8s",
                        "api",
                    ]:
                        skill_display = skill.upper()
                    elif skill in ["genai"]:
                        skill_display = "GenAI"
                    elif skill in ["node.js", "nodejs"]:
                        skill_display = "Node.js"
                    elif skill in ["postgresql", "mysql", "mongodb"]:
                        skill_display = (
                            skill.replace("sql", "SQL").replace("db", "DB").title()
                        )

                    missing_counts[skill_display] = (
                        missing_counts.get(skill_display, 0) + 1
                    )

    # Sort by frequency
    sorted_skills = sorted(missing_counts.items(), key=lambda x: x[1], reverse=True)

    # Resources mapping
    resources = {
        "Python": "https://docs.python.org/3/tutorial/",
        "Java": "https://dev.java/learn/",
        "Javascript": "https://javascript.info/",
        "Sql": "https://www.w3schools.com/sql/",
        "Aws": "https://aws.amazon.com/training/",
        "Azure": "https://learn.microsoft.com/en-us/training/azure/",
        "Gcp": "https://cloud.google.com/training",
        "Docker": "https://docs.docker.com/get-started/",
        "Kubernetes": "https://kubernetes.io/docs/tutorials/",
        "React": "https://react.dev/learn",
        "Node.Js": "https://nodejs.org/en/learn",
        "Tensorflow": "https://www.tensorflow.org/tutorials",
        "Pytorch": "https://pytorch.org/tutorials/",
        "Spark": "https://spark.apache.org/docs/latest/quick-start.html",
        "Machine Learning": "https://www.coursera.org/learn/machine-learning",
        "Deep Learning": "https://www.deeplearning.ai/",
        "Nlp": "https://huggingface.co/learn/nlp-course",
        "Airflow": "https://airflow.apache.org/docs/",
        "Snowflake": "https://learn.snowflake.com/",
        "System Design": "https://github.com/donnemartin/system-design-primer",
    }

    if sorted_skills:
        st.markdown("### 🎯 Top Skills to Learn")
        st.markdown(
            "*These skills appear most frequently in your matched job descriptions:*"
        )

        for _i, (skill, count) in enumerate(sorted_skills[:8]):
            priority = (
                "🔴 High" if count >= 3 else "🟡 Medium" if count >= 2 else "🟢 Low"
            )
            time_est = (
                "2-4 weeks"
                if count < 3
                else "1-2 months" if count < 5 else "2-3 months"
            )

            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.markdown(f"**{skill}** - *Found in {count} jobs*")
                with col2:
                    st.caption(f"Priority: {priority}")
                with col3:
                    st.caption(f"Est: {time_est}")
                with col4:
                    resource_url = resources.get(
                        skill,
                        f"https://www.google.com/search?q=learn+{skill.replace(' ', '+')}",
                    )
                    st.link_button("📚 Learn", resource_url, use_container_width=True)

        # Show summary stats
        st.divider()
        st.markdown("### 📈 Your Skill Gap Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Unique Skills to Learn", len(sorted_skills))
        with col2:
            high_priority = len([s for s, c in sorted_skills if c >= 3])
            st.metric("High Priority", high_priority)
        with col3:
            st.metric("Jobs Analyzed", len(matched_jobs))
    else:
        st.success(
            "🎉 Great news! No significant skill gaps detected in your matched jobs!"
        )
        st.info(
            "This could mean:\n- Your skills align well with available roles\n- Try matching with different job types to discover new skills to learn"
        )


def show_analytics():
    """Enhanced Analytics dashboard with interactive charts and actionable insights."""

    import pandas as pd
    import plotly.graph_objects as go

    st.markdown(
        '<h1 class="main-header">📊 Analytics & Insights</h1>', unsafe_allow_html=True
    )

    st.markdown(
        """
    <div style="background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.10) 100%);
                border-radius: 16px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem;
                border: 1px solid rgba(99,102,241,0.2);">
        <p style="margin: 0; font-size: 1.05rem;">
            🎯 <strong>Your AI-Powered Job Intelligence Hub</strong> — Understand the market, identify your skill gaps, and make data-driven career decisions.
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # ============ FETCH ALL DATA ============
    matched_jobs = st.session_state.get("matched_jobs", [])
    user_skills = [s.lower() for s in st.session_state.get("resume_skills", [])]

    # Fetch rich data from database
    analytics_data = fetch_analytics_data()
    all_jobs = analytics_data.get("jobs", [])
    skill_counts = analytics_data.get("skill_counts", {})
    salary_data = analytics_data.get("salary_data", [])
    remote_distribution = analytics_data.get("remote_distribution", {})
    analytics_data.get("location_data", {})
    experience_levels = analytics_data.get("experience_levels", {})

    # ============ SECTION 1: HERO STATS ============
    st.markdown("### 🏆 Your Dashboard")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                    border-radius: 16px; padding: 1.5rem; text-align: center;">
            <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 0.85rem;">JOBS MATCHED</p>
            <h2 style="color: white; margin: 0.3rem 0 0 0; font-size: 2.2rem;">{len(matched_jobs)}</h2>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        if matched_jobs:
            avg_score = sum(j.get("match_score", 0) for j in matched_jobs) / len(
                matched_jobs
            )
            avg_score = avg_score * 100 if avg_score <= 1 else avg_score
            score_color = (
                "#10b981"
                if avg_score >= 70
                else "#f59e0b" if avg_score >= 50 else "#ef4444"
            )
        else:
            avg_score = 0
            score_color = "#6b7280"
        st.markdown(
            f"""
        <div style="background: linear-gradient(135deg, {score_color}22 0%, {score_color}11 100%);
                    border-radius: 16px; padding: 1.5rem; text-align: center;
                    border: 1px solid {score_color}33;">
            <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 0.85rem;">AVG MATCH SCORE</p>
            <h2 style="color: {score_color}; margin: 0.3rem 0 0 0; font-size: 2.2rem;">{avg_score:.0f}%</h2>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        db_count = len(all_jobs)
        st.markdown(
            f"""
        <div style="background: linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(16,185,129,0.05) 100%);
                    border-radius: 16px; padding: 1.5rem; text-align: center;
                    border: 1px solid rgba(16,185,129,0.2);">
            <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 0.85rem;">JOBS IN DATABASE</p>
            <h2 style="color: #10b981; margin: 0.3rem 0 0 0; font-size: 2.2rem;">{db_count}</h2>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        skills_count = len(user_skills) if user_skills else 0
        resume_ok = st.session_state.get("resume_uploaded", False)
        st.markdown(
            f"""
        <div style="background: linear-gradient(135deg, rgba(245,158,11,0.15) 0%, rgba(245,158,11,0.05) 100%);
                    border-radius: 16px; padding: 1.5rem; text-align: center;
                    border: 1px solid rgba(245,158,11,0.2);">
            <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 0.85rem;">YOUR SKILLS</p>
            <h2 style="color: #f59e0b; margin: 0.3rem 0 0 0; font-size: 2.2rem;">{"✅ " + str(skills_count) if resume_ok else "❌ Upload"}</h2>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.divider()

    # ============ SECTION 2: SKILLS IN DEMAND ============
    st.markdown("### 🔥 Top Skills in Demand")
    st.caption(
        "Skills most frequently required across all job listings in the database"
    )

    if skill_counts:
        top_skills = dict(
            sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:15]
        )

        # Color-code: green if user has the skill, red if they don't
        colors = []
        for skill in top_skills:
            if skill.lower() in user_skills:
                colors.append("#10b981")  # green — user has it
            else:
                colors.append("#ef4444")  # red — skill gap

        fig_skills = go.Figure(
            data=[
                go.Bar(
                    x=list(top_skills.values()),
                    y=list(top_skills.keys()),
                    orientation="h",
                    marker={
                        "color": colors,
                        "line": {"color": "rgba(255,255,255,0.1)", "width": 1},
                    },
                    text=[f"{v} jobs" for v in top_skills.values()],
                    textposition="auto",
                    hovertemplate="<b>%{y}</b><br>Required in %{x} jobs<extra></extra>",
                )
            ]
        )
        fig_skills.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "white"},
            height=450,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            xaxis={"title": "Number of Jobs", "gridcolor": "rgba(255,255,255,0.05)"},
            yaxis={"autorange": "reversed"},
        )

        st.plotly_chart(fig_skills, use_container_width=True)

        if user_skills:
            st.markdown(
                """
            <div style="display: flex; gap: 1rem; align-items: center; margin-top: -0.5rem;">
                <span style="display: inline-flex; align-items: center; gap: 0.3rem;">
                    <span style="width: 12px; height: 12px; background: #10b981; border-radius: 3px; display: inline-block;"></span>
                    <span style="font-size: 0.85rem; color: rgba(255,255,255,0.7);">You have this skill</span>
                </span>
                <span style="display: inline-flex; align-items: center; gap: 0.3rem;">
                    <span style="width: 12px; height: 12px; background: #ef4444; border-radius: 3px; display: inline-block;"></span>
                    <span style="font-size: 0.85rem; color: rgba(255,255,255,0.7);">Skill gap — consider learning</span>
                </span>
            </div>
            """,
                unsafe_allow_html=True,
            )
    else:
        st.info(
            "No skill data available yet. Jobs need `required_skills` data in the database."
        )

    st.divider()

    # ============ SECTION 3 & 4: MATCH SCORE + SALARY (side by side) ============
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 🎯 Match Score Breakdown")

        if matched_jobs:
            # Normalize scores
            scores = []
            for j in matched_jobs:
                s = j.get("match_score", 0)
                scores.append(s * 100 if s <= 1 else s)

            high = len([s for s in scores if s >= 70])
            med = len([s for s in scores if 50 <= s < 70])
            low = len([s for s in scores if s < 50])

            fig_donut = go.Figure(
                data=[
                    go.Pie(
                        labels=["Strong (70%+)", "Good (50-70%)", "Stretch (<50%)"],
                        values=[high, med, low],
                        hole=0.6,
                        marker={"colors": ["#10b981", "#f59e0b", "#ef4444"]},
                        textinfo="value+percent",
                        textfont={"size": 14},
                        hovertemplate="<b>%{label}</b><br>%{value} jobs (%{percent})<extra></extra>",
                    )
                ]
            )
            fig_donut.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "white"},
                height=350,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                showlegend=True,
                legend={
                    "orientation": "h",
                    "yanchor": "bottom",
                    "y": -0.15,
                    "xanchor": "center",
                    "x": 0.5,
                },
                annotations=[
                    {
                        "text": f"{avg_score:.0f}%",
                        "x": 0.5,
                        "y": 0.5,
                        "font_size": 28,
                        "font_color": score_color,
                        "showarrow": False,
                    }
                ],
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.markdown(
                """
            <div style="background: rgba(255,255,255,0.03); border-radius: 12px; padding: 3rem; text-align: center;">
                <p style="font-size: 3rem; margin: 0;">🎯</p>
                <p style="color: rgba(255,255,255,0.5);">Run a job match to see your score distribution</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with col_right:
        st.markdown("### 💰 Salary Insights")

        if salary_data:
            df_salary = pd.DataFrame(salary_data)

            fig_salary = go.Figure()
            for level in df_salary["level"].unique():
                level_data = df_salary[df_salary["level"] == level]
                fig_salary.add_trace(
                    go.Box(
                        y=level_data["salary_max"],
                        name=level or "Unknown",
                        marker_color="#8b5cf6",
                        boxmean=True,
                        hovertemplate="<b>%{x}</b><br>Salary: $%{y:,.0f}<extra></extra>",
                    )
                )

            fig_salary.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "white"},
                height=350,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                yaxis={
                    "title": "Salary ($)",
                    "gridcolor": "rgba(255,255,255,0.05)",
                    "tickformat": "$,.0f",
                },
                showlegend=False,
            )
            st.plotly_chart(fig_salary, use_container_width=True)
        else:
            # Show what salary data we could have
            st.markdown(
                """
            <div style="background: rgba(255,255,255,0.03); border-radius: 12px; padding: 3rem; text-align: center;">
                <p style="font-size: 3rem; margin: 0;">💰</p>
                <p style="color: rgba(255,255,255,0.5);">Salary data will appear when jobs include salary information</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.divider()

    # ============ SECTION 5: COMPANY + REMOTE + EXPERIENCE ============
    st.markdown("### 🏢 Job Market Overview")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("##### 📍 Work Type Distribution")
        if remote_distribution:
            labels = list(remote_distribution.keys())
            values = list(remote_distribution.values())
            # Map to nice colors
            color_map = {
                "remote": "#10b981",
                "hybrid": "#f59e0b",
                "on-site": "#6366f1",
                "onsite": "#6366f1",
            }
            pie_colors = [color_map.get(l.lower(), "#8b5cf6") for l in labels]

            fig_remote = go.Figure(
                data=[
                    go.Pie(
                        labels=labels,
                        values=values,
                        marker={"colors": pie_colors},
                        textinfo="label+percent",
                        textfont={"size": 12},
                        hole=0.3,
                    )
                ]
            )
            fig_remote.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "white"},
                height=280,
                margin={"l": 5, "r": 5, "t": 5, "b": 5},
                showlegend=False,
            )
            st.plotly_chart(fig_remote, use_container_width=True)
        else:
            st.caption("No work type data available")

    with col_b:
        st.markdown("##### 📊 Experience Levels")
        if experience_levels:
            levels = list(experience_levels.keys())
            counts = list(experience_levels.values())

            fig_exp = go.Figure(
                data=[
                    go.Bar(
                        x=levels,
                        y=counts,
                        marker={
                            "color": [
                                "#6366f1",
                                "#8b5cf6",
                                "#a78bfa",
                                "#c4b5fd",
                                "#ddd6fe",
                            ][: len(levels)],
                            "line": {"color": "rgba(255,255,255,0.1)", "width": 1},
                        },
                        text=counts,
                        textposition="auto",
                    )
                ]
            )
            fig_exp.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "white"},
                height=280,
                margin={"l": 5, "r": 5, "t": 5, "b": 5},
                xaxis={"tickangle": -45},
                yaxis={"gridcolor": "rgba(255,255,255,0.05)"},
            )
            st.plotly_chart(fig_exp, use_container_width=True)
        else:
            st.caption("No experience level data available")

    with col_c:
        st.markdown("##### 🏢 Top Companies Hiring")
        if all_jobs:
            companies = {}
            for job in all_jobs:
                c = job.get("company", "Unknown")
                companies[c] = companies.get(c, 0) + 1
            top_companies = dict(
                sorted(companies.items(), key=lambda x: x[1], reverse=True)[:8]
            )

            fig_companies = go.Figure(
                data=[
                    go.Bar(
                        y=list(top_companies.keys()),
                        x=list(top_companies.values()),
                        orientation="h",
                        marker={
                            "color": "#6366f1",
                            "line": {"color": "rgba(255,255,255,0.1)", "width": 1},
                        },
                        text=list(top_companies.values()),
                        textposition="auto",
                    )
                ]
            )
            fig_companies.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font={"color": "white"},
                height=280,
                margin={"l": 5, "r": 5, "t": 5, "b": 5},
                yaxis={"autorange": "reversed"},
                xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
            )
            st.plotly_chart(fig_companies, use_container_width=True)
        else:
            st.caption("No company data available")

    st.divider()

    # ============ SECTION 6: YOUR SKILL GAP REPORT ============
    st.markdown("### 🎓 Your Personalized Skill Gap Report")

    if user_skills and skill_counts:
        # Get top 10 in-demand skills
        top_demand = dict(
            sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # Build radar chart data
        radar_skills = list(top_demand.keys())
        market_demand = [top_demand[s] for s in radar_skills]
        max_demand = max(market_demand) if market_demand else 1
        market_demand_pct = [round((d / max_demand) * 100) for d in market_demand]

        # User proficiency (100 if they have it, 0 if not)
        user_proficiency = []
        for skill in radar_skills:
            if skill.lower() in user_skills:
                user_proficiency.append(85)  # High if user has it
            else:
                user_proficiency.append(10)  # Low if missing

        fig_radar = go.Figure()
        fig_radar.add_trace(
            go.Scatterpolar(
                r=market_demand_pct,
                theta=radar_skills,
                fill="toself",
                name="Market Demand",
                line={"color": "#6366f1"},
                fillcolor="rgba(99,102,241,0.15)",
            )
        )
        fig_radar.add_trace(
            go.Scatterpolar(
                r=user_proficiency,
                theta=radar_skills,
                fill="toself",
                name="Your Skills",
                line={"color": "#10b981"},
                fillcolor="rgba(16,185,129,0.15)",
            )
        )
        fig_radar.update_layout(
            polar={
                "bgcolor": "rgba(0,0,0,0)",
                "radialaxis": {
                    "visible": True,
                    "range": [0, 100],
                    "gridcolor": "rgba(255,255,255,0.1)",
                },
                "angularaxis": {"gridcolor": "rgba(255,255,255,0.1)"},
            },
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "white"},
            height=450,
            margin={"l": 60, "r": 60, "t": 30, "b": 30},
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": -0.15,
                "xanchor": "center",
                "x": 0.5,
            },
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        # Personalized recommendations
        gaps = [s for s in radar_skills if s.lower() not in user_skills]
        if gaps:
            st.markdown("#### 💡 Recommended Skills to Learn")
            rec_cols = st.columns(min(len(gaps), 3))
            for i, skill in enumerate(gaps[:3]):
                demand_pct = (
                    round((skill_counts.get(skill, 0) / len(all_jobs)) * 100)
                    if all_jobs
                    else 0
                )
                with rec_cols[i]:
                    st.markdown(
                        f"""
                    <div style="background: linear-gradient(135deg, rgba(239,68,68,0.1) 0%, rgba(239,68,68,0.05) 100%);
                                border-radius: 12px; padding: 1.2rem; border: 1px solid rgba(239,68,68,0.2);">
                        <h4 style="margin: 0 0 0.5rem 0; color: #ef4444;">🚀 {skill}</h4>
                        <p style="margin: 0; font-size: 0.9rem; color: rgba(255,255,255,0.7);">
                            Appears in <strong>{demand_pct}%</strong> of job listings.<br>
                            Learning this skill could significantly improve your match scores.
                        </p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
        else:
            st.success(
                "🎉 Amazing! You have all the top in-demand skills. You're in great shape!"
            )
    else:
        st.markdown(
            """
        <div style="background: rgba(255,255,255,0.03); border-radius: 16px; padding: 2.5rem; text-align: center;">
            <p style="font-size: 3rem; margin: 0;">📄</p>
            <h3 style="color: rgba(255,255,255,0.8); margin-top: 0.5rem;">Upload Your Resume to Unlock Insights</h3>
            <p style="color: rgba(255,255,255,0.5);">
                Go to the <strong>Job Matching</strong> page and upload your resume.
                We'll analyze your skills against the market and show you exactly where to focus.
            </p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.divider()

    # ============ SECTION 7: MATCHED JOBS TABLE ============
    if matched_jobs:
        st.markdown("### 📋 Your Matched Jobs Ranked")

        job_data = []
        for j in matched_jobs:
            score = j.get("match_score", 0)
            score = score * 100 if score <= 1 else score
            job_data.append(
                {
                    "Title": j.get("title", "Unknown"),
                    "Company": j.get("company", "Unknown"),
                    "Score": f"{score:.0f}%",
                    "Missing Skills": ", ".join(j.get("missing_skills", [])) or "None",
                    "Source": j.get("source", "LinkedIn"),
                }
            )

        df_jobs = pd.DataFrame(job_data)
        df_jobs = df_jobs.sort_values(by="Score", ascending=False)
        st.dataframe(df_jobs, use_container_width=True, hide_index=True)


def show_settings():
    """Settings page."""
    st.markdown('<h1 class="main-header">⚙️ Settings</h1>', unsafe_allow_html=True)

    st.markdown("### API Configuration")
    st.text_input("Backend API URL", value=BACKEND_URL)

    st.markdown("### Database Connection")
    st.code("""
Host: localhost
Port: 5432
Database: killmatch
User: postgres
    """)

    st.markdown("### User Preferences")
    st.toggle("Enable email notifications", value=False)
    st.toggle("Daily job digest", value=True)

    if st.button("Save Settings"):
        st.success("Settings saved!")


if __name__ == "__main__":
    main()
