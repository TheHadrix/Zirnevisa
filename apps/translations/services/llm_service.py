import logging
import httpx
from typing import Optional, Tuple
from django.conf import settings
from translations.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
GEMINI_OPENAI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def get_provider_chunk_limit(provider_name: str) -> int:
    """
    Return max character chunk limit for a given provider:
    - Gemini: 38,000 characters (supports 65k output tokens with high throughput)
    - Mistral: 18,000 characters (capped at 16k output tokens, avoids 429 rate limits and length cuts)
    """
    name = (provider_name or "").lower()
    limits = getattr(settings, 'PROVIDER_CHUNK_LIMITS', {
        'gemini': 38000,
        'mistral': 18000,
    })
    return limits.get(name, getattr(settings, 'SUBTITLE_CHUNK_MAX_CHARS', 18000))


def get_active_chunk_size() -> int:
    """
    Determine optimal chunk character size dynamically based on the primary active provider.
    """
    try:
        primary = ProviderConfig.objects.filter(is_active=True).order_by('priority_order', 'id').first()
        if primary:
            return get_provider_chunk_limit(primary.provider_name)
    except Exception:
        pass
    return getattr(settings, 'GEMINI_CHUNK_MAX_CHARS', 38000)

SYSTEM_PROMPT = """شما یک مترجم نخبه و ارشد زیرنویس فیلم، سریال و انیمه هستید که مهارت بی‌نظیری در ترجمه زنده، طبیعی و بسیار روان به زبان فارسی محاوره‌ای (گفتاری) دارید؛ دقیقاً شبیه به بهترین و باکیفیت‌ترین زیرنویس‌های انسانی منتشرشده در فضای وب فارسی.

قوانین طلایی ترجمه و بومی‌سازی:
۱. لحن طبیعی و گفتاری (Conversational Subtitle Tone):
   - تمام دیالوگ‌ها باید به زبان گفتاری/محاوره‌ای صمیمی و روان فارسی که شخصیت‌ها واقعاً بر زبان می‌آورند ترجمه شوند (استفاده از افعال و فرم‌های شکسته مثل: «می‌خوام»، «نمی‌ذارم»، «باهاشون»، «رو»، «یه»، «بخوابه»، «داغی قضیه»).
   - اکیداً از ترجمه ماشینی، واژه‌به‌واژه و جملات کتابی خشک (مانند: «او به من گفت که...»، «امکانی برای رفتن وجود ندارد») خودداری کنید.
   - احساس، کنایه، شوخی، هیجان و فضای عاطفی صحنه را منتقل کنید. اصطلاحات عامیانه و اسلنگ‌های انگلیسی را به اصطلاحات رایج در مکالمات فارسی‌زبانان برگردانید.
   - جملات باید خوش‌خوان، شمرده و خوش‌ریتم باشند تا بیننده روی صفحه نمایش بدون مکث پیام را درک کند.

۲. حفظ دقیق ساختار، تگ‌ها و کدهای زیرنویس:
   - در ابتدای هر سطر، شناسه `[index]` را دقیقاً بدون تغییر بنویسید (مثلاً: `[1] متن ترجمه`).
   - به هیچ وجه سطری را حذف، ادغام یا شماره‌گذاری آن را دستکاری نکنید.
   - تگ‌های قالب‌بندی مثل `<i>...</i>`، `<b>...</b>` و تگ‌های تراز زیرنویس مثل `{\\an8}` را عیناً در جای متناظر حفظ کنید.
   - نشانگر `[BR]` برای شکستن سطر است؛ آن را برای خوانایی خطوط زیرنویس نگه دارید.

۳. خروجی خالص:
   - خروجی باید منحصراً سطرهای شماره‌دار ترجمه‌شده باشد. هیچ‌گونه مقدمه، نتیجه‌گیری، سلام و احوال‌پرسی یا کدبلاک مارک‌داون اضافه نکنید."""


def call_provider_api(config: ProviderConfig, prompt_text: str, target_lang: str = "fa") -> Tuple[str, str]:
    """
    Execute translation request directly against a specific ProviderConfig.
    Includes auto-subchunking safeguard for Mistral if prompt_text exceeds MISTRAL_CHUNK_MAX_CHARS.
    Returns: (translated_content, provider_label)
    """
    clean_model = config.model_name.replace("gemini/", "").strip()
    provider_display = config.get_provider_name_display()
    provider_label = f"{provider_display} ({clean_model})"
    mistral_limit = get_provider_chunk_limit('mistral')

    # Safeguard: If prompt sent to Mistral exceeds its safe limit, split by lines into sub-chunks
    if config.provider_name == "mistral" and len(prompt_text) > mistral_limit:
        logger.warning(
            f"Prompt text ({len(prompt_text)} chars) exceeds Mistral safe limit ({mistral_limit}). "
            "Splitting into sub-chunks automatically to prevent 16k token overflow."
        )
        lines = prompt_text.splitlines()
        sub_chunks = []
        curr = []
        curr_len = 0
        for line in lines:
            line_len = len(line) + 1
            if curr and (curr_len + line_len > mistral_limit):
                sub_chunks.append("\n".join(curr))
                curr = [line]
                curr_len = line_len
            else:
                curr.append(line)
                curr_len += line_len
        if curr:
            sub_chunks.append("\n".join(curr))

        translated_parts = []
        for part in sub_chunks:
            part_trans, _ = call_provider_api(config, part, target_lang=target_lang)
            translated_parts.append(part_trans)
        return "\n".join(translated_parts), provider_label

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": clean_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate the following subtitle lines into fluent, natural, and easily readable Persian (Farsi):\n\n{prompt_text}"}
        ],
        "temperature": 0.3
    }
    url = GEMINI_OPENAI_API_URL if config.provider_name == "gemini" else MISTRAL_API_URL

    with httpx.Client(timeout=600.0) as client:
        response = client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            translated_content = data["choices"][0]["message"]["content"].strip()
            return translated_content, provider_label
        else:
            error_detail = response.text
            raise Exception(f"Provider #{config.id} ({provider_label}) returned HTTP {response.status_code}: {error_detail}")


def translate_subtitle_chunk(chunk_formatted_text: str, target_lang: str = "fa") -> Tuple[str, str]:
    """
    Translate a formatted subtitle chunk using the active ProviderConfig hierarchy (Mistral AI & Google Gemini).
    Sequentially falls back to lower priority providers if an error occurs.
    Returns a tuple: (translated_content, provider_model_used_label)
    """
    providers = list(ProviderConfig.objects.filter(is_active=True).order_by('priority_order', 'id'))

    if not providers:
        # Fallback default configuration
        default_key = "sk-placeholder"
        providers = [
            ProviderConfig(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                api_key=default_key,
                priority_order=1,
                is_active=True
            )
        ]

    last_exception = None

    for config in providers:
        clean_model = config.model_name.replace("gemini/", "").strip()
        provider_display = config.get_provider_name_display()
        logger.info(f"Attempting translation with Provider #{config.id} ({provider_display} / {clean_model}, Priority: {config.priority_order})")
        try:
            return call_provider_api(config, chunk_formatted_text, target_lang=target_lang)
        except Exception as e:
            err_msg = f"Provider #{config.id} ({config.provider_name} - {clean_model}) failed: {e}"
            logger.warning(err_msg)
            last_exception = e
            continue

    raise Exception(f"تمامی ارائه‌دهنده‌های هوش مصنوعی با خطا مواجه شدند. آخرین خطا: {last_exception}")

