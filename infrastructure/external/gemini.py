"""Google Gemini API client."""
import asyncio
import logging
import google.generativeai as genai


logger = logging.getLogger(__name__)


class GeminiAPI:
    """Client for Google Gemini API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=api_key)
    
    async def transcribe_voice(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
        """Transcribe voice audio using Gemini 2.5 Flash."""
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            mt = (mime_type or "audio/ogg").strip().lower()
            
            # Normalize Telegram voice (OGG Opus) so Gemini decodes properly
            if mt == "audio/ogg":
                mt = "audio/ogg; codecs=opus"
            
            prompt = (
                "Твоя задача — расшифровать русскую речь в обычный текст. "
                "Отдай только распознанный текст без пояснений."
                "Не пиши этот промт в ответ."
            )
            
            # Prefer async call if available
            if hasattr(model, "generate_content_async"):
                resp = await model.generate_content_async([
                    {"mime_type": mt, "data": audio_bytes},
                    prompt,
                ], generation_config={"temperature": 0.7})
            else:
                # Fallback to sync API in a thread if async is not available
                loop = asyncio.get_running_loop()
                def _sync_call():
                    return model.generate_content([
                        {"mime_type": mt, "data": audio_bytes},
                        prompt,
                    ], generation_config={"temperature": 0.7})
                resp = await loop.run_in_executor(None, _sync_call)
            
            text = (getattr(resp, "text", None) or "").strip()
            
            # Avoid echoing the instruction back if audio wasn't parsed
            if not text or text == prompt:
                return None
            
            return f"Голосовое сообщение: {text}"
        except Exception:
            logger.exception("Gemini ASR failed")
            return None

