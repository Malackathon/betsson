"""Playwright network listener that turns game-server traffic into ground truth.

The game DOM is off limits, but its XHR/fetch/WebSocket traffic is visible to the
browser. ``NetworkMonitor`` records the transactional exchanges (init, spin,
collect), keeps the last known balance, and decides when a spin round is settled,
so the flow can take its final screenshot at the exact right moment.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.core.money import reconcile
from src.network.models import (
    GameTransaction,
    RoundResult,
    SpinAttempt,
    SpinAttemptStatus,
    TxKind,
)
from src.network.parser import DEFAULT_FIELDS, FieldMap, build_transaction, parse_payload

logger = logging.getLogger(__name__)

URL_KEYWORDS: tuple[str, ...] = ("gameservice", "/spin", "/balance", "/result", "/gs2c/")
ACTION_BODY_MARKER = "action=do"
LISTENED_RESOURCE_TYPES = frozenset({"xhr", "fetch"})
SETTLED_ACTIONS = frozenset({"s"})
ROUND_KINDS = frozenset({TxKind.SPIN, TxKind.COLLECT, TxKind.BONUS})
BALANCE_KINDS = frozenset({TxKind.INIT, TxKind.SPIN, TxKind.COLLECT, TxKind.BONUS, TxKind.BALANCE})
POLL_INTERVAL_MS = 100
DEFAULT_ROUND_TIMEOUT_S = 25.0
WS_METHOD = "WS"


class NetworkMonitor:
    """Thread-safe recorder of the game's transactional network traffic."""

    def __init__(
        self,
        fields: FieldMap = DEFAULT_FIELDS,
        url_keywords: tuple[str, ...] = URL_KEYWORDS,
    ) -> None:
        self._fields = fields
        self._keywords = tuple(k.lower() for k in url_keywords)
        self._txs: list[GameTransaction] = []
        self._pending: list[tuple[Any, str, str, int | None, str | None]] = []
        self._lock = threading.Lock()
        self._page: Any = None

    # ------------------------------------------------------------------ attach

    def attach(self, page: Any) -> None:
        """Start listening. Call BEFORE the game loads so the init balance is captured."""
        self._page = page
        page.on("response", self._on_response)
        page.on("websocket", self._on_websocket)
        logger.info("NetworkMonitor attached")

    def detach(self) -> None:
        if self._page is None:
            return
        for event, handler in (("response", self._on_response), ("websocket", self._on_websocket)):
            try:
                self._page.remove_listener(event, handler)
            except Exception:  # page/context may already be closed
                logger.debug("Could not remove %s listener", event)
        self._page = None

    def _on_response(self, response: Any) -> None:
        """Cheap synchronous filter; the body is fetched lazily in ``_drain``."""
        try:
            request = response.request
            if request.resource_type not in LISTENED_RESOURCE_TYPES:
                return
            post_data = _safe_post_data(request)
            if not self._is_relevant(response.url, post_data):
                return
            with self._lock:
                self._pending.append((response, request.method, response.url, response.status, post_data))
        except Exception:
            logger.debug("Ignoring response that could not be inspected", exc_info=True)

    def _on_websocket(self, websocket: Any) -> None:
        url = websocket.url
        websocket.on("framereceived", lambda payload: self._on_ws_frame(url, payload))

    def _on_ws_frame(self, url: str, payload: str | bytes) -> None:
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                return
        self.ingest(url=url, method=WS_METHOD, http_status=None, request_body=None, response_body=payload)

    def _drain(self) -> None:
        """Read the bodies of filtered responses (runs on the caller's thread)."""
        with self._lock:
            batch, self._pending = self._pending, []
        for response, method, url, status, post_data in batch:
            try:
                body: str | None = response.text()
            except Exception:  # redirects, aborted or already-disposed responses
                body = None
            self.ingest(url=url, method=method, http_status=status, request_body=post_data, response_body=body)

    # ------------------------------------------------------------------ ingest

    def _is_relevant(self, url: str, request_body: str | None) -> bool:
        lowered = url.lower()
        if any(keyword in lowered for keyword in self._keywords):
            return True
        return bool(request_body) and ACTION_BODY_MARKER in request_body.lower()

    def ingest(
        self,
        url: str,
        method: str,
        http_status: int | None,
        request_body: str | None,
        response_body: str | None,
    ) -> GameTransaction | None:
        """Record one exchange if it is game-transactional; returns the transaction or None."""
        is_ws = method == WS_METHOD
        if not is_ws and not self._is_relevant(url, request_body):
            return None
        with self._lock:
            tx = build_transaction(
                seq=len(self._txs),
                url=url,
                http_status=http_status,
                request_body=request_body,
                response_body=response_body,
                fields=self._fields,
            )
            if tx.kind is TxKind.OTHER and tx.balance is None and tx.error is None:
                return None
            if is_ws and tx.balance is None and tx.next_action is None:
                return None
            self._txs.append(tx)
        return tx

    # ------------------------------------------------------------------- state

    @property
    def transactions(self) -> tuple[GameTransaction, ...]:
        with self._lock:
            return tuple(self._txs)

    @property
    def transaction_count(self) -> int:
        with self._lock:
            return len(self._txs)

    @property
    def last_balance(self) -> Decimal | None:
        return self._balance_at(self.transaction_count)

    @property
    def last_bet(self) -> Decimal | None:
        """Most recent bet the server reported (coin x lines), e.g. the default bet at init."""
        with self._lock:
            txs = tuple(self._txs)
        return next((tx.bet for tx in reversed(txs) if tx.bet is not None), None)

    def mark(self) -> int:
        """Bookmark the current position; pass it to ``evaluate_round`` after the click."""
        self._drain()
        return self.transaction_count

    def _balance_at(self, index: int) -> Decimal | None:
        with self._lock:
            earlier = self._txs[:index]
        for tx in reversed(earlier):
            if tx.kind in BALANCE_KINDS and tx.balance is not None:
                return tx.balance
        return None

    # --------------------------------------------------------------- evaluation

    def evaluate_round(self, since: int) -> SpinAttempt:
        """Judge the spin that started after bookmark ``since`` with what has arrived so far."""
        with self._lock:
            after = self._txs[since:]
        spin_txs = [t for t in after if t.kind in ROUND_KINDS]
        if not any(t.kind is TxKind.SPIN for t in spin_txs):
            return SpinAttempt(SpinAttemptStatus.NO_TRAFFIC, detail="no spin request reached the server")
        errored = next((t for t in spin_txs if t.error), None)
        if errored is not None:
            return SpinAttempt(SpinAttemptStatus.REJECTED, error=errored.error, detail=f"tx#{errored.seq}")
        last = spin_txs[-1]
        if (last.next_action or "").lower() not in SETTLED_ACTIONS:
            return SpinAttempt(
                SpinAttemptStatus.PENDING,
                detail=f"waiting for settlement (na={last.next_action!r}, tx#{last.seq})",
            )
        return SpinAttempt(SpinAttemptStatus.SETTLED, round=self._build_round(since, spin_txs))

    def _build_round(self, since: int, spin_txs: list[GameTransaction]) -> RoundResult:
        first_spin = next(t for t in spin_txs if t.kind is TxKind.SPIN)
        wins = [t.total_win for t in spin_txs if t.total_win is not None]
        before = self._balance_at(since)
        after = spin_txs[-1].balance
        bet = first_spin.bet
        total_win = max(wins) if wins else None
        reconciles = None
        if None not in (before, after, bet, total_win):
            reconciles, _ = reconcile(before, bet, total_win, after)
        return RoundResult(
            balance_before=before,
            balance_after=after,
            bet=bet,
            total_win=total_win,
            bonus_triggered=any(t.bonus for t in spin_txs),
            server_reconciles=reconciles,
            transactions=tuple(spin_txs),
        )

    def wait_for_round(self, since: int, timeout_s: float = DEFAULT_ROUND_TIMEOUT_S) -> SpinAttempt:
        """Poll (pumping Playwright events) until the round settles, is rejected, or times out."""
        deadline = time.monotonic() + timeout_s
        while True:
            self._drain()
            attempt = self.evaluate_round(since)
            if attempt.status in (SpinAttemptStatus.SETTLED, SpinAttemptStatus.REJECTED):
                return attempt
            if time.monotonic() >= deadline:
                return attempt
            self._pump(POLL_INTERVAL_MS)

    def _pump(self, ms: int) -> None:
        if self._page is not None:
            self._page.wait_for_timeout(ms)
        else:
            time.sleep(ms / 1000)

    # ---------------------------------------------------------------- evidence

    def save_evidence(self, path: Path | str) -> Path:
        """Write the sanitized transaction log (no headers, cookies or tokens)."""
        self._drain()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "seq": tx.seq,
                "kind": tx.kind.value,
                "url": tx.url,
                "http_status": tx.http_status,
                "request": dict(tx.request),
                "response": dict(tx.response),
                "error": tx.error,
                "bonus": tx.bonus,
            }
            for tx in self.transactions
        ]
        target.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        return target


def _safe_post_data(request: Any) -> str | None:
    try:
        return request.post_data
    except Exception:  # binary bodies raise on decode
        return None


__all__ = ["NetworkMonitor", "parse_payload"]
