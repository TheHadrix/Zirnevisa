import logging
import httpx
from typing import Optional, Tuple
from translations.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
GEMINI_OPENAI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

SYSTEM_PROMPT = """You are an expert subtitle translator specialized in translating movie and series subtitles accurately and idiomatically into natural Persian (Farsi).
Rules:
1. Each line is prefixed with an index like `[1] Subtitle text`.
2. You MUST preserve the exact index `[index]` at the beginning of each translated line.
3. If a line contains `[BR]`, preserve `[BR]` to indicate line breaks.
4. Translate idiomatic expressions, slang, and cultural context naturally into Persian.
5. Return ONLY the translated numbered lines. Do NOT add any introductory text, markdown commentary, or explanations.
"""

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
        logger.info(f"Attempting translation with Provider #{config.id} ({config.provider_name} / {config.model_name}, Priority: {config.priority_order})")
        try:
            with httpx.Client(timeout=60.0) as client:
                clean_model = config.model_name.replace("gemini/", "").strip()
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": clean_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Translate the following subtitle lines to Persian (Farsi):\n\n{chunk_formatted_text}"}
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
                    provider_label = f"{config.get_provider_name_display()} ({clean_model})"
                    logger.info(f"Successfully translated chunk with Provider #{config.id} ({provider_label})")
                    return translated_content, provider_label
                else:
                    error_detail = response.text
                    logger.warning(f"Provider #{config.id} ({config.provider_name}) returned status {response.status_code}: {error_detail}")
                    last_exception = Exception(f"Provider #{config.id} HTTP {response.status_code}: {error_detail}")

        except Exception as e:
            logger.warning(f"Provider #{config.id} ({config.provider_name}) failed with exception: {e}")
            last_exception = e
            continue

    raise Exception(f"All AI translation providers failed. Last error: {last_exception}")
