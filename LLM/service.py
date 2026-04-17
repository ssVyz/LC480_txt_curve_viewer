"""Gemini API service — manages client, chat session, and token tracking."""

from google import genai
from google.genai import types

from LLM.declarations import ALL_DECLARATIONS

SYSTEM_PROMPT = """\
You are a qPCR data analysis assistant integrated into the LC480 Result Viewer \
application. You help users analyze and visualize LightCycler 480 amplification \
curve data through natural conversation.

Capabilities:
- Query experiment info and per-well summary data (raw signal, derivatives, Ct, Call)
- Modify the view: display mode, color mode, channels, line width, smoothing, log scale
- Select, activate, or inactivate wells
- Assign custom colors to wells
- Adjust baseline parameters (start/end cycle, Ct/call thresholds)

Guidelines:
- Be concise. Query only the wells and channels you need to minimize token usage.
- A standard 96-well plate has rows A-H and columns 1-12. Wells are named like A1, B12, H6.
- When checking whether wells are empty or populated, examine raw signal levels and \
first derivatives. Empty wells typically have near-zero fluorescence that stays flat \
across cycles (very low max first derivative).
- Prefer the default baseline settings (start_cycle=3, end_cycle=8, ct_threshold=1.5, \
call_threshold=1.5) unless a change is obviously needed or the user explicitly requests it.
- Colors are hex strings: '#FF0000' red, '#00AA00' green, '#0000FF' blue, etc.
- Always confirm what actions you have taken.
"""


class TokenLimitReached(Exception):
    pass


class GeminiService:
    """Wraps a Gemini chat session with token accounting."""

    def __init__(self, api_key: str, token_limit: int):
        self._client = genai.Client(api_key=api_key)
        self._token_limit = token_limit
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._chat = self._client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=ALL_DECLARATIONS)],
            ),
        )

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def token_limit(self) -> int:
        return self._token_limit

    def send_message(self, message):
        """Send a message (text or function-response parts) and return the response.

        Raises TokenLimitReached if the cumulative token budget is exhausted.
        """
        if self.total_tokens >= self._token_limit:
            raise TokenLimitReached(
                f"Token limit reached ({self.total_tokens:,} / {self._token_limit:,}). "
                "Close and reopen the console to start a new session."
            )
        response = self._chat.send_message(message)
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.total_input_tokens += getattr(usage, "prompt_token_count", 0) or 0
            self.total_output_tokens += getattr(usage, "candidates_token_count", 0) or 0
        return response
