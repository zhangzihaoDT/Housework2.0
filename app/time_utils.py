"""统一时间工具模块"""

import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TZ = None


def _load_timezone() -> str:
    tz_name = os.environ.get("TIMEZONE", "").strip()
    if tz_name:
        return tz_name
    return ""


def now_local() -> datetime:
    tz_name = _load_timezone()
    if tz_name:
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(tz_name)
            return datetime.now(tz)
        except Exception as e:
            logger.warning("failed to load timezone %s: %s, fallback to UTC+8", tz_name, e)
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def to_datetime(value) -> datetime:
    if value is None:
        return now_local()
    if isinstance(value, datetime):
        return value.astimezone(timezone(timedelta(hours=8)))
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone(timedelta(hours=8)))
        if value > 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone(timedelta(hours=8)))
        logger.warning("timestamp too small: %s, returning now_local()", value)
        return now_local()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone(timedelta(hours=8)))
            except ValueError:
                continue
        logger.warning("unrecognized datetime string: %s, returning now_local()", value)
        return now_local()
    logger.warning("unexpected type %s, returning now_local()", type(value).__name__)
    return now_local()


def to_feishu_timestamp_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def get_date_fields(value=None) -> dict:
    dt = to_datetime(value)
    date_str = dt.strftime("%Y-%m-%d")
    iso_year, iso_week, _ = dt.isocalendar()
    week_str = f"{iso_year}-W{iso_week:02d}"
    month_str = dt.strftime("%Y-%m")
    return {
        "date": date_str,
        "week": week_str,
        "month": month_str,
        "datetime_ms": to_feishu_timestamp_ms(dt),
    }
