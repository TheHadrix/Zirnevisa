from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config import TEMPLATES_DIR
from app.database import get_db
from app.models import User, ProviderConfig
from app.auth import get_current_admin
from app.services.mistral_service import MistralTranslationService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --- User Management ---

@router.post("/users/{user_id}/toggle-vip")
async def toggle_user_vip(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        if target.is_vip:
            target.subscription_end_date = None
        else:
            target.subscription_end_date = datetime.utcnow() + timedelta(days=30)
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/users/{user_id}/toggle-admin")
async def toggle_user_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != admin.id:  # prevent self-demoting
        target.is_admin = not target.is_admin
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/users/{user_id}/reset-usage")
async def reset_user_usage(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.daily_usage = 0
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


# --- Provider Config Management ---

@router.post("/providers/create")
async def create_provider(
    provider_name: str = Form("mistral"),
    model_name: str = Form(...),
    api_key: str = Form(...),
    priority_order: int = Form(1),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    config = ProviderConfig(
        provider_name=provider_name.strip(),
        model_name=model_name.strip(),
        api_key=api_key.strip(),
        priority_order=priority_order,
        is_active=True
    )
    db.add(config)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/providers/reorder")
async def reorder_providers(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Accepts JSON list of provider IDs in their new order and updates priority_order 1..N
    """
    try:
        data = await request.json()
        provider_ids = data.get("order", [])
        for index, p_id in enumerate(provider_ids, start=1):
            config = db.query(ProviderConfig).filter(ProviderConfig.id == int(p_id)).first()
            if config:
                config.priority_order = index
        db.commit()
        return JSONResponse({"status": "success", "message": "اولویت‌ها با موفقیت ذخیره شد."})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)


@router.post("/providers/{provider_id}/toggle")
async def toggle_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    config = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if config:
        config.is_active = not config.is_active
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/providers/{provider_id}/priority")
async def update_provider_priority(
    provider_id: int,
    priority_order: int = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    config = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if config:
        config.priority_order = priority_order
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/providers/{provider_id}/delete")
async def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    config = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if config:
        db.delete(config)
        db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    config = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if not config:
        return HTMLResponse('<span class="text-xs px-2 py-1 bg-red-500/20 text-red-500 rounded-lg">یافت نشد</span>')

    success = await MistralTranslationService.test_api_key(config.api_key, config.model_name)
    if success:
        return HTMLResponse('<span class="text-xs px-2 py-1 bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 rounded-lg font-semibold">اتصال موفق ✓</span>')
    else:
        return HTMLResponse('<span class="text-xs px-2 py-1 bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/30 rounded-lg font-semibold">خطا در اتصال ✕</span>')
