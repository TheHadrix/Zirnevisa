import os
import json
import uuid
import httpx
import threading
import logging
from pathlib import Path
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Max
from django.conf import settings

from accounts.models import User
from translations.models import ProviderConfig, TranslationTask, GuestUsage
from translations.services.srt_processor import SRTProcessor
from translations.services.llm_service import translate_subtitle_chunk, MISTRAL_API_URL, GEMINI_OPENAI_API_URL
from translations.services.cleanup_service import schedule_file_cleanup

logger = logging.getLogger(__name__)

def get_client_identifier(request) -> str:
    """Get unique client identifier for guest quota tracking."""
    if request.user.is_authenticated:
        return f"user_{request.user.id}"
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return f"ip_{ip}"


def index_view(request):
    """Render home page with quota status and translation upload component."""
    if request.user.is_authenticated:
        request.user.check_and_reset_daily_usage()
        daily_used = request.user.daily_usage
        max_quota = request.user.max_daily_quota
        is_vip = request.user.is_vip
    else:
        ident = get_client_identifier(request)
        guest, _ = GuestUsage.objects.get_or_create(identifier=ident)
        guest.check_and_reset_daily_usage()
        daily_used = guest.daily_usage
        max_quota = settings.GUEST_DAILY_LIMIT
        is_vip = False

    remaining_quota = max(0, max_quota - daily_used)

    return render(request, 'index.html', {
        'daily_used': daily_used,
        'max_quota': max_quota,
        'remaining_quota': remaining_quota,
        'is_vip': is_vip,
    })


def _process_translation_background(task_id: str, input_path: str, output_path: str, target_lang: str):
    """Background thread function for translating subtitle chunks sequentially."""
    try:
        task = TranslationTask.objects.get(task_id=task_id)
        task.status = 'PROCESSING'
        task.save()

        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            raw_content = f.read()

        blocks, total_chars = SRTProcessor.parse_srt(raw_content)
        if not blocks:
            task.status = 'FAILED'
            task.error_message = 'هیچ بخش معتبری در فایل زیرنویس یافت نشد.'
            task.save()
            return

        max_chunk_chars = getattr(settings, 'SUBTITLE_CHUNK_MAX_CHARS', 38000)
        chunks = SRTProcessor.chunk_blocks(blocks, max_chars_per_chunk=max_chunk_chars)
        task.total_chunks = len(chunks)
        task.save()

        translated_blocks = []
        model_used_label = None
        for i, chunk in enumerate(chunks):
            task.current_chunk = i + 1
            task.progress = int(((i + 1) / len(chunks)) * 95)
            task.save()

            formatted_text = SRTProcessor.format_chunk_for_llm(chunk)
            llm_response, model_label = translate_subtitle_chunk(formatted_text, target_lang=target_lang)
            if not model_used_label:
                model_used_label = model_label
            chunk_translated_blocks = SRTProcessor.parse_llm_response(llm_response, chunk)
            translated_blocks.extend(chunk_translated_blocks)

        # Reconstruct SRT
        reconstructed = SRTProcessor.reconstruct_srt(translated_blocks)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(reconstructed)

        task.status = 'COMPLETED'
        task.progress = 100
        task.provider_used = model_used_label
        task.result_file_path = output_path
        task.save()

        # File retention logic:
        # - Guests (not logged in): Delete files automatically after 5 minutes (300 seconds).
        # - Logged-in users: Retain translated files permanently for dashboard access!
        if task.user is None:
            schedule_file_cleanup(input_path, delay_seconds=settings.GUEST_CLEANUP_DELAY_SECONDS)
            schedule_file_cleanup(output_path, delay_seconds=settings.GUEST_CLEANUP_DELAY_SECONDS)
            logger.info(f"Scheduled 5-minute cleanup for guest task {task_id}")
        else:
            schedule_file_cleanup(input_path, delay_seconds=settings.GUEST_CLEANUP_DELAY_SECONDS)
            logger.info(f"Preserving translated file permanently for logged-in user '{task.user.username}' (task {task_id})")

        logger.info(f"Task {task_id} successfully completed and saved to {output_path}")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        try:
            task = TranslationTask.objects.get(task_id=task_id)
            task.status = 'FAILED'
            err_str = str(e)
            if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                task.error_message = f"خطای پایان مهلت زمانی (Timeout پس از ۱۰ دقیقه): {err_str} — لطفاً وضعیت اینترنت، تحریم‌شکن یا کلید هوش مصنوعی را بررسی کنید."
            else:
                task.error_message = f"خطا در پردازش هوش مصنوعی: {err_str}"
            task.save()
        except Exception:
            pass


