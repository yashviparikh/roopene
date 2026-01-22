import smtplib
from email.mime.text import MIMEText

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
EMAIL = "apikey"
PASSWORD = "your_brevo_smtp_key"

def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)
