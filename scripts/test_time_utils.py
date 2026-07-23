"""测试统一时间工具模块"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.time_utils import (
    get_date_fields,
    now_local,
    to_datetime,
    to_feishu_timestamp_ms,
)


def test_now_local():
    print("=== 测试 now_local() ===")
    dt = now_local()
    print(f"  now_local() = {dt}")
    assert dt.year >= 2026, f"year should be >= 2026, got {dt.year}"
    print(f"  year={dt.year} ✅")
    assert dt.tzinfo is not None, "should be timezone-aware"
    print("  timezone-aware ✅")


def test_to_datetime_none():
    print("\n=== 测试 to_datetime(None) ===")
    dt = to_datetime(None)
    print(f"  to_datetime(None) = {dt}")
    assert dt.year >= 2026
    print(f"  year={dt.year} ✅")


def test_to_datetime_seconds():
    print("\n=== 测试 to_datetime(秒级 timestamp) ===")
    ts = int(time.time())
    dt = to_datetime(ts)
    print(f"  to_datetime({ts}) = {dt}")
    assert dt.year >= 2026, f"year={dt.year}"
    print(f"  year={dt.year} ✅")


def test_to_datetime_milliseconds():
    print("\n=== 测试 to_datetime(毫秒级 timestamp) ===")
    ts = int(time.time() * 1000)
    dt = to_datetime(ts)
    print(f"  to_datetime({ts}) = {dt}")
    assert dt.year >= 2026, f"year={dt.year}"
    print(f"  year={dt.year} ✅")


def test_to_feishu_timestamp_ms():
    print("\n=== 测试 to_feishu_timestamp_ms() ===")
    dt = now_local()
    ms = to_feishu_timestamp_ms(dt)
    print(f"  to_feishu_timestamp_ms({dt}) = {ms}")
    assert ms > 1_000_000_000_000, f"should be 13-digit ms timestamp, got {ms}"
    assert ms < 9_999_999_999_999, f"unrealistically large: {ms}"
    print(f"  {ms} is valid 13-digit ms timestamp ✅")


def test_get_date_fields_default():
    print("\n=== 测试 get_date_fields() 默认值 ===")
    fields = get_date_fields()
    print(f"  date={fields['date']}")
    print(f"  week={fields['week']}")
    print(f"  month={fields['month']}")
    print(f"  datetime_ms={fields['datetime_ms']}")
    assert fields["date"].startswith("202"), f"date should not be 1970, got {fields['date']}"
    assert "1970" not in fields["week"], f"week should not be 1970, got {fields['week']}"
    assert "1970" not in fields["month"], f"month should not be 1970, got {fields['month']}"
    assert fields["datetime_ms"] > 1_000_000_000_000
    print("  ✅ 所有字段都不是 1970")


def test_get_date_fields_with_seconds():
    print("\n=== 测试 get_date_fields(秒级 timestamp) ===")
    ts = int(time.time())
    fields = get_date_fields(ts)
    print(f"  date={fields['date']}")
    assert "1970" not in fields["date"]
    print("  ✅ 秒级 timestamp 正确转换为当前日期")


def test_get_date_fields_with_milliseconds():
    print("\n=== 测试 get_date_fields(毫秒级 timestamp) ===")
    ts = int(time.time() * 1000)
    fields = get_date_fields(ts)
    print(f"  date={fields['date']}")
    assert "1970" not in fields["date"]
    print("  ✅ 毫秒级 timestamp 正确转换为当前日期")


def test_week_format():
    print("\n=== 测试 week 格式 ===")
    fields = get_date_fields()
    week = fields["week"]
    print(f"  week = {week}")
    assert "-W" in week, f"week should contain -W, got {week}"
    parts = week.split("-W")
    assert len(parts) == 2
    year, wn = parts
    assert len(year) == 4
    assert wn.isdigit() and 1 <= int(wn) <= 53
    print(f"  ✅ week 格式正确: {week}")


def test_month_format():
    print("\n=== 测试 month 格式 ===")
    fields = get_date_fields()
    month = fields["month"]
    print(f"  month = {month}")
    assert "-" in month
    parts = month.split("-")
    assert len(parts) == 2
    assert len(parts[0]) == 4
    assert len(parts[1]) == 2
    print(f"  ✅ month 格式正确: {month}")


if __name__ == "__main__":
    test_now_local()
    test_to_datetime_none()
    test_to_datetime_seconds()
    test_to_datetime_milliseconds()
    test_to_feishu_timestamp_ms()
    test_get_date_fields_default()
    test_get_date_fields_with_seconds()
    test_get_date_fields_with_milliseconds()
    test_week_format()
    test_month_format()
    print("\n" + "=" * 40)
    print("所有时间工具测试通过 ✅")
    print("=" * 40)
