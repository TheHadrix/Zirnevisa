from datetime import date
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import TEMPLATES_DIR, GUEST_DAILY_LIMIT, VIP_DAILY_LIMIT
from app.database import get_db
from app.models import User, GuestUsage, ProviderConfig, TranslationTask
from app.auth import get_current_user_optional, get_current_user, get_current_admin, get_client_identifier

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/", response_class=HTMLResponse)
async def index_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional)
):
    # Calculate usage and limit
    if user:
        daily_used = user.daily_usage
        max_quota = user.max_daily_quota
        is_vip = user.is_vip
    else:
        ident = get_client_identifier(request)
        guest = db.query(GuestUsage).filter(GuestUsage.identifier == ident).first()
        if guest:
            guest.check_and_reset_daily_usage()
            db.commit()
            daily_used = guest.daily_usage
        else:
            daily_used = 0
        max_quota = GUEST_DAILY_LIMIT
        is_vip = False

    remaining_quota = max(0, max_quota - daily_used)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "daily_used": daily_used,
            "max_quota": max_quota,
            "remaining_quota": remaining_quota,
            "is_vip": is_vip
        }
    )

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: User = Depends(get_current_user_optional)
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"user": None}
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user: User = Depends(get_current_user_optional)
):
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"user": None}
    )

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    tasks = db.query(TranslationTask)\
        .filter(TranslationTask.user_id == user.id)\
        .order_by(TranslationTask.created_at.desc())\
        .limit(15)\
        .all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "tasks": tasks,
            "remaining_days": user.remaining_vip_days,
            "is_vip": user.is_vip,
            "daily_used": user.daily_usage,
            "max_quota": user.max_daily_quota
        }
    )

@router.get("/payment/checkout", response_class=HTMLResponse)
async def payment_page(
    request: Request,
    user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="payment.html",
        context={
            "user": user,
            "amount": "99,000"
        }
    )

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    providers = db.query(ProviderConfig).order_by(ProviderConfig.priority_order.asc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": admin,
            "users": users,
            "providers": providers
        }
    )
