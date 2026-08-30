from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user

router = APIRouter(prefix="/payment", tags=["payment"])

@router.post("/process")
async def process_payment(
    action: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if action == "success":
        now = datetime.utcnow()
        if user.is_vip and user.subscription_end_date and user.subscription_end_date > now:
            user.subscription_end_date = user.subscription_end_date + timedelta(days=30)
        else:
            user.subscription_end_date = now + timedelta(days=30)

        db.commit()
        return RedirectResponse(url="/dashboard?payment=success", status_code=302)
    else:
        return RedirectResponse(url="/dashboard?payment=cancelled", status_code=302)
