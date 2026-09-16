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
        record = existing.get(period_id)

        retry_count = 0
        existing_record_id = ""
        if isinstance(record, dict):
            status = record.get("status", "")
            if status in ("sent", "processing"):
                continue
            retry_count = record.get("retry_count", 0)
            if status == "failed":
                if retry_count >= _MAX_RETRIES:
                    logger.warning(
                        "settlement %s exceeded max retries (%d), skipping",
                        period_id,
                        _MAX_RETRIES,
                    )
                    continue
                existing_record_id = record.get("record_id", "")

        logger.info(
            "found unsent settlement: period_id=%s status=%s retry_count=%d",
            period_id,
            record.get("status", "") if isinstance(record, dict) else "new",
            retry_count,
        )
        try:
            await execute_settlement(
                period,
                existing_record_id=existing_record_id,
                retry_count=retry_count,
            )
        except Exception:
            logger.exception("settlement execution failed: period_id=%s", period_id)


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
