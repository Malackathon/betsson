"""Ground Gemini with the game server's numbers so it verifies instead of inventing.

Playwright already knows the exact balance, bet and win from the network. Those
facts go into the prompt as *reference only*; the model must transcribe what the
screen shows, and the comparison is done here in code on the transcription, never
trusting a model-made "it matches" verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from src.core.money import detect_currency_symbol, parse_money

TOLERANCE = Decimal("0.01")
_CENTS = Decimal("0.01")
_COMMA_DECIMAL_MARKETS = {"pe"}


class GroundedScreenReading(BaseModel):
    """Transcription of the screen (raw text), requested in one Gemini call."""

    credit_raw: str | None = Field(default=None, description="CREDIT/BALANCE text exactly as displayed")
    bet_raw: str | None = Field(default=None, description="BET text exactly as displayed")
    win_raw: str | None = Field(default=None, description="WIN text exactly as displayed, null if none shown")
    currency_raw: str | None = Field(default=None, description="Currency symbol or code visible on screen")
    message_raw: str | None = Field(default=None, description="Full text of any dialog/error visible, else null")
    message_language: str | None = Field(default=None, description="Language of that dialog: EN or ES")
    legible: bool = Field(default=True, description="False if the numbers could not be read with confidence")


@dataclass(frozen=True)
class ScreenReference:
    """Server-side facts the screen is expected to show (None = not known)."""

    balance: Decimal | None
    bet: Decimal | None
    win: Decimal | None
    currency_symbol: str
    market: str


@dataclass(frozen=True)
class FieldComparison:
    field: str
    expected: str
    observed_raw: str | None
    matches: bool | None  # True / False, or None when the screen did not show a readable value
    detail: str
    observed: Decimal | None = None  # parsed on-screen amount (amount fields only)


def _format(value: Decimal, market: str) -> str:
    text = f"{value.quantize(_CENTS, rounding=ROUND_HALF_UP):f}"
    return text.replace(".", ",") if market.lower() in _COMMA_DECIMAL_MARKETS else text


def build_reference_block(ref: ScreenReference, include_values: bool = True) -> str:
    """Prompt section with the reference facts.

    ``include_values=False`` keeps only format hints (currency, separator) for a fully
    blind read when confirmation bias is a concern.
    """
    separator = "," if ref.market.lower() in _COMMA_DECIMAL_MARKETS else "."
    lines = [
        "REFERENCE FACTS from the game server (collected by the test harness, NOT from this image).",
        "Use them only to know the expected currency and number format. The screen may legitimately",
        "differ (animation unfinished, rendering bug). NEVER copy a reference value into your answer:",
        "transcribe only text you can literally read on the screen, and use null for anything not visible.",
        f"- Expected currency symbol: {ref.currency_symbol}",
        f"- Decimal separator used by this market: '{separator}'",
    ]
    if include_values:
        for label, value in (("balance", ref.balance), ("bet", ref.bet), ("win", ref.win)):
            if value is not None:
                lines.append(f"- Server {label}: {_format(value, ref.market)}")
    return "\n".join(lines)


def compare_reading(
    reading: GroundedScreenReading,
    ref: ScreenReference,
    tolerance: Decimal = TOLERANCE,
) -> tuple[FieldComparison, ...]:
    """Compare the transcription with the reference, field by field, in code."""
    results: list[FieldComparison] = []
    for name, raw, expected in (
        ("balance", reading.credit_raw, ref.balance),
        ("bet", reading.bet_raw, ref.bet),
        ("win", reading.win_raw, ref.win),
    ):
        if expected is not None:
            results.append(_compare_amount(name, raw, expected, tolerance))
    results.append(_compare_currency(reading, ref))
    return tuple(results)


def _compare_amount(name: str, raw: str | None, expected: Decimal, tolerance: Decimal) -> FieldComparison:
    observed = _try_parse(raw)
    if observed is None:
        if name == "win" and expected == 0:
            return FieldComparison(name, str(expected), raw, True, "no win displayed and server win is 0")
        return FieldComparison(name, str(expected), raw, None, f"{name} not readable on screen (raw={raw!r})")
    if abs(observed - expected) <= tolerance:
        return FieldComparison(name, str(expected), raw, True, f"screen {observed} == server {expected}", observed)
    return FieldComparison(name, str(expected), raw, False, f"screen shows {observed}, server says {expected}", observed)


def _compare_currency(reading: GroundedScreenReading, ref: ScreenReference) -> FieldComparison:
    blob = " ".join(filter(None, (reading.currency_raw, reading.credit_raw, reading.bet_raw)))
    seen = detect_currency_symbol(blob)
    if seen is None:
        return FieldComparison("currency", ref.currency_symbol, blob or None, None, "no currency visible on screen")
    ok = seen == ref.currency_symbol
    return FieldComparison("currency", ref.currency_symbol, blob, ok, f"screen currency {seen!r}, expected {ref.currency_symbol!r}")


def _try_parse(raw: str | None) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    try:
        return parse_money(raw)
    except (ValueError, TypeError, ArithmeticError):
        return None
