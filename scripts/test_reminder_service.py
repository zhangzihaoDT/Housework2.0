"""reminder_service 单元测试 —— 关键词预检、时间计算、回复格式化"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.reminder_service import (
    matches_reminder_pattern,
    get_today_info,
    build_remind_at,
    format_create_reply,
)


class FakeParsed:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_matches_reminder_pattern_hits():
    cases = [
        "明天 shuyao 去杭州",
        "下周三 shuyao 去杭州",
        "7月12日妈妈体检",
        "7 月 12 日家里保洁上门",
        "明天早上9点提醒我交水费",
        "周六全家去迪士尼",
        "下个月 5 号妈妈体检",
        "下个月5号妈妈体检",
        "后天倒垃圾",
        "提醒我明天交水费",
    ]
    for c in cases:
        assert matches_reminder_pattern(c), f"should match reminder pattern: {c!r}"
    print("  ✅ 提醒类文本关键词命中")


def test_matches_reminder_pattern_clean_misses():
    cases = [
        "你好",
        "在吗",
        "你是谁",
        "测试",
        "好",
        "知道了",
        "收到",
    ]
    for c in cases:
        assert not matches_reminder_pattern(c), f"should NOT match reminder pattern: {c!r}"
    print("  ✅ 非提醒文本未误判")


def test_build_remind_at_default_time():
    dt = build_remind_at("2026-07-08", "")
    assert dt.strftime("%H:%M") == "08:00"
    assert dt.strftime("%Y-%m-%d") == "2026-07-08"
    print("  ✅ 默认提醒时间为 08:00")


def test_build_remind_at_explicit_time():
    dt = build_remind_at("2026-07-08", "09:30")
    assert dt.strftime("%H:%M") == "09:30"
    print("  ✅ 明确时间优先")


def test_build_remind_at_invalid_fallback():
    dt = build_remind_at("not-a-date", "abc")
    # Should not crash; returns current time
    assert dt is not None
    print("  ✅ 异常输入不会崩溃")


def test_get_today_info():
    date_str, wd = get_today_info()
    assert "-" in date_str
    assert wd in ("一", "二", "三", "四", "五", "六", "日")
    print("  ✅ get_today_info 格式正确")


def test_format_create_reply_member_level():
    parsed = FakeParsed(
        target_person="shuyao",
        event_text="去杭州",
        event_date="2026-07-08",
        remind_time="08:00",
        remind_text="今天 shuyao 去杭州",
    )
    reply = format_create_reply(parsed)
    assert "已记录提醒" in reply
    assert "shuyao" in reply
    assert "2026-07-08" in reply
    assert "08:00" in reply
    print("  ✅ 成员级提醒回复格式正确")


def test_format_create_reply_family_level():
    parsed = FakeParsed(
        target_person="",
        event_text="去迪士尼",
        event_date="2026-07-11",
        remind_time="",
        remind_text="今天全家去迪士尼",
    )
    reply = format_create_reply(parsed)
    assert "已记录提醒" in reply
    assert "家庭" in reply or "全家" in reply
    assert "08:00" in reply
    print("  ✅ 家庭级提醒回复格式正确")


if __name__ == "__main__":
    test_matches_reminder_pattern_hits()
    test_matches_reminder_pattern_clean_misses()
    test_build_remind_at_default_time()
    test_build_remind_at_explicit_time()
    test_build_remind_at_invalid_fallback()
    test_get_today_info()
    test_format_create_reply_member_level()
    test_format_create_reply_family_level()
    print("\n✅ reminder_service 全部测试通过")
