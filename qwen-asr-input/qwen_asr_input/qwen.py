from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from websockets.asyncio.client import connect

from .config import QwenSettings
from .contracts import TranscriptCallback, TranscriptUpdate


class QwenStreamingAsrClient:
    def __init__(self, settings: QwenSettings, api_key: str) -> None:
        self.settings = settings
        self.api_key = api_key

    async def transcribe(
        self,
        audio: AsyncIterator[bytes],
        on_update: TranscriptCallback | None = None,
    ) -> str:
        task_id = uuid.uuid4().hex
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with connect(
            self.settings.endpoint,
            additional_headers=headers,
            max_size=None,
            open_timeout=10,
            close_timeout=3,
        ) as websocket:
            await websocket.send(json.dumps(self._run_task(task_id), ensure_ascii=False))
            await self._wait_started(websocket, task_id)

            receiver = asyncio.create_task(
                self._collect_final(websocket, task_id, on_update)
            )
            try:
                async for chunk in audio:
                    await websocket.send(chunk)
                await websocket.send(json.dumps(self._finish_task(task_id)))
                return await receiver
            except BaseException:
                receiver.cancel()
                raise

    def _run_task(self, task_id: str) -> dict:
        task_input: dict = {}
        if self.settings.prompt:
            task_input["context"] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": self.settings.prompt}
                    ],
                }
            ]
        parameters: dict = {
            "format": "pcm",
            "sample_rate": 16_000,
            "semantic_punctuation_enabled": False,
        }
        if self.settings.language not in {"", "auto"}:
            parameters["language_hints"] = [self.settings.language]
        return {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": self.settings.model,
                "parameters": parameters,
                "input": task_input,
            },
        }

    @staticmethod
    def _finish_task(task_id: str) -> dict:
        return {
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }

    async def _wait_started(self, websocket, task_id: str) -> None:
        while True:
            event = self._decode(await websocket.recv(), task_id)
            name = event["header"].get("event")
            if name == "task-started":
                return
            if name == "task-failed":
                self._raise_task_failed(event)

    async def _collect_final(
        self,
        websocket,
        task_id: str,
        on_update: TranscriptCallback | None,
    ) -> str:
        sentences: dict[str, str] = {}
        while True:
            event = self._decode(await websocket.recv(), task_id)
            name = event["header"].get("event")
            if name == "task-failed":
                self._raise_task_failed(event)
            if name == "result-generated":
                sentence = (
                    event.get("payload", {}).get("output", {}).get("sentence")
                    or {}
                )
                if not sentence.get("heartbeat"):
                    text = str(sentence.get("text", ""))
                    sentence_end = bool(sentence.get("sentence_end"))
                    sentence_id = str(
                        sentence.get("sentence_id", len(sentences))
                    )
                    if text and sentence_end:
                        sentences[sentence_id] = text
                    if text and on_update is not None:
                        stable = "".join(sentences.values())
                        display = stable if sentence_end else stable + text
                        on_update(
                            TranscriptUpdate(text=display, final=sentence_end)
                        )
            if name == "task-finished":
                return "".join(sentences.values()).strip()

    @staticmethod
    def _decode(message: str | bytes, task_id: str) -> dict:
        if isinstance(message, bytes):
            raise RuntimeError("unexpected binary event from DashScope")
        event = json.loads(message)
        header = event.get("header", {})
        received_id = header.get("task_id")
        if received_id and received_id != task_id:
            raise RuntimeError("DashScope returned an event for another task")
        return event

    @staticmethod
    def _raise_task_failed(event: dict) -> None:
        header = event.get("header", {})
        code = header.get("error_code", "unknown")
        message = header.get("error_message", "unknown error")
        raise RuntimeError(f"DashScope task failed ({code}): {message}")
