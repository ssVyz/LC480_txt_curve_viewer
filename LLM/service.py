"""Gemini API service — manages client, chat session, and token tracking."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

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
- When checking whether wells are empty (loaded) or populated (filled), examine raw signal levels and \
first derivatives. Empty wells typically have lower or near-zero fluorescence that stays flat \
across cycles (very low max first derivative). Consider that sometimes individual channels could have been measured, but the assay actually does not include a dye for that channel. It may be necessary to identify first which channels have signals.
- Prefer the default baseline settings (start_cycle=3, end_cycle=8, ct_threshold=1.5, \
call_threshold=1.5) unless a change is obviously needed or the user explicitly requests it.
- Colors are hex strings: '#FF0000' red, '#00AA00' green, '#0000FF' blue, etc.
- Always confirm what actions you have taken.
"""


def _dbg(msg: str):
    """Print a debug message to stderr (survives crashes better than stdout)."""
    print(f"[LLM-DEBUG] {msg}", file=sys.stderr, flush=True)


class TokenLimitReached(Exception):
    pass


@dataclass
class FunctionCallInfo:
    name: str
    args: dict


@dataclass
class ParsedResponse:
    """Thread-safe, plain-Python representation of a Gemini response."""
    text_parts: list[str] = field(default_factory=list)
    function_calls: list[FunctionCallInfo] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class GeminiService:
    """Wraps a Gemini chat session with token accounting."""

    def __init__(self, api_key: str, token_limit: int):
        _dbg("GeminiService.__init__: creating client")
        self._client = genai.Client(api_key=api_key)
        _dbg("GeminiService.__init__: client created, creating chat")
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
        _dbg("GeminiService.__init__: chat session created OK")

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def token_limit(self) -> int:
        return self._token_limit

    def send_message(self, message) -> ParsedResponse:
        """Send a message and return a ParsedResponse with plain Python data.

        Raises TokenLimitReached if the cumulative token budget is exhausted.
        """
        if self.total_tokens >= self._token_limit:
            raise TokenLimitReached(
                f"Token limit reached ({self.total_tokens:,} / {self._token_limit:,}). "
                "Close and reopen the console to start a new session."
            )

        msg_type = type(message).__name__
        if isinstance(message, str):
            _dbg(f"send_message: sending text ({len(message)} chars)")
        elif isinstance(message, list):
            _dbg(f"send_message: sending list of {len(message)} parts")
        else:
            _dbg(f"send_message: sending {msg_type}")

        _dbg("send_message: calling chat.send_message ...")
        response = self._chat.send_message(message)
        _dbg("send_message: response received from API")

        # Extract token usage
        parsed = ParsedResponse()
        _dbg("send_message: extracting usage_metadata")
        usage = getattr(response, "usage_metadata", None)
        if usage:
            parsed.input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            parsed.output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            self.total_input_tokens += parsed.input_tokens
            self.total_output_tokens += parsed.output_tokens
            _dbg(f"send_message: tokens this call: in={parsed.input_tokens} out={parsed.output_tokens}")
        else:
            _dbg("send_message: no usage_metadata on response")

        # Extract parts into plain Python objects before returning
        _dbg("send_message: extracting response parts")
        if response.candidates:
            n_parts = len(response.candidates[0].content.parts)
            _dbg(f"send_message: {n_parts} part(s) in response")
            for i, part in enumerate(response.candidates[0].content.parts):
                _dbg(f"send_message: part[{i}] type fields: "
                     f"function_call={part.function_call is not None}, "
                     f"text={bool(getattr(part, 'text', None))}")
                if part.function_call:
                    fc_name = part.function_call.name
                    fc_args_raw = part.function_call.args
                    _dbg(f"send_message: part[{i}] is function_call: {fc_name}, "
                         f"args type={type(fc_args_raw).__name__}")
                    args = dict(fc_args_raw) if fc_args_raw else {}
                    _dbg(f"send_message: part[{i}] args converted to dict OK: {list(args.keys())}")
                    parsed.function_calls.append(
                        FunctionCallInfo(name=fc_name, args=args)
                    )
                elif hasattr(part, "text") and part.text:
                    _dbg(f"send_message: part[{i}] is text ({len(part.text)} chars)")
                    parsed.text_parts.append(part.text)
                else:
                    _dbg(f"send_message: part[{i}] is neither function_call nor text")
        else:
            _dbg("send_message: no candidates in response")

        _dbg(f"send_message: parsed OK — "
             f"{len(parsed.text_parts)} text, {len(parsed.function_calls)} func_calls")
        return parsed

    def send_function_results(self, results: list[tuple[str, dict]]) -> ParsedResponse:
        """Send function results back to the model.

        *results* is a list of (function_name, result_dict) tuples.
        """
        _dbg(f"send_function_results: building {len(results)} Part(s)")
        response_parts = []
        for i, (name, data) in enumerate(results):
            _dbg(f"send_function_results: [{i}] name={name}, "
                 f"data keys={list(data.keys()) if isinstance(data, dict) else '?'}")
            part = types.Part.from_function_response(name=name, response=data)
            _dbg(f"send_function_results: [{i}] Part created OK")
            response_parts.append(part)
        _dbg("send_function_results: all Parts built, calling send_message")
        return self.send_message(response_parts)
