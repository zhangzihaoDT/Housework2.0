"""测试多维表格时间字段写入"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.time_utils import get_date_fields, now_local, to_feishu_timestamp_ms


async def main():
    from app.bitable_client import bitable_client

    print("=" * 60)
    print("多维表格时间字段写入测试")
    print("=" * 60)

    if not bitable_client.is_configured:
        print("\n⚠️  FEISHU_BITABLE_APP_TOKEN 未配置，跳过测试")
        return

    now = now_local()
    received_at = int(now.timestamp())
    date_fields = get_date_fields(received_at)

    print(f"\n当前时间: {now}")
    print(f"date (text): {date_fields['date']}")
    print(f"week (text): {date_fields['week']}")
    print(f"month (text): {date_fields['month']}")
    print(f"datetime_ms (Feishu): {date_fields['datetime_ms']}")

    assert "1970" not in date_fields["date"], "date should NOT be 1970"
    assert "1970" not in date_fields["week"], "week should NOT be 1970"
    assert "1970" not in date_fields["month"], "month should NOT be 1970"
    print("\n✅ 时间字段本地验证通过")

    # Write test record to raw_inputs
    print("\n[1/2] 写入 raw_inputs 测试记录...")
    ri_res = await bitable_client.append_raw_input(
        message_id="test_time_raw_001",
        chat_id="test_chat",
        sender_id="test_user",
        raw_text="时间字段测试",
        normalized_text="时间字段测试",
        chore_text="测试",
        status="parsed",
        received_at=received_at,
        total_points=1,
        task_count=1,
        reply_text="测试时间字段",
    )
    ri_ok = ri_res is not None and ri_res.get("code") == 0
    print(f"  {'✅ OK' if ri_ok else '❌ FAIL'}  code={ri_res.get('code') if ri_res else None}")

    # Write test record to chore_records
    print("\n[2/2] 写入 chore_records 测试记录...")
    cr_res = await bitable_client.append_chore_record(
        message_id="test_time_cr_001",
        chat_id="test_chat",
        sender_id="test_user",
        task_type="洗碗",
        points=1,
        confidence=1.0,
        evidence="测试时间字段",
        source_text="测试",
        status="confirmed",
        created_at=received_at,
        member_name="TestUser",
        date=received_at,
        week=date_fields["week"],
        month=date_fields["month"],
    )
    cr_ok = cr_res is not None and cr_res.get("code") == 0
    print(f"  {'✅ OK' if cr_ok else '❌ FAIL'}  code={cr_res.get('code') if cr_res else None}")

    print("\n" + "=" * 60)
    if ri_ok and cr_ok:
        print("时间字段写入测试通过 ✅")
        print("\n请在飞书多维表格中检查：")
        print(f"  - raw_inputs.received_at: 显示当前日期 {date_fields['date']}")
        print(f"  - chore_records.created_at: 显示当前日期时间")
        print(f"  - chore_records.date: 显示当前日期 {date_fields['date']}")
        print(f"  - chore_records.week: 显示 {date_fields['week']}")
        print(f"  - chore_records.month: 显示 {date_fields['month']}")
        print("\n如果仍然显示 1970 年，请联系开发排查。")
    else:
        print("时间字段写入测试失败 ❌")
        if ri_res:
            print(f"raw_inputs error: {ri_res.get('msg')}")
        if cr_res:
            print(f"chore_records error: {cr_res.get('msg')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
