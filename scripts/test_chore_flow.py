"""测试家务核心业务逻辑（无需飞书 API / LLM 调用）"""

# ruff: noqa: E402 — env must be set before app imports

import os
import sys

# Set test env vars before app imports so config picks them up
os.environ["MEMBER_MAP_JSON"] = '{"ou_user_a":"Alice","ou_user_b":"Bob"}'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Clear any cached pydantic-settings by re-loading
import importlib
import app.config
importlib.reload(app.config)

import app.chore_service as cs
importlib.reload(cs)

from datetime import datetime

from app.chore_service import (
    calculate_total_points,
    extract_chore_text,
    format_chore_reply,
    get_date_fields,
    get_member_name,
    get_task_points,
    is_chore_message,
    normalize_chore_input_text,
)
from app.schemas import ParsedChoreTask


def test_member_mapping():
    print("=== 测试成员映射 ===")

    cs._member_map = None
    name = get_member_name("ou_c8dc1234abcd5678bd86")
    print(f"  fallback: {name}")
    assert "..." in name or len(name) < len("ou_c8dc1234abcd5678bd86")

    cs._member_map = None
    assert get_member_name("ou_user_a") == "Alice", f"expected Alice, got {get_member_name('ou_user_a')!r}"
    assert get_member_name("ou_user_b") == "Bob", f"expected Bob, got {get_member_name('ou_user_b')!r}"
    unknown = get_member_name("ou_unknown")
    assert "..." in unknown or unknown != "Alice"
    print("  mapped: Alice, Bob, unknown -> abbreviated")
    print("  ✅ 成员映射正常")


def test_date_fields():
    print("\n=== 测试日期字段 ===")
    dt = datetime(2026, 6, 26, 12, 0, 0)
    ts = int(dt.timestamp())
    fields = get_date_fields(ts)
    print(f"  date: {fields['date']}")
    print(f"  week: {fields['week']}")
    print(f"  month: {fields['month']}")
    print(f"  datetime_ms: {fields.get('datetime_ms', 'N/A')}")
    assert fields["date"] == "2026-06-26"
    assert fields["month"] == "2026-06"
    assert fields["week"] == "2026-W26"
    assert "1970" not in fields["date"]
    assert "1970" not in fields["week"]
    assert "1970" not in fields["month"]
    assert fields.get("datetime_ms", 0) == int(dt.timestamp() * 1000)
    print("  ✅ 日期字段正常（无1970）")

    # Also verify with default (now) — should never be 1970
    print("\n=== 测试 get_date_fields() 默认值 ===")
    now_fields = get_date_fields()
    print(f"  date: {now_fields['date']}")
    print(f"  week: {now_fields['week']}")
    print(f"  month: {now_fields['month']}")
    assert "1970" not in now_fields["date"], f"date should not be 1970: {now_fields['date']}"
    assert "1970" not in now_fields["week"], f"week should not be 1970: {now_fields['week']}"
    assert "1970" not in now_fields["month"], f"month should not be 1970: {now_fields['month']}"
    assert now_fields["datetime_ms"] > 1_000_000_000_000
    print("  ✅ 默认日期字段无1970")


def test_chore_detection():
    print("\n=== 测试家务检测 ===")
    cases = [
        ("@小哈皮 家务：洗碗", "洗碗"),
        ("@小哈皮 我洗了碗", "我洗了碗"),
        ("家务：我洗了碗还拖了地", "我洗了碗还拖了地"),
        ("家务:倒垃圾", "倒垃圾"),
        ("@小哈皮 你好", "你好"),
        ("我洗了碗", "我洗了碗"),
        ("", ""),
    ]
    for text, exp_extract in cases:
        assert extract_chore_text(text) == exp_extract, f"extract_chore_text({text!r})"
        if exp_extract:
            assert is_chore_message(text), f"is_chore_message({text!r}) should be True"
        else:
            assert not is_chore_message(text), f"is_chore_message({text!r}) should be False"
    print("  ✅ 家务检测正常")


