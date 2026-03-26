# email_utils.py
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _markdown_to_html(md: str) -> str:
    """Convert markdown to HTML. Falls back to preformatted text if the
    'markdown' package is not installed."""
    try:
        import markdown as md_lib
        return md_lib.markdown(md, extensions=["tables", "nl2br"])
    except ImportError:
        escaped = (
            md.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
        )
        return f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{escaped}</pre>"


def send_daily_email(subject: str, body_markdown: str) -> bool:
    """
    Send an HTML+plain-text email via SMTP.

    Required GitHub Secrets (passed as environment variables):
        SMTP_USER   – sender email address
        SMTP_PASS   – sender password or app-password
        EMAIL_TO    – recipient(s), comma-separated

    Optional secrets (have sensible defaults):
        SMTP_SERVER – default: smtp.gmail.com
        SMTP_PORT   – default: 587
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port   = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user   = os.environ.get("SMTP_USER", "")
    smtp_pass   = os.environ.get("SMTP_PASS", "")
    email_to    = os.environ.get("EMAIL_TO", "")

    if not all([smtp_user, smtp_pass, email_to]):
        print("[Email] Credentials incomplete – skipping email notification.")
        return False

    recipients = [addr.strip() for addr in email_to.split(",") if addr.strip()]

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body  {{ font-family: Arial, sans-serif; max-width: 820px;
             margin: auto; padding: 24px; color: #222; }}
    h1   {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
    h2   {{ color: #2980b9; margin-top: 32px; }}
    h3   {{ color: #555; }}
    p    {{ line-height: 1.7; }}
    li   {{ margin-bottom: 6px; line-height: 1.6; }}
  </style>
</head>
<body>
{_markdown_to_html(body_markdown)}
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,     "html",  "utf-8"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
        print(f"[Email] Sent to {', '.join(recipients)}.")
        return True
    except Exception as exc:
        print(f"[Email] Failed to send: {exc}")
        return False
