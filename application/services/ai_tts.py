"""TTS generation mixin for AIService."""

from __future__ import annotations

import asyncio
import re
import tempfile
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
        """Generate speech via voice-sp/Qwen first, fallback to legacy TTS_URL."""
        if not text:
            log.warning("tts.empty_text")
            return None

        cleaned_text = re.sub(r"\s+", " ", text.strip())[:300]
        if not cleaned_text:
            return None

        voice_sp_audio = await self._generate_speech_voice_sp(cleaned_text)
        if voice_sp_audio:
            return voice_sp_audio

        return await self._generate_speech_legacy(
            cleaned_text,
            language_id=language_id,
            ref_wav=ref_wav,
            exaggeration=exaggeration,
            temperature=temperature,
            cfg_weight=cfg_weight,
        )

    async def _generate_speech_voice_sp(self, text: str) -> bytes | None:
        """Generate Telegram voice-ready OGG/Opus audio using /usr/local/bin/voice-sp."""
        speaker = getattr(self.config, "VOICE_SP_SPEAKER", "ono_anna")
        language = getattr(self.config, "VOICE_SP_LANGUAGE", "russian")
        instruct = getattr(
            self.config,
            "VOICE_SP_INSTRUCT",
            "Говори дружелюбно и живо, как телеграм-бот MineBridge.",
        )
        timeout = float(getattr(self.config, "VOICE_SP_TIMEOUT", 600))

        with tempfile.TemporaryDirectory(prefix="bridjik-tts-") as tmpdir:
            wav_path = Path(tmpdir) / "voice.wav"
            ogg_path = Path(tmpdir) / "voice.ogg"
            cmd = [
                "/usr/local/bin/voice-sp",
                text,
                "-s",
                speaker,
                "-l",
                language,
                "-o",
                str(wav_path),
            ]
            if instruct:
                cmd.extend(["-i", instruct])

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                if proc.returncode != 0:
                    log.error(
                        "tts.voice_sp_failed",
                        returncode=proc.returncode,
                        stdout=stdout.decode(errors="ignore")[-500:],
                        stderr=stderr.decode(errors="ignore")[-500:],
                    )
                    return None

                ffmpeg = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    str(ogg_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, ffmpeg_stderr = await asyncio.wait_for(ffmpeg.communicate(), timeout=60)
                if ffmpeg.returncode != 0:
                    log.error(
                        "tts.ffmpeg_failed",
                        stderr=ffmpeg_stderr.decode(errors="ignore")[-500:],
                    )
                    return None

                audio = ogg_path.read_bytes()
                log.info("tts.voice_sp_generated", speaker=speaker, size=len(audio))
                return audio
            except Exception:
                log.exception("tts.voice_sp_exception")
                return None

    async def _generate_speech_legacy(
        self,
        text: str,
        language_id: str = "ru",
        ref_wav: str | None = None,
        exaggeration: float = 0.5,
        temperature: float = 0.8,
        cfg_weight: float = 0.5,
    ) -> bytes | None:
        """Fallback: generate speech using legacy Chatterbox-compatible TTS_URL."""
        files = {}
        data = {
            "text": text,
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
                    log.info("tts.legacy_generated", lang=language_id, size=len(response.content))
                    return response.content
                log.error("tts.legacy_server_error", status=response.status_code, body=response.text)
                return None
        except Exception:
            log.exception("tts.legacy_failed")
            return None
