"""飞书长连接（WebSocket）事件接收入口。

使用 lark-oapi 的 FeishuChannel 建立 WebSocket 长连接，
接收 im.message.receive_v1 事件并调用共享业务逻辑处理。

长连接模式不需要公网地址，适合本地开发和常驻部署。

飞书后台配置步骤：
1. 事件与回调 → 回调配置 → 订阅方式选择「使用长连接接收事件」
2. 添加事件 im.message.receive_v1
3. 必须先运行本脚本，后台才能保存成功（因为需要验证长连接可达）
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lark_oapi import LogLevel
from lark_oapi.channel import FeishuChannel

from app.config import settings
from app.schemas import ParsedIncomingMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_message(msg):
    logger.info(
        "[WS] received message: message_id=%s chat_id=%s sender=%s chat_type=%s",
        msg.message_id,
        msg.chat_id,
        msg.sender_id,
        msg.chat_type,
    )

    raw_text = msg.content_text or ""

    logger.info(
        "[WS] text message: message_id=%s chat_id=%s sender=%s raw_text=%s",
        msg.message_id,
        msg.chat_id,
        msg.sender_id,
        raw_text,
    )

    parsed = ParsedIncomingMessage(
        message_id=msg.message_id,
        chat_id=msg.chat_id,
        sender_open_id=msg.sender_id,
        raw_text=raw_text,
        receive_id_type="chat_id" if msg.chat_type == "group" else "open_id",
        receive_id=msg.chat_id if msg.chat_type == "group" else msg.sender_id,
    )

    from app.event_handler import handle_chore_message

    reply = await handle_chore_message(parsed)
    if reply:
        logger.info("[WS] replied: message_id=%s reply=%s", msg.message_id, reply)
    else:
        logger.info("[WS] no reply needed: message_id=%s", msg.message_id)


async def main():
    app_id = settings.feishu_app_id
    app_secret = settings.feishu_app_secret

    if not app_id or not app_secret:
        logger.error(
            "FEISHU_APP_ID and FEISHU_APP_SECRET must be set in .env"
        )
        sys.exit(1)

    channel = FeishuChannel(
        app_id=app_id,
        app_secret=app_secret,
        log_level=LogLevel.INFO,
    )

    channel.on("message", on_message)

    async def on_error(err):
        logger.error("[WS] channel error: %s", err)

    channel.on("error", on_error)

    async def on_reconnecting():
        logger.warning("[WS] reconnecting ...")

    channel.on("reconnecting", on_reconnecting)

    async def on_reconnected():
        logger.info("[WS] reconnected successfully")

    channel.on("reconnected", on_reconnected)

    if settings.settlement_enabled:
        _scheduler_task = asyncio.create_task(start_settlement_scheduler())
        logger.info("settlement scheduler background task created")

    logger.info("starting feishu websocket channel ...")
    await channel.connect()
    logger.info("connected to wss://msg-frontier.feishu.cn")


async def start_settlement_scheduler():
    from app.settlement_scheduler import start_settlement_scheduler as _scheduler

    await _scheduler()


if __name__ == "__main__":
    asyncio.run(main())
