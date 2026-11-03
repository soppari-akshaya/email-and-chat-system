import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def send_external_smtp_email(to_email, subject, body_text, body_html=None):
    """
    Sends an external email via SMTP if configured in current_app.config.
    Returns True if sent successfully, or False if skipped/failed.
    """
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")
    mail_port = current_app.config.get("MAIL_PORT", 587)
    mail_sender = current_app.config.get("MAIL_DEFAULT_SENDER") or mail_username

    if not mail_server or not mail_sender:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = mail_sender
        msg["To"] = to_email

        part1 = MIMEText(body_text, "plain")
        msg.attach(part1)

        if body_html:
            part2 = MIMEText(body_html, "html")
            msg.attach(part2)

        with smtplib.SMTP(mail_server, mail_port, timeout=10) as server:
            if current_app.config.get("MAIL_USE_TLS", True):
                server.starttls()
            if mail_username and mail_password:
                server.login(mail_username, mail_password)
            server.sendmail(mail_sender, [to_email], msg.as_string())
        return True
    except Exception as e:
        current_app.logger.warning(f"SMTP delivery failed to {to_email}: {e}")
        return False

