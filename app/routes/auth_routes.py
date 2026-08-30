import random
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.config import (
    COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    OTP_EXPIRE_MINUTES,
    TEMPLATES_DIR
)
from app.database import get_db
from app.models import User, EmailOTP
from app.auth import verify_password, get_password_hash, create_access_token
from app.services.email_service import send_otp_email_async

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

@router.post("/send-otp")
async def send_otp(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    username = username.strip()
    email = email.strip().lower()

    if len(username) < 3:
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">نام کاربری باید حداقل ۳ کاراکتر باشد.</div>', status_code=400)
    
    if len(password) < 6:
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">رمز عبور باید حداقل ۶ کاراکتر باشد.</div>', status_code=400)

    if not re.match(EMAIL_REGEX, email):
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">فرمت آدرس ایمیل نامعتبر است.</div>', status_code=400)

    # Check if user already exists
    existing = db.query(User).filter(or_(User.username == username, User.email == email)).first()
    if existing:
        if existing.email == email:
            msg = "این ایمیل قبلاً در سیستم ثبت شده است. لطفاً وارد شوید."
        else:
            msg = "این نام کاربری قبلاً انتخاب شده است."
        return HTMLResponse(f'<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">{msg}</div>', status_code=400)

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)
    pwd_hash = get_password_hash(password)

    # Invalidate previous unused OTPs for this email
    db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.is_used == False).update({"is_used": True})

    otp_record = EmailOTP(
        email=email,
        username=username,
        password_hash=pwd_hash,
        otp_code=otp_code,
        expires_at=expires_at,
        is_used=False
    )
    db.add(otp_record)
    db.commit()

    # Send Email via SMTP
    try:
        await send_otp_email_async(to_email=email, otp_code=otp_code, username=username)
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">خطا در ارسال ایمیل تایید. لطفاً اتصال اینترنت یا آدرس ایمیل را بررسی کنید. ({str(e)})</div>', status_code=500)

    # Render Step 2: OTP Verification UI
    return templates.TemplateResponse(
        request=request,
        name="components/otp_step.html",
        context={"email": email, "username": username}
    )


@router.post("/verify-otp")
async def verify_otp(
    request: Request,
    email: str = Form(...),
    otp_code: str = Form(...),
    db: Session = Depends(get_db)
):
    email = email.strip().lower()
    otp_code = otp_code.strip()

    now = datetime.utcnow()
    record = db.query(EmailOTP)\
        .filter(
            EmailOTP.email == email,
            EmailOTP.is_used == False,
            EmailOTP.expires_at > now
        )\
        .order_by(EmailOTP.created_at.desc())\
        .first()

    if not record or record.otp_code != otp_code:
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">کد تایید وارد شده نامعتبر یا منقضی شده است.</div>', status_code=400)

    # Check if already registered in the meantime
    existing = db.query(User).filter(or_(User.username == record.username, User.email == record.email)).first()
    if existing:
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">این حساب قبلاً فعال شده است. لطفاً وارد شوید.</div>', status_code=400)

    # Create User
    new_user = User(
        username=record.username,
        email=record.email,
        password_hash=record.password_hash,
        is_admin=False
    )
    db.add(new_user)
    record.is_used = True
    db.commit()
    db.refresh(new_user)

    # Generate JWT Token
    token = create_access_token(data={"sub": str(new_user.id), "username": new_user.username})

    # Return HTMX redirect response
    res = HTMLResponse('<div class="p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-300 rounded-xl text-xs mb-4 font-bold text-center">ثبت‌نام با موفقیت انجام شد! در حال انتقال...</div>')
    res.headers["HX-Redirect"] = "/dashboard"
    res.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return res


@router.post("/resend-otp")
async def resend_otp(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    email = email.strip().lower()
    record = db.query(EmailOTP).filter(EmailOTP.email == email).order_by(EmailOTP.created_at.desc()).first()
    if not record:
        return HTMLResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">اطلاعاتی برای ارسال مجدد یافت نشد.</div>', status_code=400)

    new_code = f"{random.randint(100000, 999999)}"
    record.otp_code = new_code
    record.expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)
    record.is_used = False
    db.commit()

    try:
        await send_otp_email_async(to_email=email, otp_code=new_code, username=record.username)
        return HTMLResponse('<div class="p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-300 rounded-xl text-xs mb-4">کد تایید جدید با موفقیت به ایمیل شما ارسال شد.</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">خطا در ارسال مجدد ایمیل: {str(e)}</div>', status_code=500)


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username_or_email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    val = username_or_email.strip()
    user = db.query(User).filter(or_(User.username == val, User.email == val.lower())).first()
    
    if not user or not verify_password(password, user.password_hash):
        error_msg = "نام کاربری/ایمیل یا رمز عبور اشتباه است."
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">{error_msg}</div>', status_code=400)
        return RedirectResponse(f"/login?error={error_msg}", status_code=302)

    token = create_access_token(data={"sub": str(user.id), "username": user.username})
    target_redirect = "/admin" if user.is_admin else "/dashboard"

    if request.headers.get("HX-Request"):
        res = HTMLResponse("")
        res.headers["HX-Redirect"] = target_redirect
        res.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax"
        )
        return res
    else:
        redirect = RedirectResponse(target_redirect, status_code=302)
        redirect.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax"
        )
        return redirect


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
