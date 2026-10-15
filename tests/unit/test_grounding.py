from decimal import Decimal

from src.vision.grounding import (
    GroundedScreenReading,
    ScreenReference,
    build_reference_block,
    compare_reading,
)


def _ref(**overrides) -> ScreenReference:
    base = dict(
        balance=Decimal("99.80"),
        bet=Decimal("0.20"),
        win=Decimal("0.00"),
        currency_symbol="€",
        market="com",
    )
    base.update(overrides)
    return ScreenReference(**base)


def _reading(**overrides) -> GroundedScreenReading:
    base = dict(credit_raw="€99.80", bet_raw="€0.20", win_raw="0.00", currency_raw="€", legible=True)
    base.update(overrides)
    return GroundedScreenReading(**base)


def test_reference_block_contains_facts_and_anti_copy_rule():
    block = build_reference_block(_ref())
    assert "99.80" in block
    assert "0.20" in block
    assert "€" in block
    assert "NEVER copy" in block


def test_reference_block_uses_market_decimal_separator():
    block = build_reference_block(_ref(market="pe", currency_symbol="S/", balance=Decimal("1234.50")))
    assert "1234,50" in block


def test_reference_block_can_withhold_values_for_blind_reads():
    block = build_reference_block(_ref(), include_values=False)
    assert "99.80" not in block
    assert "€" in block  # the expected currency is still a format hint


def test_matching_screen_matches_every_field():
    result = {c.field: c for c in compare_reading(_reading(), _ref())}
    assert result["balance"].matches is True
    assert result["bet"].matches is True
    assert result["win"].matches is True
    assert result["currency"].matches is True


def test_wrong_balance_on_screen_is_a_mismatch_not_a_pass():
    result = {c.field: c for c in compare_reading(_reading(credit_raw="€100.00"), _ref())}
    assert result["balance"].matches is False
    assert "100.00" in result["balance"].detail


def test_unreadable_field_is_unknown_not_matching():
    result = {c.field: c for c in compare_reading(_reading(credit_raw=None), _ref())}
    assert result["balance"].matches is None


def test_missing_win_text_matches_when_server_win_is_zero():
    result = {c.field: c for c in compare_reading(_reading(win_raw=None), _ref())}
    assert result["win"].matches is True


def test_missing_win_text_is_unknown_when_server_paid_something():
    ref = _ref(win=Decimal("1.50"), balance=Decimal("101.30"))
    result = {c.field: c for c in compare_reading(_reading(win_raw=None), ref)}
    assert result["win"].matches is None


def test_wrong_currency_on_screen_is_a_mismatch():
    reading = _reading(credit_raw="S/99.80", bet_raw="S/0.20", currency_raw="S/")
    result = {c.field: c for c in compare_reading(reading, _ref())}
    assert result["currency"].matches is False


def test_pe_locale_amounts_are_parsed_with_comma_decimals():
    ref = _ref(market="pe", currency_symbol="S/", balance=Decimal("1234.50"), bet=Decimal("0.20"))
    reading = _reading(credit_raw="S/ 1.234,50", bet_raw="S/ 0,20", currency_raw="S/")
    result = {c.field: c for c in compare_reading(reading, ref)}
    assert result["balance"].matches is True
    assert result["bet"].matches is True


def test_fields_without_reference_are_skipped():
    comparisons = compare_reading(_reading(), _ref(balance=None, bet=None, win=None))
    assert {c.field for c in comparisons} == {"currency"}
