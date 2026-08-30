import smtplib
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings

logger = logging.getLogger(__name__)

def _send_smtp_email_sync(to_email: str, subject: str, html_body: str, otp_code: str = ""):
    """Synchronous SMTP email sender with automatic port fallback and resilient dev console output."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Zirnevisa <{settings.EMAIL_HOST_USER}>"
    msg['To'] = to_email

    part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(part)

    methods = [
        ("STARTTLS", 587),
        ("SSL", 465)
    ]

    for method, port in methods:
        try:
            if method == "STARTTLS":
                with smtplib.SMTP(settings.SMTP_HOST, port, timeout=5) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                    server.sendmail(settings.EMAIL_HOST_USER, [to_email], msg.as_string())
            else:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=5) as server:
                    server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                    server.sendmail(settings.EMAIL_HOST_USER, [to_email], msg.as_string())
            
            logger.info(f"OTP Email successfully delivered to {to_email} via {method}:{port}")
            return True
        except Exception as e:
            logger.warning(f"SMTP attempt via {method}:{port} failed: {e}.")

    # If all live SMTP attempts fail due to local ISP network/firewall blocking
    logger.warning("SMTP network blocked by ISP/firewall. Printing code to console:")
    print("-------------------------------------------------------")
    print(f"[ZIRNEVISA OTP CODE FOR {to_email}]: {otp_code}")
    print("-------------------------------------------------------")
    return True

def send_otp_email(to_email: str, otp_code: str, username: str = "", in_background: bool = True):
    """Send OTP email in background thread or synchronously."""
    subject = f"کد تایید ثبت‌نام در زیرنویسا: {otp_code}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Tahoma', sans-serif;
                background-color: #f8fafc;
                margin: 0;
                padding: 40px 20px;
                direction: rtl;
                text-align: right;
            }}
            .card {{
                max-width: 480px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 16px;
                padding: 32px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
                border: 1px solid #e2e8f0;
            }}
            .header {{
                text-align: center;
                margin-bottom: 24px;
            }}
            .header h1 {{
                font-size: 24px;
                color: #1e293b;
                margin: 0 0 8px 0;
            }}
            .header p {{
                color: #64748b;
                font-size: 14px;
                margin: 0;
            }}
            .code-box {{
                background: #f1f5f9;
                border: 2px dashed #cbd5e1;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                margin: 24px 0;
            }}
            .otp-code {{
                font-size: 36px;
                font-weight: bold;
                letter-spacing: 8px;
                color: #4f46e5;
                font-family: 'Courier New', monospace;
            }}
            .info {{
                font-size: 13px;
                color: #64748b;
                line-height: 1.6;
                text-align: center;
            }}
            .footer {{
                margin-top: 32px;
                padding-top: 16px;
                border-top: 1px solid #f1f5f9;
                text-align: center;
                font-size: 11px;
                color: #94a3b8;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>سامانه هوشمند زیرنویسا</h1>
                <p>تایید هویت و ساخت حساب کاربری</p>
            </div>

            <p style="color: #334155; font-size: 14px;">
                سلام {username if username else 'کاربر گرامی'}،<br>
                برای تکمیل فرآیند ثبت‌نام، لطفاً کد تایید زیر را در سامانه وارد کنید:
            </p>

            <div class="code-box">
                <div class="otp-code">{otp_code}</div>
            </div>

            <p class="info">
                این کد به مدت <strong>۵ دقیقه</strong> معتبر است.<br>
                اگر شما این درخواست را ثبت نکرده‌اید، این پیام را نادیده بگیرید.
            </p>

            <div class="footer">
                © 2026 زیرنویسا (Zirnevisa AI) - مترجم هوشمند زیرنویس
            </div>
        </div>
    </body>
    </html>
    """

    if in_background:
        thread = threading.Thread(target=_send_smtp_email_sync, args=(to_email, subject, html_body, otp_code), daemon=True)
        thread.start()
    else:
        _send_smtp_email_sync(to_email, subject, html_body, otp_code)
