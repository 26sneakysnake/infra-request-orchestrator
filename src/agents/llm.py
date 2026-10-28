"""Anthropic client with content-addressed cassettes and a spend guard.

NETCO_LLM_MODE:
- replay (default without ANTHROPIC_API_KEY): answers come from cassettes/llm/, with no network and
  no key. A prompt that was never recorded fails with a clear message.
- record: calls the API and stores each exchange in cassettes/llm/ (`make eval-live`).
- live (default with a key): calls the API and stores nothing (workers during a demo).

A cassette is keyed by the SHA-256 of the request body, so it does not depend on call order and is
shared by the evaluation, the e2e scenario and the tests. Headers are never stored: no API key.
Every live call is checked first against a cumulative budget (out/llm-spend.json).
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import anthropic
import httpx2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CASSETTE_DIR = ROOT / "cassettes" / "llm"
SPEND_FILE = ROOT / "out" / "llm-spend.json"
MODES = ("replay", "record", "live")
DEFAULT_MODEL = "claude-sonnet-5-5"

# USD per million tokens: input, output, cache write (5 min), cache read.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}


class CassetteMiss(RuntimeError):
    """Replay mode met a prompt that was never recorded."""


class BudgetExceeded(RuntimeError):
    """A live call could push the cumulative spend over the budget."""


def cost_usd(model: str, usage: dict[str, Any]) -> float:
    price_in, price_out, price_write, price_read = PRICES[model]
    return (
        (usage.get("input_tokens") or 0) * price_in
        + (usage.get("output_tokens") or 0) * price_out
        + (usage.get("cache_creation_input_tokens") or 0) * price_write
        + (usage.get("cache_read_input_tokens") or 0) * price_read
    ) / 1_000_000


def request_key(method: str, path: str, body: bytes) -> str:
    canonical = json.dumps(
        json.loads(body), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(f"{method} {path}\n{canonical}".encode()).hexdigest()


class SpendLedger:
    """Cumulative spend of live calls, kept across runs in out/llm-spend.json."""

    def __init__(self, path: Path = SPEND_FILE, budget_usd: float | None = None) -> None:
        self.path = path
        self.budget_usd = (
            budget_usd
            if budget_usd is not None
            else float(os.environ.get("NETCO_LLM_BUDGET_USD", "3"))
        )
        self._lock = threading.Lock()

    def spent(self) -> float:
        if not self.path.exists():
            return 0.0
        return json.loads(self.path.read_text(encoding="utf-8"))["spent_usd"]

    def check(self, worst_case_usd: float) -> None:
        if self.spent() + worst_case_usd > self.budget_usd:
            raise BudgetExceeded(
                f"LLM budget reached: {self.spent():.4f} $ spent, the next call could cost up to "
                f"{worst_case_usd:.4f} $, budget {self.budget_usd:.2f} $ (NETCO_LLM_BUDGET_USD)"
            )

    def add(self, usd: float) -> None:
        with self._lock:
            data = {"spent_usd": 0.0, "calls": 0}
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
            data["spent_usd"] = round(data["spent_usd"] + usd, 6)
            data["calls"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _worst_case_usd(payload: dict[str, Any]) -> float:
    # Rough upper bound: about 4 characters per input token, and the whole max_tokens produced.
    price_in, price_out, _, _ = PRICES[payload["model"]]
    input_tokens = len(json.dumps(payload)) / 4
    return (input_tokens * price_in + payload.get("max_tokens", 0) * price_out) / 1_000_000


class CassetteTransport(httpx2.BaseTransport):
    def __init__(
        self,
        mode: str,
        directory: Path = CASSETTE_DIR,
        ledger: SpendLedger | None = None,
        inner: httpx2.BaseTransport | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"NETCO_LLM_MODE must be one of {', '.join(MODES)}, not {mode!r}")
        self.mode = mode
        self.directory = directory
        self.ledger = ledger or SpendLedger()
        self.inner = inner or httpx2.HTTPTransport()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        body = request.read()
        key = request_key(request.method, request.url.path, body)
        path = self.directory / f"{key}.json"
        # Record mode only pays for prompts it has never seen; known ones are replayed.
        if self.mode == "replay" or (self.mode == "record" and path.exists()):
            if not path.exists():
                raise CassetteMiss(
                    f"no recorded answer for this prompt ({key[:12]}): record it with "
                    "`make eval-live` or NETCO_LLM_MODE=record (needs ANTHROPIC_API_KEY)"
                )
            recorded = json.loads(path.read_text(encoding="utf-8"))
            return httpx2.Response(
                recorded["status"],
                headers={"content-type": "application/json"},
                content=json.dumps(recorded["response"]).encode(),
                request=request,
            )

        payload = json.loads(body)
        self.ledger.check(_worst_case_usd(payload))
        response = self.inner.handle_request(request)
        response.read()
        if response.status_code == 200:
            answer = response.json()
            self.ledger.add(cost_usd(payload["model"], answer.get("usage") or {}))
            if self.mode == "record":
                self.directory.mkdir(parents=True, exist_ok=True)
                recorded = {"model": payload["model"], "status": 200, "response": answer}
                text = json.dumps(recorded, indent=1, ensure_ascii=False) + "\n"
                path.write_text(text, encoding="utf-8", newline="\n")
        return response

    def close(self) -> None:
        self.inner.close()


def llm_mode() -> str:
    load_dotenv(override=False)
    mode = os.environ.get("NETCO_LLM_MODE", "").strip().lower()
    if mode:
        return mode
    return "live" if os.environ.get("ANTHROPIC_API_KEY") else "replay"


def llm_model() -> str:
    load_dotenv(override=False)
    return os.environ.get("NETCO_LLM_MODEL", DEFAULT_MODEL)


def anthropic_client(mode: str | None = None) -> anthropic.Anthropic:
    load_dotenv(override=False)  # ANTHROPIC_API_KEY and the budget may come from .env
    mode = mode or llm_mode()
    http_client = anthropic.DefaultHttpxClient(transport=CassetteTransport(mode))
    if mode == "replay":
        # The cassette answers every request: no key is needed, and none ever leaves the process.
        return anthropic.Anthropic(api_key="replay", http_client=http_client, max_retries=0)
    return anthropic.Anthropic(http_client=http_client)
