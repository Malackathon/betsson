"""Live execution of one scenario: real browser, network monitor, grounded Gemini read.

Gemini budget per scenario: one call to locate the Spin button (cached per market) and one
grounded read of the screenshot taken when the server settled the round.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from config.settings import get_settings
from src.agents.networked_scenarios import ScenarioContext, evaluate_scenario_1, evaluate_scenario_2
from src.browser.game_canvas import RelativeCoords
from src.browser.selectors import get_market_selectors
from src.core.checks import CheckRunner
from src.flows.game_flow import GameFlow
from src.vision.gemini_inspector import GeminiInspector

logger = logging.getLogger(__name__)

MIN_SPIN_CONFIDENCE = 0.5


def build_spin_provider(
    inspector: GeminiInspector, market: str, *, use_cache: bool = True
) -> Callable[[Path], RelativeCoords]:
    """Gemini finds the Spin button; a low-confidence answer makes GameFlow use its fallback.

    ``use_cache=False`` always asks again: after a click that did nothing, the cached position
    (found on an intro screen) is the thing that must not be trusted.
    """

    def provider(screenshot: Path) -> RelativeCoords:
        location = inspector.locate_spin_button(screenshot, market=market if use_cache else "")
        if not location.legible or location.confidence < MIN_SPIN_CONFIDENCE:
            raise ValueError(f"Spin button not located with confidence (confidence={location.confidence})")
        return RelativeCoords(x=location.x_pct, y=location.y_pct)

    return provider


def run_live_scenario(
    *,
    agent_id: str,
    market: str,
    scenario: int,
    username: str,
    password: str,
    artifacts_dir: Path,
    runner: CheckRunner,
    inspector: GeminiInspector | None = None,
) -> None:
    """Run the scenario against the real site and record every check in ``runner``."""
    from playwright.sync_api import sync_playwright  # imported lazily: unit tests never need a browser

    settings = get_settings()
    mkt = get_market_selectors(market)
    inspector = inspector or GeminiInspector(api_key=settings.gemini_api_key or None)
    ctx = ScenarioContext(
        market=market,
        currency_symbol=mkt.currency_symbol,
        insufficient_keywords=list(mkt.keywords_insufficient),
        inspector=inspector,
        # GROUNDING_INCLUDE_VALUES=false withholds the server numbers from the prompt (blind read).
        include_reference_values=os.getenv("GROUNDING_INCLUDE_VALUES", "true").lower() != "false",
    )
    provider = build_spin_provider(inspector, market)

    with sync_playwright() as playwright:
        with GameFlow(
            playwright,
            market=market,
            agent_id=agent_id,
            username=username,
            password=password,
            artifacts_dir=artifacts_dir,
            headless=settings.headless,
        ) as flow:
            flow.prepare()
            if scenario == 1:
                evaluate_scenario_1(runner, flow.execute_scenario_1(provider, build_spin_provider(inspector, market, use_cache=False)), ctx)
            else:
                evaluate_scenario_2(runner, flow.execute_scenario_2(provider), ctx)
