"""
Email Notification Service

Send job match notifications via Gmail SMTP.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via Gmail SMTP."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_password:
        print("[email] SMTP credentials not configured, skipping")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Jobzilla AI <{smtp_from}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, to_email, msg.as_string())
        print(f"[email] Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[email] Failed to send to {to_email}: {e}")
        return False


def build_match_email(user_name: str, matches: list[dict]) -> str:
    """Build HTML email body for job match notifications."""
    job_rows = ""
    for match in matches[:10]:
        title = match.get("title", "Unknown Role")
        company = match.get("company", "Unknown Company")
        score = match.get("score", 0)
        score_pct = int(score * 100) if score <= 1 else int(score)
        job_rows += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <strong>{title}</strong><br>
                <span style="color: #666;">{company}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="background: #4CAF50; color: white; padding: 4px 12px; border-radius: 12px;">
                    {score_pct}%
                </span>
            </td>
        </tr>
        """

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px 12px 0 0;">
            <h1 style="color: white; margin: 0;">Jobzilla AI</h1>
            <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Your Daily Job Matches</p>
        </div>
        <div style="background: white; padding: 30px; border: 1px solid #eee; border-radius: 0 0 12px 12px;">
            <p>Hi <strong>{user_name}</strong>,</p>
            <p>We found <strong>{len(matches)} new job matches</strong> for you today!</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <th style="padding: 12px; text-align: left;">Position</th>
                    <th style="padding: 12px; text-align: center;">Match</th>
                </tr>
                {job_rows}
            </table>
            <p style="color: #666; font-size: 14px;">
                Log in to Jobzilla AI to view full details, run agent debates, and generate personalized cover letters.
            </p>
        </div>
        <p style="text-align: center; color: #999; font-size: 12px; margin-top: 20px;">
            Jobzilla AI — Your AI-Powered Job Search Companion
        </p>
    </div>
    """