@require_http_methods(["POST"])
def upload_task_view(request):
    """Handle SRT file upload, validation, quota check, and start background processing."""
    uploaded_file = request.FILES.get('file')
    target_lang = request.POST.get('target_lang', 'fa')

    if not uploaded_file:
        return HttpResponse('<div class="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-2xl text-xs font-bold">لطفاً یک فایل زیرنویس انتخاب کنید.</div>', status=400)

    if not uploaded_file.name.lower().endswith('.srt'):
        return HttpResponse('<div class="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-2xl text-xs font-bold">فقط فایل‌های با پسوند .srt مجاز هستند.</div>', status=400)

    # Check Quota
    if request.user.is_authenticated:
        request.user.check_and_reset_daily_usage()
        if request.user.remaining_quota <= 0:
            return HttpResponse('<div class="p-4 bg-amber-500/15 border border-amber-500/30 text-amber-500 rounded-2xl text-xs font-bold">سهمیه روزانه شما به پایان رسیده است. لطفاً حساب خود را به VIP ارتقا دهید.</div>', status=400)
    else:
        ident = get_client_identifier(request)
        guest, _ = GuestUsage.objects.get_or_create(identifier=ident)
        guest.check_and_reset_daily_usage()
        if guest.daily_usage >= settings.GUEST_DAILY_LIMIT:
            return HttpResponse('<div class="p-4 bg-amber-500/15 border border-amber-500/30 text-amber-500 rounded-2xl text-xs font-bold">سهمیه رایگان مهمان (۳ فایل در روز) شما تمام شده است. برای ترجمه نامحدودتر ثبت‌نام یا VIP شوید.</div>', status=400)

    # Read and parse content
    try:
        content_bytes = uploaded_file.read()
        content_str = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            content_str = content_bytes.decode('windows-1256')
        except Exception:
            return HttpResponse('<div class="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-2xl text-xs font-bold">فرمت انکودینگ فایل خوانا نیست. لطفاً فایل UTF-8 آپلود کنید.</div>', status=400)

    blocks, char_count = SRTProcessor.parse_srt(content_str)
    if not blocks:
        return HttpResponse('<div class="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-2xl text-xs font-bold">فایل آپلود شده ساختار استاندارد زیرنویس SRT ندارد.</div>', status=400)

    if char_count > settings.CHAR_LIMIT:
        return HttpResponse(f'<div class="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-2xl text-xs font-bold">حجم متن زیرنویس ({char_count:,} کاراکتر) بیشتر از حد مجاز ۳۰,۰۰۰ کاراکتر است.</div>', status=400)

    # Deduct quota
    if request.user.is_authenticated:
        request.user.daily_usage += 1
        request.user.save()
    else:
        guest.daily_usage += 1
        guest.save()

    task_id = uuid.uuid4().hex
    input_path = os.path.join(settings.UPLOAD_DIR, f"{task_id}_{uploaded_file.name}")
    output_path = os.path.join(settings.OUTPUT_DIR, f"translated_{task_id}_{uploaded_file.name}")

    with open(input_path, 'w', encoding='utf-8') as f:
        f.write(content_str)

    task = TranslationTask.objects.create(
        task_id=task_id,
        user=request.user if request.user.is_authenticated else None,
        identifier=get_client_identifier(request),
        filename=uploaded_file.name,
        char_count=char_count,
        target_lang=target_lang,
        status='PENDING',
        progress=5,
        total_chunks=len(SRTProcessor.chunk_blocks(blocks, getattr(settings, 'SUBTITLE_CHUNK_MAX_CHARS', 38000)))
    )

    # Start background translation thread
    worker_thread = threading.Thread(
        target=_process_translation_background,
        args=(task_id, input_path, output_path, target_lang),
        daemon=True
    )
    worker_thread.start()

    return render(request, 'components/task_card.html', {'task': task})


def task_status_view(request, task_id):
    """Return updated task status component for HTMX polling."""
    task = get_object_or_404(TranslationTask, task_id=task_id)
    return render(request, 'components/task_card.html', {'task': task})


def task_download_view(request, task_id):
    """Download translated SRT file."""
    task = get_object_or_404(TranslationTask, task_id=task_id)
    if task.status != 'COMPLETED' or not task.result_file_path or not os.path.exists(task.result_file_path):
        raise Http404("فایل ترجمه شده یافت نشد یا مدت اعتبار آن (۲ دقیقه) منقضی شده است.")

    response = FileResponse(
        open(task.result_file_path, 'rb'),
        as_attachment=True,
        filename=f"fa_{task.filename}"
    )
    return response


