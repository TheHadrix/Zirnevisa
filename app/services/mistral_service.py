import logging
from typing import List, Optional
import httpx
from sqlalchemy.orm import Session
from app.models import ProviderConfig

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM_PROMPT = """You are an expert subtitle translator specializing in cinema and natural dialogue.
Translate the following numbered subtitle lines into natural, fluent Persian (Farsi) suitable for movie and video subtitles.
Strict Rules:
1. Maintain the exact same numbering and bracket format: [1] <translation>, [2] <translation>, etc.
2. Translate colloquialisms, idioms, and emotions naturally and concisely.
3. Do NOT add any explanations, introductory text, notes, markdown formatting, or commentary.
4. Output only the translated lines with their brackets."""

class MistralTranslationService:
    @staticmethod
    async def call_mistral_api(api_key: str, model_name: str, payload_text: str, target_lang: str = "fa") -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate these subtitle lines to {target_lang}:\n\n{payload_text}"}
        ]
        
        body = {
            "model": model_name or "mistral-small-latest",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 3000
        }
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(MISTRAL_API_URL, headers=headers, json=body)
            if response.status_code != 200:
                error_detail = response.text
                try:
                    err_json = response.json()
                    error_detail = err_json.get("message", error_detail)
                except Exception:
                    pass
                raise Exception(f"Mistral API Error ({response.status_code}): {error_detail}")
                
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise Exception("Empty response received from Mistral API.")
            return choices[0]["message"]["content"]

    @staticmethod
    async def translate_batch_with_fallback(db: Session, payload_text: str, target_lang: str = "fa") -> str:
        """
        Retrieves active configs ordered by priority_order ASC.
        Tries each config in sequence. If one fails, seamlessly falls back to the next.
        """
        configs: List[ProviderConfig] = db.query(ProviderConfig)\
            .filter(ProviderConfig.is_active == True)\
            .order_by(ProviderConfig.priority_order.asc())\
            .all()

        if not configs:
            raise Exception("هیچ کلید فعال Mistral در سیستم تنظیم نشده است. لطفاً در پنل ادمین کلید API ثبت کنید.")

        last_error = None
        for config in configs:
            try:
                logger.info(f"Trying Mistral Provider ID {config.id} (Priority: {config.priority_order}, Model: {config.model_name})")
                translated_text = await MistralTranslationService.call_mistral_api(
                    api_key=config.api_key,
                    model_name=config.model_name,
                    payload_text=payload_text,
                    target_lang=target_lang
                )
                return translated_text
            except Exception as e:
                logger.warning(f"Provider {config.id} failed with error: {str(e)}. Attempting fallback to next config...")
                last_error = e
                continue

        raise Exception(f"تمام کانفیگ‌های هوش مصنوعی با خطا مواجه شدند. آخرین خطا: {str(last_error)}")

    @staticmethod
    async def test_api_key(api_key: str, model_name: str) -> bool:
        """Tests if a given API key and model work correctly with Mistral."""
        test_payload = "[1] Hello world."
        try:
            res = await MistralTranslationService.call_mistral_api(api_key, model_name, test_payload)
            return len(res) > 0
        except Exception:
            return False
