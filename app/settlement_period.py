"""双周周期计算 — 基于固定锚点计算当前/上一周期及结算时间"""

import logging
from datetime import timedelta, date

logger = logging.getLogger(__name__)


def _period_id_from_dates(period_start: date, period_end_exclusive: date) -> str:
    last_date = period_end_exclusive - timedelta(days=1)
    return f"{period_start.strftime('%Y%m%d')}_{last_date.strftime('%Y%m%d')}"


def compute_period_id(anchor_date: date, interval_days: int, point: date | None = None) -> str:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    periods_since_anchor = days_since_anchor // interval_days
    period_start = anchor_date + timedelta(days=periods_since_anchor * interval_days)
    period_end = period_start + timedelta(days=interval_days)
    return _period_id_from_dates(period_start, period_end)


def compute_period_start_end(anchor_date: date, interval_days: int, point: date | None = None) -> tuple[str, str, str]:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    periods_since_anchor = days_since_anchor // interval_days
    period_start = anchor_date + timedelta(days=periods_since_anchor * interval_days)
    period_end = period_start + timedelta(days=interval_days)
    period_id = _period_id_from_dates(period_start, period_end)
    return period_id, period_start.isoformat(), period_end.isoformat()


def compute_current_period(anchor_date: date, interval_days: int, point: date | None = None) -> dict:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    periods_since_anchor = days_since_anchor // interval_days
    period_start = anchor_date + timedelta(days=periods_since_anchor * interval_days)
    period_end = period_start + timedelta(days=interval_days)
    return {
        "period_id": _period_id_from_dates(period_start, period_end),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


def compute_completed_periods(anchor_date: date, interval_days: int, point: date | None = None) -> list[dict]:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    if days_since_anchor < 0:
        return []
    max_periods = days_since_anchor // interval_days
    results = []
    for p in range(max_periods):
        ps = anchor_date + timedelta(days=p * interval_days)
        pe = ps + timedelta(days=interval_days)
        if pe <= today:
            results.append({
                "period_id": _period_id_from_dates(ps, pe),
                "period_start": ps.isoformat(),
                "period_end": pe.isoformat(),
            })
    return results


def compute_last_completed_period(anchor_date: date, interval_days: int, point: date | None = None) -> dict | None:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    if days_since_anchor < interval_days:
        return None
    latest = (days_since_anchor // interval_days) - 1
    if latest < 0:
        return None
    ps = anchor_date + timedelta(days=latest * interval_days)
    pe = ps + timedelta(days=interval_days)
    return {
        "period_id": _period_id_from_dates(ps, pe),
        "period_start": ps.isoformat(),
        "period_end": pe.isoformat(),
    }


def compute_next_settlement_time(anchor_date: date, interval_days: int, settlement_time_str: str, point: date | None = None) -> str | None:
    today = point or date.today()
    days_since_anchor = (today - anchor_date).days
    periods_since_anchor = days_since_anchor // interval_days
    next_period_end = anchor_date + timedelta(days=(periods_since_anchor + 1) * interval_days)
    return f"{next_period_end.isoformat()}T{settlement_time_str}:00+08:00"
