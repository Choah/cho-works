from datetime import date

from cho_works.periods import period_range


def test_period_range_returns_quarter_bounds():
    assert period_range("quarter", date(2026, 5, 8)) == (
        date(2026, 4, 1),
        date(2026, 6, 30),
    )


def test_period_range_returns_iso_week_bounds():
    assert period_range("week", date(2026, 5, 8)) == (
        date(2026, 5, 4),
        date(2026, 5, 10),
    )

