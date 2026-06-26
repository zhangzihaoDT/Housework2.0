"""测试多维表格写入"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.bitable_client import bitable_client
from app.schemas import ParsedChoreTask


async def main():
    print("=" * 60)
    print("多维表格写入测试")
    print("=" * 60)

    if not bitable_client.is_configured:
        print("\n⚠️  FEISHU_BITABLE_APP_TOKEN 未配置，跳过测试")
        return

    now = int(datetime.now(timezone.utc).timestamp())

    # 1. Write raw_inputs test record
    print("\n[1/3] 写入 raw_inputs 测试记录...")
    ri_result = await bitable_client.append_raw_input(
        message_id="test_msg_001",
        chat_id="test_chat_001",
        sender_id="test_user_001",
        raw_text="@小哈皮 家务：我洗了碗还拖了地",
        normalized_text="家务：我洗了碗还拖了地",
        chore_text="我洗了碗还拖了地",
        status="parsed",
        received_at=now,
        ai_result_json=json.dumps(
            {
                "tasks": [
                    {"task_type": "洗碗", "confidence": 0.95, "evidence": "洗了碗"},
                    {"task_type": "拖地", "confidence": 0.95, "evidence": "拖了地"},
                ],
                "ignored": [],
                "need_confirm": False,
            },
            ensure_ascii=False,
        ),
    )
    print(f"  raw_inputs 结果: {ri_result}")
    if ri_result and ri_result.get("code") == 0:
        print("  ✅ raw_inputs 写入成功")
    else:
        print("  ❌ raw_inputs 写入失败")
        if ri_result:
            print(f"  错误信息: {ri_result.get('msg')}")

    # 2. Write single chore_record test
    print("\n[2/3] 写入 chore_record (单个) 测试...")
    cr_result = await bitable_client.append_chore_record(
        message_id="test_msg_001",
        chat_id="test_chat_001",
        sender_id="test_user_001",
        task_type="洗碗",
        points=5,
        confidence=0.95,
        evidence="洗了碗",
        source_text="我洗了碗还拖了地",
    )
    print(f"  chore_record 结果: {cr_result}")
    if cr_result and cr_result.get("code") == 0:
        print("  ✅ chore_record 写入成功")
    else:
        print("  ❌ chore_record 写入失败")
        if cr_result:
            print(f"  错误信息: {cr_result.get('msg')}")

    # 3. Write multiple chore_records via append_chore_records
    print("\n[3/3] 写入 chore_records (批量) 测试...")
    tasks = [
        ParsedChoreTask(task_type="洗碗", confidence=0.95, evidence="洗了碗"),
        ParsedChoreTask(task_type="拖地", confidence=0.95, evidence="拖了地"),
    ]
    cr_results = await bitable_client.append_chore_records(
        message_id="test_msg_001",
        chat_id="test_chat_001",
        sender_id="test_user_001",
        tasks=tasks,
        source_text="我洗了碗还拖了地",
    )
    print(f"  chore_records 结果: {cr_results}")
    success = all(r is not None and r.get("code") == 0 for r in cr_results)
    if success:
        print("  ✅ chore_records 批量写入成功")
    else:
        print("  ❌ chore_records 批量写入部分失败")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
