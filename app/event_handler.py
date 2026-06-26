"""im.message.receive_v1 事件处理核心逻辑"""

import json
import logging

from app.bitable_client import bitable_client
from app.chore_service import (
    calculate_total_points,
    extract_chore_text,
    format_chore_reply,
    format_supported_tasks_reply,
    get_default_task_types,
    get_member_name,
    normalize_chore_input_text,
)
from app.feishu_client import feishu_client
from app.llm_parser import llm_parser
from app.schemas import FeishuMessageEvent, ParsedIncomingMessage
from app.time_utils import now_local

logger = logging.getLogger(__name__)

_processed_message_ids: set[str] = set()


def _dedup(message_id: str) -> bool:
    if message_id in _processed_message_ids:
        return True
    _processed_message_ids.add(message_id)
    if len(_processed_message_ids) > 10000:
        _processed_message_ids.clear()
    return False


async def handle_chore_message(msg: ParsedIncomingMessage) -> str | None:
    if _dedup(msg.message_id):
        logger.info("ignored duplicate message_id=%s", msg.message_id)
        return None

    raw_text = msg.raw_text
    normalized = normalize_chore_input_text(raw_text)
    chore_text = extract_chore_text(raw_text)

    logger.info(
        "chore check: message_id=%s raw_text=%s normalized=%s chore_text=%s",
        msg.message_id,
        raw_text,
        normalized,
        chore_text,
    )

    if not chore_text:
        logger.info(
            "ignored empty chore text: message_id=%s raw_text=%s",
            msg.message_id,
            raw_text,
        )
        return None

    # Layer 2: persistent dedup (check raw_inputs table)
    if bitable_client.is_configured:
        try:
            already_exists = await bitable_client.find_raw_input_by_message_id(msg.message_id)
            if already_exists:
                logger.info(
                    "persistent dedup: skipped duplicate message_id=%s",
                    msg.message_id,
                )
                return None
        except Exception:
            logger.warning(
                "persistent dedup check failed, proceeding: message_id=%s",
                msg.message_id,
            )

    logger.info(
        "calling LLM to parse: message_id=%s chore_text=%s",
        msg.message_id,
        chore_text,
    )

    result = await llm_parser.parse_chore_text(chore_text, get_default_task_types())

    logger.info(
        "LLM result: message_id=%s tasks=%d ignored=%s need_confirm=%s",
        msg.message_id,
        len(result.tasks),
        result.ignored,
        result.need_confirm,
    )

    # Determine status for raw_inputs
    if result.tasks:
        status = "parsed"
    elif result.need_confirm:
        status = "need_confirm"
    else:
        status = "ignored"

    now = now_local()
    received_at = int(now.timestamp())
    member_name = get_member_name(msg.sender_open_id)

    # --- Compute totals and build base reply ---
    total_points = calculate_total_points(result.tasks) if result.tasks else 0
    task_count = len(result.tasks)

    supported_tasks = format_supported_tasks_reply()

    if result.tasks:
        base_reply = format_chore_reply(result.tasks, total_points)
        logger.info(
            "parsed chores: message_id=%s tasks=%s total_points=%d",
            msg.message_id,
            [t.task_type for t in result.tasks],
            total_points,
        )
    elif result.need_confirm:
        base_reply = (
            f"我不太确定这条记录对应哪项家务，暂未计分。\n"
            f"{supported_tasks}\n"
            f"你可以说得更明确一些，例如：「我扫了地」「我拖了地」。"
        )
        logger.info(
            "need confirm: message_id=%s chore_text=%s",
            msg.message_id,
            chore_text,
        )
    elif result.ignored:
        base_reply = (
            f"这条我先不计分。{supported_tasks}\n"
            f"你可以说得更明确一些，例如：「我洗了碗」「我做了晚饭」。"
        )
        logger.info(
            "no tasks with ignored: message_id=%s chore_text=%s ignored=%s",
            msg.message_id,
            chore_text,
            result.ignored,
        )
    else:
        base_reply = (
            f"这条我先不计分。{supported_tasks}\n"
            f"你可以说得更明确一些，例如：「我洗了碗」「我做了晚饭」。"
        )
        logger.info(
            "no tasks found: message_id=%s chore_text=%s",
            msg.message_id,
            chore_text,
        )

    # --- Write raw_inputs (best-effort, include base reply) ---
    raw_input_ok = True
    if bitable_client.is_configured:
        try:
            ri_res = await bitable_client.append_raw_input(
                message_id=msg.message_id,
                chat_id=msg.chat_id,
                sender_id=msg.sender_open_id,
                raw_text=raw_text,
                normalized_text=normalized,
                chore_text=chore_text,
                status=status,
                received_at=received_at,
                ai_result_json=json.dumps(result.model_dump(), ensure_ascii=False),
                total_points=total_points,
                task_count=task_count,
                reply_text=base_reply,
            )
            raw_input_ok = ri_res is not None and ri_res.get("code") == 0
        except Exception:
            raw_input_ok = False
            logger.exception("raw_inputs write failed: message_id=%s", msg.message_id)

    # --- Write chore_records (best-effort) ---
    chore_records_ok = True
    if bitable_client.is_configured and result.tasks:
        try:
            cr_results = await bitable_client.append_chore_records(
                message_id=msg.message_id,
                chat_id=msg.chat_id,
                sender_id=msg.sender_open_id,
                tasks=result.tasks,
                source_text=chore_text,
                member_name=member_name,
                date=received_at,
            )
            chore_records_ok = all(r is not None and r.get("code") == 0 for r in cr_results)
        except Exception:
            chore_records_ok = False
            logger.exception("chore_records write failed: message_id=%s", msg.message_id)

    # --- Build final reply (adjust for write status) ---
    write_ok = raw_input_ok and chore_records_ok
    if result.tasks and not write_ok:
        reply_text = base_reply.replace("已记录", "已识别", 1)
        reply_text = reply_text.replace("：", "，但写入多维表格失败，请稍后检查：", 1)
    else:
        reply_text = base_reply

    result_api = await feishu_client.send_text_message(
        msg.receive_id_type, msg.receive_id, reply_text
    )

    if result_api.get("code") == 0:
        logger.info("replied to chore message: message_id=%s", msg.message_id)
    else:
        logger.error(
            "failed to reply to chore message: message_id=%s result=%s",
            msg.message_id,
            result_api,
        )

    return reply_text


