"""Unit tests for src/core/money.py.

Tests cover:
    - parse_money with ES format (1.234,56) and EN format (1,234.56)
    - Currency symbols (€, S/, S/., PEN, EUR, $, USD) and NBSP/whitespace
    - Edge cases: integers, negatives, accounting parens, empty strings, invalid inputs
    - format_money for COM (€1,234.56) and PE (S/1.234,56) markets
    - Strict prohibition of float values
    - reconcile balance verification and formula detail
    - currency_for_market mapping
    - detect_currency_symbol extraction
"""

from decimal import Decimal
import pytest

from src.core.money import (
    currency_for_market,
    detect_currency_symbol,
    format_money,
    parse_money,
    reconcile,
)


class TestParseMoney:
    """Tests for parse_money."""

    def test_parse_en_format(self) -> None:
        assert parse_money("1,234.56") == Decimal("1234.56")
        assert parse_money("1234.56") == Decimal("1234.56")
        assert parse_money("10.50") == Decimal("10.50")
        assert parse_money("0.20") == Decimal("0.20")

    def test_parse_es_format(self) -> None:
        assert parse_money("1.234,56") == Decimal("1234.56")
        assert parse_money("1234,56") == Decimal("1234.56")
        assert parse_money("10,50") == Decimal("10.50")
        assert parse_money("0,20") == Decimal("0.20")
        assert parse_money("12,5") == Decimal("12.5")

    def test_parse_integers_and_no_separators(self) -> None:
        assert parse_money("1234") == Decimal("1234")
        assert parse_money("0") == Decimal("0")
        assert parse_money("1,234") == Decimal("1234")
        assert parse_money("1,234,567") == Decimal("1234567")

    def test_parse_with_currency_symbols(self) -> None:
        assert parse_money("€ 1,234.56") == Decimal("1234.56")
        assert parse_money("1.234,56 €") == Decimal("1234.56")
        assert parse_money("EUR 1,234.56") == Decimal("1234.56")
        assert parse_money("S/ 1.234,56") == Decimal("1234.56")
        assert parse_money("S/. 1.234,56") == Decimal("1234.56")
        assert parse_money("1.234,56 PEN") == Decimal("1234.56")
        assert parse_money("$ 1,234.56") == Decimal("1234.56")
        assert parse_money("1,234.56 USD") == Decimal("1234.56")

    def test_parse_with_whitespace_and_nbsp(self) -> None:
        # Non-breaking space \xa0
        assert parse_money("1.234,56\xa0€") == Decimal("1234.56")
        assert parse_money("S/\xa01.234,56") == Decimal("1234.56")
        # Narrow NBSP \u202f
        assert parse_money("€\u202f50.00") == Decimal("50.00")
        # Extra spaces
        assert parse_money("   €   100.50   ") == Decimal("100.50")

    def test_parse_with_currency_hint(self) -> None:
        assert parse_money("1.234,56", currency_hint="EUR") == Decimal("1234.56")
        assert parse_money("1.234,56", currency_hint="COM") == Decimal("1234.56")
        assert parse_money("1.234,56", currency_hint="PE") == Decimal("1234.56")
        assert parse_money("1.234,56", currency_hint="PEN") == Decimal("1234.56")

    def test_parse_negatives(self) -> None:
        assert parse_money("-1,234.56") == Decimal("-1234.56")
        assert parse_money("-1.234,56") == Decimal("-1234.56")
        assert parse_money("-€1,234.56") == Decimal("-1234.56")
        assert parse_money("€ -1,234.56") == Decimal("-1234.56")
        assert parse_money("-S/ 50,00") == Decimal("-50.00")
        assert parse_money("S/ -50,00") == Decimal("-50.00")
        assert parse_money("(1,234.56)") == Decimal("-1234.56")
        assert parse_money("(€1.234,56)") == Decimal("-1234.56")
        # Unicode minus \u2212
        assert parse_money("\u2212 25.50") == Decimal("-25.50")

    def test_parse_zero(self) -> None:
        assert parse_money("0") == Decimal("0")
        assert parse_money("0.00") == Decimal("0.00")
        assert parse_money("0,00") == Decimal("0.00")
        assert parse_money("-0.00") == Decimal("0.00")

    def test_parse_edge_separators(self) -> None:
        assert parse_money(",50") == Decimal("0.50")
        assert parse_money(".50") == Decimal("0.50")
        assert parse_money("100,") == Decimal("100")
        assert parse_money("100.") == Decimal("100")

    def test_parse_invalid_inputs(self) -> None:
        with pytest.raises(ValueError, match="empty string"):
            parse_money("")

        with pytest.raises(ValueError, match="empty string"):
            parse_money("   ")

        with pytest.raises(ValueError, match="Cannot parse money from None"):
            parse_money(None)  # type: ignore

        with pytest.raises(TypeError, match="Expected str"):
            parse_money(1234)  # type: ignore

        with pytest.raises(ValueError, match="without digits"):
            parse_money("€")

        with pytest.raises(ValueError, match="without digits"):
            parse_money("S/")

        with pytest.raises(ValueError, match="Invalid characters"):
            parse_money("12.34 abc")

        with pytest.raises(ValueError, match="Multiple decimal points"):
            parse_money("1.2.3")

        with pytest.raises(ValueError, match="Multiple comma separators"):
            parse_money("1,2,3")


