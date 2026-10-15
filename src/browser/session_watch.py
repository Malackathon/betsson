"""Record what happens around the moment the session is lost (privacy-safe, paths only).

Logs main-frame navigations, popups and failed HTTP responses as ``host/path`` (never query
strings, headers, cookies or bodies), plus explicit checkpoints saying whether the page still
looks logged in. ``summary()`` is attached to errors so a lost session can be explained.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

MAX_EVENTS = 60
ERROR_STATUS = 400


def _safe(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


class SessionWatch:
    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._events: deque[str] = deque(maxlen=max_events)
        self._page: Any = None

    def attach(self, page: Any) -> None:
        self._page = page
        page.on("framenavigated", self._on_navigated)
        page.on("response", self._on_response)
        page.on("popup", self._on_popup)

    def detach(self) -> None:
        if self._page is None:
            return
        for event, handler in (
            ("framenavigated", self._on_navigated),
            ("response", self._on_response),
            ("popup", self._on_popup),
        ):
            try:
                self._page.remove_listener(event, handler)
            except Exception:
                logger.debug("Could not remove %s listener", event)
        self._page = None

    def checkpoint(self, label: str, logged_out: bool) -> None:
        state = "SESSION LOST (login button visible)" if logged_out else "logged in"
        self._add(f"CHECKPOINT {label}: {state}")
        (logger.warning if logged_out else logger.info)("Session checkpoint '%s': %s", label, state)

    def summary(self) -> str:
        return "Recent events (oldest first):\n" + "\n".join(self._events) if self._events else "No events recorded"

    def _add(self, line: str) -> None:
        self._events.append(line)

    def _on_navigated(self, frame: Any) -> None:
        if self._page is not None and frame is not self._page.main_frame:
            return
        self._add(f"NAVIGATED {_safe(frame.url)}")

    def _on_response(self, response: Any) -> None:
        if response.status >= ERROR_STATUS:
            self._add(f"{response.request.method} {response.status} {_safe(response.url)}")

    def _on_popup(self, popup: Any) -> None:
        self._add(f"POPUP {_safe(popup.url)}")
