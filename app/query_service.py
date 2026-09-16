"""数据查询：意图识别 + 近 N 天记录 / 本轮得分对比（纯文本回复）"""

import logging
import re
from datetime import timedelta

from app.bitable_client import bitable_client
from app.chore_service import get_member_map, normalize_chore_input_text
from app.config import settings
from app.feishu_client import feishu_client
from app.schemas import ParsedIncomingMessage
from app.settlement_period import (
    compute_current_period,
    compute_last_completed_period,
)
from app.settlement_service import _build_member_summary, _format_date_cn
from app.time_utils import now_local, to_datetime

logger = logging.getLogger(__name__)

_DEFAULT_RECENT_DAYS = 5

_RECENT_N_DAYS_RE = re.compile(r"(?:近|最近)\s*(\d+)\s*天")
_RECENT_WORDS = ("这几天", "最近", "近期")
_RECENT_VERBS = (
    "做了哪些", "做了什么", "干了哪些", "干了什么", "有哪些", "哪几项",
    "清单", "明细",
)
_SCORE_WORDS = (
    "得分", "分数", "积分", "总分", "累计", "排行", "排名", "对比",
    "谁多", "谁高", "领先", "比分", "战况",
)
# 强查询信号：单独出现即可判定为查询，避免"我累计拖了两次地"被误判
_SCORE_STRONG = ("对比", "排行", "排名", "谁多", "谁高", "比分", "战况", "领先")
_PERIOD_WORDS = (
    "本轮", "本期", "这轮", "这个周期", "这周期", "当前周期",
    "上一轮", "上期", "上个周期", "上一期", "上轮", "上周期",
)
_LAST_WORDS = ("上一轮", "上期", "上个周期", "上一期", "上轮", "上周期")


def classify_intent(text: str) -> dict:
    """识别消息意图：recent_chores / period_score / chore_log"""
    normalized = normalize_chore_input_text(text)
    if not normalized:
        return {"type": "chore_log"}

    if any(w in normalized for w in _SCORE_WORDS) and (
        any(w in normalized for w in _SCORE_STRONG)
        or any(w in normalized for w in _PERIOD_WORDS)
    ):
        kind = "last" if any(w in normalized for w in _LAST_WORDS) else "current"
        return {"type": "period_score", "period": kind}

    m = _RECENT_N_DAYS_RE.search(normalized)
    if m:
        days = max(1, min(settings.recent_query_max_days, int(m.group(1))))
        return {"type": "recent_chores", "days": days}

    if any(w in normalized for w in _RECENT_WORDS) and any(
        v in normalized for v in _RECENT_VERBS
    ):
        return {"type": "recent_chores", "days": _DEFAULT_RECENT_DAYS}

    if any(v in normalized for v in _RECENT_VERBS):
        return {"type": "recent_chores", "days": _DEFAULT_RECENT_DAYS}

    return {"type": "chore_log"}


def _field_text(value) -> str:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("text") or item.get("value")
                if text:
                    return str(text)
            elif item:
                return str(item)
        return ""
    return str(value) if value is not None else ""


def _aggregate_totals(records: list[dict]) -> tuple[dict[str, int], int]:
    totals: dict[str, int] = {}
    record_count = 0
    for r in records:
        fields = r.get("fields", {})
        member_name = _field_text(fields.get("member_name", ""))
        points = fields.get("points", 0)
        if isinstance(points, list):
            points = points[0] if points else 0
        try:
            points = int(points)
        except (TypeError, ValueError):
            points = 0
        if member_name:
            totals[member_name] = totals.get(member_name, 0) + points
            record_count += 1
    return totals, record_count


async def _reply(msg: ParsedIncomingMessage, text: str) -> str:
    result = await feishu_client.send_text_message(msg.receive_id_type, msg.receive_id, text)
    if result.get("code") == 0:
        logger.info("replied to query: message_id=%s", msg.message_id)
    else:
        logger.error("failed to reply query: message_id=%s result=%s", msg.message_id, result)
    return text


async def handle_recent_chores(msg: ParsedIncomingMessage, days: int) -> str:
    if not bitable_client.is_configured:
        return await _reply(msg, "多维表格未配置，暂时无法查询。")

    now = now_local()
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=days)).timestamp() * 1000)

    records = await bitable_client.find_chore_records_by_time_range(start_ms, end_ms)
    mine = [r for r in records if _field_text(r.get("fields", {}).get("sender_id", "")) == msg.sender_open_id]

    if not mine:
        return await _reply(msg, f"近 {days} 天没有查询到你的家务记录。")

    by_day: dict[str, list[str]] = {}
    total_points = 0
    total_count = 0
    for r in mine:
        fields = r.get("fields", {})
        task_type = _field_text(fields.get("task_type", ""))
        if not task_type:
            continue
        points = fields.get("points", 0)
        if isinstance(points, list):
            points = points[0] if points else 0
        try:
            total_points += int(points)
        except (TypeError, ValueError):
            pass
        total_count += 1
        ts = fields.get("date") or fields.get("created_at")
        if isinstance(ts, list):
            ts = ts[0] if ts else None
        day = to_datetime(ts).strftime("%m-%d") if ts else "未知日期"
        by_day.setdefault(day, []).append(task_type)

    lines = [f"近 {days} 天你的家务记录（共 {total_count} 项，{total_points} 分）："]
    for day in sorted(by_day.keys(), reverse=True):
        tasks = by_day[day]
        lines.append(f"- {day}：{'、'.join(tasks)}")
    return await _reply(msg, "\n".join(lines))


async def handle_period_score(msg: ParsedIncomingMessage, period_kind: str = "current") -> str:
    if not bitable_client.is_configured:
        return await _reply(msg, "多维表格未配置，暂时无法查询。")

    anchor = settings.settlement_anchor_date
    if not anchor:
        return await _reply(msg, "未配置结算周期，暂时无法查询。")

    interval = settings.settlement_interval_days
    if period_kind == "last":
        period = compute_last_completed_period(anchor, interval)
        if not period:
            return await _reply(msg, "暂无已完成的周期。")
    else:
        period = compute_current_period(anchor, interval)

    records = await bitable_client.find_chore_records_by_period(period["period_id"])
    totals, record_count = _aggregate_totals(records)
    summary = _build_member_summary(totals, get_member_map())
    total_points = sum(item["points"] for item in summary)

    label_start = _format_date_cn(period["period_start"])
    label_end = _format_date_cn(period["period_end"])
    title = "上一轮" if period_kind == "last" else "本轮"

    lines = [f"{title}累计得分（{label_start}—{label_end}）："]
    for item in summary:
        lines.append(f"- {item['member_name']}：{item['points']} 分")
    lines.append(f"合计：{total_points} 分，共 {record_count} 项")
    return await _reply(msg, "\n".join(lines))
