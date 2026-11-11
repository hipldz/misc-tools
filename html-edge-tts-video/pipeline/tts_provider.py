"""Provider selection and synthesis dispatch for Edge TTS and Azure Speech."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

PROVIDERS = {"edge", "azure"}


def azure_configuration_status() -> dict:
    key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    endpoint_value = os.environ.get("AZURE_SPEECH_ENDPOINT", "").strip()
    endpoint = urlparse(endpoint_value)
    missing = [
        name
        for name, value in [
            ("AZURE_SPEECH_KEY", key),
            ("AZURE_SPEECH_ENDPOINT", endpoint_value),
        ]
        if not value
    ]
    endpoint_valid = bool(
        endpoint_value
        and endpoint.scheme in {"http", "https"}
        and endpoint.netloc
    )
    configured = bool(key and endpoint_valid)
    if missing:
        message = (
            f"Python 进程未读取到 {', '.join(missing)}。请在启动 Studio 的终端中使用 export，"
            "然后重启 Studio。"
        )
    elif not endpoint_valid:
        message = "AZURE_SPEECH_ENDPOINT 不是完整的 http/https URL。"
    else:
        message = "Azure Speech 凭据已导出到 Python 进程；有效性将在生成时验证。"
    return {
        "configured": configured,
        "message": message,
        "missing": missing,
    }


def azure_configured() -> bool:
    return bool(azure_configuration_status()["configured"])


def provider_options() -> list[dict]:
    azure = azure_configuration_status()
    return [
        {
            "id": "edge",
            "label": "Edge TTS",
            "configured": True,
            "message": "Edge TTS 无需配置密钥。",
        },
        {"id": "azure", "label": "Azure Speech", **azure},
    ]


def resolve_provider(value: str | None) -> str:
    requested = str(value or "edge").strip().lower()
    if requested not in PROVIDERS:
        raise RuntimeError("TTS provider must be edge or azure")
    if requested == "azure" and not azure_configured():
        status = azure_configuration_status()
        raise RuntimeError(
            "Azure Speech is selected but unavailable. "
            f"{status['message']}"
        )
    return requested


def synthesize_to_file(
    provider: str,
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: Path,
    *,
    capture_words: bool = True,
) -> tuple[list[dict], float]:
    resolved = resolve_provider(provider)
    if resolved == "azure":
        try:
            from .azure_speech import synthesize_to_file as synthesize
        except ImportError:
            from azure_speech import synthesize_to_file as synthesize
    else:
        try:
            from .edge_speech import synthesize_to_file as synthesize
        except ImportError:
            from edge_speech import synthesize_to_file as synthesize
    return synthesize(
        text,
        voice,
        rate,
        pitch,
        output_path,
        capture_words=capture_words,
    )
