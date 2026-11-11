from __future__ import annotations

import asyncio
import logging
import threading

from .audio import ArecordAudioSource
from .config import AppSettings, require_api_key
from .hotkey import EvdevPushToTalk, HotkeyTransition
from .overlay import QtStreamingOverlay
from .qwen import QwenStreamingAsrClient
from .x11_input import X11FocusTracker, X11XTestPasteInjector


LOG = logging.getLogger("qwen-asr-input")


class PushToTalkApp:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.hotkey = EvdevPushToTalk()
        self.focus = X11FocusTracker()
        self.injector = X11XTestPasteInjector()
        self.client = QwenStreamingAsrClient(settings.qwen, require_api_key())
        self.overlay = QtStreamingOverlay(settings.overlay)
        self._stop: asyncio.Event | None = None
        self._all_keys_released: asyncio.Event | None = None
        self._session: asyncio.Task | None = None

    async def run(self) -> None:
        LOG.info("ready — hold Ctrl+Win to record")
        loop = asyncio.get_running_loop()
        transitions: asyncio.Queue[HotkeyTransition] = asyncio.Queue()
        threading.Thread(
            target=self._hotkey_worker,
            args=(loop, transitions),
            name="evdev-hotkey",
            daemon=True,
        ).start()
        while True:
            transition = await transitions.get()
            if transition is HotkeyTransition.START:
                await self._start()
            elif transition is HotkeyTransition.STOP:
                if self._stop is not None:
                    self._stop.set()
                    self.overlay.transcribing()
                    LOG.info("recording stopped; transcribing")
            elif transition is HotkeyTransition.RELEASED:
                if self._all_keys_released is not None:
                    self._all_keys_released.set()

    def _hotkey_worker(
        self,
        loop: asyncio.AbstractEventLoop,
        transitions: asyncio.Queue[HotkeyTransition],
    ) -> None:
        while True:
            transition = self.hotkey.next_transition()
            loop.call_soon_threadsafe(transitions.put_nowait, transition)

    async def _start(self) -> None:
        if self._session is not None and not self._session.done():
            LOG.warning("previous transcription is still finishing")
            return
        target = await asyncio.to_thread(self.focus.capture)
        self._stop = asyncio.Event()
        self._all_keys_released = asyncio.Event()
        self._session = asyncio.create_task(
            self._record_transcribe_inject(
                target, self._stop, self._all_keys_released
            )
        )
        self.overlay.listening()
        LOG.info("recording started")

    async def _record_transcribe_inject(
        self, target, stop: asyncio.Event, all_keys_released: asyncio.Event
    ) -> None:
        try:
            audio = ArecordAudioSource(self.settings.audio)
            text = await self.client.transcribe(
                audio.chunks(stop), on_update=self.overlay.update
            )
            await all_keys_released.wait()
            if not text:
                LOG.info("no speech recognized")
                self.overlay.complete("未识别到语音")
                return
            await asyncio.to_thread(self.injector.inject, text, target)
            self.overlay.complete(text)
            LOG.info("inserted: %s", text)
        except Exception as exc:
            LOG.exception("dictation failed")
            self.overlay.error(str(exc))
