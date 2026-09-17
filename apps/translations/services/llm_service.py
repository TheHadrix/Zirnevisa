import logging
import httpx
from typing import Optional, Tuple
from translations.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
GEMINI_OPENAI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

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
            # 10 minutes timeout = 600.0 seconds
            with httpx.Client(timeout=600.0) as client:
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": clean_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Translate the following subtitle lines into fluent, natural, and easily readable Persian (Farsi):\n\n{chunk_formatted_text}"}
                    ],
                    "temperature": 0.3
                }

                if config.provider_name == "gemini":
                    url = GEMINI_OPENAI_API_URL
                else:
                    url = MISTRAL_API_URL

                response = client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    translated_content = data["choices"][0]["message"]["content"].strip()
                    provider_label = f"{provider_display} ({clean_model})"
                    logger.info(f"Successfully translated chunk with Provider #{config.id} ({provider_label})")
                    return translated_content, provider_label
                else:
                    error_detail = response.text
                    logger.warning(f"Provider #{config.id} ({config.provider_name}) returned status {response.status_code}: {error_detail}")
                    last_exception = Exception(f"Provider #{config.id} ({config.provider_name} - {clean_model}) returned HTTP {response.status_code}: {error_detail}")

        except httpx.TimeoutException as te:
            err_msg = f"Provider #{config.id} ({config.provider_name} - {clean_model}) failed with exception: The read operation timed out after 10 minutes"
            logger.warning(err_msg)
            last_exception = Exception(err_msg)
            continue
        except Exception as e:
            err_msg = f"Provider #{config.id} ({config.provider_name} - {clean_model}) failed with exception: {e}"
            logger.warning(err_msg)
            last_exception = Exception(err_msg)
            continue

    raise Exception(f"تمامی ارائه‌دهنده‌های هوش مصنوعی با خطا مواجه شدند. آخرین خطا: {last_exception}")

