from __future__ import annotations

import calendar
from datetime import date, timedelta


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def period_range(period_type: str, anchor: str | date) -> tuple[date, date]:
    day = parse_date(anchor)
    if period_type == "day":
        return day, day
    if period_type == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period_type == "month":
        last = calendar.monthrange(day.year, day.month)[1]
        return date(day.year, day.month, 1), date(day.year, day.month, last)
    if period_type == "quarter":
        start_month = ((day.month - 1) // 3) * 3 + 1
        end_month = start_month + 2
        last = calendar.monthrange(day.year, end_month)[1]
        return date(day.year, start_month, 1), date(day.year, end_month, last)
    if period_type == "year":
        return date(day.year, 1, 1), date(day.year, 12, 31)
    raise ValueError(f"unsupported period type: {period_type}")


def period_key(period_type: str, anchor: str | date) -> str:
    day = parse_date(anchor)
    if period_type == "day":
        return day.isoformat()
    if period_type == "week":
        iso_year, iso_week, _ = day.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if period_type == "month":
        return f"{day.year}-{day.month:02d}"
    if period_type == "quarter":
        quarter = ((day.month - 1) // 3) + 1
        return f"{day.year}-Q{quarter}"
    if period_type == "year":
        return str(day.year)
    raise ValueError(f"unsupported period type: {period_type}")

