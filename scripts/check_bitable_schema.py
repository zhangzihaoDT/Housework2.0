"""检查多维表格字段完整性"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from app.bitable_client import bitable_client

    if not bitable_client.is_configured:
        print("FEISHU_BITABLE_APP_TOKEN 未配置，跳过检查")
        return

    print("=" * 60)
    print("多维表格字段完整性检查")
    print("=" * 60)

    result = await bitable_client.validate_required_fields()

    print("\n--- raw_inputs ---")
    ri = result["raw_inputs"]
    print(f"当前字段 ({len(ri['fields'])}): {ri['fields']}")
    if ri["ok"]:
        print("缺失字段: 无")
        print("✅ raw_inputs 字段完整")
    else:
        print(f"❌ 缺失字段: {ri['missing']}")
        print("请手动在飞书多维表格中添加以上缺失字段")

    print("\n--- chore_records ---")
    cr = result["chore_records"]
    print(f"当前字段 ({len(cr['fields'])}): {cr['fields']}")
    if cr["ok"]:
        print("缺失字段: 无")
        print("✅ chore_records 字段完整")
    else:
        print(f"❌ 缺失字段: {cr['missing']}")
        print("请手动在飞书多维表格中添加以上缺失字段")

    all_ok = ri["ok"] and cr["ok"]
    print("\n" + "=" * 60)
    if all_ok:
        print("所有字段完整 ✅")
    else:
        print("存在缺失字段，请修复后重试 ❌")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
