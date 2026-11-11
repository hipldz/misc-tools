"""Azure Speech synthesis shared by narration and voice previews."""
from __future__ import annotations

import os
from datetime import timedelta
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import azure.cognitiveservices.speech as speechsdk

TICKS_PER_SECOND = 10_000_000
OUTPUT_FORMAT = speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not visible to Python. Export AZURE_SPEECH_KEY and "
            "AZURE_SPEECH_ENDPOINT in the terminal that starts Studio, then try again."
        )
    return value


def speech_config(voice: str) -> speechsdk.SpeechConfig:
    key = _required_environment("AZURE_SPEECH_KEY")
    endpoint_url = _required_environment("AZURE_SPEECH_ENDPOINT")
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(
            "AZURE_SPEECH_ENDPOINT must be a complete Azure Speech endpoint URL")
    base_endpoint = f"{parsed.scheme}://{parsed.netloc}"
    config = speechsdk.SpeechConfig(subscription=key, endpoint=base_endpoint)
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(OUTPUT_FORMAT)
    return config


def _duration_seconds(value: object) -> float:
    if isinstance(value, timedelta):
        return value.total_seconds()
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric


def _tick_seconds(value: object) -> float:
    try:
        return float(value) / TICKS_PER_SECOND
    except (TypeError, ValueError):
        return 0.0


def ssml(text: str, voice: str, rate: str, pitch: str) -> str:
    locale = "-".join(voice.split("-")[:2]) or "en-US"
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{escape(locale, quote=True)}">'
        f'<voice name="{escape(voice, quote=True)}">'
        f'<prosody rate="{escape(rate, quote=True)}" pitch="{escape(pitch, quote=True)}">'
        f"{escape(text)}</prosody></voice></speak>"
    )


def _cancellation_message(result: speechsdk.SpeechSynthesisResult) -> str:
    details = result.cancellation_details
    reason = getattr(details, "reason", "unknown")
    error_code = getattr(details, "error_code", "")
    error_details = getattr(details, "error_details", "")
    parts = [f"reason={reason}"]
    if error_code:
        parts.append(f"code={error_code}")
    if error_details:
        parts.append(str(error_details))
    return "; ".join(parts)


def synthesize_to_file(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: Path,
    *,
    capture_words: bool = True,
) -> tuple[list[dict], float]:
    """Synthesize one utterance and return word timings plus provider duration."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_config = speechsdk.audio.AudioOutputConfig(
        filename=str(output_path.resolve()))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config(voice),
        audio_config=audio_config,
    )
    words: list[dict] = []

    if capture_words:
        def on_word_boundary(event: object) -> None:
            start = _tick_seconds(getattr(event, "audio_offset", 0))
            duration = _duration_seconds(getattr(event, "duration", 0))
            word = str(getattr(event, "text", "") or "")
            if word:
                words.append(
                    {"start": start, "end": start + duration, "text": word})

        synthesizer.synthesis_word_boundary.connect(on_word_boundary)

    result = synthesizer.speak_ssml_async(ssml(text, voice, rate, pitch)).get()
    if result.reason == speechsdk.ResultReason.Canceled:
        raise RuntimeError(
            f"Azure Speech synthesis was canceled: {_cancellation_message(result)}")
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(
            f"Azure Speech synthesis did not complete: {result.reason}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Azure Speech returned an empty audio file")
    return words, _duration_seconds(getattr(result, "audio_duration", 0))
