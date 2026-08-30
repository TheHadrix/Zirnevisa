import logging
import httpx
from typing import Optional, Tuple
from translations.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
GEMINI_OPENAI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

SYSTEM_PROMPT = """You are an expert, professional subtitle translator and localizer specializing in film, TV series, and cinematic media. Your task is to translate and localize subtitle lines into natural, fluent, and idiomatic Persian (Farsi).

Key Translation & Formatting Guidelines:
1. Readability & Natural Flow:
   - Deliver translations that are exceptionally fluent, natural, and expressive in contemporary Persian.
   - Optimize sentence structure, phrasing, and line length for effortless on-screen reading and quick visual scanning by viewers.
   - Avoid rigid, robotic, or overly literal word-for-word translations. Capture the true intent, tone, emotional nuance, humor, sarcasm, and cultural idioms of the original dialogue.

2. Structure & Tag Preservation:
   - Each subtitle block starts with a numerical index marker: `[index] Subtitle text`.
   - You MUST strictly preserve each exact index marker `[index]` at the beginning of its corresponding translated line.
   - If a line contains the `[BR]` token, preserve `[BR]` to maintain proper subtitle line breaks.
   - Keep character names, sound effect notations (e.g., in brackets), and formatting tags intact where appropriate.

3. Output Constraints:
   - Return ONLY the translated numbered lines.
   - Do NOT include any introductory commentary, conversational filler, notes, or markdown code fences."""


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

