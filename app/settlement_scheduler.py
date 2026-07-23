"""后台结算调度器：每分钟扫描是否有应结算周期"""

import asyncio
import logging
from datetime import date

from app.bitable_client import bitable_client
from app.settlement_period import compute_completed_periods
from app.settlement_service import execute_settlement
from app.config import settings

logger = logging.getLogger(__name__)

_SCAN_INTERVAL_SECONDS = 60
_MAX_RETRIES = 5


async def check_and_execute_settlements() -> None:
    if not settings.settlement_enabled:
        return
    if not bitable_client.is_configured:
        return

    anchor = settings.settlement_anchor_date
    if not anchor:
        logger.warning("SETTLEMENT_ANCHOR_DATE not configured, skipping settlement check")
        return

    interval = settings.settlement_interval_days
    today = date.today()

    completed = compute_completed_periods(anchor, interval, today)
    if not completed:
        return

    existing = await bitable_client.find_settled_period_ids()

    for period in completed:
        period_id = period["period_id"]
        if period_id in existing:
            continue

        retry_record = existing.get(period_id)
        if retry_record and isinstance(retry_record, dict):
            retry_count = retry_record.get("retry_count", 0)
            status = retry_record.get("status", "")
            if status == "failed" and retry_count >= _MAX_RETRIES:
                logger.warning("settlement %s exceeded max retries (%d), skipping", period_id, _MAX_RETRIES)
                continue

        logger.info("found unsent settlement: period_id=%s", period_id)
        await execute_settlement(period)


async def start_settlement_scheduler() -> None:
    logger.info("settlement scheduler started (interval=%ds)", _SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await check_and_execute_settlements()
        except asyncio.CancelledError:
            logger.info("settlement scheduler cancelled")
            break
        except Exception:
            logger.exception("settlement scheduler error")
        await asyncio.sleep(_SCAN_INTERVAL_SECONDS)