@login_required
@require_http_methods(["POST"])
def task_delete_view(request, task_id):
    """Delete a user translation task and its file from disk."""
    task = get_object_or_404(TranslationTask, task_id=task_id)
    if task.user != request.user and not (request.user.is_staff or request.user.is_superuser):
        return HttpResponse("شما دسترسی حذف این فایل را ندارید.", status=403)

    if task.result_file_path and os.path.exists(task.result_file_path):
        try:
            os.remove(task.result_file_path)
            logger.info(f"User deleted task file: {task.result_file_path}")
        except Exception as e:
            logger.warning(f"Could not delete file {task.result_file_path}: {e}")

    task.delete()
    return redirect('/dashboard/')


@login_required
@require_http_methods(["POST"])
def task_delete_all_view(request):
    """Delete all translation tasks and files for the logged-in user."""
    tasks = TranslationTask.objects.filter(user=request.user)
    for task in tasks:
        if task.result_file_path and os.path.exists(task.result_file_path):
            try:
                os.remove(task.result_file_path)
            except Exception:
                pass
    tasks.delete()
    return redirect('/dashboard/')



@login_required
def dashboard_view(request):
    """User dashboard view with RTL sidebar and recent tasks list."""
    request.user.check_and_reset_daily_usage()
    tasks = TranslationTask.objects.filter(user=request.user).order_by('-created_at')[:15]

    return render(request, 'dashboard.html', {
        'tasks': tasks,
        'remaining_days': request.user.remaining_vip_days,
        'is_vip': request.user.is_vip,
        'daily_used': request.user.daily_usage,
        'max_quota': request.user.max_daily_quota,
        'payment_success': request.GET.get('payment') == 'success',
    })


@login_required
def payment_checkout_view(request):
    """Simulated VIP payment checkout page."""
    return render(request, 'payment.html', {'amount': '99,000'})


@login_required
@require_http_methods(["POST"])
def payment_process_view(request):
    """Process simulated VIP payment."""
    action = request.POST.get('action')
    if action == 'success':
        request.user.is_vip = True
        request.user.vip_expires_at = timezone.now() + timedelta(days=30)
        request.user.max_daily_quota = settings.VIP_DAILY_LIMIT
        request.user.save()
        return redirect('/dashboard/?payment=success')
    return redirect('/payment/checkout/?error=cancelled')


def is_admin_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@user_passes_test(is_admin_user, login_url='/login/')
def admin_panel_view(request):
    """Custom RTL Admin Panel for managing users and AI providers."""
    users = User.objects.all().order_by('-date_joined')
    providers = ProviderConfig.objects.all().order_by('priority_order', 'id')

    return render(request, 'admin_panel.html', {
        'users': users,
        'providers': providers,
    })


@user_passes_test(is_admin_user, login_url='/login/')
@require_http_methods(["POST"])
def admin_create_provider_view(request):
    """Add a new AI provider config with automatic last priority."""
    from django.db.models import Max
    provider_name = request.POST.get('provider_name', 'mistral')
    model_name = request.POST.get('model_name', '').strip() or 'mistral-small-2506'
    api_key = request.POST.get('api_key', '').strip()

    max_priority = ProviderConfig.objects.aggregate(Max('priority_order'))['priority_order__max'] or 0
    priority_order = max_priority + 1

    if api_key:
        ProviderConfig.objects.create(
            provider_name=provider_name,
            model_name=model_name,
            api_key=api_key,
            priority_order=priority_order,
            is_active=True
        )
    return redirect('/admin-panel/')


@user_passes_test(is_admin_user, login_url='/login/')
@require_http_methods(["POST"])
def admin_delete_provider_view(request, provider_id):
    """Delete an AI provider config."""
    provider = get_object_or_404(ProviderConfig, id=provider_id)
    provider.delete()
    return redirect('/admin-panel/')


@user_passes_test(is_admin_user, login_url='/login/')
@require_http_methods(["POST"])
def admin_toggle_provider_view(request, provider_id):
    """Toggle active status of an AI provider."""
    provider = get_object_or_404(ProviderConfig, id=provider_id)
    provider.is_active = not provider.is_active
    provider.save()
    return redirect('/admin-panel/')


