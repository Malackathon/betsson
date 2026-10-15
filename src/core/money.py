"""Money parsing, formatting, and reconciliation for Betsson Game Validation.

This module enforces strict Decimal arithmetic for all financial operations.
Floating-point numbers are strictly forbidden to prevent precision errors.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

# Currency tokens recognized during parsing
_CURRENCY_PATTERNS = [
    r"\bEUR\b",
    r"\bPEN\b",
    r"\bUSD\b",
    r"\bGBP\b",
    r"S/\.?",
    r"s/\.?",
    r"[€$£]",
]

_MARKET_CURRENCY_MAP: dict[str, str] = {
    "COM": "€",
    "PE": "S/",
}


def _normalize_market(market: str | Any) -> str:
    """Extract and normalize a market code to an uppercase string.

    Supports string values ('COM', 'PE') and enum objects with a .value attribute.

    Args:
        market: Market identifier or Enum.

    Returns:
        Normalized market string ('COM' or 'PE').

    Raises:
        TypeError: If market is not a string or enum.
        ValueError: If market is not 'COM' or 'PE'.
    """
    if hasattr(market, "value"):
        market = market.value
    if not isinstance(market, str):
        raise TypeError(f"Market must be a str or Enum, got {type(market).__name__}: {market!r}")
    m = market.strip().upper()
    if m not in _MARKET_CURRENCY_MAP:
        raise ValueError(f"Unsupported market: {market!r}. Expected 'COM' or 'PE'.")
    return m


def parse_money(raw: str, currency_hint: str | None = None) -> Decimal:
    """Parse a money string in Spanish or English format into a Decimal.

    Supports:
        - Spanish format: '1.234,56' (dot = thousands, comma = decimal)
        - English format: '1,234.56' (comma = thousands, dot = decimal)
        - Currency symbols and codes: '€', 'EUR', 'S/', 'S/.', 'PEN', '$', 'USD'
        - Whitespace and non-breaking spaces (NBSP '\\xa0', '\\u202f')
        - Edge cases: integers, no separators, negative values, accounting parenthesis

    Heuristic:
        If a comma is the LAST separator in the cleaned numeric string and
        has <= 2 digits after it, ES format is assumed (comma = decimal).
        Otherwise, EN format is assumed (dot = decimal).

    Args:
        raw: Raw money string to parse.
        currency_hint: Optional currency hint (e.g. 'EUR', 'PEN', 'COM', 'PE').

    Returns:
        Decimal representation of the parsed money amount.

    Raises:
        ValueError: If raw is empty, has invalid characters, or cannot be parsed.
        TypeError: If raw is not a string.
    """
    if raw is None:
        raise ValueError("Cannot parse money from None")
    if not isinstance(raw, str):
        raise TypeError(f"Expected str for raw money, got {type(raw).__name__}")

    # Normalize whitespace characters (NBSP, narrow NBSP, zero-width spaces)
    cleaned = (
        raw.replace("\xa0", " ")
        .replace("\u202f", " ")
        .replace("\u200b", " ")
        .strip()
    )
    if not cleaned:
        raise ValueError(f"Cannot parse money from empty string: {raw!r}")

    # Check for accounting negative format: (1,234.56)
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()

    # Build currency stripping patterns
    patterns = list(_CURRENCY_PATTERNS)
    if currency_hint:
        hint_str = currency_hint.value if hasattr(currency_hint, "value") else str(currency_hint)
        hint_clean = hint_str.strip()
        if hint_clean.upper() in ("COM", "EUR"):
            patterns.extend([r"\bCOM\b", r"\bEUR\b", r"€"])
        elif hint_clean.upper() in ("PE", "PEN"):
            patterns.extend([r"\bPE\b", r"\bPEN\b", r"S/\.?", r"s/\.?"])
        elif hint_clean:
            patterns.append(re.escape(hint_clean))

    for pat in patterns:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError(f"Cannot parse money from string without digits: {raw!r}")

    # Detect negative signs: ASCII '-', Unicode minus '−' (\u2212), en-dash '–' (\u2013)
    minus_chars = ("-", "\u2212", "\u2013")
    for m in minus_chars:
        if cleaned.startswith(m):
            is_negative = True
            cleaned = cleaned[len(m):].strip()
            break

    for m in minus_chars:
        if cleaned.endswith(m):
            is_negative = True
            cleaned = cleaned[:-len(m)].strip()
            break

    # Strip leading plus if present
    if cleaned.startswith("+"):
        cleaned = cleaned[1:].strip()

    # Remove internal spaces (e.g. thousands separators in French/ISO format '1 234,56')
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        raise ValueError(f"Cannot parse money from string without digits: {raw!r}")

    # Ensure only digits, commas, and dots remain
    if not re.fullmatch(r"[\d.,]+", cleaned):
        raise ValueError(f"Invalid characters in money string {raw!r} (cleaned: {cleaned!r})")

    # Ensure at least one digit is present
    if not any(c.isdigit() for c in cleaned):
        raise ValueError(f"No numeric digits found in money string: {raw!r}")

    # Apply separator heuristic
    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")

    if last_comma == -1 and last_dot == -1:
        # Integer value without separators
        normalized = cleaned
    elif last_comma > last_dot:
        # Comma is the LAST separator
        digits_after = cleaned[last_comma + 1:]
        if len(digits_after) <= 2:
            # ES format: comma is decimal separator, dots are thousands separators
            if cleaned.count(",") > 1:
                raise ValueError(
                    f"Multiple comma separators in ES format money string: {raw!r}"
                )
            without_dots = cleaned.replace(".", "")
            normalized = without_dots.replace(",", ".")
        else:
            # EN format: commas are thousands separators, dot is decimal (if present)
            without_commas = cleaned.replace(",", "")
            normalized = without_commas
    else:
        # Dot is the LAST separator -> EN format (dot = decimal)
        if cleaned.count(".") > 1:
            raise ValueError(
                f"Multiple decimal points in EN format money string: {raw!r}"
            )
        without_commas = cleaned.replace(",", "")
        normalized = without_commas

    try:
        val = Decimal(normalized)
    except InvalidOperation as err:
        raise ValueError(f"Cannot parse money '{raw}': invalid decimal value '{normalized}'") from err

    if is_negative:
        val = -val if val != Decimal(0) else abs(val)

    return val


def format_money(value: Decimal, market: str | Any) -> str:
    """Format a Decimal value into the appropriate market currency string.

    Format rules:
        - COM format: '€1,234.56' (EN style: dot decimal, comma thousands)
        - PE format: 'S/1.234,56' (ES style: comma decimal, dot thousands)
        - Always 2 decimal places.

    Args:
        value: Amount to format (must be Decimal, never float).
        market: Market identifier ('COM' or 'PE', case-insensitive).

    Returns:
        Formatted money string with currency symbol.

    Raises:
        TypeError: If value is not a Decimal or market is invalid type.
        ValueError: If market is not recognized.
    """
    if isinstance(value, float):
        raise TypeError(f"Money value must be Decimal, never float: {value!r}")
    if not isinstance(value, Decimal):
        raise TypeError(f"Money value must be Decimal, got {type(value).__name__}: {value!r}")

    market_norm = _normalize_market(market)

    # Quantize to exactly 2 decimal places using half-up rounding
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    is_neg = quantized < 0
    abs_val = abs(quantized)

    # Format integer part and decimal part
    parts = f"{abs_val:.2f}".split(".")
    int_num = int(parts[0])
    dec_part = parts[1]

    int_en = f"{int_num:,}"

    if market_norm == "COM":
        formatted = f"€{int_en}.{dec_part}"
    else:  # PE
        int_es = int_en.replace(",", ".")
        formatted = f"S/{int_es},{dec_part}"

    if is_neg:
        return f"-{formatted}"
    return formatted


def reconcile(
    before: Decimal,
    bet: Decimal,
    prize: Decimal,
    after: Decimal,
    tolerance: Decimal = Decimal("0.01"),
) -> tuple[bool, str]:
    """Reconcile player balance before and after a game spin.

    Implements the formula:
        expected = before - bet + prize

    Checks whether:
        abs(after - expected) <= tolerance

    Args:
        before: Balance before spin.
        bet: Amount bet on the spin.
        prize: Prize/win amount from the spin.
        after: Balance observed after spin.
        tolerance: Maximum allowed discrepancy (default 0.01).

    Returns:
        tuple[bool, str]: (passed, detail)
            passed is True if discrepancy <= tolerance, False otherwise.
            detail describes the formula, expected and observed values, and diff.

    Raises:
        TypeError: If any monetary parameter is a float or not a Decimal.
    """
    params = [
        ("before", before),
        ("bet", bet),
        ("prize", prize),
        ("after", after),
        ("tolerance", tolerance),
    ]
    for name, val in params:
        if isinstance(val, float):
            raise TypeError(f"Money value '{name}' must be Decimal, never float: {val!r}")
        if not isinstance(val, Decimal):
            raise TypeError(f"Money value '{name}' must be Decimal, got {type(val).__name__}")

    expected = before - bet + prize
    diff = abs(after - expected)
    passed = diff <= tolerance

    status_str = "PASSED" if passed else "FAILED"
    detail = (
        f"Reconciliation {status_str}: "
        f"expected = before ({before}) - bet ({bet}) + prize ({prize}) = {expected}; "
        f"observed after = {after}; diff = {diff} (tolerance = {tolerance})"
    )
    return passed, detail


def currency_for_market(market: str | Any) -> str:
    """Return the normalized currency symbol for a market.

    Args:
        market: Market identifier ('COM' or 'PE').

    Returns:
        '€' for 'COM', 'S/' for 'PE'.

    Raises:
        TypeError: If market is not a str or Enum.
        ValueError: If market is unrecognized.
    """
    market_norm = _normalize_market(market)
    return _MARKET_CURRENCY_MAP[market_norm]


def detect_currency_symbol(text: str) -> str | None:
    """Detect and return normalized currency symbol from text.

    Searches for currency indicators:
        - '€' or 'EUR' -> returns '€'
        - 'S/' or 'PEN' -> returns 'S/'

    If multiple distinct currencies appear, the one appearing first is returned.

    Args:
        text: Text to inspect.

    Returns:
        Normalized symbol ('€' or 'S/') or None if no currency symbol found.
    """
    if not text or not isinstance(text, str):
        return None

    matches: list[tuple[int, str]] = []

    # Check for EUR / €
    for m in re.finditer(r"€|\bEUR\b", text, flags=re.IGNORECASE):
        matches.append((m.start(), "€"))

    # Check for S/ / PEN / S/.
    for m in re.finditer(r"S/\.?|\bPEN\b", text, flags=re.IGNORECASE):
        matches.append((m.start(), "S/"))

    if not matches:
        return None

    matches.sort(key=lambda x: x[0])
    return matches[0][1]
