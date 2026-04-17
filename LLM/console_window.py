"""LLM chat console window."""

from __future__ import annotations

import json
import sys
import threading
import traceback
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Signal

from LLM.bridge import MainWindowBridge
from LLM.service import GeminiService, TokenLimitReached, ParsedResponse
from LLM.functions import FUNCTION_MAP

if TYPE_CHECKING:
    from main_window import MainWindow


def _dbg(msg: str):
    print(f"[LLM-DEBUG] {msg}", file=sys.stderr, flush=True)


class LLMConsoleWindow(QWidget):
    closed = Signal()

    # Internal signals for thread → main-thread communication
    _api_finished = Signal(object)   # ParsedResponse
    _api_error = Signal(str)

    def __init__(self, main_window: MainWindow, api_key: str, token_limit: int):
        super().__init__()
        _dbg("LLMConsoleWindow.__init__: start")
        self.setWindowTitle("LLM Assistant")
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(620, 700)

        self._bridge = MainWindowBridge(main_window)
        _dbg("LLMConsoleWindow.__init__: bridge created")
        self._service = GeminiService(api_key, token_limit)
        _dbg("LLMConsoleWindow.__init__: service created")

        self._setup_ui()

        # Connect internal signals (queued: worker thread → main thread)
        self._api_finished.connect(self._on_response)
        self._api_error.connect(self._on_error)
        _dbg("LLMConsoleWindow.__init__: done")

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
        _dbg(f"_on_send: user text='{text[:80]}...'")
        self._input.clear()
        self._append_user(text)
        self._set_busy(True)
        self._call_api(text)

    def _call_api(self, message, is_function_result: bool = False):
        """Run the blocking API call on a daemon thread."""
        _dbg(f"_call_api: spawning thread (is_function_result={is_function_result})")

        def _worker():
            _dbg(f"_worker: start (is_function_result={is_function_result})")
            try:
                if is_function_result:
                    parsed = self._service.send_function_results(message)
                else:
                    parsed = self._service.send_message(message)
                _dbg("_worker: emitting _api_finished")
                self._api_finished.emit(parsed)
            except TokenLimitReached as exc:
                _dbg(f"_worker: TokenLimitReached: {exc}")
                self._api_error.emit(str(exc))
            except Exception:
                tb = traceback.format_exc()
                _dbg(f"_worker: exception:\n{tb}")
                self._api_error.emit(tb)
            _dbg("_worker: done")

        threading.Thread(target=_worker, daemon=True).start()
        _dbg("_call_api: thread started")

    # -- Response handling ---------------------------------------------------

    def _on_response(self, parsed: ParsedResponse):
        _dbg(f"_on_response: received ParsedResponse "
             f"(text={len(parsed.text_parts)}, funcs={len(parsed.function_calls)}, "
             f"in={parsed.input_tokens}, out={parsed.output_tokens})")
        self._update_token_label()

        if parsed.function_calls:
            _dbg(f"_on_response: processing {len(parsed.function_calls)} function call(s)")
            results: list[tuple[str, dict]] = []
            for fc in parsed.function_calls:
                _dbg(f"_on_response: calling {fc.name}({list(fc.args.keys())})")
                self._append_function_call(fc.name, fc.args)

                fn = FUNCTION_MAP.get(fc.name)
                if fn:
                    try:
                        result = fn(self._bridge, **fc.args)
                        _dbg(f"_on_response: {fc.name} returned OK, "
                             f"keys={list(result.keys()) if isinstance(result, dict) else '?'}")
                    except Exception as exc:
                        _dbg(f"_on_response: {fc.name} raised: {exc}")
                        result = {"error": str(exc)}
                else:
                    _dbg(f"_on_response: unknown function {fc.name}")
                    result = {"error": f"Unknown function: {fc.name}"}

                self._append_function_result(fc.name, result)
                results.append((fc.name, result))

            _dbg(f"_on_response: sending {len(results)} function result(s) back to API")
            self._call_api(results, is_function_result=True)
            return

        text = "\n".join(parsed.text_parts) if parsed.text_parts else "(no response)"
        _dbg(f"_on_response: text response ({len(text)} chars), turn complete")
        self._append_assistant(text)
        self._set_busy(False)

    def _on_error(self, error_text: str):
        _dbg(f"_on_error: {error_text[:200]}")
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
        _dbg("LLMConsoleWindow.closeEvent")
        self.closed.emit()
        super().closeEvent(event)


def _esc(text: str) -> str:
    """Escape HTML entities."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
