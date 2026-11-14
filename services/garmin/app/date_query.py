"""Validation shared by the MCP query and private collector service."""

from datetime import date


SPORTS = ("running", "cycling", "swimming", "multisport", "all")


def validate_range(start_date: str, end_date: str | None, sport: str = "all") -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date or start_date)
    except (TypeError, ValueError):
        raise ValueError("Dates must use YYYY-MM-DD") from None
    if start.isoformat() != start_date or (end_date is not None and end.isoformat() != end_date):
        raise ValueError("Dates must use YYYY-MM-DD")
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    if (end - start).days >= 31:
        raise ValueError("Date range must be at most 31 days, including both endpoints")
    if sport not in SPORTS:
        raise ValueError("Unsupported sport")
    return start, end