@user_passes_test(is_admin_user, login_url='/login/')
@require_http_methods(["POST"])
def admin_reorder_providers_view(request):
    """Handle Drag & Drop SortableJS priority reordering."""
    try:
        body = json.loads(request.body.decode('utf-8'))
        order_list = body.get('order', [])
        for index, provider_id in enumerate(order_list, start=1):
            ProviderConfig.objects.filter(id=provider_id).update(priority_order=index)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def admin_test_provider_view(request, provider_id):
    """Test connection and response of an AI provider config."""
    import time
    if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'عدم دسترسی: لطفاً به عنوان ادمین لاگین کنید.'}, status=403)

    provider = get_object_or_404(ProviderConfig, id=provider_id)
    clean_model = provider.model_name.replace("gemini/", "").strip()
    
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": clean_model,
        "messages": [
            {"role": "user", "content": "Ping! Answer with 'OK'"}
        ],
        "temperature": 0.2
    }

    if provider.provider_name == "gemini":
        url = GEMINI_OPENAI_API_URL
    else:
        url = MISTRAL_API_URL

    start_time = time.time()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload, headers=headers)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                sample_text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                return JsonResponse({
                    'status': 'success',
                    'latency_ms': latency_ms,
                    'message': f'اتصال به مدل {provider.model_name} با موفقیت برقرار شد ({latency_ms}ms)',
                    'sample_response': sample_text
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'latency_ms': latency_ms,
                    'message': f'خطای HTTP {response.status_code} از سمت هوش مصنوعی: {response.text[:200]}'
                })

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return JsonResponse({
            'status': 'error',
            'latency_ms': latency_ms,
            'message': f'عدم برقراری ارتباط: {str(e)}'
        })




@user_passes_test(is_admin_user, login_url='/login/')
@require_http_methods(["POST"])
def admin_update_user_view(request, user_id):
    """Admin update user VIP status and quota."""
    target_user = get_object_or_404(User, id=user_id)
    action = request.POST.get('action')
    
    if action == 'toggle_vip':
        target_user.is_vip = not target_user.is_vip
        if target_user.is_vip:
            target_user.vip_expires_at = timezone.now() + timedelta(days=30)
            target_user.max_daily_quota = settings.VIP_DAILY_LIMIT
        else:
            target_user.max_daily_quota = settings.GUEST_DAILY_LIMIT
        target_user.save()
    elif action == 'reset_usage':
        target_user.daily_usage = 0
        target_user.save()

    return redirect('/admin-panel/')


@csrf_exempt
@require_http_methods(["POST"])
def api_create_provider_view(request):
    """
    REST API endpoint to create a new AI ProviderConfig.
    Requires Admin authentication via JSON body (username & password) or session.
    
    JSON Body:
    {
        "username": "admin",
        "password": "admin_password",
        "provider_name": "gemini",       # "gemini" or "mistral"
        "model_name": "gemini-2.5-flash",
        "api_key": "AQ.Ab8..."
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    # 1. Admin Authentication Check
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = None
    if username and password:
        user = authenticate(request, username=username, password=password)
    elif request.user.is_authenticated:
        user = request.user

    if not user or not (user.is_staff or user.is_superuser):
        return JsonResponse({
            'status': 'error',
            'message': 'احراز هویت ناموفق بود یا کاربر دسترسی ادمین ندارد.'
        }, status=401)

    # 2. Extract & Validate Fields
    provider_name = data.get('provider_name', '').strip().lower()
    model_name = data.get('model_name', '').strip()
    api_key = data.get('api_key', '').strip()

    if not provider_name or provider_name not in ['gemini', 'mistral']:
        return JsonResponse({
            'status': 'error',
            'message': 'فیلد provider_name نامعتبر است. مقادیر مجاز: gemini یا mistral'
        }, status=400)

    if not model_name:
        return JsonResponse({
            'status': 'error',
            'message': 'فیلد model_name الزامی است.'
        }, status=400)

    if not api_key:
        return JsonResponse({
            'status': 'error',
            'message': 'فیلد api_key الزامی است.'
        }, status=400)

    # 3. Calculate auto priority (last in queue)
    max_priority = ProviderConfig.objects.aggregate(Max('priority_order'))['priority_order__max'] or 0
    priority_order = max_priority + 1

    # 4. Create in DB
    provider = ProviderConfig.objects.create(
        provider_name=provider_name,
        model_name=model_name,
        api_key=api_key,
        priority_order=priority_order,
        is_active=True
    )

    return JsonResponse({
        'status': 'success',
        'message': f'کانفیگ {provider.get_provider_name_display()} با موفقیت با اولویت {priority_order} ثبت شد.',
        'data': {
            'id': provider.id,
            'provider_name': provider.provider_name,
            'provider_label': provider.get_provider_name_display(),
            'model_name': provider.model_name,
            'priority_order': provider.priority_order,
            'is_active': provider.is_active,
            'created_at': provider.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    }, status=201)

