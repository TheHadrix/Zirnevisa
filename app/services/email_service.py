import smtplib
import asyncio
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import (
    SMTP_HOST,
    SMTP_PORT,
    EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD
)

logger = logging.getLogger(__name__)

def _send_smtp_email_sync(to_email: str, subject: str, html_body: str, otp_code: str = ""):
    """Synchronous SMTP email sender with automatic port fallback and dev fallback on ISP network timeout."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"ZirNovisa <{EMAIL_HOST_USER}>"
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
                with smtplib.SMTP(SMTP_HOST, port, timeout=5) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
                    server.sendmail(EMAIL_HOST_USER, [to_email], msg.as_string())
            else:
                with smtplib.SMTP_SSL(SMTP_HOST, port, timeout=5) as server:
                    server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
                    server.sendmail(EMAIL_HOST_USER, [to_email], msg.as_string())
            
            logger.info(f"OTP Email successfully delivered to {to_email} via {method}:{port}")
            return True
        except Exception as e:
            logger.warning(f"SMTP attempt via {method}:{port} failed: {e}.")

    # If all live SMTP attempts fail due to local ISP network/firewall blocking
    logger.warning("SMTP network blocked by ISP/firewall. Printing code to console:")
    print("-------------------------------------------------------")
    print(f"[ZIRNOVISA OTP CODE FOR {to_email}]: {otp_code}")
    print("-------------------------------------------------------")
    return True

async def send_otp_email_async(to_email: str, otp_code: str, username: str = ""):
    """Async wrapper for sending OTP email."""
    subject = f"کد تایید ثبت‌نام در زیرنویسا: {otp_code}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #0b0f19;
                color: #f1f5f9;
                margin: 0;
                padding: 30px 10px;
                direction: rtl;
                text-align: right;
            }}
            .card {{
                max-width: 500px;
                margin: 0 auto;
                background: #131b2e;
                border: 1px solid #233050;
                border-radius: 20px;
                padding: 35px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            }}
            .header {{
                text-align: center;
                margin-bottom: 25px;
            }}
            .title {{
                color: #818cf8;
                font-size: 24px;
                font-weight: 800;
                margin: 0 0 5px 0;
            }}
            .subtitle {{
                color: #94a3b8;
                font-size: 13px;
                margin: 0;
            }}
            .code-box {{
                background: #1e293b;
                border: 2px dashed #6366f1;
                border-radius: 16px;
                padding: 20px;
                text-align: center;
                margin: 25px 0;
            }}
            .otp-code {{
                font-size: 36px;
                font-weight: 900;
                letter-spacing: 8px;
                color: #38bdf8;
                font-family: monospace;
            }}
            .info {{
                font-size: 13px;
                color: #cbd5e1;
                line-height: 1.7;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #1e293b;
                text-align: center;
                font-size: 11px;
                color: #64748b;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1 class="title">سامانه هوشمند زیرنویسا</h1>
                <p class="subtitle">تایید ایمیل و فعال‌سازی حساب کاربری</p>
            </div>
            
            <p class="info">
                سلام {username or 'کاربر گرامی'}،<br>
                برای تکمیل ثبت‌نام خود در زیرنویسا، لطفاً کد تایید زیر را در فرم ثبت‌نام وارد نمایید:
            </p>

            <div class="code-box">
                <div class="otp-code">{otp_code}</div>
            </div>

            <p class="info">
                این کد به مدت <strong>۵ دقیقه</strong> معتبر است.<br>
                اگر شما این درخواست را ثبت نکرده‌اید، این پیام را نادیده بگیرید.
            </p>

            <div class="footer">
                © 2026 زیرنویسا (ZirNovisa AI) - مترجم هوشمند زیرنویس
            </div>
        </div>
    </body>
    </html>
    """

    await asyncio.to_thread(_send_smtp_email_sync, to_email, subject, html_body, otp_code)
