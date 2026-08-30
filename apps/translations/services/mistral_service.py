import logging
import httpx
from typing import Optional
from translations.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM_PROMPT = """You are an expert subtitle translator specialized in translating movie and series subtitles accurately and idiomatically into natural Persian (Farsi).
Rules:
1. Each line is prefixed with an index like `[1] Subtitle text`.
2. You MUST preserve the exact index `[index]` at the beginning of each translated line.
3. If a line contains `[BR]`, preserve `[BR]` to indicate line breaks.
4. Translate idiomatic expressions, slang, and cultural context naturally into Persian.
5. Return ONLY the translated numbered lines. Do NOT add any introductory text, markdown commentary, or explanations.
"""

def translate_subtitle_chunk(chunk_formatted_text: str, target_lang: str = "fa") -> str:
    """
    Translate a formatted subtitle chunk using the active ProviderConfig hierarchy.
    Sequentially falls back to lower priority providers if an error occurs.
    """
    providers = list(ProviderConfig.objects.filter(is_active=True).order_by('priority_order', 'id'))

    if not providers:
        # Fallback default configuration
        default_key = "sk-placeholder"
        providers = [
            ProviderConfig(
                provider_name="mistral",
                model_name="mistral-small-2506",
                api_key=default_key,
                priority_order=1,
                is_active=True
            )
        ]

    last_exception = None

    for config in providers:
        logger.info(f"Attempting translation with Provider #{config.id} ({config.provider_name} / {config.model_name}, Priority: {config.priority_order})")
        try:
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": config.model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Translate the following subtitle lines to Persian (Farsi):\n\n{chunk_formatted_text}"}
                ],
                "temperature": 0.3
            }

            with httpx.Client(timeout=60.0) as client:
                response = client.post(MISTRAL_API_URL, json=payload, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    translated_content = data["choices"][0]["message"]["content"].strip()
                    logger.info(f"Successfully translated chunk with provider #{config.id}")
                    return translated_content
                else:
                    error_detail = response.text
                    logger.warning(f"Provider #{config.id} returned status {response.status_code}: {error_detail}")
                    last_exception = Exception(f"Provider #{config.id} HTTP {response.status_code}: {error_detail}")

        except Exception as e:
            logger.warning(f"Provider #{config.id} failed with exception: {e}")
            last_exception = e
            continue

    raise Exception(f"All AI translation providers failed. Last error: {last_exception}")
