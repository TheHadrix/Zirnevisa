import asyncio
import os
import uuid
from datetime import datetime, date
from pathlib import Path
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import TEMPLATES_DIR, UPLOAD_DIR, GUEST_DAILY_LIMIT, VIP_DAILY_LIMIT, MAX_SRT_CHARACTERS
from app.database import get_db, SessionLocal
from app.models import User, GuestUsage, TranslationTask
from app.auth import get_current_user_optional, get_client_identifier
from app.services.srt_processor import SRTProcessor
from app.services.mistral_service import MistralTranslationService
from app.services.cleanup_service import delayed_file_cleanup

router = APIRouter(prefix="/tasks", tags=["tasks"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

async def process_translation_background(task_id: str, raw_content: str, target_lang: str):
    db: Session = SessionLocal()
    orig_path = None
    trans_path = None
    try:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        task.progress = 10
        task.current_step = "در حال تحلیل و بخش‌بندی ساختار زیرنویس..."
        db.commit()

        # Parse blocks
        blocks, char_count = SRTProcessor.parse_srt(raw_content)
        if not blocks:
            raise Exception("هیچ بلاک متنی معتبری در فایل زیرنویس یافت نشد.")

        task.char_count = char_count
        task.progress = 20
        task.current_step = "در حال اتصال به هوش مصنوعی و ترجمه..."
        db.commit()

        # Chunk into batches
        batches = SRTProcessor.chunk_blocks(blocks, max_batch_size=25)
        total_batches = len(batches)

        for idx, batch in enumerate(batches):
            payload = SRTProcessor.create_translation_prompt(batch, target_lang=target_lang)
            
            # Step progress calculation
            task.current_step = f"در حال ترجمه بخش {idx + 1} از {total_batches} با هوش مصنوعی..."
            batch_progress = 20 + int(((idx) / total_batches) * 70)
            task.progress = min(90, batch_progress)
            db.commit()

            # Call Mistral with Fallback
            llm_response = await MistralTranslationService.translate_batch_with_fallback(
                db=db,
                payload_text=payload,
                target_lang=target_lang
            )

            # Update batch translated text
            SRTProcessor.parse_llm_response_and_update(batch, llm_response)

        # Build final SRT
        task.current_step = "در حال بازسازی و ذخیره فایل نهایی..."
        task.progress = 95
        db.commit()

        translated_srt = SRTProcessor.build_srt(blocks)
        
        # Save output file
        clean_name = Path(task.original_filename).stem
        out_filename = f"{clean_name}_translated_{target_lang}.srt"
        trans_file_path = UPLOAD_DIR / f"{task_id}_{out_filename}"
        
        with open(trans_file_path, "w", encoding="utf-8") as f:
            f.write(translated_srt)

        orig_path = task.file_path
        trans_path = str(trans_file_path)

        task.translated_filename = out_filename
        task.translated_file_path = trans_path
        task.status = "completed"
        task.progress = 100
        task.current_step = "ترجمه با موفقیت به پایان رسید!"
        task.completed_at = datetime.utcnow()
        db.commit()

        # Schedule automatic disk cleanup after 2 minutes
        asyncio.create_task(delayed_file_cleanup([orig_path, trans_path]))

    except Exception as e:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(e)
            task.current_step = "خطا در پردازش فایل"
            db.commit()
            if task.file_path:
                asyncio.create_task(delayed_file_cleanup([task.file_path]))
    finally:
        db.close()


@router.post("/upload")
async def upload_subtitle(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = Form("fa"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional)
):
    # 1. Quota Check
    if user:
        user.check_and_reset_daily_usage()
        if user.daily_usage >= user.max_daily_quota:
            res = templates.TemplateResponse(
                request=request,
                name="components/quota_exceeded.html",
                context={
                    "is_guest": False,
                    "is_vip": user.is_vip,
                    "max_quota": user.max_daily_quota
                }
            )
            res.headers["HX-Trigger"] = '{"showVipModal": true}'
            return res
    else:
        ident = get_client_identifier(request)
        guest = db.query(GuestUsage).filter(GuestUsage.identifier == ident).first()
        if not guest:
            guest = GuestUsage(identifier=ident, daily_usage=0, last_usage_date=date.today())
            db.add(guest)
            db.commit()
            db.refresh(guest)
        else:
            guest.check_and_reset_daily_usage()
            db.commit()

        if guest.daily_usage >= GUEST_DAILY_LIMIT:
            res = templates.TemplateResponse(
                request=request,
                name="components/quota_exceeded.html",
                context={
                    "is_guest": True,
                    "is_vip": False,
                    "max_quota": GUEST_DAILY_LIMIT
                }
            )
            res.headers["HX-Trigger"] = '{"showVipModal": true}'
            return res

    # 2. File Format Check
    filename = file.filename or "subtitle.srt"
    if not filename.lower().endswith(".srt"):
        return templates.TemplateResponse(
            request=request,
            name="components/error_card.html",
            context={"error": "فرمت فایل نامعتبر است. فقط فایل‌های با پسوند .srt مجاز هستند."}
        )

    # 3. Read and Decode Content
    raw_bytes = await file.read()
    content = ""
    for enc in ["utf-8-sig", "utf-8", "cp1256", "latin1", "windows-1256"]:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return templates.TemplateResponse(
            request=request,
            name="components/error_card.html",
            context={"error": "فایل قابل خواندن نبود یا انکودینگ آن پشتیبانی نمی‌شود."}
        )

    # 4. Character Limit Check (30,000 characters)
    blocks, char_count = SRTProcessor.parse_srt(content)
    if not blocks:
        return templates.TemplateResponse(
            request=request,
            name="components/error_card.html",
            context={"error": "فایل خالی است یا ساختار استاندارد زیرنویس SRT ندارد."}
        )

    if char_count > MAX_SRT_CHARACTERS:
        return templates.TemplateResponse(
            request=request,
            name="components/error_card.html",
            context={"error": f"حجم متن زیرنویس ({char_count:,} کاراکتر) بیشتر از حد مجاز ({MAX_SRT_CHARACTERS:,} کاراکتر) است."}
        )

    # 5. Create Task Record
    task_id = str(uuid.uuid4())
    orig_file_path = UPLOAD_DIR / f"{task_id}_orig.srt"
    with open(orig_file_path, "w", encoding="utf-8") as f:
        f.write(content)

    task = TranslationTask(
        id=task_id,
        user_id=user.id if user else None,
        original_filename=filename,
        file_path=str(orig_file_path),
        target_lang=target_lang,
        status="pending",
        progress=5,
        current_step="در صف پردازش هوش مصنوعی...",
        char_count=char_count
    )
    db.add(task)

    # 6. Deduct Quota
    if user:
        user.daily_usage += 1
    else:
        ident = get_client_identifier(request)
        guest = db.query(GuestUsage).filter(GuestUsage.identifier == ident).first()
        if guest:
            guest.daily_usage += 1

    db.commit()
    db.refresh(task)

    # 7. Launch Background Processing
    background_tasks.add_task(process_translation_background, task_id, content, target_lang)

    return templates.TemplateResponse(
        request=request,
        name="components/task_card.html",
        context={"task": task}
    )


@router.get("/{task_id}/status")
async def task_status(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
    if not task:
        return templates.TemplateResponse(
            request=request,
            name="components/error_card.html",
            context={"error": "تسک مورد نظر یافت نشد یا منقضی شده است."}
        )

    return templates.TemplateResponse(
        request=request,
        name="components/task_card.html",
        context={"task": task}
    )


@router.get("/{task_id}/download")
async def download_translated_file(
    task_id: str,
    db: Session = Depends(get_db)
):
    task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
    if not task or not task.translated_file_path:
        raise HTTPException(status_code=404, detail="فایل ترجمه شده یافت نشد یا مهلت دانلود آن به پایان رسیده است.")

    file_path = Path(task.translated_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="فایل به دلیل پایان مهلت نگهداری (۲ دقیقه) از سرور پاک شده است.")

    return FileResponse(
        path=str(file_path),
        filename=task.translated_filename or "translated.srt",
        media_type="text/plain"
    )
