import random
import re
from datetime import timedelta
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.conf import settings

from accounts.models import User, EmailOTP
from translations.services.email_service import send_otp_email

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

def normalize_digits(text: str) -> str:
    """Convert Persian and Arabic numerals to standard English digits."""
    if not text:
        return ""
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for p, e in zip(persian_digits, '0123456789'):
        text = text.replace(p, e)
    for a, e in zip(arabic_digits, '0123456789'):
        text = text.replace(a, e)
    return text.strip()


def login_view(request):
    """Handle user login for both standard form and HTMX submissions with clear visual error messaging."""
    if request.user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        val = request.POST.get('username_or_email', '').strip()
        password = request.POST.get('password', '')

        if not val or not password:
            error_msg = "لطفاً نام کاربری/ایمیل و رمز عبور را وارد کنید."
        else:
            user = User.objects.filter(Q(username__iexact=val) | Q(email__iexact=val)).first()
            if user and user.check_password(password):
                login(request, user)
                target = '/admin-panel/' if (user.is_staff or user.is_superuser) else '/dashboard/'
                
                if request.headers.get('HX-Request'):
                    response = HttpResponse('')
                    response['HX-Redirect'] = target
                    return response
                return redirect(target)
            else:
                error_msg = "نام کاربری/ایمیل یا رمز عبور اشتباه است. لطفاً مجدداً بررسی کنید."

        # Return formatted error component for HTMX or standard template render
        if request.headers.get('HX-Request'):
            return HttpResponse(
                f'''<div class="p-3.5 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-400 rounded-2xl text-xs font-bold flex items-center gap-2.5 mb-4 shadow-sm">
                    <svg class="w-5 h-5 shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span>{error_msg}</span>
                </div>''',
                status=200
            )
        return render(request, 'login.html', {'error': error_msg})

    return render(request, 'login.html')


def register_view(request):
    """Render registration page."""
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'register.html')


@require_http_methods(["POST"])
def send_otp_view(request):
    """Validate registration details, generate OTP, send email, and return Step 2 component."""
    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip().lower()
    password = request.POST.get('password', '')

    if len(username) < 3:
        return HttpResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">نام کاربری باید حداقل ۳ کاراکتر باشد.</div>', status=200)

    if len(password) < 6:
        return HttpResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">رمز عبور باید حداقل ۶ کاراکتر باشد.</div>', status=200)

    if not re.match(EMAIL_REGEX, email):
        return HttpResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">فرمت آدرس ایمیل نامعتبر است.</div>', status=200)

    # Check existing user
    if User.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).exists():
        if User.objects.filter(email__iexact=email).exists():
            msg = "این ایمیل قبلاً در سیستم ثبت شده است. لطفاً وارد شوید."
        else:
            msg = "این نام کاربری قبلاً انتخاب شده است."
        return HttpResponse(f'<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">{msg}</div>', status=200)

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = timezone.now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    pwd_hash = make_password(password)

    # Invalidate previous unused OTPs for this email
    EmailOTP.objects.filter(email=email, is_used=False).update(is_used=True)

    EmailOTP.objects.create(
        email=email,
        username=username,
        password_hash=pwd_hash,
        otp_code=otp_code,
        expires_at=expires_at,
        is_used=False
    )

    # Send Email
    send_otp_email(to_email=email, otp_code=otp_code, username=username, in_background=True)

    return render(request, 'components/otp_step.html', {'email': email, 'username': username})


@require_http_methods(["POST"])
def verify_otp_view(request):
    """Verify OTP code (with Persian/Arabic numeral normalization), create user account, log in, and redirect."""
    email = request.POST.get('email', '').strip().lower()
    raw_otp = request.POST.get('otp_code', '')
    otp_code = normalize_digits(raw_otp)

    now = timezone.now()
    record = EmailOTP.objects.filter(
        email=email,
        is_used=False,
        expires_at__gt=now
    ).order_by('-created_at').first()

    if not record or record.otp_code != otp_code:
        return HttpResponse(
            '<div class="p-3.5 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-400 rounded-2xl text-xs font-bold flex items-center justify-center gap-2 mb-4 text-center">'
            '<svg class="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
            '<span>کد تایید وارد شده نامعتبر یا منقضی شده است.</span>'
            '</div>',
            status=200
        )

    if User.objects.filter(Q(username__iexact=record.username) | Q(email__iexact=record.email)).exists():
        return HttpResponse(
            '<div class="p-3.5 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-400 rounded-2xl text-xs font-bold flex items-center justify-center gap-2 mb-4 text-center">'
            '<span>این حساب قبلاً فعال شده است. لطفاً وارد شوید.</span>'
            '</div>',
            status=200
        )

    # Create User
    new_user = User(
        username=record.username,
        email=record.email,
        password=record.password_hash,
        is_staff=False,
        is_superuser=False
    )
    new_user.save()
    record.is_used = True
    record.save()

    # Log in session
    login(request, new_user)

    response = HttpResponse('<div class="p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-300 rounded-xl text-xs mb-4 font-bold text-center">ثبت‌نام با موفقیت انجام شد! در حال انتقال...</div>')
    response['HX-Redirect'] = '/dashboard/'
    return response


@require_http_methods(["POST"])
def resend_otp_view(request):
    """Resend a fresh OTP code to user's email."""
    email = request.POST.get('email', '').strip().lower()
    record = EmailOTP.objects.filter(email=email).order_by('-created_at').first()
    
    if not record:
        return HttpResponse('<div class="p-3 bg-red-500/15 border border-red-500/30 text-red-600 dark:text-red-300 rounded-xl text-xs mb-4">اطلاعاتی برای ارسال مجدد یافت نشد.</div>', status=200)

    new_code = f"{random.randint(100000, 999999)}"
    record.otp_code = new_code
    record.expires_at = timezone.now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    record.is_used = False
    record.save()

    send_otp_email(to_email=email, otp_code=new_code, username=record.username, in_background=True)

    return HttpResponse('<div class="p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-300 rounded-xl text-xs mb-4">کد تایید جدید با موفقیت به ایمیل شما ارسال شد.</div>', status=200)


def logout_view(request):
    """Log out the current user and redirect to home."""
    logout(request)
    return redirect('/')
