from __future__ import annotations

import argparse
import asyncio
import atexit
import ctypes.util
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from .app import PushToTalkApp
from .config import load_settings
from .hotkey import EvdevPushToTalk
from .x11_input import X11FocusTracker, X11XTestPasteInjector


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen push-to-talk input")
    parser.add_argument("--config", type=Path, help="TOML config path")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="check local dependencies without networking"
    )
    parser.add_argument(
        "--inject-test",
        metavar="TEXT",
        help="after 3 seconds, paste TEXT into the currently focused X11 input",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # websockets DEBUG logs include the Authorization request header.
    logging.getLogger("websockets").setLevel(logging.WARNING)
    settings = load_settings(args.config)
    if args.check:
        _check_environment(settings.overlay.enabled)
        return
    if args.inject_test is not None:
        print("3 秒内切换到目标输入框……", flush=True)
        time.sleep(3)
        target = X11FocusTracker().capture()
        X11XTestPasteInjector().inject(args.inject_test, target)
        print("注入测试完成；文字也保留在剪贴板。")
        return
    _register_pid_file()
    try:
        asyncio.run(PushToTalkApp(settings).run())
    except KeyboardInterrupt:
        pass


def _register_pid_file() -> None:
    raw_path = os.environ.get("QWEN_ASR_INPUT_PID_FILE")
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    current_pid = str(os.getpid())
    path.write_text(current_pid + "\n", encoding="utf-8")

    def cleanup() -> None:
        try:
            if path.read_text(encoding="utf-8").strip() == current_pid:
                path.unlink()
        except FileNotFoundError:
            pass

    atexit.register(cleanup)


def _check_environment(overlay_enabled: bool) -> None:
    failures: list[str] = []
    commands = ["arecord", "xclip"]
    for command in commands:
        path = shutil.which(command)
        print(f"{command}: {path or 'MISSING'}")
        if path is None:
            failures.append(command)
    if overlay_enabled:
        qt = subprocess.run(
            ["/usr/bin/python3", "-c", "from PyQt5.QtWidgets import QApplication"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
        print(f"PyQt5 overlay: {'available' if qt else 'MISSING'}")
        if not qt:
            failures.append("PyQt5 overlay")
    for library in ("X11", "Xtst"):
        path = ctypes.util.find_library(library)
        print(f"lib{library}: {path or 'MISSING'}")
        if path is None:
            failures.append(f"lib{library}")
    print(f"DISPLAY: {os.environ.get('DISPLAY') or 'MISSING'}")
    print(
        "ALIYUN_ASR_API_KEY:",
        "set" if os.environ.get("ALIYUN_ASR_API_KEY") else "MISSING",
    )
    try:
        target = X11FocusTracker().capture()
        print(f"X11 input focus: {target.window_id}")
    except Exception as exc:
        failures.append("X11 focus")
        print(f"X11 input focus: FAILED ({exc})")
    try:
        hotkey = EvdevPushToTalk()
        hotkey.close()
        print("evdev keyboard: readable")
    except Exception as exc:
        failures.append("evdev")
        print(f"evdev keyboard: FAILED ({exc})")
    if failures:
        raise SystemExit("check failed: " + ", ".join(failures))
    print("local component check passed (no network request was made)")


if __name__ == "__main__":
    main()
