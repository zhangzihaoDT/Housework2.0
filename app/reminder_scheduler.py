"""后台提醒调度器：定时扫描待发送提醒并推送"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.bitable_client import bitable_client
from app.feishu_client import feishu_client

logger = logging.getLogger(__name__)

_SCAN_INTERVAL_SECONDS = 60


def _now_ts_ms() -> int:
    return int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)


def _now_ts() -> int:
    return int(datetime.now(timezone(timedelta(hours=8))).timestamp())


async def check_and_send_reminders() -> None:
    if not bitable_client.is_configured:
        return

    reminders = await bitable_client.find_pending_reminders(_now_ts_ms())
    if not reminders:
        return

    for item in reminders:
        record_id = item.get("record_id", "")
        fields = item.get("fields", {})
        remind_text = fields.get("remind_text", "")
        chat_id = fields.get("chat_id", "")

        if not record_id or not remind_text or not chat_id:
            logger.warning("skipping incomplete reminder record: %s", record_id)
            continue

        result = await feishu_client.send_text_message("chat_id", chat_id, remind_text)

        sent_ok = result.get("code") == 0
        status = "sent" if sent_ok else "failed"

        await bitable_client.update_reminder_status(record_id, status, _now_ts())

        if sent_ok:
            logger.info("reminder sent: record_id=%s text=%s", record_id, remind_text)
        else:
            logger.error("reminder send failed: record_id=%s", record_id)


async def start_reminder_scheduler() -> None:
    logger.info("reminder scheduler started (interval=%ds)", _SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await check_and_send_reminders()
        except asyncio.CancelledError:
            logger.info("reminder scheduler cancelled")
            break
        except Exception:
            logger.exception("reminder scheduler error")
        await asyncio.sleep(_SCAN_INTERVAL_SECONDS)
