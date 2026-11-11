from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QwenSettings:
    region: str = "beijing"
    model: str = "qwen-audio-3.0-asr-flash-streaming"
    language: str = "zh"
    prompt: str | None = None

    @property
    def endpoint(self) -> str:
        hosts = {
            "beijing": "dashscope.aliyuncs.com",
            "singapore": "dashscope-intl.aliyuncs.com",
        }
        try:
            host = hosts[self.region]
        except KeyError as exc:
            raise ValueError("qwen.region must be 'beijing' or 'singapore'") from exc
        return f"wss://{host}/api-ws/v1/inference"


@dataclass(frozen=True, slots=True)
class AudioSettings:
    device: str = "default"
    sample_rate: int = 16_000
    chunk_ms: int = 100

    @property
    def chunk_bytes(self) -> int:
        return self.sample_rate * 2 * self.chunk_ms // 1000


@dataclass(frozen=True, slots=True)
class OverlaySettings:
    enabled: bool = True
    final_hold_ms: int = 1200
    width: int = 620
    bottom_margin: int = 72


@dataclass(frozen=True, slots=True)
class AppSettings:
    qwen: QwenSettings = QwenSettings()
    audio: AudioSettings = AudioSettings()
    overlay: OverlaySettings = OverlaySettings()


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or Path(os.environ.get("QWEN_ASR_INPUT_CONFIG", "config.toml"))
    raw: dict = {}
    if path.exists():
        with path.open("rb") as handle:
            raw = tomllib.load(handle)

    qwen = raw.get("qwen", {})
    audio = raw.get("audio", {})
    overlay = raw.get("overlay", {})
    settings = AppSettings(
        qwen=QwenSettings(
            region=str(qwen.get("region", "beijing")).lower(),
            model=str(qwen.get("model", "qwen-audio-3.0-asr-flash-streaming")),
            language=str(qwen.get("language", "zh")),
            prompt=qwen.get("prompt"),
        ),
        audio=AudioSettings(
            device=str(audio.get("device", "default")),
            sample_rate=int(audio.get("sample_rate", 16_000)),
            chunk_ms=int(audio.get("chunk_ms", 100)),
        ),
        overlay=OverlaySettings(
            enabled=bool(overlay.get("enabled", True)),
            final_hold_ms=int(overlay.get("final_hold_ms", 1200)),
            width=int(overlay.get("width", 620)),
            bottom_margin=int(overlay.get("bottom_margin", 72)),
        ),
    )
    if settings.audio.sample_rate != 16_000:
        raise ValueError("first version requires audio.sample_rate = 16000")
    if settings.audio.chunk_ms <= 0:
        raise ValueError("audio.chunk_ms must be positive")
    if settings.overlay.final_hold_ms < 0:
        raise ValueError("overlay.final_hold_ms cannot be negative")
    if not 320 <= settings.overlay.width <= 1200:
        raise ValueError("overlay.width must be between 320 and 1200")
    if settings.overlay.bottom_margin < 0:
        raise ValueError("overlay.bottom_margin cannot be negative")
    if not settings.qwen.model.endswith("-streaming"):
        raise ValueError("use the streaming model: qwen-audio-3.0-asr-flash-streaming")
    return settings


def require_api_key() -> str:
    key = os.environ.get("ALIYUN_ASR_API_KEY", "")
    if not key:
        raise RuntimeError("ALIYUN_ASR_API_KEY is not set")
    return key
