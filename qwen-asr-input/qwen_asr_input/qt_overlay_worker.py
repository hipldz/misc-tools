from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PyQt5.QtCore import QSize, QSocketNotifier, Qt, QTimer
from PyQt5.QtGui import QCursor, QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


COLORS = {
    "listening": "#ff5c72",
    "streaming": "#8b7cff",
    "final": "#65d6ad",
    "transcribing": "#f7c85e",
    "complete": "#65d6ad",
    "error": "#ff6b6b",
}


class LatestTextLabel(QLabel):
    """Single-line label that keeps the newest complete characters visible."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full_text = ""
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setContentsMargins(1, 0, 0, 0)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self._update_elision()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elision()

    def _update_elision(self) -> None:
        available_width = max(0, self.contentsRect().width())
        visible_text = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideLeft, available_width
        )
        super().setText(visible_text)


class OverlayWindow(QWidget):
    def __init__(self, width: int, bottom_margin: int) -> None:
        super().__init__()
        self.overlay_width = width
        self.bottom_margin = bottom_margin
        self.pulse_on = False
        self.state = "listening"

        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(width, 92)

        panel = QWidget(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(
            "#panel { background: rgba(25, 27, 35, 238);"
            " border: 1px solid rgba(255, 255, 255, 34); border-radius: 22px; }"
        )
        self.icon = QLabel()
        self.icon.setFixedSize(52, 52)
        self.icon.setAlignment(Qt.AlignCenter)
        microphone = Path(__file__).parent / "assets" / "mic.svg"
        microphone_icon = QIcon(str(microphone))
        if microphone_icon.isNull():
            self.icon.setText("●")
            self.icon.setFont(QFont("Sans", 24, QFont.Bold))
        else:
            # QIcon's SVG engine renders at the screen DPR (36 physical px at
            # 1.25x) instead of scaling the SVG's intrinsic 32 px bitmap.
            self.icon.setPixmap(microphone_icon.pixmap(QSize(29, 29)))

        self.caption = QLabel("QWEN 语音输入")
        self.caption.setStyleSheet(
            "color: rgba(255,255,255,145); font-size: 10px;"
            " font-weight: 600; letter-spacing: 1px;"
        )
        self.text = LatestTextLabel("正在聆听…")
        self.text.setStyleSheet(
            "color: #f7f7fb; font-size: 16px; font-weight: 500;"
        )
        # Leave a little more than one full font line so glyph descenders and
        # antialiasing are not clipped on fractional display scaling.
        self.text.setMinimumHeight(self.text.fontMetrics().height() + 4)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 12, 0)
        copy.setSpacing(4)
        copy.addWidget(self.caption)
        copy.addWidget(self.text, 1)

        content = QHBoxLayout(panel)
        content.setContentsMargins(18, 14, 18, 14)
        content.setSpacing(14)
        content.addWidget(self.icon)
        content.addLayout(copy, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 12)
        root.addWidget(panel)

        self.pulse = QTimer(self)
        self.pulse.timeout.connect(self._pulse)
        self.pulse.start(520)
        self.set_message("listening", "正在聆听…")

    def set_message(self, state: str, text: str) -> None:
        self.state = state
        color = COLORS.get(state, COLORS["streaming"])
        self.icon.setStyleSheet(
            f"background: #eef4ff; color: {color}; border-radius: 17px;"
            f" border: 2px solid {color};"
        )
        captions = {
            "listening": "QWEN · 正在录音",
            "streaming": "QWEN · 实时识别",
            "final": "QWEN · 语句完成",
            "transcribing": "QWEN · 正在整理",
            "complete": "QWEN · 已输入",
            "error": "QWEN · 识别失败",
        }
        self.caption.setText(captions.get(state, "QWEN 语音输入"))
        self.text.setText(text)
        self._position_bottom_center()
        if not self.isVisible():
            self.show()

    def _pulse(self) -> None:
        if self.state not in {"listening", "streaming"}:
            return
        self.pulse_on = not self.pulse_on
        color = COLORS[self.state]
        border = f"3px solid {color}" if self.pulse_on else f"2px solid {color}"
        self.icon.setStyleSheet(
            f"background: #eef4ff; color: {color}; border-radius: 17px;"
            f" border: {border};"
        )

    def _position_bottom_center(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + geometry.height() - self.height() - self.bottom_margin
        self.move(x, y)

    def showEvent(self, event) -> None:
        self._position_bottom_center()
        super().showEvent(event)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=620)
    parser.add_argument("--bottom-margin", type=int, default=72)
    args = parser.parse_args()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    window = OverlayWindow(args.width, args.bottom_margin)
    window.show()

    notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Read)

    def receive() -> None:
        line = sys.stdin.readline()
        if not line:
            app.quit()
            return
        try:
            message = json.loads(line)
            window.set_message(str(message.get("state", "streaming")), str(message.get("text", "")))
        except (json.JSONDecodeError, TypeError):
            pass

    notifier.activated.connect(receive)
    raise SystemExit(app.exec_())


if __name__ == "__main__":
    main()
