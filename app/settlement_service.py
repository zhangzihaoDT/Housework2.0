"""结算服务：汇总积分、构建飞书消息卡片、执行结算流程"""

import json
import logging
from datetime import date

from app.bitable_client import bitable_client
from app.feishu_client import feishu_client
from app.chore_service import get_member_map
from app.settlement_period import compute_next_settlement_time
from app.config import settings

logger = logging.getLogger(__name__)


def _build_member_summary(totals: dict[str, int], member_map: dict[str, str]) -> list[dict]:
    """构建成员积分列表，包含零积分成员，按积分降序排列"""
    members = set(member_map.values())
    for m in members:
        totals.setdefault(m, 0)
    sorted_members = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
    return [{"member_name": m, "points": p} for m, p in sorted_members]


def _format_date_cn(iso_str: str) -> str:
    """2026-07-27 → 2026年7月27日"""
    parts = iso_str.split("-")
    if len(parts) == 3:
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return iso_str


def _get_rank_emoji(rank: int) -> str:
    if rank == 0:
        return "🥇"
    if rank == 1:
        return "🥈"
    if rank == 2:
        return "🥉"
    return ""


def build_settlement_card(period: dict, summary: list[dict], total_points: int, record_count: int, next_settlement: str) -> dict:
    period_start = _format_date_cn(period["period_start"])
    period_end = _format_date_cn(period["period_end"])
    period_label = f"{period_start}—{period_end}"

    member_lines = []
    for rank, item in enumerate(summary):
        emoji = _get_rank_emoji(rank)
        prefix = f"{emoji} " if emoji else "  "
        member_lines.append(f"{prefix}**{item['member_name']}**　{item['points']} 分")

    member_section = "\n\n".join(member_lines) if member_lines else "暂无记录"

    next_settlement_display = _format_date_cn(next_settlement.split("T")[0]) if "T" in next_settlement else next_settlement

    card = {
        "config": {
            "wide_screen_mode": True,
        },
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": "🏆 小哈皮双周家务结算",
            },
        },
        "elements": [
            {"tag": "markdown", "content": f"**结算周期**\n{period_label}"},
            {"tag": "hr"},
            {"tag": "markdown", "content": member_section},
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": (
                    f"本期共完成 **{record_count} 项家务**，累计 **{total_points} 分**\n\n"
                    f"新一期积分已开始累计\n"
                    f"下次结算：**{next_settlement_display}**"
                ),
            },
        ],
    }
    return card


def _build_empty_card(period: dict, next_settlement: str) -> dict:
    period_start = _format_date_cn(period["period_start"])
    period_end = _format_date_cn(period["period_end"])
    next_settlement_display = _format_date_cn(next_settlement.split("T")[0]) if "T" in next_settlement else next_settlement

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": "🏆 小哈皮双周家务结算",
            },
        },
        "elements": [
            {"tag": "markdown", "content": f"**结算周期**\n{period_start}—{period_end}"},
            {"tag": "hr"},
            {"tag": "markdown", "content": "本期暂时没有家务积分记录。"},
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": f"新一期积分已开始累计\n下次结算：**{next_settlement_display}**",
            },
        ],
    }


async def execute_settlement(period: dict) -> dict:
    anchor_date = date.fromisoformat(settings.settlement_anchor_date)
    interval_days = settings.settlement_interval_days
    settlement_time = settings.settlement_time

    period_id = period["period_id"]
    period_start = period["period_start"]
    period_end = period["period_end"]

    logger.info("executing settlement: period_id=%s", period_id)

    if not bitable_client.is_configured:
        logger.warning("bitable not configured, cannot execute settlement")
        return {"success": False, "reason": "bitable not configured"}

    records = await bitable_client.find_chore_records_by_period(period_id)
    logger.info("found %d chore records for period_id=%s", len(records), period_id)

    totals: dict[str, int] = {}
    record_count = 0
    for r in records:
        fields = r.get("fields", {})
        member_name = fields.get("member_name", "")
        points = fields.get("points", 0)
        if isinstance(points, (int, float)):
            totals[member_name] = totals.get(member_name, 0) + int(points)
            record_count += 1

    member_map = get_member_map()
    summary = _build_member_summary(totals, member_map)
    total_points = sum(item["points"] for item in summary)

    next_settlement = compute_next_settlement_time(anchor_date, interval_days, settlement_time)
    next_settlement_str = next_settlement or ""

    if record_count == 0:
        card = _build_empty_card(period, next_settlement_str)
    else:
        card = build_settlement_card(period, summary, total_points, record_count, next_settlement_str)

    if not settings.settlement_chat_id:
        logger.warning("SETTLEMENT_CHAT_ID not configured, skipping send")
        return {"success": False, "reason": "SETTLEMENT_CHAT_ID not configured"}

    member_summary_json = json.dumps(
        {item["member_name"]: item["points"] for item in summary},
        ensure_ascii=False,
    )

    result = await bitable_client.create_settlement_record(
        period_id=period_id,
        period_start=period_start,
        period_end=period_end,
        status="processing",
        total_points=total_points,
        member_summary=member_summary_json,
        record_count=record_count,
    )
    if result is None:
        logger.error("failed to create settlement record: period_id=%s", period_id)
        return {"success": False, "reason": "create settlement record failed"}

    record_id = result.get("data", {}).get("record", {}).get("record_id", "")
    logger.info("settlement record created: record_id=%s period_id=%s", record_id, period_id)

    send_result = await feishu_client.send_interactive_card(
        receive_id=settings.settlement_chat_id,
        card=card,
    )

    sent_ok = send_result.get("code") == 0
    status = "sent" if sent_ok else "failed"
    feishu_message_id = send_result.get("data", {}).get("message_id", "")

    await bitable_client.update_settlement_record(
        record_id=record_id,
        status=status,
        feishu_message_id=feishu_message_id,
        error_message="" if sent_ok else str(send_result.get("msg", "")),
    )

    if sent_ok:
        logger.info("settlement sent: period_id=%s feishu_message_id=%s", period_id, feishu_message_id)
    else:
        logger.error("settlement send failed: period_id=%s result=%s", period_id, send_result)

    return {"success": sent_ok, "period_id": period_id, "record_id": record_id}