class TestFormatMoney:
    """Tests for format_money."""

    def test_format_com_market(self) -> None:
        assert format_money(Decimal("1234.56"), "COM") == "€1,234.56"
        assert format_money(Decimal("0"), "COM") == "€0.00"
        assert format_money(Decimal("1000000"), "COM") == "€1,000,000.00"
        assert format_money(Decimal("5.5"), "COM") == "€5.50"

    def test_format_pe_market(self) -> None:
        assert format_money(Decimal("1234.56"), "PE") == "S/1.234,56"
        assert format_money(Decimal("0"), "PE") == "S/0,00"
        assert format_money(Decimal("1000000"), "PE") == "S/1.000.000,00"
        assert format_money(Decimal("5.5"), "PE") == "S/5,50"

    def test_format_case_insensitive_market(self) -> None:
        assert format_money(Decimal("10.00"), "com") == "€10.00"
        assert format_money(Decimal("10.00"), "pe") == "S/10,00"

    def test_format_negative(self) -> None:
        assert format_money(Decimal("-1234.56"), "COM") == "-€1,234.56"
        assert format_money(Decimal("-1234.56"), "PE") == "-S/1.234,56"

    def test_format_rounding_half_up(self) -> None:
        assert format_money(Decimal("1.234"), "COM") == "€1.23"
        assert format_money(Decimal("1.235"), "COM") == "€1.24"

    def test_format_rejects_float(self) -> None:
        with pytest.raises(TypeError, match="must be Decimal, never float"):
            format_money(1234.56, "COM")  # type: ignore

    def test_format_invalid_market(self) -> None:
        with pytest.raises(ValueError, match="Unsupported market"):
            format_money(Decimal("10.00"), "UK")


class TestReconcile:
    """Tests for reconcile."""

    def test_reconcile_exact_pass(self) -> None:
        passed, detail = reconcile(
            before=Decimal("100.00"),
            bet=Decimal("10.00"),
            prize=Decimal("5.00"),
            after=Decimal("95.00"),
        )
        assert passed is True
        assert "expected = before (100.00) - bet (10.00) + prize (5.00) = 95.00" in detail
        assert "observed after = 95.00" in detail

    def test_reconcile_with_tolerance(self) -> None:
        passed, _ = reconcile(
            before=Decimal("100.00"),
            bet=Decimal("10.00"),
            prize=Decimal("0.00"),
            after=Decimal("89.995"),
            tolerance=Decimal("0.01"),
        )
        assert passed is True

    def test_reconcile_fail(self) -> None:
        passed, detail = reconcile(
            before=Decimal("100.00"),
            bet=Decimal("10.00"),
            prize=Decimal("0.00"),
            after=Decimal("95.00"),
        )
        assert passed is False
        assert "FAILED" in detail

    def test_reconcile_rejects_float(self) -> None:
        with pytest.raises(TypeError, match="must be Decimal, never float"):
            reconcile(
                before=100.0,  # type: ignore
                bet=Decimal("10.00"),
                prize=Decimal("0.00"),
                after=Decimal("90.00"),
            )


class TestCurrencyForMarket:
    """Tests for currency_for_market."""

    def test_currency_for_market(self) -> None:
        assert currency_for_market("COM") == "€"
        assert currency_for_market("PE") == "S/"
        assert currency_for_market("com") == "€"
        assert currency_for_market("pe") == "S/"

    def test_invalid_market(self) -> None:
        with pytest.raises(ValueError, match="Unsupported market"):
            currency_for_market("SE")


class TestDetectCurrencySymbol:
    """Tests for detect_currency_symbol."""

    def test_detect_symbols(self) -> None:
        assert detect_currency_symbol("Balance: €1,234.56") == "€"
        assert detect_currency_symbol("Balance: 1,234.56 EUR") == "€"
        assert detect_currency_symbol("Saldo: S/ 1.234,56") == "S/"
        assert detect_currency_symbol("Saldo: S/. 1.234,56") == "S/"
        assert detect_currency_symbol("Saldo: 1.234,56 PEN") == "S/"

    def test_word_boundaries(self) -> None:
        # PENNY should not trigger PEN
        assert detect_currency_symbol("A lucky PENNY") is None
        # EUROPE should not trigger EUR
        assert detect_currency_symbol("Trip to EUROPE") is None

    def test_order_precedence(self) -> None:
        assert detect_currency_symbol("€100 or S/ 200") == "€"
        assert detect_currency_symbol("S/ 200 or €100") == "S/"

    def test_none_detected(self) -> None:
        assert detect_currency_symbol("100.00") is None
        assert detect_currency_symbol("") is None
