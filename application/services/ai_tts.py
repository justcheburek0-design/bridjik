"""TTS generation mixin for AIService."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


class AITTSMixin:
    """Mixin for TTS (text-to-speech) generation."""

    # Provided by AIService
    config: Any

    async def generate_speech(
        self,
        text: str,
        language_id: str = "ru",
        ref_wav: str | None = None,
        exaggeration: float = 0.5,
        temperature: float = 0.8,
        seed: int = 0,
        cfg_weight: float = 0.5,
    ) -> bytes | None:
        """Generate speech from text using ResembleAI Chatterbox TTS."""
        if not text:
            log.warning("tts.empty_text")
            return None

        cleaned_text = re.sub(r"\s+", " ", text.strip())[:300]
        if not cleaned_text:
            return None

        files = {}
        data = {
            "text": cleaned_text,
            "language_id": language_id,
            "exaggeration": str(exaggeration),
            "temperature": str(temperature),
            "cfg_weight": str(cfg_weight),
        }

        ref_path: Path | None = None
        if ref_wav and Path(ref_wav).exists():
            ref_path = Path(ref_wav)
        else:
            for candidate in [
                self.config.VOICES_DIR / "voice.wav",
                self.config.VOICES_DIR / "voice.mp3",
            ]:
                if candidate.exists():
                    ref_path = candidate
                    break

        if ref_path:
            files["reference_audio"] = (ref_path.name, ref_path.read_bytes())

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.config.TTS_URL, data=data, files=files)
                if response.status_code == 200:
                    log.info("tts.generated", lang=language_id, size=len(response.content))
                    return response.content
                log.error("tts.server_error", status=response.status_code, body=response.text)
                return None
        except Exception:
            log.exception("tts.failed")
            return None
