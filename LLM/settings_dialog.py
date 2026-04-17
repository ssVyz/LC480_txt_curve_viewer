"""LLM settings dialog for API key and token limit configuration."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QPushButton, QHBoxLayout,
)


class LLMSettingsDialog(QDialog):
    def __init__(self, api_key: str = "", token_limit: int = 500_000, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Settings")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._key_edit = QLineEdit(api_key)
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("Google AI Studio API key")
        form.addRow("API Key:", self._key_edit)

        self._limit_spin = QSpinBox()
        self._limit_spin.setRange(10_000, 10_000_000)
        self._limit_spin.setSingleStep(50_000)
        self._limit_spin.setValue(token_limit)
        self._limit_spin.setSuffix(" tokens")
        form.addRow("Token Limit:", self._limit_spin)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def get_api_key(self) -> str:
        return self._key_edit.text().strip()

    def get_token_limit(self) -> int:
        return self._limit_spin.value()
