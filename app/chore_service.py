"""家务积分业务逻辑"""

import json
import re
import logging

from app.config import settings
from app.schemas import ParsedChoreTask
from app.time_utils import get_date_fields as _get_date_fields

logger = logging.getLogger(__name__)

CHORE_PREFIXES = ("家务：", "家务:")

TASK_POINTS: dict[str, int] = {
    "倒垃圾": 1,
    "收衣服": 1,
    "晾衣服": 1,
    "洗碗": 1,
    "扫地": 1,
    "洗衣服": 1,
    "整理房间": 1,
    "拖地": 1,
    "做饭": 1,
}

_member_map: dict[str, str] | None = None


def get_member_map() -> dict[str, str]:
    global _member_map
    if _member_map is not None:
        return _member_map
    raw = settings.member_map_json
    if not raw:
        _member_map = {}
        return _member_map
    try:
        _member_map = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("failed to parse MEMBER_MAP_JSON: %s", e)
        _member_map = {}
    return _member_map


def get_member_name(sender_id: str) -> str:
    mapping = get_member_map()
    if sender_id in mapping:
        return mapping[sender_id]
    if len(sender_id) > 12:
        return sender_id[:4] + "..." + sender_id[-4:]
    return sender_id


def get_date_fields(ts: int | None = None) -> dict[str, str]:
    return _get_date_fields(ts)


def get_default_task_types() -> list[str]:
    return list(TASK_POINTS.keys())


def get_task_points(task_type: str) -> int:
    return TASK_POINTS.get(task_type, 0)


def calculate_total_points(tasks: list[ParsedChoreTask]) -> int:
    return sum(get_task_points(t.task_type) for t in tasks)


SUPPORTED_TASKS_TEXT = "我会记录已完成的家务，例如：「我洗了碗」「我做了晚饭」「我整理了房间」。"


def format_supported_tasks_reply() -> str:
    return SUPPORTED_TASKS_TEXT


def format_chore_reply(tasks: list[ParsedChoreTask], total_points: int) -> str:
    lines = [f"已记录 {len(tasks)} 项家务，共 {total_points} 分："]
    for t in tasks:
        pts = get_task_points(t.task_type)
        lines.append(f"- {t.task_type}：{pts} 分")
    return "\n".join(lines)


def normalize_chore_input_text(text: str) -> str:
    text = text.strip()
    if text.startswith("@"):
        text = re.sub(r"^@\S+\s*", "", text).strip()
    return text


def is_chore_message(text: str) -> bool:
    return bool(extract_chore_text(text))


def extract_chore_text(text: str) -> str:
    normalized = normalize_chore_input_text(text)
    if not normalized:
        return ""
    for prefix in CHORE_PREFIXES:
        if normalized.startswith(prefix):
            return normalized[len(prefix):].strip()
    return normalized
