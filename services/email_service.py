"""
ASAP Food Trailer - Email Notification Service
Sends email notifications for new leads/contact form submissions.
Uses Gmail SMTP with App Password.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


class EmailService:
    """Send email notifications via Gmail SMTP."""

    def __init__(self):
        self.smtp_email = os.getenv("SMTP_EMAIL", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.notify_email = os.getenv("NOTIFY_EMAIL", self.smtp_email)
        self.enabled = bool(self.smtp_email and self.smtp_password)
        if not self.enabled:
            print(
                "WARNING: Email not configured (set SMTP_EMAIL + SMTP_PASSWORD env vars)"
            )

    def send_lead_notification(self, lead_data: dict) -> bool:
        """Send email notification when a new lead is received."""
        if not self.enabled:
            print("Email skipped: not configured")
            return False

        try:
            name = lead_data.get("customer_name", "Unknown")
            email = lead_data.get("email", "N/A")
            phone = lead_data.get("phone", "N/A")
            message = lead_data.get("message", "No message")
            truck_id = lead_data.get("truck_id", "")
            now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

            subject = f"🚛 New Lead from ASAP Food Trailer - {name}"

            html = f"""
            <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.1);">
                <div style="background:linear-gradient(135deg,#ff6b00,#ff8c33);padding:28px 32px;text-align:center;">
                    <h1 style="color:#fff;margin:0;font-size:22px;">🚛 New Lead Received!</h1>
                    <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">{now}</p>
                </div>
                <div style="padding:28px 32px;">
                    <table style="width:100%;border-collapse:collapse;">
                        <tr style="border-bottom:1px solid #f0f0f0;">
                            <td style="padding:12px 0;color:#888;font-size:13px;width:100px;">Name</td>
                            <td style="padding:12px 0;font-weight:600;font-size:15px;">{name}</td>
                        </tr>
                        <tr style="border-bottom:1px solid #f0f0f0;">
                            <td style="padding:12px 0;color:#888;font-size:13px;">Email</td>
                            <td style="padding:12px 0;font-size:15px;"><a href="mailto:{email}" style="color:#ff6b00;text-decoration:none;">{email}</a></td>
                        </tr>
                        <tr style="border-bottom:1px solid #f0f0f0;">
                            <td style="padding:12px 0;color:#888;font-size:13px;">Phone</td>
                            <td style="padding:12px 0;font-size:15px;"><a href="tel:{phone}" style="color:#ff6b00;text-decoration:none;">{phone or 'N/A'}</a></td>
                        </tr>
                        {"<tr style='border-bottom:1px solid #f0f0f0;'><td style='padding:12px 0;color:#888;font-size:13px;'>Vehicle</td><td style='padding:12px 0;font-size:15px;'>" + truck_id + "</td></tr>" if truck_id else ""}
                        <tr>
                            <td style="padding:12px 0;color:#888;font-size:13px;vertical-align:top;">Message</td>
                            <td style="padding:12px 0;font-size:15px;line-height:1.5;">{message or 'No message provided'}</td>
                        </tr>
                    </table>
                </div>
                <div style="background:#f8f9fa;padding:16px 32px;text-align:center;">
                    <p style="margin:0;color:#999;font-size:12px;">ASAP Food Trailer — Lead Notification System</p>
                </div>
            </div>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"ASAP Food Trailer <{self.smtp_email}>"
            msg["To"] = self.notify_email
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.smtp_email, self.smtp_password)
                server.sendmail(self.smtp_email, self.notify_email, msg.as_string())

            print(f"Email sent to {self.notify_email} for lead: {name}")
            return True
        except Exception as e:
            print(f"Email send error: {e}")
            return False


email_service = EmailService()