async def handle_feishu_message_event(event_payload: dict) -> dict:
    header = event_payload.get("header", {})
    event = event_payload.get("event", {})
    event_type = header.get("event_type", "")

    logger.info("received event: event_type=%s", event_type)

    if event_type != "im.message.receive_v1":
        logger.info("ignored event: event_type=%s (not im.message.receive_v1)", event_type)
        return {"event_type": event_type, "handled": False, "reason": "not im.message.receive_v1"}

    msg_event = FeishuMessageEvent(**event)
    message = msg_event.message
    sender_open_id = msg_event.sender.sender_id.get("open_id", "")

    logger.info(
        "im.message.receive_v1: message_id=%s chat_id=%s chat_type=%s sender_open_id=%s message_type=%s",
        message.message_id,
        message.chat_id,
        message.chat_type,
        sender_open_id,
        message.message_type,
    )

    if message.message_type != "text":
        logger.info("ignored non-text message: message_type=%s", message.message_type)
        return {"handled": False, "reason": "non-text message"}

    try:
        content = json.loads(message.content)
        raw_text = content.get("text", "")
    except (json.JSONDecodeError, KeyError):
        logger.warning("failed to parse message content: %s", message.content)
        return {"handled": False, "reason": "parse content failed"}

    logger.info(
        "text message: message_id=%s chat_id=%s sender=%s raw_text=%s",
        message.message_id,
        message.chat_id,
        sender_open_id,
        raw_text,
    )

    chat_type = message.chat_type
    msg = ParsedIncomingMessage(
        message_id=message.message_id,
        chat_id=message.chat_id,
        sender_open_id=sender_open_id,
        raw_text=raw_text,
        receive_id_type="chat_id" if chat_type == "group" else "open_id",
        receive_id=message.chat_id if chat_type == "group" else sender_open_id,
    )

    reply_text = await handle_chore_message(msg)
    return {"handled": True, "replied": reply_text is not None}
