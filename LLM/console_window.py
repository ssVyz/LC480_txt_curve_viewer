"""LLM chat console window."""

from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

from LLM.bridge import MainWindowBridge
from LLM.service import GeminiService, TokenLimitReached
from LLM.functions import FUNCTION_MAP

if TYPE_CHECKING:
    from main_window import MainWindow


# ---------------------------------------------------------------------------
# Background worker for the blocking API call
# ---------------------------------------------------------------------------

class _ApiWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, service: GeminiService, message):
        super().__init__()
        self._service = service
        self._message = message

    def run(self):
        try:
            response = self._service.send_message(self._message)
            self.finished.emit(response)
        except TokenLimitReached as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Console window
# ---------------------------------------------------------------------------

class LLMConsoleWindow(QWidget):
    closed = Signal()

    def __init__(self, main_window: MainWindow, api_key: str, token_limit: int):
        super().__init__()
        self.setWindowTitle("LLM Assistant")
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(620, 700)

        self._bridge = MainWindowBridge(main_window)
        self._service = GeminiService(api_key, token_limit)
        self._thread: QThread | None = None

        self._setup_ui()

    # -- UI ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._chat_view = QTextBrowser()
        self._chat_view.setOpenExternalLinks(False)
        layout.addWidget(self._chat_view, stretch=1)

        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message...")
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)
        layout.addLayout(input_row)

        self._token_label = QLabel()
        self._update_token_label()
        layout.addWidget(self._token_label)

    # -- Sending messages ----------------------------------------------------

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append_user(text)
        self._set_busy(True)
        self._call_api(text)

    def _call_api(self, message):
        worker = _ApiWorker(self._service, message)
        thread = QThread()
        worker.moveToThread(thread)

        worker.finished.connect(self._on_response)
        worker.error.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        thread.started.connect(worker.run)

        # prevent GC
        self._thread = thread
        self._worker = worker

        thread.start()

    # -- Response handling ---------------------------------------------------

    def _on_response(self, response):
        self._update_token_label()

        parts = response.candidates[0].content.parts
        func_calls = [p for p in parts if p.function_call]
        text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]

        if func_calls:
            from google.genai import types

            response_parts = []
            for part in func_calls:
                fc = part.function_call
                args = dict(fc.args) if fc.args else {}
                self._append_function_call(fc.name, args)

                fn = FUNCTION_MAP.get(fc.name)
                if fn:
                    try:
                        result = fn(self._bridge, **args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                else:
                    result = {"error": f"Unknown function: {fc.name}"}

                self._append_function_result(fc.name, result)
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response=result)
                )

            # Send function results back to the model
            self._call_api(response_parts)
            return

        # Text-only response
        text = "\n".join(text_parts) if text_parts else "(no response)"
        self._append_assistant(text)
        self._set_busy(False)

    def _on_error(self, error_text: str):
        self._update_token_label()
        self._append_html(
            f'<div style="background:#FFEBEE; padding:8px; margin:4px 0; '
            f'border-radius:4px; white-space:pre-wrap;">'
            f'<b>Error:</b><br>{_esc(error_text)}</div>'
        )
        self._set_busy(False)

    # -- Chat display helpers ------------------------------------------------

    def _append_user(self, text: str):
        self._append_html(
            f'<div style="background:#E3F2FD; padding:8px; margin:4px 0; border-radius:4px;">'
            f'<b>You:</b><br>{_esc(text)}</div>'
        )

    def _append_assistant(self, text: str):
        tokens = self._service.total_tokens
        limit = self._service.token_limit
        self._append_html(
            f'<div style="background:#F5F5F5; padding:8px; margin:4px 0; border-radius:4px;">'
            f'<b>Assistant:</b><br>{_esc(text)}<br>'
            f'<span style="color:#888; font-size:0.85em;">'
            f'Tokens: {self._service.total_input_tokens:,} in / '
            f'{self._service.total_output_tokens:,} out '
            f'({tokens:,} / {limit:,})</span></div>'
        )

    def _append_function_call(self, name: str, args: dict):
        args_str = json.dumps(args, indent=2) if args else "()"
        self._append_html(
            f'<div style="background:#FFF3E0; padding:6px; margin:2px 0; '
            f'border-radius:4px; font-size:0.9em;">'
            f'<b>Call:</b> <code>{_esc(name)}</code><br>'
            f'<pre style="margin:2px 0;">{_esc(args_str)}</pre></div>'
        )

    def _append_function_result(self, name: str, result: dict):
        result_str = json.dumps(result, indent=2, default=str)
        # Truncate very long results for display
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "\n... (truncated)"
        self._append_html(
            f'<div style="background:#E8F5E9; padding:6px; margin:2px 0; '
            f'border-radius:4px; font-size:0.9em;">'
            f'<b>Result:</b> <code>{_esc(name)}</code><br>'
            f'<pre style="margin:2px 0;">{_esc(result_str)}</pre></div>'
        )

    def _append_html(self, html: str):
        self._chat_view.append(html)
        sb = self._chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -- UI state ------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._send_btn.setText("Thinking..." if busy else "Send")
        if not busy:
            self._input.setFocus()

    def _update_token_label(self):
        t = self._service.total_tokens
        lim = self._service.token_limit
        self._token_label.setText(
            f"Tokens used: {t:,} / {lim:,}  "
            f"(in: {self._service.total_input_tokens:,}  "
            f"out: {self._service.total_output_tokens:,})"
        )

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


def _esc(text: str) -> str:
    """Escape HTML entities."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
