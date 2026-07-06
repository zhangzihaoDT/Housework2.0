"""家庭提醒业务逻辑：意图检测、提醒创建、到点推送"""

import logging
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_CN_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

_REMINDER_KEYWORDS = re.compile(
    r"(今天|明天|后天|大后天|"
    r"周[一二三四五六日天]|"
    r"下个?(周|月)([一二三四五六日天]|\d)?|"
    r"\d+\s*月\s*\d+\s*[号日]|"
    r"\d{4}\s*年\s*\d+\s*月\s*\d+\s*[号日]|"
    r"早上|上午|中午|下午|晚上|"
    r"\d+[：:]\d+|\d+\s*点|"
    r"提醒)"
)


def matches_reminder_pattern(text: str) -> bool:
    return bool(_REMINDER_KEYWORDS.search(text))


def get_today_info() -> tuple[str, str]:
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    wd = _CN_WEEKDAYS[now.weekday()]
    return date_str, wd


def build_remind_at(event_date: str, remind_time: str) -> datetime:
    if not remind_time:
        remind_time = "08:00"
    try:
        dt = datetime.strptime(f"{event_date} {remind_time}", "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=8)))
    except (ValueError, TypeError):
        logger.warning("failed to parse remind_at: date=%s time=%s", event_date, remind_time)
        return datetime.now(timezone(timedelta(hours=8)))


def format_create_reply(parsed) -> str:
    scope = "家庭" if not parsed.target_person else parsed.target_person
    reminder_time_display = parsed.remind_time or "08:00"
    remind_text_preview = parsed.remind_text or (
        f"今天 {parsed.target_person} {parsed.event_text}"
        if parsed.target_person
        else f"今天全家{parsed.event_text}"
    )
    return (
        f"收到～已记录提醒：\n"
        f"{parsed.event_date} 早上 {reminder_time_display}，我会提醒：{remind_text_preview}"
    )