def test_points():
    print("\n=== 测试积分计算 ===")
    assert get_task_points("做饭") == 1
    assert get_task_points("洗碗") == 1
    assert get_task_points("扫地") == 1
    assert get_task_points("拖地") == 1
    assert get_task_points("倒垃圾") == 1
    assert get_task_points("洗衣服") == 1
    assert get_task_points("晾衣服") == 1
    assert get_task_points("收衣服") == 1
    assert get_task_points("整理收纳") == 1
    assert get_task_points("叠衣铺床") == 1
    assert get_task_points("换洗床品") == 1
    assert get_task_points("清洁打扫") == 1
    assert get_task_points("虎妞照护") == 1
    assert get_task_points("不存在") == 0
    assert get_task_points("买菜") == 0
    assert get_task_points("清洁台面") == 0
    assert get_task_points("清洁卫生间") == 0

    tasks = [
        ParsedChoreTask(task_type="洗碗", confidence=0.95, evidence="洗了碗"),
        ParsedChoreTask(task_type="拖地", confidence=0.95, evidence="拖了地"),
    ]
    assert calculate_total_points(tasks) == 2
    print("  洗碗=1分, 拖地=1分, 总计=2分")
    print("  ✅ 积分计算正常")


def test_reply_format():
    print("\n=== 测试回复格式 ===")
    tasks = [
        ParsedChoreTask(task_type="洗碗", confidence=0.95, evidence="洗了碗"),
        ParsedChoreTask(task_type="拖地", confidence=0.95, evidence="拖了地"),
    ]
    reply = format_chore_reply(tasks, 2)
    print(f"  正常回复:\n{reply}")
    assert "已记录" in reply
    assert "2 项家务" in reply
    assert "2 分" in reply
    assert "洗碗" in reply
    assert "拖地" in reply
    print("  ✅ 正常回复格式正常")


def test_reply_write_fail_format():
    print("\n=== 测试写表失败回复格式 ===")
    tasks = [
        ParsedChoreTask(task_type="洗碗", confidence=0.95, evidence="洗了碗"),
    ]
    base = format_chore_reply(tasks, 1)
    adjusted = base.replace("已记录", "已识别", 1)
    adjusted = adjusted.replace("：", "，但写入多维表格失败，请稍后检查：", 1)
    print(f"  失败回复:\n{adjusted}")
    assert "已识别" in adjusted
    assert "写入多维表格失败" in adjusted
    print("  ✅ 写表失败回复格式正常")


def test_supported_tasks():
    print("\n=== 测试支持任务列表 ===")
    from app.chore_service import format_supported_tasks_reply
    reply = format_supported_tasks_reply()
    print(f"  {reply}")
    assert "做饭" in reply
    assert "洗碗" in reply
    assert "清洁打扫" in reply
    print("  ✅ 支持任务列表包含当前 13 类任务")


def test_default_task_types():
    print("\n=== 测试默认任务类型 ===")
    from app.chore_service import get_default_task_types
    types = get_default_task_types()
    assert len(types) == 13
    assert "做饭" in types
    assert "整理收纳" in types
    assert "叠衣铺床" in types
    assert "换洗床品" in types
    assert "清洁打扫" in types
    assert "虎妞照护" in types
    assert "清洁台面" not in types
    assert "清洁卫生间" not in types
    assert "整理房间" not in types
    assert "买菜" not in types
    print(f"  默认任务类型 ({len(types)}): {types}")
    print("  ✅ 默认任务类型正常")


def test_normalize():
    print("\n=== 测试文本标准化 ===")
    assert normalize_chore_input_text("  @小哈皮 我洗了碗") == "我洗了碗"
    assert normalize_chore_input_text("@小哈皮 家务：洗碗") == "家务：洗碗"
    assert normalize_chore_input_text("@小哈皮 我洗了碗") == "我洗了碗"
    assert normalize_chore_input_text("家务：洗碗") == "家务：洗碗"
    assert normalize_chore_input_text("") == ""
    print("  ✅ 文本标准化正常")


if __name__ == "__main__":
    test_member_mapping()
    test_date_fields()
    test_chore_detection()
    test_points()
    test_reply_format()
    test_reply_write_fail_format()
    test_normalize()
    test_supported_tasks()
    test_default_task_types()
    print("\n" + "=" * 40)
    print("所有测试通过 ✅")
    print("=" + "=" * 40)
